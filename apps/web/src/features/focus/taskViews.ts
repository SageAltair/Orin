import type { Task } from "../../api";

export type TaskView = "all" | "inbox" | "today" | "upcoming" | "completed";

export function filterTasksForView(tasks: Task[], view: TaskView, search: string, now = new Date()): Task[] {
  const query = search.trim().toLocaleLowerCase();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return tasks.filter(task => {
    if (query && !`${task.title} ${task.description ?? ""}`.toLocaleLowerCase().includes(query)) return false;
    if (view === "inbox") return task.focus_state === "inbox" && !["done", "cancelled"].includes(task.status);
    if (view === "today") return ["today", "active"].includes(task.focus_state ?? "") && !["done", "cancelled"].includes(task.status);
    if (view === "upcoming") return Boolean(task.due_at && new Date(task.due_at).getTime() >= today && !["done", "cancelled"].includes(task.status));
    if (view === "completed") return task.status === "done";
    return true;
  });
}
