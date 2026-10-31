import { request, wasRefreshCredentialRejected } from "./api";
import { getLocalReminderEnabled, revokeLocalReminderOwner, syncLocalReminders } from "./native-reminders";
import type { NotificationPolicy, Reminder, Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;
const INBOX_PAGE_SIZE = 200;
const MAX_INBOX_PAGES = 50;

// Date.parse normalizes impossible dates (e.g. February 31) and accepts
// nonstandard timezone offsets (e.g. +15:00). Both could silently move a
// reminder to the wrong day. Fail closed before replacing OS schedules.
function isAwareTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
  const hour = Number(match[4]), minute = Number(match[5]), second = Number(match[6] ?? "0");
  const zone = match[8]!;
  if (year < 1000) return false;
  if (zone !== "Z") {
    const hours = Number(zone.slice(1, 3)), minutes = Number(zone.slice(4, 6));
    if (hours > 14 || minutes > 59 || (hours === 14 && minutes !== 0)) return false;
  }
  const wall = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  return Number.isFinite(Date.parse(value)) &&
    wall.getUTCFullYear() === year && wall.getUTCMonth() + 1 === month &&
    wall.getUTCDate() === day && wall.getUTCHours() === hour &&
    wall.getUTCMinutes() === minute && wall.getUTCSeconds() === second;
}

// A malformed server policy must not turn quiet hours into an empty device
// schedule. Validate every field used for suppression before touching OS alerts.
// Explicit opt-out is authoritative even if unrelated fields are malformed.
function assertValidDevicePolicy(value: unknown): asserts value is NotificationPolicy {
  if (!value || typeof value !== "object" ||
      typeof (value as NotificationPolicy).enabled !== "boolean") {
    throw new Error("Invalid notification policy; device schedules were preserved.");
  }
  const policy = value as NotificationPolicy;
  if (!policy.enabled) return;
  if (!Array.isArray(policy.categories) ||
      policy.categories.some((category) => typeof category !== "string")) {
    throw new Error("Invalid notification policy; device schedules were preserved.");
  }
  // Removing every category is also an explicit opt-out. Do not let an
  // unrelated malformed quiet-hours field keep old alerts on the device.
  if (policy.categories.length === 0) return;
  const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  if (typeof policy.quiet_enabled !== "boolean" ||
      typeof policy.respect_focus !== "boolean" ||
      typeof policy.timezone !== "string" ||
      typeof policy.quiet_start !== "string" || !clock.test(policy.quiet_start) ||
      typeof policy.quiet_end !== "string" || !clock.test(policy.quiet_end)) {
    throw new Error("Invalid notification policy; device schedules were preserved.");
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: policy.timezone });
  } catch {
    throw new Error("Invalid notification policy timezone; device schedules were preserved.");
  }
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
          (task.due_at !== null && !isAwareTimestamp(task.due_at))) {
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
type InboxPageSnapshot = {
  reminders: Reminder[];
  signatures: Map<string, string>;
  pages: number;
};

async function scanInboxPages(): Promise<InboxPageSnapshot> {
  const reminders: Reminder[] = [];
  const signatures = new Map<string, string>();
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
      if (signatures.has(reminder.id)) {
        throw new Error("Overlapping notification inbox pages; device schedules were preserved.");
      }
      // Only fields that influence local scheduling need to remain stable.
      signatures.set(reminder.id, JSON.stringify([
        reminder.category, reminder.source_id, reminder.due_at,
        reminder.read_at, reminder.snoozed_until, reminder.revision,
      ]));
      reminders.push(reminder);
    }
    if (rows.length < INBOX_PAGE_SIZE) return { reminders, signatures, pages: page + 1 };
  }
  // Exactly 10,000 records are safe only after an empty boundary probe.
  const extra = await request<Reminder[]>(
    `/notifications?limit=1&offset=${MAX_INBOX_PAGES * INBOX_PAGE_SIZE}`,
  );
  if (Array.isArray(extra) && extra.length === 0) {
    return { reminders, signatures, pages: MAX_INBOX_PAGES + 1 };
  }
  throw new Error("Notification inbox exceeds 10,000 records or returned an invalid page. Existing device reminders were preserved.");
}

// Confirm multi-page inbox identity and scheduling state before replacing OS
// alerts. Offset deletions can omit a reminder without overlapping page IDs.
// This is best-effort consistency, not an atomic database snapshot.
export async function fetchDeviceReminderInbox(): Promise<Reminder[]> {
  const initial = await scanInboxPages();
  if (initial.pages > 1) {
    const confirmed = await scanInboxPages();
    if (initial.signatures.size !== confirmed.signatures.size ||
        [...initial.signatures].some(([id, signature]) =>
          confirmed.signatures.get(id) !== signature)) {
      throw new Error("Notification inbox changed during pagination; device schedules were preserved.");
    }
  }
  return initial.reminders;
}

// No permission prompts here. Only an explicitly opted-in owner is eligible.
// Session and workspace changes fence stale in-flight network responses.
async function refreshDeviceRemindersInternal(
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
  assertValidDevicePolicy(policy);
  if (!policy.enabled || policy.categories.length === 0) {
    // No enabled categories means no alert can be delivered. Cancel without
    // depending on the inbox or task endpoints being online.
    await syncLocalReminders(owner, workspaceId, [], policy, []);
    return;
  }
  const [reminders, tasks] = await Promise.all([
    fetchDeviceReminderInbox(),
    policy.categories.includes("tasks") ? fetchDeviceReminderTasks() : Promise.resolve([]),
  ]);
  if (!isCurrent()) return;
  // A remote opt-out, category change or quiet-hours update can arrive while
  // paginated tasks and inbox reminders are being fetched. Re-read policy
  // before replacing OS schedules; a revoked opt-in clears alerts immediately.
  const livePolicy = await request<NotificationPolicy>("/notifications/preferences");
  if (!isCurrent()) return;
  assertValidDevicePolicy(livePolicy);
  if (!livePolicy.enabled || livePolicy.categories.length === 0) {
    await syncLocalReminders(owner, workspaceId, [], livePolicy, []);
    return;
  }
  // The initial policy excluded task fetching, so newly enabling the category
  // cannot safely schedule a partial snapshot. Retry on the next refresh.
  if (!policy.categories.includes("tasks") && livePolicy.categories.includes("tasks")) {
    throw new Error("Task notification policy changed during sync; device schedules were preserved.");
  }
  await syncLocalReminders(owner, workspaceId, reminders, livePolicy, tasks);
}

/** A definitive refresh rejection revokes only this owner's local OS alerts.
 * A temporary network/5xx refresh failure does not set that auth signal, so
 * offline schedules survive. An old request cannot clear a newer account.
 */
export async function refreshDeviceReminders(
  owner: string,
  workspaceId: string,
  isCurrent: () => boolean = () => true,
): Promise<void> {
  try {
    await refreshDeviceRemindersInternal(owner, workspaceId, isCurrent);
  } catch (error) {
    if (isCurrent() && wasRefreshCredentialRejected()) {
      await revokeLocalReminderOwner(owner);
    }
    throw error;
  }
}
