import { describe, expect, it } from "vitest";
import { planTaskPriorities, type PriorityPlanningTask } from "./priorityIntelligence";

const now = "2026-10-30T12:00:00Z";
const task = (id: string, changes: Partial<PriorityPlanningTask> = {}): PriorityPlanningTask => ({
  id, workspaceId: "work", priority: "normal", status: "todo",
  dueAt: "2026-10-30T13:00:00Z", estimatedMinutes: 20, ...changes,
});
const options = { now, visibleWorkspaceIds: ["work", "personal"] };

describe("intentional priority planning", () => {
  it("defaults to balanced, intervening only for important at-risk commitments", () => {
    const plan = planTaskPriorities([
      task("routine", { dueAt: "2026-10-30T12:10:00Z" }),
      task("important", { priority: "high", dueAt: "2026-10-30T12:10:00Z" }),
    ], options);
    expect(plan.find(item => item.taskId === "routine")?.canIntervene).toBe(false);
    expect(plan.find(item => item.taskId === "important")?.canIntervene).toBe(true);
  });

  it("proactive can suggest ordinary at-risk work; planning-only never interrupts", () => {
    const items = [task("normal", { dueAt: "2026-10-30T12:10:00Z" })];
    expect(planTaskPriorities(items, { ...options, mode: "proactive" })[0].canIntervene).toBe(true);
    expect(planTaskPriorities(items, { ...options, mode: "planning-only" })[0].canIntervene).toBe(false);
  });

  it("detects cross-workspace workload conflicts without treating every deadline equally", () => {
    const items = [
      task("personal", { workspaceId: "personal", priority: "low", estimatedMinutes: 40 }),
      task("team", { priority: "high", estimatedMinutes: 40, committedToOthers: true }),
    ];
    const plan = planTaskPriorities(items, options);
    expect(plan.find(item => item.taskId === "team")?.risk).toBe("capacity");
    expect(plan[0].taskId).toBe("team");
    expect(plan[0].reasons).toContain("Explicit commitment to another person");
  });

  it("does not expose tasks from workspaces absent from the authorized view", () => {
    const plan = planTaskPriorities([
      task("private", { workspaceId: "secret", priority: "urgent", estimatedMinutes: 1000 }),
      task("visible", { estimatedMinutes: 20 }),
    ], options);
    expect(plan.map(item => item.taskId)).toEqual(["visible"]);
    expect(plan[0].risk).toBe("none");
  });

  it("avoids fabricated urgency when deadlines or effort estimates are missing", () => {
    const plan = planTaskPriorities([
      task("undated", { dueAt: null, estimatedMinutes: 120, priority: "urgent" }),
      task("unestimated", { dueAt: "2026-10-30T12:05:00Z", estimatedMinutes: null, priority: "urgent" }),
    ], options);
    expect(plan.every(item => item.risk === "none" && !item.canIntervene)).toBe(true);
  });

  it("suppresses interruptions during focus, quiet hours and snooze", () => {
    const items = [task("deadline", { priority: "urgent", dueAt: "2026-10-30T12:10:00Z" })];
    expect(planTaskPriorities(items, { ...options, focusActive: true })[0].canIntervene).toBe(false);
    expect(planTaskPriorities(items, { ...options, quietHoursActive: true })[0].canIntervene).toBe(false);
    expect(planTaskPriorities([task("deadline", { priority: "urgent", dueAt: "2026-10-30T12:10:00Z", snoozedUntil: "2026-10-30T12:30:00Z" })], options)[0].canIntervene).toBe(false);
  });

  it("deduplicates by workspace, task and due instant even after risk changes", () => {
    const items = [task("deadline", { priority: "urgent", dueAt: "2026-10-30T12:25:00Z" })];
    const first = planTaskPriorities(items, options)[0];
    const later = planTaskPriorities(items, { ...options, now: "2026-10-30T12:30:00Z", acknowledgedKeys: [first.dedupeKey] })[0];
    expect(first.risk).toBe("imminent");
    expect(later.risk).toBe("overdue");
    expect(later.dedupeKey).toBe(first.dedupeKey);
    expect(later.canIntervene).toBe(false);
  });

  it("does not recommend starting blocked work or completed tasks", () => {
    const plan = planTaskPriorities([
      task("blocker", { dueAt: null }),
      task("dependent", { priority: "urgent", dueAt: "2026-10-30T12:05:00Z", dependencyIds: ["blocker"] }),
      task("done", { priority: "urgent", status: "done" }),
    ], options);
    expect(plan.find(item => item.taskId === "dependent")?.canIntervene).toBe(false);
    expect(plan.some(item => item.taskId === "done")).toBe(false);
  });

  it("requires timezone-aware timestamps and rejects invalid modes", () => {
    expect(() => planTaskPriorities([], { ...options, now: "2026-10-30T12:00:00" })).toThrow("timezone-aware");
    expect(() => planTaskPriorities([], { ...options, mode: "unknown" as never })).toThrow("Unknown");
  });

  it("accepts server microseconds and offsets but rejects calendar rollover", () => {
    const plan = planTaskPriorities([
      task("valid", { priority: "urgent", dueAt: "2026-10-30T15:25:00.123456+03:00" }),
      task("rollover", { priority: "urgent", dueAt: "2026-02-31T12:05:00Z" }),
      task("offset", { priority: "urgent", dueAt: "2026-10-30T12:05:00+15:00" }),
    ], options);
    expect(plan.find(item => item.taskId === "valid")?.risk).toBe("imminent");
    expect(plan.find(item => item.taskId === "rollover")?.risk).toBe("none");
    expect(plan.find(item => item.taskId === "offset")?.risk).toBe("none");
  });

  it("sorts tied recommendations deterministically and does not mutate inputs", () => {
    const tasks = [task("z"), task("a")];
    const plan = planTaskPriorities(tasks, options);
    expect(plan.map(item => item.taskId)).toEqual(["a", "z"]);
    expect(tasks.map(item => item.id)).toEqual(["z", "a"]);
  });
});
