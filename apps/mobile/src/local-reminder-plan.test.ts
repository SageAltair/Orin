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
    const afterQuiet = Date.parse("2026-10-30T07:00:00Z");
    expect(planLocalReminders([r], { ...policy, quiet_enabled: true }, now))
      .toEqual([{ key: `quiet:1:${afterQuiet}`, fireAt: afterQuiet }]);
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
    const afterQuiet = Date.parse("2026-10-30T07:00:00Z");
    expect(planLocalReminders([], { ...policy, quiet_enabled: true }, now, [candidate]))
      .toEqual([{ key: `task:quiet:${afterQuiet}`, fireAt: afterQuiet }]);
    expect(planLocalReminders([], policy, now, [task("far", "2026-11-10T12:00:00Z")])).toEqual([]);
    const many = Array.from({ length: 40 }, (_, i) => task(String(i), new Date(now + (40 - i) * 60_000).toISOString()));
    expect(planLocalReminders([], policy, now, many)).toHaveLength(32);
  });
  it("defers quiet-hour reminders to the next allowed time in the policy timezone", () => {
    const due = "2026-10-29T20:00:00Z"; // 23:00 in Dar es Salaam
    const next = Date.parse("2026-10-30T04:00:00Z"); // 07:00 in Dar es Salaam
    const localPolicy = { ...policy, quiet_enabled: true, timezone: "Africa/Dar_es_Salaam" };
    expect(planLocalReminders([reminder("tz", due)], localPolicy, now))
      .toEqual([{ key: `tz:1:${next}`, fireAt: next }]);
    expect(planLocalReminders([], localPolicy, now, [task("tz", due)]))
      .toEqual([{ key: `task:tz:${next}`, fireAt: next }]);
  });
  it("preserves deferred reminders when reopening during quiet hours after the original due time", () => {
    const due = "2026-10-29T23:00:00Z";
    const resumedAt = Date.parse("2026-10-30T02:00:00Z");
    const next = Date.parse("2026-10-30T07:00:00Z");
    const quiet = { ...policy, quiet_enabled: true };
    expect(planLocalReminders([reminder("inbox", due)], quiet, resumedAt))
      .toEqual([{ key: `inbox:1:${next}`, fireAt: next }]);
    expect(planLocalReminders([], quiet, resumedAt, [task("deadline", due)]))
      .toEqual([{ key: `task:deadline:${next}`, fireAt: next }]);
    // A past-due item outside the quiet interval must not be resurrected.
    expect(planLocalReminders([reminder("past", due)], policy, resumedAt)).toEqual([]);
    expect(planLocalReminders([], policy, resumedAt, [task("past", due)])).toEqual([]);
  });
  it("coalesces simultaneous generic alerts after quiet hours", () => {
    const quiet = { ...policy, quiet_enabled: true };
    const due1 = "2026-10-29T22:15:00Z";
    const due2 = "2026-10-29T23:45:30Z";
    const fireAt = Date.parse("2026-10-30T07:00:00Z");
    const result = planLocalReminders([reminder("a", due1), reminder("b", due2)],
      quiet, now, [task("c", due1)]);
    expect(result).toHaveLength(1);
    expect(result[0]?.fireAt).toBe(fireAt);
  });
  it("handles spring-forward and fall-back quiet-hour boundaries", () => {
    const eastern = { ...policy, quiet_enabled: true, timezone: "America/New_York" };
    const springNow = Date.parse("2027-03-14T05:00:00Z");
    const springDue = "2027-03-14T06:30:00Z"; // 01:30 EST
    const springEnd = Date.parse("2027-03-14T11:00:00Z"); // 07:00 EDT
    expect(planLocalReminders([reminder("spring", springDue)], eastern, springNow))
      .toEqual([{ key: `spring:1:${springEnd}`, fireAt: springEnd }]);
    const fallNow = Date.parse("2026-11-01T04:00:00Z");
    const fallDue = "2026-11-01T05:30:00Z"; // first 01:30 EDT
    const fallEnd = Date.parse("2026-11-01T12:00:00Z"); // 07:00 EST
    expect(planLocalReminders([reminder("fall", fallDue)], eastern, fallNow))
      .toEqual([{ key: `fall:1:${fallEnd}`, fireAt: fallEnd }]);
  });
  it("fails closed on invalid quiet settings and does not defer beyond horizon", () => {
    const due = "2026-10-29T23:00:00Z";
    expect(planLocalReminders([reminder("invalid", due)],
      { ...policy, quiet_enabled: true, timezone: "Invalid/Timezone" }, now)).toEqual([]);
    expect(planLocalReminders([reminder("invalid", due)],
      { ...policy, quiet_enabled: true, quiet_end: "99:00" }, now)).toEqual([]);
    const nearHorizon = "2026-11-05T11:00:00Z";
    expect(planLocalReminders([], {
      ...policy, quiet_enabled: true, quiet_start: "10:00", quiet_end: "12:30",
    }, now, [task("beyond", nearHorizon)])).toEqual([]);
  });
  it("caps device scheduling and prioritizes earliest dates", () => {
    const items = Array.from({ length: 40 }, (_, i) => reminder(String(i), new Date(now + (40 - i) * 60_000).toISOString()));
    const result = planLocalReminders(items, policy, now);
    expect(result).toHaveLength(32);
    expect(result[0]?.fireAt).toBe(now + 60_000);
    expect(result[31]?.fireAt).toBe(now + 32 * 60_000);
  });
});
