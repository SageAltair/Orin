import { beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { getLocalReminderEnabled, reconcileLocalReminderAccount, reconcileLocalReminderWorkspace, reminderOwnerForSession, revokeLocalReminderOwner, setLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder, Task } from "./types";

vi.mock("react-native", () => ({ Platform: { OS: "android", Version: 35 } }));
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(), setItemAsync: vi.fn(), deleteItemAsync: vi.fn(),
}));
vi.mock("expo-notifications", () => ({
  setNotificationHandler: vi.fn(),
  setNotificationChannelAsync: vi.fn(),
  getNotificationChannelAsync: vi.fn(),
  getPermissionsAsync: vi.fn(),
  requestPermissionsAsync: vi.fn(),
  getAllScheduledNotificationsAsync: vi.fn(),
  getPresentedNotificationsAsync: vi.fn(),
  scheduleNotificationAsync: vi.fn(),
  cancelScheduledNotificationAsync: vi.fn(),
  dismissNotificationAsync: vi.fn(),
  SchedulableTriggerInputTypes: { DATE: "date" },
  AndroidImportance: { NONE: 2, DEFAULT: 5 },
}));
let stored: string | null;
let scopeStored: string | null;
let scheduled: Array<{ identifier: string; content: { data: Record<string, unknown> } }>;
const now = Date.now();
const reminder: Reminder = {
  id: "rem-1", title: "Sensitive title", message: "Secret body", category: "tasks",
  source_id: null, due_at: new Date(now + 120_000).toISOString(),
  read_at: null, snoozed_until: null, revision: 1, repeats: 0, attention_ready: false,
};
const policy: NotificationPolicy = {
  enabled: true, categories: ["tasks"], persistent: false, repeat_minutes: 15,
  max_repeats: 1, timezone: "UTC", quiet_enabled: false, quiet_start: "22:00",
  quiet_end: "07:00", respect_focus: false, browser_alerts: false, sound: false,
};
beforeEach(async () => {
  vi.clearAllMocks();
  Object.assign(Platform, { Version: 35 });
  stored = null;
  scopeStored = null;
  scheduled = [];
  vi.mocked(SecureStore.getItemAsync).mockImplementation(async (key) =>
    key.includes("workspace-scope") ? scopeStored : stored);
  vi.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
    if (key.includes("workspace-scope")) scopeStored = value;
    else stored = value;
  });
  vi.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
    if (key.includes("workspace-scope")) scopeStored = null;
    else stored = null;
  });
  vi.mocked(Notifications.getAllScheduledNotificationsAsync).mockImplementation(async () => scheduled as never);
  vi.mocked(Notifications.getPresentedNotificationsAsync).mockResolvedValue([]);
  vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: true } as never);
  vi.mocked(Notifications.getNotificationChannelAsync).mockResolvedValue({ importance: Notifications.AndroidImportance.DEFAULT } as never);
  vi.mocked(Notifications.requestPermissionsAsync).mockResolvedValue({ granted: true } as never);
  vi.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (request) => {
    const identifier = `scheduled-${scheduled.length + 1}`;
    scheduled.push({ identifier, content: { data: request.content.data as Record<string, unknown> } });
    return identifier;
  });
  vi.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(async (id) => {
    scheduled = scheduled.filter((item) => item.identifier !== id);
  });
  await reconcileLocalReminderWorkspace("alice", "workspace-a");
  vi.clearAllMocks();
});
describe("native reminder account isolation and consent", () => {
  it("preserves opted-in schedules on offline unauthenticated boot but reconciles authenticated sessions", () => {
    expect(reminderOwnerForSession(true, "alice")).toBeUndefined();
    expect(reminderOwnerForSession(false, null)).toBeUndefined();
    expect(reminderOwnerForSession(false, "alice")).toBe("alice");
  });
  it("does not request permission or schedule before explicit opt in", async () => {
    await syncLocalReminders("alice", "workspace-a", [reminder], policy);
    expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled();
  });
  it("schedules generic private content once, then cancels after acknowledgement", async () => {
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy)).toBe(true);
    expect(scheduled).toHaveLength(1);
    expect(vi.mocked(Notifications.scheduleNotificationAsync).mock.calls[0]?.[0].trigger).toHaveProperty("channelId", "orin-reminders");
    const content = vi.mocked(Notifications.scheduleNotificationAsync).mock.calls[0]?.[0].content;
    expect(content?.title).toBe("Orin reminder");
    expect(JSON.stringify(content)).not.toContain("Sensitive");
    await syncLocalReminders("alice", "workspace-a", [reminder], policy);
    expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(1);
    await syncLocalReminders("alice", "workspace-a", [{ ...reminder, read_at: new Date().toISOString() }], policy);
    expect(scheduled).toHaveLength(0);
  });
  it("reconciles future task deadlines, rescheduling and completion without revealing task details", async () => {
    const task: Task = {
      id: "future-task", title: "Secret task title", description: null, status: "todo",
      priority: "normal", project_id: null, due_at: new Date(now + 4 * 86_400_000).toISOString(),
      created_at: new Date(now).toISOString(), updated_at: new Date(now).toISOString(),
    };
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [], policy, [task])).toBe(true);
    expect(scheduled).toHaveLength(1);
    expect(JSON.stringify(vi.mocked(Notifications.scheduleNotificationAsync).mock.calls[0]?.[0].content))
      .not.toContain("Secret");
    await syncLocalReminders("alice", "workspace-a", [], policy, [{ ...task, due_at: new Date(now + 5 * 86_400_000).toISOString() }]);
    expect(scheduled).toHaveLength(1);
    expect(Notifications.cancelScheduledNotificationAsync).toHaveBeenCalledTimes(1);
    await syncLocalReminders("alice", "workspace-a", [], policy, [{ ...task, status: "done" }]);
    expect(scheduled).toHaveLength(0);
  });
  it("cancels previous-account schedules and revokes opt in on sign out", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    expect(await getLocalReminderEnabled("bob")).toBe(false);
    expect(scheduled).toHaveLength(0);
    await reconcileLocalReminderWorkspace("bob", "workspace-b");
    await setLocalReminderEnabled("bob", "workspace-b", true, [reminder], policy);
    await reconcileLocalReminderAccount(null);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
  it("does not let a stale consent read revoke the new account's alerts", async () => {
    await reconcileLocalReminderWorkspace("bob", "workspace-b");
    await setLocalReminderEnabled("bob", "workspace-b", true, [reminder], policy);
    const originalId = scheduled[0]!.identifier;
    let current = true;
    // The old account's queued check becomes stale while secure storage is
    // returning the newly opted-in owner's key.
    vi.mocked(SecureStore.getItemAsync).mockImplementationOnce(async () => {
      current = false;
      return stored;
    });
    expect(await getLocalReminderEnabled("alice", () => current)).toBe(false);
    expect(stored).toBe("bob");
    expect(scopeStored).toBe("bob:workspace-b");
    expect(scheduled.map((item) => item.identifier)).toEqual([originalId]);
    expect(Notifications.cancelScheduledNotificationAsync).not.toHaveBeenCalled();
  });

  it("preserves consent when a stale permission check finishes after a new session", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    let current = true;
    vi.mocked(Notifications.getPermissionsAsync).mockImplementationOnce(async () => {
      current = false;
      return { granted: false } as never;
    });
    expect(await getLocalReminderEnabled("alice", () => current)).toBe(false);
    expect(stored).toBe("alice");
    expect(scheduled).toHaveLength(1);
    expect(Notifications.cancelScheduledNotificationAsync).not.toHaveBeenCalled();
  });

  it("revokes the opted-in owner's scheduled alerts after confirmed session rejection", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    expect(scheduled).toHaveLength(1);
    await revokeLocalReminderOwner("alice");
    expect(stored).toBeNull();
    expect(scopeStored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });

  it("preserves same-owner alerts when a newer login supersedes queued revocation", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    let revisionChecks = 0;
    // Simulate a successful login between the initial revision check and
    // the secure-storage read in the serialized native cleanup operation.
    await revokeLocalReminderOwner("alice", () => ++revisionChecks === 1);
    expect(revisionChecks).toBe(2);
    expect(stored).toBe("alice");
    expect(scopeStored).toBe("alice:workspace-a");
    expect(scheduled).toHaveLength(1);
  });

  it("does not let a stale owner's revocation clear a newer account's alerts", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    await reconcileLocalReminderWorkspace("bob", "workspace-b");
    await setLocalReminderEnabled("bob", "workspace-b", true, [reminder], policy);
    expect(scheduled).toHaveLength(1);
    await revokeLocalReminderOwner("alice");
    expect(stored).toBe("bob");
    expect(scheduled).toHaveLength(1);
    expect(scheduled[0]!.content.data.owner).toBe("bob");
  });

  it("replaces stale revisions and removes alerts when server preferences disable reminders", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    await syncLocalReminders("alice", "workspace-a", [{ ...reminder, revision: 2 }], policy);
    expect(Notifications.cancelScheduledNotificationAsync).toHaveBeenCalledTimes(1);
    expect(scheduled).toHaveLength(1);
    await syncLocalReminders("alice", "workspace-a", [reminder], { ...policy, enabled: false });
    expect(scheduled).toHaveLength(0);
  });
  it("rolls back partial OS schedules without deleting prior alerts when replacement fails", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    const originalId = scheduled[0]!.identifier;
    const changed = { ...reminder, revision: 2 };
    const additional = {
      ...reminder, id: "rem-2", due_at: new Date(now + 240_000).toISOString(),
    };
    vi.mocked(Notifications.scheduleNotificationAsync)
      .mockImplementationOnce(async (request) => {
        const identifier = "partial-new-alert";
        scheduled.push({
          identifier, content: { data: request.content.data as Record<string, unknown> },
        });
        return identifier;
      })
      .mockRejectedValueOnce(new Error("OS scheduling unavailable"));

    await expect(syncLocalReminders("alice", "workspace-a", [changed, additional], policy))
      .rejects.toThrow("OS scheduling unavailable");
    expect(scheduled.map((item) => item.identifier)).toEqual([originalId]);
    expect(Notifications.cancelScheduledNotificationAsync).toHaveBeenCalledWith("partial-new-alert");
    expect(Notifications.cancelScheduledNotificationAsync).not.toHaveBeenCalledWith(originalId);

    // A later successful refresh replaces the stale revision normally.
    await syncLocalReminders("alice", "workspace-a", [changed, additional], policy);
    expect(scheduled).toHaveLength(2);
    expect(scheduled.some((item) => item.identifier === originalId)).toBe(false);
  });
  it("revokes stale opt in when Android permission is removed, preserving unrelated alerts", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    expect(await getLocalReminderEnabled("alice")).toBe(true);
    scheduled.push({ identifier: "unrelated", content: { data: {} } });
    vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: false } as never);
    expect(await getLocalReminderEnabled("alice")).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toEqual([{ identifier: "unrelated", content: { data: {} } }]);
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled();
  });
  it("revokes stale opt in if permission disappears during synchronization", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: false } as never);
    await syncLocalReminders("alice", "workspace-a", [reminder], policy);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
    expect(await getLocalReminderEnabled("alice")).toBe(false);
  });
  it("detects Android channel-level blocking even when app permission remains granted", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    vi.mocked(Notifications.getNotificationChannelAsync).mockResolvedValue({ importance: Notifications.AndroidImportance.NONE } as never);
    expect(await getLocalReminderEnabled("alice")).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
    expect(Notifications.getPermissionsAsync).toHaveBeenCalled();
  });
  it("refuses opt in when the user has disabled the Android reminder channel", async () => {
    vi.mocked(Notifications.getNotificationChannelAsync).mockResolvedValue({ importance: Notifications.AndroidImportance.NONE } as never);
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy)).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
  it("does not require notification channels on Android before API 26", async () => {
    Object.assign(Platform, { Version: 25 });
    vi.mocked(Notifications.getNotificationChannelAsync).mockResolvedValue(null);
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy)).toBe(true);
    expect(await getLocalReminderEnabled("alice")).toBe(true);
    expect(Notifications.setNotificationChannelAsync).not.toHaveBeenCalled();
    expect(Notifications.getNotificationChannelAsync).not.toHaveBeenCalled();
    expect(vi.mocked(Notifications.scheduleNotificationAsync).mock.calls[0]?.[0].trigger).not.toHaveProperty("channelId");
    expect(scheduled).toHaveLength(1);
  });
  it("cancels stale workspace alerts offline without revoking owner consent", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    expect(scheduled).toHaveLength(1);
    await reconcileLocalReminderWorkspace("alice", "workspace-b");
    expect(scheduled).toHaveLength(0);
    expect(stored).toBe("alice");
    expect(scopeStored).toBe("alice:workspace-b");
    // An old screen or request must not reintroduce the previous workspace.
    await syncLocalReminders("alice", "workspace-a", [reminder], policy);
    expect(scheduled).toHaveLength(0);
    await syncLocalReminders("alice", "workspace-b", [reminder], policy);
    expect(scheduled).toHaveLength(1);
    expect(scheduled[0]?.content.data.workspace).toBe("workspace-b");
  });
  it("preserves already scheduled alerts when restoring the same workspace offline", async () => {
    await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy);
    await reconcileLocalReminderWorkspace("alice", "workspace-a");
    expect(scheduled).toHaveLength(1);
  });
  it("rejects stale workspace opt-in after a switch", async () => {
    await reconcileLocalReminderWorkspace("alice", "workspace-b");
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy)).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
  it("does not opt in if OS permission is denied", async () => {
    vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: false } as never);
    vi.mocked(Notifications.requestPermissionsAsync).mockResolvedValue({ granted: false } as never);
    expect(await setLocalReminderEnabled("alice", "workspace-a", true, [reminder], policy)).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
});
