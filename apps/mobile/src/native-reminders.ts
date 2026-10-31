import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { planLocalReminders } from "./local-reminder-plan";
import type { NotificationPolicy, Reminder, Task } from "./types";

const OPT_IN_KEY = "orin.mobile.device-reminders.v1";
const SCOPE_KEY = "orin.mobile.device-reminders.workspace-scope.v1";
const scopeFor = (owner: string, workspaceId: string) => `${owner}:${workspaceId}`;
// Synchronous scope invalidation prevents an old workspace's pending network
// response from re-scheduling notifications after a switch or sign-out.
let activeScope: string | null = null;
const CHANNEL = "orin-reminders";
const TAG = "orinLocalReminder";
let queue: Promise<unknown> = Promise.resolve();

function serialized<T>(work: () => Promise<T>): Promise<T> {
  const next = queue.then(work, work);
  queue = next.then(() => undefined, () => undefined);
  return next;
}

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

async function clearTagged() {
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  for (const entry of scheduled) {
    if (entry.content.data?.[TAG] === true) {
      await Notifications.cancelScheduledNotificationAsync(entry.identifier);
    }
  }
  const presented = await Notifications.getPresentedNotificationsAsync();
  for (const entry of presented) {
    if (entry.request.content.data?.[TAG] === true) {
      await Notifications.dismissNotificationAsync(entry.request.identifier);
    }
  }
}

function supportsAndroidChannels(): boolean {
  return Platform.OS === "android" && Number(Platform.Version) >= 26;
}

async function canDeliverLocally(): Promise<boolean> {
  const permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) return false;
  if (!supportsAndroidChannels()) return true;
  const channel = await Notifications.getNotificationChannelAsync(CHANNEL);
  return channel !== null && channel.importance !== Notifications.AndroidImportance.NONE;
}

async function revokeLocalOptIn() {
  await clearTagged();
  await SecureStore.deleteItemAsync(OPT_IN_KEY);
  await SecureStore.deleteItemAsync(SCOPE_KEY);
}

async function ownerEnabled(owner: string): Promise<boolean> {
  const stored = await SecureStore.getItemAsync(OPT_IN_KEY);
  if (stored === owner) return true;
  if (stored !== null) await revokeLocalOptIn();
  return false;
}

async function sync(owner: string, workspaceId: string, reminders: Reminder[], policy: NotificationPolicy, tasks: Task[] = []) {
  const scope = scopeFor(owner, workspaceId);
  if (activeScope !== scope || !(await ownerEnabled(owner)) || activeScope !== scope) return;
  if (!(await canDeliverLocally())) {
    await revokeLocalOptIn();
    return;
  }
  if (activeScope !== scope) return;
  const desired = new Map(
    planLocalReminders(reminders, policy, Date.now(), tasks).map((item) => [item.key, item.fireAt]),
  );
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const existing = new Set<string>();
  const obsolete: string[] = [];
  for (const entry of scheduled) {
    if (entry.content.data?.[TAG] !== true) continue;
    const key = entry.content.data?.key;
    if (
      entry.content.data?.owner === owner &&
      entry.content.data?.workspace === workspaceId &&
      typeof key === "string" &&
      desired.has(key) &&
      !existing.has(key)
    ) {
      existing.add(key);
    } else {
      obsolete.push(entry.identifier);
    }
  }
  // Schedule replacements before cancelling old alerts. A transient OS
  // scheduling failure must not discard an owner's last working reminder.
  // Roll back any partial additions, leaving the previous schedule intact.
  const added: string[] = [];
  try {
    for (const [key, fireAt] of desired) {
      if (activeScope !== scope) throw new Error("Reminder workspace changed during scheduling.");
      if (existing.has(key)) continue;
      const identifier = await Notifications.scheduleNotificationAsync({
        content: {
          title: "Orin reminder",
          body: "Open Orin to review an upcoming reminder.",
          data: { [TAG]: true, owner, workspace: workspaceId, key },
          sound: false,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(fireAt),
          ...(supportsAndroidChannels() ? { channelId: CHANNEL } : {}),
        },
      });
      added.push(identifier);
    }
    if (activeScope !== scope) throw new Error("Reminder workspace changed during scheduling.");
  } catch (error) {
    for (const identifier of added) {
      try {
        await Notifications.cancelScheduledNotificationAsync(identifier);
      } catch {
        // The next reconciliation can clean up an OS cancellation failure.
      }
    }
    throw error;
  }
  for (const identifier of obsolete) {
    if (activeScope !== scope) return;
    await Notifications.cancelScheduledNotificationAsync(identifier);
  }
}

