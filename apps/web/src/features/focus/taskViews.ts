import type { Task } from "../../api";

export type TaskView = "all" | "inbox" | "today" | "upcoming" | "overdue" | "completed";

const finished = (task: Task) => task.status === "done" || task.status === "cancelled";
const localDay = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();

export function filterTasksForView(tasks: Task[], view: TaskView, search: string, now = new Date()): Task[] {
  const query = search.trim().toLocaleLowerCase();
  const today = localDay(now);
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime();
  return tasks.filter(task => {
    if (query && !`${task.title} ${task.description ?? ""}`.toLocaleLowerCase().includes(query)) return false;
    const due = task.due_at ? new Date(task.due_at).getTime() : null;
    if (view === "inbox") return task.focus_state === "inbox" && !finished(task);
    if (view === "today") return !finished(task) && ((due !== null && due >= today && due < tomorrow) || (due === null && ["today", "active"].includes(task.focus_state ?? "")));
    if (view === "upcoming") return !finished(task) && due !== null && due >= tomorrow;
    if (view === "overdue") return !finished(task) && due !== null && due < now.getTime();
    if (view === "completed") return task.status === "done";
    return true;
  });
}

export function toLocalDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Keep an existing exact instant if the user only edited other task fields. */
export function dueAtForEdit(localValue: string, original: string | null): string | null {
  if (original && toLocalDateTime(original) === localValue) return original;
  return toUtcDueAt(localValue);
}

export function toUtcDueAt(localValue: string): string | null {
  if (!localValue) return null;
  // Reject calendar rollovers and nonexistent local times during DST transitions.
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(localValue)) throw new Error("Choose a valid date and time.");
  const date = new Date(localValue);
  if (Number.isNaN(date.getTime()) || toLocalDateTime(date.toISOString()) !== localValue) {
    throw new Error("Choose a valid date and time.");
  }
  // A fall-back clock change can map one wall time to two UTC instants.
  // Refuse to guess which occurrence the user intended.
  const offset = date.getTimezoneOffset();
  for (const hours of [-24, 24]) {
    const nearbyOffset = new Date(date.getTime() + hours * 60 * 60 * 1000).getTimezoneOffset();
    if (nearbyOffset === offset) continue;
    const alternative = new Date(date.getTime() + (nearbyOffset - offset) * 60 * 1000);
    if (toLocalDateTime(alternative.toISOString()) === localValue) {
      throw new Error("This time occurs twice when clocks change. Choose another time.");
    }
  }
  return date.toISOString();
}
