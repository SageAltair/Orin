import { describe, expect, it } from "vitest";
import type { Task } from "../../api";
import { blankTaskDraft, draftFromTask, nextTaskStatus, taskPayload } from "./taskEditor";

const task = (changes: Partial<Task> = {}): Task => ({
  id: "task-1", title: "Prepare launch", description: null,
  status: "todo", priority: "normal", due_at: null, project_id: null,
  created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z",
  ...changes,
});

describe("professional task editor status and persistence", () => {
  it("creates new tasks as To do with no project or deadline", () => {
    const draft = blankTaskDraft();
    expect(draft.status).toBe("todo");
    expect(taskPayload({ ...draft, title: "  Write brief  " })).toEqual({
      title: "Write brief", description: null, priority: "normal",
      status: "todo", project_id: null, due_at: null,
    });
  });

  it("preserves existing blocked/cancelled status and due instant on unrelated edits", () => {
    for (const status of ["blocked", "cancelled"] as const) {
      const existing = task({
        status, description: "Review notes", priority: "urgent",
        project_id: "project-1", due_at: "2026-10-11T13:35:27.000Z",
      });
      const draft = draftFromTask(existing);
      expect(draft.status).toBe(status);
      expect(taskPayload(draft, existing)).toEqual({});
      expect(taskPayload({ ...draft, title: "  Revised title  " }, existing)).toEqual({
        title: "Revised title",
      });
    }
  });

  it("sends explicit status changes without overwriting unrelated fields", () => {
    const existing = task({ status: "done", project_id: "project-1" });
    const draft = draftFromTask(existing);
    expect(taskPayload({ ...draft, status: "in_progress" }, existing)).toEqual({
      status: "in_progress",
    });
    expect(taskPayload({ ...draft, status: "done" }, existing)).toEqual({});
  });

  it("preserves concurrent server edits when only priority or title was changed", () => {
    const existing = task({ status: "todo", focus_state: "today" });
    const payload = taskPayload({
      ...draftFromTask(existing), title: "  Revised title  ", priority: "high",
    }, existing);
    expect(payload).toEqual({ title: "Revised title", priority: "high" });
    expect(payload).not.toHaveProperty("status");
    expect(payload).not.toHaveProperty("due_at");
    expect(payload).not.toHaveProperty("project_id");
  });

  it("includes explicit due-date removal and project unlinking", () => {
    const existing = task({
      due_at: "2026-10-11T13:35:27.000Z", project_id: "project-1",
    });
    expect(taskPayload({
      ...draftFromTask(existing), due: "", project_id: "",
    }, existing)).toEqual({ due_at: null, project_id: null });
  });

  it("reopens cancelled and completed tasks rather than completing them again", () => {
    expect(nextTaskStatus(task({ status: "cancelled" }))).toBe("todo");
    expect(nextTaskStatus(task({ status: "done" }))).toBe("todo");
    expect(nextTaskStatus(task({ status: "blocked" }))).toBe("done");
  });
});
