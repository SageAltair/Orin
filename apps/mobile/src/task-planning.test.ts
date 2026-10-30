import { describe, expect, it } from "vitest";
import { dueAtForMobileEdit, filterMobileTasks, toLocalTaskDateTime, toUtcTaskDueAt } from "./task-planning";
import type { Task } from "./types";

const now = new Date(2026, 9, 29, 12, 0, 0);
const due = (day: number, hour: number) => new Date(2026, 9, day, hour).toISOString();
function task(id: string, dueAt: string | null, status: Task["status"] = "todo"): Task {
  return {
    id, title: id, description: id === "searchable" ? "Find me here" : null,
    status, priority: "normal", due_at: dueAt, project_id: null,
    created_at: now.toISOString(), updated_at: now.toISOString(),
  };
}
describe("mobile Tasks planning", () => {
  const items = [
    task("today", due(29, 16)), task("earlier", due(29, 9)),
    task("tomorrow", due(30, 8)), task("completed", due(29, 10), "done"),
    task("undated", null), task("searchable", due(30, 10)),
  ];
  it("shows all tasks by default and filters by local due instant", () => {
    expect(filterMobileTasks(items, "all", "", now)).toHaveLength(6);
    expect(filterMobileTasks(items, "today", "", now).map((t) => t.id)).toEqual(["today", "earlier"]);
    expect(filterMobileTasks(items, "upcoming", "", now).map((t) => t.id)).toEqual(["tomorrow", "searchable"]);
    expect(filterMobileTasks(items, "overdue", "", now).map((t) => t.id)).toEqual(["earlier"]);
    expect(filterMobileTasks(items, "completed", "", now).map((t) => t.id)).toEqual(["completed"]);
  });
  it("reclassifies a task after the local day rolls over", () => {
    const nextDay = task("next day", due(30, 0));
    const before = new Date(2026, 9, 29, 23, 59, 50);
    const after = new Date(2026, 9, 30, 0, 0, 10);
    expect(filterMobileTasks([nextDay], "today", "", before)).toEqual([]);
    expect(filterMobileTasks([nextDay], "today", "", after).map((item) => item.id))
      .toEqual(["next day"]);
    expect(filterMobileTasks([nextDay], "overdue", "", after).map((item) => item.id))
      .toEqual(["next day"]);
  });

  it("searches title and description case-insensitively", () => {
    expect(filterMobileTasks(items, "all", " FIND ME ", now).map((t) => t.id)).toEqual(["searchable"]);
    expect(filterMobileTasks(items, "all", "TOMORROW", now).map((t) => t.id)).toEqual(["tomorrow"]);
  });
  it("converts local due time to UTC, preserving unchanged exact instants", () => {
    const local = "2026-10-29T14:30";
    const instant = toUtcTaskDueAt(local);
    expect(instant).not.toBeNull();
    expect(toLocalTaskDateTime(instant)).toBe(local);
    const original = new Date(2026, 9, 29, 14, 30, 47).toISOString();
    expect(dueAtForMobileEdit(local, original)).toBe(original);
    expect(dueAtForMobileEdit("", original)).toBeNull();
  });
  it("rejects invalid dates and nonexistent/ambiguous clock times", () => {
    expect(() => toUtcTaskDueAt("2026-02-30T14:30")).toThrow();
    expect(() => toUtcTaskDueAt("2026-10-29")).toThrow();
    expect(() => toUtcTaskDueAt("2026-10-29T25:00")).toThrow();
    expect(toUtcTaskDueAt("")).toBeNull();
    if (Intl.DateTimeFormat().resolvedOptions().timeZone === "America/New_York") {
      expect(() => toUtcTaskDueAt("2026-03-08T02:30")).toThrow();
      expect(() => toUtcTaskDueAt("2026-11-01T01:30")).toThrow();
    }
  });
});