// An unauthenticated launch may simply be offline. Only an explicit sign-out
// should clear existing opted-in OS schedules.
export function reminderOwnerForSession(booting: boolean, owner: string | null): string | undefined {
  return booting || !owner ? undefined : owner;
}

export function reconcileLocalReminderAccount(owner: string | null) {
  if (owner === null) activeScope = null;
  return serialized(async () => {
    if (owner === null) {
      await clearTagged();
      await SecureStore.deleteItemAsync(OPT_IN_KEY);
      await SecureStore.deleteItemAsync(SCOPE_KEY);
    } else {
      await ownerEnabled(owner);
    }
  });
}

// Clear alerts from the previous workspace before exposing the next one.
// Retain the owner's opt-in; an offline switch cancels stale schedules, and
// the next successful scoped refresh restores only current-workspace alerts.
export function reconcileLocalReminderWorkspace(owner: string, workspaceId: string) {
  const scope = scopeFor(owner, workspaceId);
  activeScope = scope;
  return serialized(async () => {
    const stored = await SecureStore.getItemAsync(SCOPE_KEY);
    if (stored !== scope) {
      await clearTagged();
      await SecureStore.setItemAsync(SCOPE_KEY, scope);
    }
  });
}

export function getLocalReminderEnabled(owner: string) {
  return serialized(async () => {
    if (!(await ownerEnabled(owner))) return false;
    if (await canDeliverLocally()) return true;
    // Android may revoke the app permission or disable only Orin's channel.
    // Neither state may appear as an enabled reminder switch.
    await revokeLocalOptIn();
    return false;
  });
}

export function syncLocalReminders(
  owner: string,
  workspaceId: string,
  reminders: Reminder[],
  policy: NotificationPolicy,
  tasks: Task[] = [],
) {
  return serialized(() => sync(owner, workspaceId, reminders, policy, tasks));
}

export function setLocalReminderEnabled(
  owner: string,
  workspaceId: string,
  enabled: boolean,
  reminders: Reminder[],
  policy: NotificationPolicy,
  tasks: Task[] = [],
): Promise<boolean> {
  return serialized(async () => {
    const scope = scopeFor(owner, workspaceId);
    if (activeScope !== scope) return false;
    if (!enabled) {
      await clearTagged();
      await SecureStore.deleteItemAsync(OPT_IN_KEY);
      await SecureStore.deleteItemAsync(SCOPE_KEY);
      return false;
    }
    // A new account must never inherit pending notifications from the old one,
    // even when the new account denies OS permission.
    await ownerEnabled(owner);
    if (supportsAndroidChannels()) {
      await Notifications.setNotificationChannelAsync(CHANNEL, {
        name: "Orin reminders",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    const existing = await Notifications.getPermissionsAsync();
    const permission = existing.granted
      ? existing
      : await Notifications.requestPermissionsAsync();
    if (!permission.granted || !(await canDeliverLocally())) {
      await revokeLocalOptIn();
      return false;
    }
    await ownerEnabled(owner);
    if (activeScope !== scope) return false;
    await SecureStore.setItemAsync(SCOPE_KEY, scope);
    await SecureStore.setItemAsync(OPT_IN_KEY, owner);
    await sync(owner, workspaceId, reminders, policy, tasks);
    return activeScope === scope;
  });
}
