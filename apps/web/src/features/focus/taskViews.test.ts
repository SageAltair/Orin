import { describe, expect, it } from "vitest";
import type { Task } from "../../api";
import { dueAtForEdit, filterTasksForView, toLocalDateTime, toUtcDueAt } from "./taskViews";

const task = (id: string, changes: Partial<Task> = {}): Task => ({
  id, title: id, description: null, status: "todo", priority: "normal", due_at: null,
  project_id: null, created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z",
  focus_state: "inbox", ...changes,
});

describe("shared task views", () => {
  const tasks = [
    task("Capture a thought", { description: "Call the venue" }),
    task("Work on launch", { focus_state: "today" }),
    task("Continue draft", { focus_state: "active" }),
    task("Prepare next week", { focus_state: "later", due_at: "2026-10-13T14:00:00Z" }),
    task("Finished outline", { status: "done", completed_at: "2026-10-10T12:00:00Z" }),
  ];

  it("filters inbox, current work, dated upcoming work, and completed records", () => {
    const now = new Date("2026-10-11T09:00:00");
    expect(filterTasksForView(tasks, "inbox", "", now).map(item => item.id)).toEqual(["Capture a thought"]);
    expect(filterTasksForView(tasks, "today", "", now).map(item => item.id)).toEqual(["Work on launch", "Continue draft"]);
    expect(filterTasksForView(tasks, "upcoming", "", now).map(item => item.id)).toEqual(["Prepare next week"]);
    expect(filterTasksForView(tasks, "completed", "", now).map(item => item.id)).toEqual(["Finished outline"]);
  });

  it("searches titles and descriptions without changing the source collection", () => {
    expect(filterTasksForView(tasks, "inbox", "CALL THE VENUE").map(item => item.id)).toEqual(["Capture a thought"]);
    expect(filterTasksForView(tasks, "all", "  launch ").map(item => item.id)).toEqual(["Work on launch"]);
    expect(tasks).toHaveLength(5);
  });

  it("includes scheduled project tasks in Today regardless of focus state", () => {
    const now = new Date(2026, 9, 11, 9);
    const due = new Date(2026, 9, 11, 16).toISOString();
    const items = [task("project", { project_id: "project-1", focus_state: "later", due_at: due }), task("done", { status: "done", due_at: due })];
    expect(filterTasksForView(items, "today", "", now).map(item => item.id)).toEqual(["project"]);
  });

  it("separates overdue from upcoming and excludes finished tasks", () => {
    const now = new Date(2026, 9, 11, 9);
    const before = new Date(2026, 9, 10, 12).toISOString();
    const after = new Date(2026, 9, 12, 12).toISOString();
    const items = [task("late", { due_at: before }), task("future", { due_at: after }), task("closed", { status: "cancelled", due_at: before })];
    expect(filterTasksForView(items, "overdue", "", now).map(item => item.id)).toEqual(["late"]);
    expect(filterTasksForView(items, "upcoming", "", now).map(item => item.id)).toEqual(["future"]);
  });

  it("marks a task overdue immediately after its scheduled time, including today", () => {
    const now = new Date(2026, 9, 11, 14, 30);
    const earlierToday = new Date(2026, 9, 11, 14, 29).toISOString();
    const laterToday = new Date(2026, 9, 11, 14, 31).toISOString();
    const items = [task("late today", { due_at: earlierToday }), task("still ahead", { due_at: laterToday })];
    expect(filterTasksForView(items, "overdue", "", now).map(item => item.id)).toEqual(["late today"]);
    expect(filterTasksForView(items, "today", "", now).map(item => item.id)).toEqual(["late today", "still ahead"]);
  });

  it("converts browser-local datetime to UTC and back without shifting wall time", () => {
    const local = "2026-10-11T16:35";
    const utc = toUtcDueAt(local);
    expect(utc).not.toBeNull();
    expect(toLocalDateTime(utc)).toBe(local);
    expect(toUtcDueAt("")).toBeNull();
    expect(() => toUtcDueAt("not-a-date")).toThrow("Choose a valid date and time.");
    expect(() => toUtcDueAt("2026-02-31T12:00")).toThrow("Choose a valid date and time.");
    expect(() => toUtcDueAt("2026-10-11T25:00")).toThrow("Choose a valid date and time.");
  });

  it("rejects nonexistent wall times during spring daylight-saving changes", () => {
    if (Intl.DateTimeFormat().resolvedOptions().timeZone !== "America/New_York") return;
    expect(() => toUtcDueAt("2026-03-08T02:30")).toThrow("Choose a valid date and time.");
    expect(toLocalDateTime(toUtcDueAt("2026-03-08T03:30"))).toBe("2026-03-08T03:30");
  });

  it("preserves the exact original due instant when editing unrelated fields", () => {
    const original = "2026-10-11T13:35:27.000Z";
    expect(dueAtForEdit(toLocalDateTime(original), original)).toBe(original);
    expect(dueAtForEdit("", original)).toBeNull();
  });

  it("rejects ambiguous fall-back wall times instead of silently choosing an offset", () => {
    if (Intl.DateTimeFormat().resolvedOptions().timeZone !== "America/New_York") return;
    expect(() => toUtcDueAt("2026-11-01T01:30")).toThrow("This time occurs twice when clocks change.");
    expect(toLocalDateTime(toUtcDueAt("2026-11-01T00:30"))).toBe("2026-11-01T00:30");
    expect(toLocalDateTime(toUtcDueAt("2026-11-01T02:30"))).toBe("2026-11-01T02:30");
  });
});
