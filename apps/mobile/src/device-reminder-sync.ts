import { request } from "./api";
import { getLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder, Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;
const INBOX_PAGE_SIZE = 200;
const MAX_INBOX_PAGES = 50;

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
      // A deadline that passed during quiet hours can still have a future
      // deferred alert. Retain a 48-hour lookback (including DST shifts);
      // the planner rejects any deadline whose deferred time has passed.
      if (Number.isFinite(due) && due > now - 48 * 60 * 60 * 1000) upcoming.push(task);
    }
    if (rows.length < PAGE_SIZE) return upcoming;
  }
  throw new Error("Task reminder sync exceeded 10,000 tasks. Existing device reminders were preserved.");
}

// The inbox API defaults to 100 newest-due notifications. Without pagination,
// earlier due alerts can disappear from the device planner even while unread.
// A failed or overlapping page must leave the existing OS schedule untouched.
export async function fetchDeviceReminderInbox(): Promise<Reminder[]> {
  const reminders: Reminder[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < MAX_INBOX_PAGES; page += 1) {
    const rows = await request<Reminder[]>(
      `/notifications?limit=${INBOX_PAGE_SIZE}&offset=${page * INBOX_PAGE_SIZE}`,
    );
    if (!Array.isArray(rows) || rows.length > INBOX_PAGE_SIZE) {
      throw new Error("Notification inbox returned an invalid page.");
    }
    for (const reminder of rows) {
      if (!reminder || typeof reminder.id !== "string") {
        throw new Error("Notification inbox returned an invalid record.");
      }
      if (seen.has(reminder.id)) {
        throw new Error("Overlapping notification inbox pages; device schedules were preserved.");
      }
      seen.add(reminder.id);
      reminders.push(reminder);
    }
    if (rows.length < INBOX_PAGE_SIZE) return reminders;
  }
  // Exactly 10,000 records are safe; distinguish them from an incomplete list.
  const extra = await request<Reminder[]>(
    `/notifications?limit=1&offset=${MAX_INBOX_PAGES * INBOX_PAGE_SIZE}`,
  );
  if (Array.isArray(extra) && extra.length === 0) return reminders;
  throw new Error("Notification inbox exceeds 10,000 records or returned an invalid page. Existing device reminders were preserved.");
}

// No permission prompts here. Only an explicitly opted-in owner is eligible.
// Session and workspace changes fence stale in-flight network responses.
export async function refreshDeviceReminders(
  owner: string,
  workspaceId: string,
  isCurrent: () => boolean = () => true,
): Promise<void> {
  if (!isCurrent()) return;
  if (!(await getLocalReminderEnabled(owner)) || !isCurrent()) return;
  // Revoking the server policy must cancel local alerts even when the task
  // endpoint is unavailable. Do not make a full task scan a prerequisite.
  const policy = await request<NotificationPolicy>("/notifications/preferences");
  if (!isCurrent()) return;
  if (!policy.enabled) {
    await syncLocalReminders(owner, workspaceId, [], policy, []);
    return;
  }
  const [reminders, tasks] = await Promise.all([
    fetchDeviceReminderInbox(),
    policy.categories.includes("tasks") ? fetchDeviceReminderTasks() : Promise.resolve([]),
  ]);
  if (!isCurrent()) return;
  await syncLocalReminders(owner, workspaceId, reminders, policy, tasks);
}
