import { describe, expect, it } from "vitest";
import { planLocalReminders } from "./local-reminder-plan";
import type { NotificationPolicy, Reminder, Task } from "./types";

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
function task(id: string, dueAt: string | null, status: Task["status"] = "todo"): Task {
  return {
    id, title: "Private task", description: null, status, priority: "normal",
    due_at: dueAt, project_id: null, created_at: new Date(now).toISOString(),
    updated_at: new Date(now).toISOString(),
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
  it("schedules future task deadlines independently of the server 30-minute inbox window", () => {
    const due = "2026-11-02T12:00:00Z";
    expect(planLocalReminders([], policy, now, [task("future", due)]))
      .toEqual([{ key: `task:future:${Date.parse(due)}`, fireAt: Date.parse(due) }]);
    expect(planLocalReminders([], policy, now, [
      task("done", due, "done"), task("cancelled", due, "cancelled"),
      task("undated", null), task("past", "2026-10-28T12:00:00Z"),
    ])).toEqual([]);
  });
  it("replaces a task deadline with its matching server inbox reminder without duplicate alerts", () => {
    const due = "2026-10-29T13:00:00Z";
    const notification = { ...reminder("inbox", due), source_id: "task-1" };
    expect(planLocalReminders([notification], policy, now, [task("task-1", due)]))
      .toEqual([{ key: `inbox:1:${Date.parse(due)}`, fireAt: Date.parse(due) }]);
    expect(planLocalReminders([{ ...notification, read_at: "2026-10-29T12:00:00Z" }], policy, now, [task("task-1", due)]))
      .toEqual([]);
    expect(planLocalReminders([notification], policy, now, [task("task-1", "2026-10-30T13:00:00Z")]))
      .toHaveLength(2);
  });
  it("applies task category, quiet hours, horizon and global cap to future tasks", () => {
    const due = "2026-10-29T23:00:00Z";
    const candidate = task("quiet", due);
    expect(planLocalReminders([], { ...policy, categories: ["calendar"] }, now, [candidate])).toEqual([]);
    expect(planLocalReminders([], { ...policy, quiet_enabled: true }, now, [candidate])).toEqual([]);
    expect(planLocalReminders([], policy, now, [task("far", "2026-11-10T12:00:00Z")])).toEqual([]);
    const many = Array.from({ length: 40 }, (_, i) => task(String(i), new Date(now + (40 - i) * 60_000).toISOString()));
    expect(planLocalReminders([], policy, now, many)).toHaveLength(32);
  });
  it("caps device scheduling and prioritizes earliest dates", () => {
    const items = Array.from({ length: 40 }, (_, i) => reminder(String(i), new Date(now + (40 - i) * 60_000).toISOString()));
    const result = planLocalReminders(items, policy, now);
    expect(result).toHaveLength(32);
    expect(result[0]?.fireAt).toBe(now + 60_000);
    expect(result[31]?.fireAt).toBe(now + 32 * 60_000);
  });
});
