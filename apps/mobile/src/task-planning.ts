import type { Task } from "./types";

export type MobileTaskView = "all" | "today" | "upcoming" | "overdue" | "completed";
const finished = (task: Task) => task.status === "done" || task.status === "cancelled";

export function filterMobileTasks(
  tasks: Task[],
  view: MobileTaskView,
  search: string,
  now = new Date(),
): Task[] {
  const query = search.trim().toLocaleLowerCase();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime();
  return tasks.filter((task) => {
    if (query && !`${task.title} ${task.description ?? ""}`.toLocaleLowerCase().includes(query)) return false;
    const due = task.due_at ? Date.parse(task.due_at) : null;
    if (view === "today") return !finished(task) && due !== null && due >= today && due < tomorrow;
    if (view === "upcoming") return !finished(task) && due !== null && due >= tomorrow;
    if (view === "overdue") return !finished(task) && due !== null && due < now.getTime();
    if (view === "completed") return task.status === "done";
    return true;
  });
}

export function toLocalTaskDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function toUtcTaskDueAt(value: string): string | null {
  if (!value.trim()) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    throw new Error("Enter a due date and time as YYYY-MM-DDTHH:MM.");
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || toLocalTaskDateTime(date.toISOString()) !== value) {
    throw new Error("Choose a real local date and time.");
  }
  const offset = date.getTimezoneOffset();
  for (const hours of [-24, 24]) {
    const nearbyOffset = new Date(date.getTime() + hours * 60 * 60 * 1000).getTimezoneOffset();
    if (nearbyOffset === offset) continue;
    const alternative = new Date(date.getTime() + (nearbyOffset - offset) * 60 * 1000);
    if (toLocalTaskDateTime(alternative.toISOString()) === value) {
      throw new Error("This local time occurs twice when clocks change. Choose another time.");
    }
  }
  return date.toISOString();
}

export function dueAtForMobileEdit(value: string, original: string | null): string | null {
  if (original && toLocalTaskDateTime(original) === value) return original;
  return toUtcTaskDueAt(value);
}
