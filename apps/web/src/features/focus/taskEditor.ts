import type { Task } from "../../api";
import { dueAtForEdit, toLocalDateTime } from "./taskViews";

export type TaskDraft = {
  title: string;
  description: string;
  due: string;
  priority: Task["priority"];
  status: Task["status"];
  project_id: string;
};

export const blankTaskDraft = (): TaskDraft => ({
  title: "", description: "", due: "", priority: "normal", status: "todo", project_id: "",
});

export const draftFromTask = (task: Task): TaskDraft => ({
  title: task.title,
  description: task.description ?? "",
  due: toLocalDateTime(task.due_at),
  priority: task.priority,
  status: task.status,
  project_id: task.project_id ?? "",
});

export function taskPayload(draft: TaskDraft, originalDue: string | null) {
  return {
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    priority: draft.priority,
    status: draft.status,
    project_id: draft.project_id || null,
    due_at: dueAtForEdit(draft.due, originalDue),
  };
}

/** Cancelled and completed tasks are reopened, not accidentally completed again. */
export const nextTaskStatus = (task: Task): Task["status"] =>
  task.status === "done" || task.status === "cancelled" ? "todo" : "done";
