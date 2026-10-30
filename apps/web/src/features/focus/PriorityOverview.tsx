import { useEffect, useState } from "react";
import { request, type Task } from "../../api";
import { fetchAllPages } from "./taskPagination";
import { planTaskPriorities, type PriorityGuidanceMode } from "./priorityIntelligence";

type OwnedTask = Task & { workspace_id?: string | null };
type Workspace = { id: string; name: string };
const loadOwnerTasks = () => fetchAllPages<OwnedTask>(
  (offset, limit) => request<OwnedTask[]>(`/priority/tasks?limit=${limit}&offset=${offset}`),
  "priority tasks", 100, 50, item => item.id,
);

export function PriorityOverview({ tasks, activeWorkspaceId, mode, now, onEditTask }: {
  tasks: Task[];
  activeWorkspaceId: string;
  mode: PriorityGuidanceMode;
  now: Date;
  onEditTask?: (task: Task) => void;
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
  }, [includeAll, refreshVersion]);

  const personalId = workspaces[0]?.id ?? activeWorkspaceId ?? "personal";
  const currentId = activeWorkspaceId || personalId || "personal";
  const source: OwnedTask[] = includeAll ? remoteTasks : tasks;
  const allowed = includeAll ? workspaces.map(space => space.id) : [currentId];
  const planningTasks = source.map(task => ({
    id: task.id,
    workspaceId: includeAll ? (task.workspace_id ?? personalId) : currentId,
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
            <span>{includeAll ? `${workspaceNames.get(item.workspaceId) ?? "Personal"} · ` : ""}
              {task.due_at ? new Date(task.due_at).toLocaleString() : "No deadline"}
            </span></div>
          <div className="focus-priority-row-actions">
            <small>{item.reasons[0] ?? (task.priority === "urgent" ? "Marked urgent" : task.priority === "high" ? "Marked high priority" : "For planning")}</small>
            {onEditTask && item.workspaceId === currentId && <button type="button"
              aria-label={`Edit ${task.title}`} onClick={() => onEditTask(task)}>Edit task</button>}
          </div>
        </li>;
      })}
    </ol> : <p className="focus-quiet-message">No active tasks to prioritize in this scope.</p>)}
  </section>;
}
