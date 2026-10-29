import type { NotificationPolicy, Reminder } from "./types";

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

export function planLocalReminders(
  reminders: Reminder[],
  policy: NotificationPolicy,
  now = Date.now(),
): PlannedLocalReminder[] {
  if (!policy.enabled) return [];
  const categories = new Set(policy.categories);
  return reminders.flatMap((reminder) => {
    if (reminder.read_at || !categories.has(reminder.category)) return [];
    const due = Date.parse(reminder.due_at);
    const snooze = reminder.snoozed_until
      ? Date.parse(reminder.snoozed_until)
      : 0;
    const fireAt = Math.max(due, snooze);
    if (
      !Number.isFinite(fireAt) ||
      fireAt < now + 10_000 ||
      fireAt > now + MAX_HORIZON_MS ||
      inQuietHours(fireAt, policy)
    ) return [];
    return [{ key: `${reminder.id}:${reminder.revision}:${fireAt}`, fireAt }];
  }).sort((a, b) => a.fireAt - b.fireAt).slice(0, MAX_REMINDERS);
}
