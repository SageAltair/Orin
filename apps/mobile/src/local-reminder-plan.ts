import type { NotificationPolicy, Reminder, Task } from "./types";

export type PlannedLocalReminder = {
  key: string;
  fireAt: number;
};

const MAX_REMINDERS = 32;
const MAX_HORIZON_MS = 7 * 24 * 60 * 60 * 1000;

function inQuietHours(fireAt: number, policy: NotificationPolicy): boolean {
  if (!policy.quiet_enabled) return false;
  const toMinutes = (time: string) => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return null;
    const [hour, minute] = time.split(":").map(Number);
    return hour! * 60 + minute!;
  };
  const start = toMinutes(policy.quiet_start);
  const end = toMinutes(policy.quiet_end);
  if (start === null || end === null) return true;
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: policy.timezone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(fireAt));
    const hour = Number(parts.find((part) => part.type === "hour")?.value);
    const minute = Number(parts.find((part) => part.type === "minute")?.value);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return true;
    const current = hour * 60 + minute;
    // The API interprets equal quiet bounds as quiet all day.
    if (start === end) return true;
    return start < end
      ? current >= start && current < end
      : current >= start || current < end;
  } catch {
    return true;
  }
}

// The server holds unread alerts through quiet hours. Device-only reminders
// must likewise defer rather than disappear when the app remains closed.
// Search around the next local quiet-end boundary in UTC so DST transitions
// do not rely on a fixed timezone offset.
function afterQuietHours(fireAt: number, policy: NotificationPolicy): number | null {
  if (!policy.quiet_enabled) return fireAt;
  const validTime = /^([01]\\d|2[0-3]):[0-5]\\d$/;
  if (!validTime.test(policy.quiet_start) || !validTime.test(policy.quiet_end)) return null;
  if (policy.quiet_start === policy.quiet_end) return null;
  if (!inQuietHours(fireAt, policy)) return fireAt;
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: policy.timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(fireAt));
    const hour = Number(parts.find((part) => part.type === "hour")?.value);
    const minute = Number(parts.find((part) => part.type === "minute")?.value);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
    const [endHour, endMinute] = policy.quiet_end.split(":").map(Number);
    const end = endHour! * 60 + endMinute!;
    const local = hour * 60 + minute;
    const minutesToEnd = ((end - local + 1440) % 1440) || 1440;
    let upper = fireAt + minutesToEnd * 60_000;
    // A fall-back DST transition can put the estimated boundary inside quiet
    // hours. Allow three hours of correction, otherwise fail closed.
    for (let i = 0; i < 180 && inQuietHours(upper, policy); i++) upper += 60_000;
    if (inQuietHours(upper, policy)) return null;
    let lower = fireAt;
    while (upper - lower > 60_000) {
      const middle = lower + Math.ceil((upper - lower) / 120_000) * 60_000;
      if (inQuietHours(middle, policy)) lower = middle;
      else upper = middle;
    }
    return upper;
  } catch {
    return null;
  }
}

export function planLocalReminders(
  reminders: Reminder[],
  policy: NotificationPolicy,
  now = Date.now(),
  tasks: Task[] = [],
): PlannedLocalReminder[] {
  if (!policy.enabled) return [];
  const categories = new Set(policy.categories);
  const coveredTaskDeadlines = new Set(
    reminders
      .filter((reminder) => reminder.category === "tasks" && reminder.source_id)
      .map((reminder) => `${reminder.source_id}:${Date.parse(reminder.due_at)}`),
  );
  const fromInbox = reminders.flatMap((reminder) => {
    if (reminder.read_at || !categories.has(reminder.category)) return [];
    const due = Date.parse(reminder.due_at);
    const snooze = reminder.snoozed_until
      ? Date.parse(reminder.snoozed_until)
      : 0;
    const originalAt = Math.max(due, snooze);
    if (!Number.isFinite(originalAt) || originalAt < now + 10_000) return [];
    const fireAt = afterQuietHours(originalAt, policy);
    if (fireAt === null || fireAt > now + MAX_HORIZON_MS) return [];
    return [{ key: `${reminder.id}:${reminder.revision}:${fireAt}`, fireAt }];
  });
  const fromTasks = categories.has("tasks") ? tasks.flatMap((task) => {
    if (!task.due_at || task.status === "done" || task.status === "cancelled") return [];
    const dueAt = Date.parse(task.due_at);
    if (!Number.isFinite(dueAt) || dueAt < now + 10_000 ||
        coveredTaskDeadlines.has(`${task.id}:${dueAt}`)) return [];
    const fireAt = afterQuietHours(dueAt, policy);
    if (fireAt === null || fireAt > now + MAX_HORIZON_MS) return [];
    return [{ key: `task:${task.id}:${fireAt}`, fireAt }];
  }) : [];
  return [...fromInbox, ...fromTasks]
    .sort((a, b) => a.fireAt - b.fireAt || a.key.localeCompare(b.key))
    .slice(0, MAX_REMINDERS);
}
