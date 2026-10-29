import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { planLocalReminders } from "./local-reminder-plan";
import type { NotificationPolicy, Reminder } from "./types";

const OPT_IN_KEY = "orin.mobile.device-reminders.v1";
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
}

async function ownerEnabled(owner: string): Promise<boolean> {
  const stored = await SecureStore.getItemAsync(OPT_IN_KEY);
  if (stored === owner) return true;
  if (stored !== null) await revokeLocalOptIn();
  return false;
}

async function sync(owner: string, reminders: Reminder[], policy: NotificationPolicy) {
  if (!(await ownerEnabled(owner))) return;
  if (!(await canDeliverLocally())) {
    await revokeLocalOptIn();
    return;
  }
  const desired = new Map(
    planLocalReminders(reminders, policy).map((item) => [item.key, item.fireAt]),
  );
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const existing = new Set<string>();
  for (const entry of scheduled) {
    if (entry.content.data?.[TAG] !== true) continue;
    const key = entry.content.data?.key;
    if (
      entry.content.data?.owner === owner &&
      typeof key === "string" &&
      desired.has(key) &&
      !existing.has(key)
    ) {
      existing.add(key);
    } else {
      await Notifications.cancelScheduledNotificationAsync(entry.identifier);
    }
  }
  for (const [key, fireAt] of desired) {
    if (existing.has(key)) continue;
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Orin reminder",
        body: "Open Orin to review an upcoming reminder.",
        data: { [TAG]: true, owner, key },
        sound: false,
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: new Date(fireAt),
        ...(Platform.OS === "android" ? { channelId: CHANNEL } : {}),
      },
    });
  }
}

export function reconcileLocalReminderAccount(owner: string | null) {
  return serialized(async () => {
    if (owner === null) {
      await clearTagged();
      await SecureStore.deleteItemAsync(OPT_IN_KEY);
    } else {
      await ownerEnabled(owner);
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
  reminders: Reminder[],
  policy: NotificationPolicy,
) {
  return serialized(() => sync(owner, reminders, policy));
}

export function setLocalReminderEnabled(
  owner: string,
  enabled: boolean,
  reminders: Reminder[],
  policy: NotificationPolicy,
): Promise<boolean> {
  return serialized(async () => {
    if (!enabled) {
      await clearTagged();
      await SecureStore.deleteItemAsync(OPT_IN_KEY);
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
    await SecureStore.setItemAsync(OPT_IN_KEY, owner);
    await sync(owner, reminders, policy);
    return true;
  });
}
