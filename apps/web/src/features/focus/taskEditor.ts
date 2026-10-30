import type { Task } from "../../api";
import { toLocalDateTime, toUtcDueAt } from "./taskViews";

export type TaskDraft = {
  title: string;
  description: string;
  due: string;
  priority: Task["priority"];
  status: Task["status"];
  project_id: string;
  estimated_minutes: string;
};

export const blankTaskDraft = (): TaskDraft => ({
  title: "", description: "", due: "", priority: "normal", status: "todo", project_id: "", estimated_minutes: "",
});

export const draftFromTask = (task: Task): TaskDraft => ({
  title: task.title,
  description: task.description ?? "",
  due: toLocalDateTime(task.due_at),
  priority: task.priority,
  status: task.status,
  project_id: task.project_id ?? "",
  estimated_minutes: task.estimated_minutes == null ? "" : String(task.estimated_minutes),
});

type EditableTask = Pick<Task, "title" | "description" | "priority" | "status" | "project_id" | "due_at" | "estimated_minutes">;

/** PATCH only fields changed since opening the editor.

    Unrelated server-side edits from another device must not be overwritten
    by stale status, due date, project, priority or description values.
*/
export function taskPayload(draft: TaskDraft, original?: EditableTask) {
  const title = draft.title.trim();
  const description = draft.description.trim() || null;
  const projectId = draft.project_id || null;
  const rawEstimate = draft.estimated_minutes.trim();
  if (rawEstimate && (!/^\d+$/.test(rawEstimate) || Number(rawEstimate) < 1 || Number(rawEstimate) > 1440)) {
    throw new Error("Estimated duration must be between 1 and 1440 whole minutes.");
  }
  const estimatedMinutes = rawEstimate ? Number(rawEstimate) : null;
  if (!original) {
    return {
      title, description, priority: draft.priority, status: draft.status,
      project_id: projectId, due_at: toUtcDueAt(draft.due), estimated_minutes: estimatedMinutes,
    };
  }
  return {
    ...(title !== original.title ? { title } : {}),
    ...(description !== original.description ? { description } : {}),
    ...(draft.priority !== original.priority ? { priority: draft.priority } : {}),
    ...(draft.status !== original.status ? { status: draft.status } : {}),
    ...(projectId !== original.project_id ? { project_id: projectId } : {}),
    ...(estimatedMinutes !== (original.estimated_minutes ?? null) ? { estimated_minutes: estimatedMinutes } : {}),
    ...(draft.due !== toLocalDateTime(original.due_at) ? { due_at: toUtcDueAt(draft.due) } : {}),
  };
}

/** Cancelled and completed tasks are reopened, not accidentally completed again. */
export const nextTaskStatus = (task: Task): Task["status"] =>
  task.status === "done" || task.status === "cancelled" ? "todo" : "done";
