/**
 * Read-only, deterministic priority planning. Callers must supply only tasks
 * the authenticated user is authorized to see. The visible-workspace filter
 * is a second boundary, not a substitute for server authorization.
 *
 * No timers, background tracking, notifications, persistence or mutations.
 * UI and delivery layers must separately enforce consent and permissions.
 */
export type PriorityGuidanceMode = "balanced" | "proactive" | "planning-only";
export type PriorityRisk = "none" | "imminent" | "capacity" | "overdue";
export type PriorityLevel = "low" | "normal" | "high" | "urgent";
export type PriorityTaskStatus = "todo" | "in_progress" | "blocked" | "done" | "cancelled";

export interface PriorityPlanningTask {
  id: string;
  workspaceId: string;
  priority: PriorityLevel;
  status: PriorityTaskStatus;
  dueAt: string | null;
  estimatedMinutes?: number | null;
  dependencyIds?: readonly string[];
  committedToOthers?: boolean;
  snoozedUntil?: string | null;
}

export interface PriorityPlanningOptions {
  now: string;
  visibleWorkspaceIds: readonly string[];
  mode?: PriorityGuidanceMode;
  focusActive?: boolean;
  quietHoursActive?: boolean;
  acknowledgedKeys?: readonly string[];
}

export interface PriorityRecommendation {
  taskId: string;
  workspaceId: string;
  dueAt: string | null;
  risk: PriorityRisk;
  score: number;
  reasons: readonly string[];
  /** An intervention candidate, never permission to send an OS notification. */
  canIntervene: boolean;
  /** Stable for one task deadline across rechecks and risk transitions. */
  dedupeKey: string;
}

const weights: Record<PriorityLevel, number> = { low: 0, normal: 20, high: 40, urgent: 60 };
const finished = (status: PriorityTaskStatus) => status === "done" || status === "cancelled";
const instant = (value: string | null | undefined): number | null => {
  // Require an explicit offset. Accept microseconds from the Python API but
  // reject calendar rollover, invalid offsets and device-local wall times.
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})$/);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, fraction, zone] = match;
  const [year, month, day, hour, minute, second] =
    [yearText, monthText, dayText, hourText, minuteText, secondText ?? "0"].map(Number);
  if (year < 1000) return null;
  const wall = Date.UTC(year, month - 1, day, hour, minute, second, Number((fraction ?? "").slice(0, 3).padEnd(3, "0")));
  const check = new Date(wall);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month ||
      check.getUTCDate() !== day || check.getUTCHours() !== hour ||
      check.getUTCMinutes() !== minute || check.getUTCSeconds() !== second) return null;
  if (zone === "Z") return wall;
  const hours = Number(zone.slice(1, 3));
  const mins = Number(zone.slice(4, 6));
  if (hours > 14 || mins > 59 || (hours === 14 && mins !== 0)) return null;
  const offset = (zone[0] === "+" ? 1 : -1) * (hours * 60 + mins) * 60_000;
  return wall - offset;
};
const minutes = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;

export function planTaskPriorities(
  tasks: readonly PriorityPlanningTask[],
  options: PriorityPlanningOptions,
): PriorityRecommendation[] {
  const now = instant(options.now);
  if (now === null) throw new Error("Priority planning requires a timezone-aware current instant.");
  const mode = options.mode ?? "balanced";
  if (mode !== "balanced" && mode !== "proactive" && mode !== "planning-only") {
    throw new Error("Unknown priority guidance mode.");
  }
  const visible = new Set(options.visibleWorkspaceIds);
  const acknowledged = new Set(options.acknowledgedKeys ?? []);
  const active = tasks.filter(task => visible.has(task.workspaceId) && !finished(task.status));
  const byWorkspace = new Map<string, Map<string, PriorityPlanningTask>>();
  for (const task of active) {
    if (!byWorkspace.has(task.workspaceId)) byWorkspace.set(task.workspaceId, new Map());
    byWorkspace.get(task.workspaceId)!.set(task.id, task);
  }
  const withDue = active.map(task => ({ task, due: instant(task.dueAt), effort: minutes(task.estimatedMinutes) }));
  return withDue.map(({ task, due, effort }) => {
    const remaining = due === null ? null : (due - now) / 60_000;
    const incompleteDependencies = (task.dependencyIds ?? []).filter(id => {
      // Never infer private or unreturned dependencies from an unknown ID.
      const dependency = byWorkspace.get(task.workspaceId)?.get(id);
      return dependency !== undefined && !finished(dependency.status);
    });
    const blocked = task.status === "blocked" || incompleteDependencies.length > 0;
    let risk: PriorityRisk = "none";
    if (remaining !== null && remaining <= 0) risk = "overdue";
    else if (remaining !== null && effort !== null) {
      // Lower-bound feasibility check across visible workspaces. Missing effort
      // is not guessed, and no task outside the authorized view is inspected.
      const committedEffort = withDue.reduce((sum, other) =>
        other.due !== null && other.due <= due! && other.effort !== null
          ? sum + other.effort : sum, 0);
      if (committedEffort > remaining) risk = "capacity";
      else if (remaining <= effort + 15) risk = "imminent";
    }
    const reasons: string[] = [];
    if (risk === "overdue") reasons.push("Deadline has passed");
    if (risk === "capacity") reasons.push("Known estimated work exceeds available time before this deadline");
    if (risk === "imminent") reasons.push("Deadline is close to the estimated time needed");
    if (task.committedToOthers) reasons.push("Explicit commitment to another person");
    if (blocked) reasons.push("Task has an unresolved dependency or is blocked");
    const key = JSON.stringify([task.workspaceId, task.id, task.dueAt]);
    const snoozed = (instant(task.snoozedUntil) ?? -Infinity) > now;
    const important = task.priority === "high" || task.priority === "urgent" || task.committedToOthers === true;
    const canIntervene = risk !== "none" && !blocked && !snoozed &&
      !options.focusActive && !options.quietHoursActive && !acknowledged.has(key) &&
      (mode === "proactive" || (mode === "balanced" && important));
    const urgency = risk === "overdue" ? 60 : risk === "capacity" ? 45 : risk === "imminent" ? 25 :
      remaining !== null && remaining <= 1440 ? 10 : 0;
    return {
      taskId: task.id, workspaceId: task.workspaceId, dueAt: task.dueAt,
      risk, score: weights[task.priority] + urgency + (task.committedToOthers ? 15 : 0) - (blocked ? 30 : 0),
      reasons, canIntervene, dedupeKey: key,
    };
  }).sort((a, b) => b.score - a.score ||
    (instant(a.dueAt) ?? Infinity) - (instant(b.dueAt) ?? Infinity) ||
    a.workspaceId.localeCompare(b.workspaceId) || a.taskId.localeCompare(b.taskId));
}
