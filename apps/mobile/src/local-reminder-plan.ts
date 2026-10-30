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

// The server retains unread alerts through quiet hours. The device planner
// defers to the first allowed minute, including ambiguous or missing wall-clock
// minutes at daylight-saving transitions.
function afterQuietHours(fireAt: number, policy: NotificationPolicy): number | null {
  if (!policy.quiet_enabled) return fireAt;
  const validTime = /^([01]\d|2[0-3]):[0-5]\d$/;
  if (!validTime.test(policy.quiet_start) || !validTime.test(policy.quiet_end)) return null;
  if (policy.quiet_start === policy.quiet_end) return null;
  if (!inQuietHours(fireAt, policy)) return fireAt;
  try {
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone: policy.timezone,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    const localAt = (utc: number) => {
      const parts = formatter.formatToParts(new Date(utc));
      const part = (name: string) => Number(parts.find((item) => item.type === name)?.value);
      const year = part("year"), month = part("month"), day = part("day");
      const hour = part("hour"), minute = part("minute");
      if (![year, month, day, hour, minute].every(Number.isFinite)) {
        throw new Error("Invalid timezone date");
      }
      return {
        minuteOfDay: hour * 60 + minute,
        offset: Date.UTC(year, month - 1, day, hour, minute) - Math.floor(utc / 60_000) * 60_000,
      };
    };
    const [startHour, startMinute] = policy.quiet_start.split(":").map(Number);
    const [endHour, endMinute] = policy.quiet_end.split(":").map(Number);
    const start = startHour! * 60 + startMinute!;
    const end = endHour! * 60 + endMinute!;
    const isQuiet = (minute: number) =>
      start < end ? minute >= start && minute < end : minute >= start || minute < end;
    const initial = localAt(fireAt);
    const minutesToEnd = ((end - initial.minuteOfDay + 1440) % 1440) || 1440;
    const estimated = Math.floor(fireAt / 60_000) * 60_000 + minutesToEnd * 60_000;
    const estimatedLocal = localAt(estimated);
    // On ordinary days the UTC offset stays constant, so this is exact and
    // avoids a minute-by-minute search for every scheduled task.
    if (initial.offset === estimatedLocal.offset && estimatedLocal.minuteOfDay === end) {
      return estimated;
    }
    // A clock change can make quiet status non-monotonic (the repeated 01:00
    // hour may briefly become allowed). Binary search would skip that window.
    // DST is rare; use a bounded, minute-accurate scan only on those days.
    const last = fireAt + 27 * 60 * 60_000;
    for (let cursor = Math.floor(fireAt / 60_000) * 60_000 + 60_000;
      cursor <= last; cursor += 60_000) {
      if (!isQuiet(localAt(cursor).minuteOfDay)) return cursor;
    }
    return null;
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
    if (!Number.isFinite(originalAt)) return [];
    const fireAt = afterQuietHours(originalAt, policy);
    // A reminder that became due during quiet hours still needs its
    // deferred alert when the app resumes before the quiet interval ends.
    if (fireAt === null || fireAt < now + 10_000 || fireAt > now + MAX_HORIZON_MS) return [];
    return [{ key: `${reminder.id}:${reminder.revision}:${fireAt}`, fireAt }];
  });
  const fromTasks = categories.has("tasks") ? tasks.flatMap((task) => {
    if (!task.due_at || task.status === "done" || task.status === "cancelled") return [];
    const dueAt = Date.parse(task.due_at);
    if (!Number.isFinite(dueAt) ||
        coveredTaskDeadlines.has(`${task.id}:${dueAt}`)) return [];
    const fireAt = afterQuietHours(dueAt, policy);
    if (fireAt === null || fireAt < now + 10_000 || fireAt > now + MAX_HORIZON_MS) return [];
    return [{ key: `task:${task.id}:${fireAt}`, fireAt }];
  }) : [];
  // A quiet-hour boundary can move many reminders to the same minute.
  // The OS message is generic, so one alert per minute is sufficient and
  // avoids a burst of indistinguishable notifications when quiet hours end.
  const scheduledMinutes = new Set<number>();
  return [...fromInbox, ...fromTasks]
    .sort((a, b) => a.fireAt - b.fireAt || a.key.localeCompare(b.key))
    .filter((item) => {
      const minute = Math.floor(item.fireAt / 60_000);
      if (scheduledMinutes.has(minute)) return false;
      scheduledMinutes.add(minute);
      return true;
    })
    .slice(0, MAX_REMINDERS);
}
