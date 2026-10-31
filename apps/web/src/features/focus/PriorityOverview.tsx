import { CalendarClock, Check, Pencil, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { request, type Task } from "../../api";
import { fetchAllPages } from "./taskPagination";
import { planTaskPriorities, type PriorityGuidanceMode } from "./priorityIntelligence";

type OwnedTask = Task & { workspace_id?: string | null };
type Workspace = { id: string; name: string };
// Legacy rows without a workspace must never be attributed to the first
// returned workspace or made actionable in the current workspace.
const unscopedWorkspaceId = "__unscoped__";
const loadOwnerTasks = () => fetchAllPages<OwnedTask>(
  (offset, limit) => request<OwnedTask[]>(`/priority/tasks?limit=${limit}&offset=${offset}`),
  "priority tasks", 100, 50, item => item.id,
);

export function PriorityOverview({ tasks, activeWorkspaceId, mode, now, onEditTask, onScheduleTask, onStartTask, onCompleteTask, actionsBusy = false, taskRevision = 0 }: {
  tasks: Task[];
  activeWorkspaceId: string;
  mode: PriorityGuidanceMode;
  now: Date;
  onEditTask?: (task: Task) => void;
  onScheduleTask?: (taskId: string) => void;
  /** Explicitly mark a not-started task in progress; does not launch a focus timer. */
  onStartTask?: (task: Task) => void;
  onCompleteTask?: (task: Task) => void;
  actionsBusy?: boolean;
  taskRevision?: number;
}) {
  const [includeAll, setIncludeAll] = useState(false);
  const [remoteTasks, setRemoteTasks] = useState<OwnedTask[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!includeAll) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([loadOwnerTasks(), request<Workspace[]>("/workspaces")])
      .then(([items, spaces]) => {
        if (cancelled) return;
        if (!Array.isArray(spaces) || spaces.some(space => !space.id || !space.name)) {
          throw new Error("Invalid workspace inventory.");
        }
        setRemoteTasks(items);
        setWorkspaces(spaces);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Priority inventory could not be loaded.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [includeAll, refreshVersion, taskRevision]);

  const currentId = activeWorkspaceId || "personal";
  const source: OwnedTask[] = includeAll ? remoteTasks : tasks;
  const allowed = includeAll ? [...workspaces.map(space => space.id), unscopedWorkspaceId] : [currentId];
  const planningTasks = source.map(task => ({
    id: task.id,
    workspaceId: includeAll ? (task.workspace_id ?? unscopedWorkspaceId) : currentId,
    priority: task.priority,
    status: task.status,
    dueAt: task.due_at,
    estimatedMinutes: task.estimated_minutes,
  }));
  const ranked = planTaskPriorities(planningTasks, {
    now: now.toISOString(), visibleWorkspaceIds: allowed, mode,
    // This is a read-only view. It does not authorize any alert or interruption.
    focusActive: true,
  });
  const byId = new Map<string, OwnedTask>(planningTasks.map((task, index): [string, OwnedTask] => [
    JSON.stringify([task.workspaceId, task.id]), source[index],
  ]));
  const workspaceNames = new Map(workspaces.map(space => [space.id, space.name]));
  const preview = ranked.slice(0, 4);

  return <section className="focus-priority-overview" aria-labelledby="priority-overview-title">
    <div className="focus-priority-overview-heading">
      <div><h2 id="priority-overview-title">Priority outlook</h2>
        <p>Suggested order based on importance, deadlines and known effort. Suggestions only. No automatic changes or alerts.</p></div>
      <span>{mode === "planning-only" ? "Planning-only" : mode === "proactive" ? "Proactive" : "Balanced"}</span>
    </div>
    <label className="focus-priority-scope">
      <input type="checkbox" checked={includeAll} onChange={event => setIncludeAll(event.target.checked)} />
      Include tasks from all my workspaces
    </label>
    {includeAll && !loading && !error && <button type="button" className="focus-priority-refresh"
      onClick={() => setRefreshVersion(value => value + 1)}>Refresh priorities</button>}
    {includeAll && loading && <p role="status">Loading your workspace priorities…</p>}
    {includeAll && error && <p role="alert">{error} <button type="button" onClick={() => setRefreshVersion(value => value + 1)}>Retry</button></p>}
    {(!includeAll || (!loading && !error)) && (preview.length ? <ol className="focus-priority-list">
      {preview.map(item => {
        const task = byId.get(JSON.stringify([item.workspaceId, item.taskId]));
        if (!task) return null;
        return <li key={item.dedupeKey}>
          <div><strong>{task.title}</strong>
            <span>{includeAll ? `${workspaceNames.get(item.workspaceId) ?? (item.workspaceId === unscopedWorkspaceId ? "Unscoped task" : "Unknown workspace")} · ` : ""}
              {task.due_at ? new Date(task.due_at).toLocaleString() : "No deadline"}
            </span></div>
          <div className="focus-priority-row-actions">
            <small>{item.reasons[0] ?? (task.priority === "urgent" ? "Marked urgent" : task.priority === "high" ? "Marked high priority" : "For planning")}</small>
            {item.workspaceId === currentId && <>
              {onEditTask && <button type="button" disabled={actionsBusy}
                aria-label={`Edit ${task.title}`} onClick={() => onEditTask(task)} title="Edit task"><Pencil size={16}/></button>}
              {onScheduleTask && <button type="button" disabled={actionsBusy}
                aria-label={`Schedule ${task.title}`} onClick={() => onScheduleTask(task.id)} title="Schedule task"><CalendarClock size={16}/></button>}
              {onStartTask && task.status === "todo" && <button type="button" disabled={actionsBusy}
                aria-label={`Start ${task.title}`} onClick={() => onStartTask(task)} title="Start task"><Play size={16}/></button>}
              {onCompleteTask && <button type="button" disabled={actionsBusy}
                aria-label={`Mark ${task.title} done`} onClick={() => onCompleteTask(task)} title="Mark done"><Check size={16}/></button>}
            </>}
          </div>
        </li>;
      })}
    </ol> : <p className="focus-quiet-message">No active tasks to prioritize in this scope.</p>)}
  </section>;
}
