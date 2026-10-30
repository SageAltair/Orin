import { request } from "./api";
import { getLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder, Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;
const INBOX_PAGE_SIZE = 200;
const MAX_INBOX_PAGES = 50;

// A malformed inbox timestamp can otherwise be silently ignored by the
// planner, cancelling a previously scheduled OS alert on the next sync.
function isAwareTimestamp(value: unknown): value is string {
  return typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

// The owner-scoped API has offset pagination but no date filter or total count.
// Fetch every page before touching OS schedules so a network failure cannot
// silently cancel previously scheduled reminders.
type TaskPageSnapshot = {
  upcoming: Task[];
  signatures: Map<string, { status: Task["status"]; dueAt: string | null }>;
  pages: number;
};

async function scanTaskPages(now: number): Promise<TaskPageSnapshot> {
  const upcoming: Task[] = [];
  const signatures = new Map<string, { status: Task["status"]; dueAt: string | null }>();
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const rows = await request<Task[]>(`/tasks?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`);
    if (!Array.isArray(rows) || rows.length > PAGE_SIZE) {
      throw new Error("Task reminder sync returned an invalid page.");
    }
    for (const task of rows) {
      if (!task || typeof task.id !== "string" || !task.id ||
          !["todo", "in_progress", "blocked", "done", "cancelled"].includes(task.status) ||
          (task.due_at !== null && (
            typeof task.due_at !== "string" ||
            !/(?:Z|[+-]\d{2}:\d{2})$/.test(task.due_at) ||
            !Number.isFinite(Date.parse(task.due_at))
          ))) {
        throw new Error("Task reminder sync returned an invalid record.");
      }
      if (signatures.has(task.id)) {
        throw new Error("Overlapping task reminder pages; device schedules were preserved.");
      }
      signatures.set(task.id, { status: task.status, dueAt: task.due_at });
      if (task.status === "done" || task.status === "cancelled" || !task.due_at) continue;
      const due = Date.parse(task.due_at);
      // Retain 48 hours of overdue deadlines for deferred quiet-hour alerts.
      if (due > now - 48 * 60 * 60 * 1000) upcoming.push(task);
    }
    if (rows.length < PAGE_SIZE) return { upcoming, signatures, pages: page + 1 };
  }
  // Exactly 10,000 tasks are valid only if the next page is empty.
  const extra = await request<Task[]>(`/tasks?limit=1&offset=${MAX_PAGES * PAGE_SIZE}`);
  if (Array.isArray(extra) && extra.length === 0) {
    return { upcoming, signatures, pages: MAX_PAGES + 1 };
  }
  throw new Error("Task reminder sync exceeds 10,000 tasks or returned an invalid page. Existing device reminders were preserved.");
}

// Offset pages can shift without overlapping IDs when another client deletes
// or edits a task. Confirm every identity/status/deadline before touching OS
// schedules. This is best-effort consistency, not an atomic database snapshot.
export async function fetchDeviceReminderTasks(now = Date.now()): Promise<Task[]> {
  const initial = await scanTaskPages(now);
  if (initial.pages > 1) {
    const confirmed = await scanTaskPages(now);
    if (initial.signatures.size !== confirmed.signatures.size ||
        [...initial.signatures].some(([id, value]) => {
          const other = confirmed.signatures.get(id);
          return !other || other.status !== value.status || other.dueAt !== value.dueAt;
        })) {
      throw new Error("Task reminder pages changed during pagination; device schedules were preserved.");
    }
  }
  return initial.upcoming;
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
      if (!reminder || typeof reminder.id !== "string" || !reminder.id ||
          typeof reminder.category !== "string" || !reminder.category ||
          !Number.isInteger(reminder.revision) || reminder.revision < 0 ||
          !isAwareTimestamp(reminder.due_at) ||
          (reminder.read_at !== null && !isAwareTimestamp(reminder.read_at)) ||
          (reminder.snoozed_until !== null && !isAwareTimestamp(reminder.snoozed_until)) ||
          (reminder.source_id !== null && typeof reminder.source_id !== "string")) {
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
