import { describe, expect, it } from "vitest";
import { filterProjectTasks, taskDueDateBoundary, taskDueDateValue } from "./ProjectWorkspace";
import type { Task } from "./api";

const task = (title: string, status: Task["status"]): Task => ({
  id: title,
  title,
  description: null,
  status,
  priority: "normal",
  due_at: null,
  project_id: "project-1",
  created_at: "2026-10-11T00:00:00Z",
  updated_at: "2026-10-11T00:00:00Z",
});

describe("project task filtering", () => {
  const tasks = [task("Draft outline", "todo"), task("Review copy", "blocked"), task("Publish page", "done"), task("Cancelled idea", "cancelled")];

  it("shows actionable tasks by default and includes blocked work", () => {
    expect(filterProjectTasks(tasks, "", "open").map(item => item.title)).toEqual(["Draft outline", "Review copy"]);
  });

  it("searches without case sensitivity and filters by completion state", () => {
    expect(filterProjectTasks(tasks, "  REVIEW ", "all").map(item => item.title)).toEqual(["Review copy"]);
    expect(filterProjectTasks(tasks, "", "done").map(item => item.title)).toEqual(["Publish page"]);
    expect(filterProjectTasks(tasks, "", "blocked").map(item => item.title)).toEqual(["Review copy"]);
  });

  it("keeps due dates on the selected local calendar day", () => {
    const dueAt = taskDueDateBoundary("2026-10-11");
    expect(dueAt).not.toBeNull();
    expect(taskDueDateValue(dueAt)).toBe("2026-10-11");
    expect(taskDueDateValue(null)).toBe("");
    expect(taskDueDateBoundary("")).toBeNull();
  });
});
