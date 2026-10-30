import { describe, expect, it } from "vitest";
import type { Task } from "../../api";
import { blankTaskDraft, draftFromTask, nextTaskStatus, taskPayload } from "./taskEditor";

const task = (changes: Partial<Task> = {}): Task => ({
  id: "task-1", title: "  Prepare launch  ", description: null,
  status: "todo", priority: "normal", due_at: null, project_id: null,
  created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z",
  ...changes,
});

describe("professional task editor status and persistence", () => {
  it("creates new tasks as To do with no project or deadline", () => {
    const draft = blankTaskDraft();
    expect(draft.status).toBe("todo");
    expect(taskPayload({ ...draft, title: "  Write brief  " }, null)).toEqual({
      title: "Write brief", description: null, priority: "normal",
      status: "todo", project_id: null, due_at: null,
    });
  });

  it("preserves blocked and cancelled states when editing other fields", () => {
    for (const status of ["blocked", "cancelled"] as const) {
      const existing = task({
        status, description: "Review notes", priority: "urgent",
        project_id: "project-1", due_at: "2026-10-11T13:35:27.000Z",
      });
      const draft = draftFromTask(existing);
      expect(draft.status).toBe(status);
      expect(taskPayload(draft, existing.due_at)).toEqual({
        title: "Prepare launch", description: "Review notes",
        priority: "urgent", status, project_id: "project-1",
        due_at: existing.due_at,
      });
    }
  });

  it("sends explicit in-progress or completed status changes", () => {
    const draft = draftFromTask(task({ status: "done" }));
    expect(taskPayload({ ...draft, status: "in_progress" }, null).status).toBe("in_progress");
    expect(taskPayload({ ...draft, status: "done" }, null).status).toBe("done");
  });

  it("reopens cancelled and completed tasks rather than completing them again", () => {
    expect(nextTaskStatus(task({ status: "cancelled" }))).toBe("todo");
    expect(nextTaskStatus(task({ status: "done" }))).toBe("todo");
    expect(nextTaskStatus(task({ status: "blocked" }))).toBe("done");
  });
});
