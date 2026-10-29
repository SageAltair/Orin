import { describe, expect, it } from "vitest";
import { planLocalReminders } from "./local-reminder-plan";
import type { NotificationPolicy, Reminder } from "./types";

const policy: NotificationPolicy = {
  enabled: true,
  categories: ["tasks", "calendar"],
  persistent: false,
  repeat_minutes: 15,
  max_repeats: 1,
  timezone: "UTC",
  quiet_enabled: false,
  quiet_start: "22:00",
  quiet_end: "07:00",
  respect_focus: true,
  browser_alerts: false,
  sound: false,
};
const now = Date.parse("2026-10-29T12:00:00Z");
function reminder(id: string, dueAt: string): Reminder {
  return {
    id, title: "Private task", message: "Sensitive details",
    category: "tasks", source_id: null, due_at: dueAt,
    read_at: null, snoozed_until: null, revision: 1,
    repeats: 0, attention_ready: false,
  };
}
describe("local Android reminder planner", () => {
  it("schedules only upcoming unread enabled-category reminders", () => {
    const future = reminder("good", "2026-10-29T12:30:00Z");
    const acknowledged = { ...reminder("read", "2026-10-29T12:45:00Z"), read_at: "2026-10-29T12:00:00Z" };
    const blocked = { ...reminder("blocked", "2026-10-29T12:30:00Z"), category: "other" };
    expect(planLocalReminders([future, acknowledged, blocked, reminder("past", "2026-10-29T11:00:00Z")], policy, now))
      .toEqual([{ key: `good:1:${Date.parse(future.due_at)}`, fireAt: Date.parse(future.due_at) }]);
  });
  it("uses snooze, revisions and rejects invalid or distant dates", () => {
    const snoozed = { ...reminder("s", "2026-10-29T11:00:00Z"), snoozed_until: "2026-10-29T12:45:00Z", revision: 3 };
    const result = planLocalReminders([snoozed, reminder("bad", "nonsense"), reminder("far", "2026-11-10T12:00:00Z")], policy, now);
    expect(result).toEqual([{ key: `s:3:${Date.parse(snoozed.snoozed_until!)}`, fireAt: Date.parse(snoozed.snoozed_until!) }]);
  });
  it("honors disabled policy and quiet hours including overnight", () => {
    const r = reminder("quiet", "2026-10-29T23:00:00Z");
    expect(planLocalReminders([r], { ...policy, enabled: false }, now)).toEqual([]);
    expect(planLocalReminders([r], { ...policy, quiet_enabled: true }, now)).toEqual([]);
    expect(planLocalReminders([r], { ...policy, quiet_enabled: true, quiet_start: "09:00", quiet_end: "17:00" }, now)).toHaveLength(1);
    expect(planLocalReminders([r], { ...policy, quiet_enabled: true, quiet_start: "12:00", quiet_end: "12:00" }, now)).toEqual([]);
  });
  it("caps device scheduling and prioritizes earliest dates", () => {
    const items = Array.from({ length: 40 }, (_, i) => reminder(String(i), new Date(now + (40 - i) * 60_000).toISOString()));
    const result = planLocalReminders(items, policy, now);
    expect(result).toHaveLength(32);
    expect(result[0]?.fireAt).toBe(now + 60_000);
    expect(result[31]?.fireAt).toBe(now + 32 * 60_000);
  });
});
