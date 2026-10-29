import { beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";
import * as Notifications from "expo-notifications";
import { getLocalReminderEnabled, reconcileLocalReminderAccount, setLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder } from "./types";

vi.mock("react-native", () => ({ Platform: { OS: "android" } }));
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(), setItemAsync: vi.fn(), deleteItemAsync: vi.fn(),
}));
vi.mock("expo-notifications", () => ({
  setNotificationHandler: vi.fn(),
  setNotificationChannelAsync: vi.fn(),
  getPermissionsAsync: vi.fn(),
  requestPermissionsAsync: vi.fn(),
  getAllScheduledNotificationsAsync: vi.fn(),
  getPresentedNotificationsAsync: vi.fn(),
  scheduleNotificationAsync: vi.fn(),
  cancelScheduledNotificationAsync: vi.fn(),
  dismissNotificationAsync: vi.fn(),
  SchedulableTriggerInputTypes: { DATE: "date" },
  AndroidImportance: { DEFAULT: 3 },
}));
let stored: string | null;
let scheduled: Array<{ identifier: string; content: { data: Record<string, unknown> } }>;
const now = Date.now();
const reminder: Reminder = {
  id: "rem-1", title: "Sensitive title", message: "Secret body", category: "task",
  source_id: null, due_at: new Date(now + 120_000).toISOString(),
  read_at: null, snoozed_until: null, revision: 1, repeats: 0, attention_ready: false,
};
const policy: NotificationPolicy = {
  enabled: true, categories: ["task"], persistent: false, repeat_minutes: 15,
  max_repeats: 1, timezone: "UTC", quiet_enabled: false, quiet_start: "22:00",
  quiet_end: "07:00", respect_focus: false, browser_alerts: false, sound: false,
};
beforeEach(() => {
  vi.clearAllMocks();
  stored = null;
  scheduled = [];
  vi.mocked(SecureStore.getItemAsync).mockImplementation(async () => stored);
  vi.mocked(SecureStore.setItemAsync).mockImplementation(async (_, value) => { stored = value; });
  vi.mocked(SecureStore.deleteItemAsync).mockImplementation(async () => { stored = null; });
  vi.mocked(Notifications.getAllScheduledNotificationsAsync).mockImplementation(async () => scheduled as never);
  vi.mocked(Notifications.getPresentedNotificationsAsync).mockResolvedValue([]);
  vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: true } as never);
  vi.mocked(Notifications.requestPermissionsAsync).mockResolvedValue({ granted: true } as never);
  vi.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (request) => {
    const identifier = `scheduled-${scheduled.length + 1}`;
    scheduled.push({ identifier, content: { data: request.content.data as Record<string, unknown> } });
    return identifier;
  });
  vi.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(async (id) => {
    scheduled = scheduled.filter((item) => item.identifier !== id);
  });
});
describe("native reminder account isolation and consent", () => {
  it("does not request permission or schedule before explicit opt in", async () => {
    await syncLocalReminders("alice", [reminder], policy);
    expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled();
  });
  it("schedules generic private content once, then cancels after acknowledgement", async () => {
    expect(await setLocalReminderEnabled("alice", true, [reminder], policy)).toBe(true);
    expect(scheduled).toHaveLength(1);
    const content = vi.mocked(Notifications.scheduleNotificationAsync).mock.calls[0]?.[0].content;
    expect(content?.title).toBe("Orin reminder");
    expect(JSON.stringify(content)).not.toContain("Sensitive");
    await syncLocalReminders("alice", [reminder], policy);
    expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(1);
    await syncLocalReminders("alice", [{ ...reminder, read_at: new Date().toISOString() }], policy);
    expect(scheduled).toHaveLength(0);
  });
  it("cancels previous-account schedules and revokes opt in on sign out", async () => {
    await setLocalReminderEnabled("alice", true, [reminder], policy);
    expect(await getLocalReminderEnabled("bob")).toBe(false);
    expect(scheduled).toHaveLength(0);
    await setLocalReminderEnabled("bob", true, [reminder], policy);
    await reconcileLocalReminderAccount(null);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
  it("replaces stale revisions and removes alerts when server preferences disable reminders", async () => {
    await setLocalReminderEnabled("alice", true, [reminder], policy);
    await syncLocalReminders("alice", [{ ...reminder, revision: 2 }], policy);
    expect(Notifications.cancelScheduledNotificationAsync).toHaveBeenCalledTimes(1);
    expect(scheduled).toHaveLength(1);
    await syncLocalReminders("alice", [reminder], { ...policy, enabled: false });
    expect(scheduled).toHaveLength(0);
  });
  it("does not opt in if OS permission is denied", async () => {
    vi.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ granted: false } as never);
    vi.mocked(Notifications.requestPermissionsAsync).mockResolvedValue({ granted: false } as never);
    expect(await setLocalReminderEnabled("alice", true, [reminder], policy)).toBe(false);
    expect(stored).toBeNull();
    expect(scheduled).toHaveLength(0);
  });
});
