import { describe, expect, it } from "vitest";
import type { Task } from "../../api";
import { filterTasksForView } from "./taskViews";

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
});
