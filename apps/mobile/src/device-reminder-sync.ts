import { request } from "./api";
import { getLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder, Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;

// The owner-scoped API has offset pagination but no date filter or total count.
// Fetch every page before touching OS schedules so a network failure cannot
// silently cancel previously scheduled reminders.
export async function fetchDeviceReminderTasks(now = Date.now()): Promise<Task[]> {
  const upcoming: Task[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const rows = await request<Task[]>(`/tasks?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`);
    if (!Array.isArray(rows)) throw new Error("Task reminder sync returned an invalid page.");
    for (const task of rows) {
      if (seen.has(task.id)) continue;
      seen.add(task.id);
      if (task.status === "done" || task.status === "cancelled" || !task.due_at) continue;
      const due = Date.parse(task.due_at);
      if (Number.isFinite(due) && due > now) upcoming.push(task);
    }
    if (rows.length < PAGE_SIZE) return upcoming;
  }
  throw new Error("Task reminder sync exceeded 10,000 tasks. Existing device reminders were preserved.");
}

// No permission prompts here. Only an explicitly opted-in owner is eligible.
// Session and workspace changes fence stale in-flight network responses.
export async function refreshDeviceReminders(
  owner: string,
  isCurrent: () => boolean = () => true,
): Promise<void> {
  if (!isCurrent()) return;
  if (!(await getLocalReminderEnabled(owner)) || !isCurrent()) return;
  const [reminders, policy, tasks] = await Promise.all([
    request<Reminder[]>("/notifications"),
    request<NotificationPolicy>("/notifications/preferences"),
    fetchDeviceReminderTasks(),
  ]);
  if (!isCurrent()) return;
  await syncLocalReminders(owner, reminders, policy, tasks);
}
