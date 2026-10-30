import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, Pencil, Plus, RotateCcw, X } from "lucide-react";
import { ApiError, request, type Project, type Task } from "../../api";
import { filterTasksForView, type TaskView } from "./taskViews";
import { blankTaskDraft, draftFromTask, nextTaskStatus, taskPayload, type TaskDraft } from "./taskEditor";
import { fetchAllPages } from "./taskPagination";
import { PriorityOverview } from "./PriorityOverview";
import type { PriorityGuidanceMode } from "./priorityIntelligence";
import "./task-workspace.css";

const views: Array<[TaskView, string]> = [
  ["all", "All tasks"], ["today", "Today"], ["upcoming", "Upcoming"],
  ["overdue", "Overdue"], ["inbox", "Inbox"], ["completed", "Completed"],
];
const errorMessage = (value: unknown, fallback: string) => value instanceof ApiError ? value.message : value instanceof Error ? value.message : fallback;

const fetchAllTasks = () => fetchAllPages<Task>(
  (offset, limit) => request<Task[]>(`/tasks?limit=${limit}&offset=${offset}`), "tasks",
  100, 50, (task) => task.id,
);
const fetchAllProjects = () => fetchAllPages<Project>(
  (offset, limit) => request<Project[]>(`/projects?limit=${limit}&offset=${offset}`), "projects",
  100, 50, (project) => project.id,
);

export function TaskCollection({ onScheduleTask, onOpenProject, onTaskSaved, activeWorkspaceId = "", priorityGuidanceMode = "balanced" }: { onScheduleTask?: (taskId: string) => void; onOpenProject?: (projectId: string) => void; onTaskSaved?: (task: Task) => void; activeWorkspaceId?: string; priorityGuidanceMode?: PriorityGuidanceMode }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [view, setView] = useState<TaskView>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<TaskDraft>(blankTaskDraft);
  const [error, setError] = useState("");
  const [projectError, setProjectError] = useState("");
  const [notice, setNotice] = useState("");
  const [now, setNow] = useState(() => new Date());
  const [taskRevision, setTaskRevision] = useState(0);
  const loadVersion = useRef(0);
  const mutationVersion = useRef(0);
  const mutationActive = useRef(false);
  const editingBaseline = useRef<Task | null>(null);

  const loadProjects = async () => {
    setProjectError("");
    try { setProjects(await fetchAllProjects()); }
    catch (value) { setProjectError(errorMessage(value, "Project choices could not be loaded.")); }
  };

  const load = async (silent = false) => {
    const version = ++loadVersion.current;
    const mutationAtStart = mutationVersion.current;
    if (!silent) { setLoading(true); setError(""); }
    try {
      const next = await fetchAllTasks();
      // An older poll must never overwrite a newer poll or a locally saved edit.
      if (version === loadVersion.current && mutationAtStart === mutationVersion.current) {
        setTasks(next);
        if (silent) setError("");
      }
    } catch (value) {
      if (version === loadVersion.current && mutationAtStart === mutationVersion.current) {
        setError(errorMessage(value, "Tasks could not be loaded. Try again."));
      }
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  };
  useEffect(() => {
    void load();
    void loadProjects();
    let lastForegroundRefresh = 0;
    const revalidate = () => {
      if (document.visibilityState !== "visible") return;
      setNow(new Date());
      if (mutationActive.current) return;
      // Focus and visibilitychange commonly arrive together.
      const stamp = Date.now();
      if (stamp - lastForegroundRefresh < 1000) return;
      lastForegroundRefresh = stamp;
      void load(true);
    };
    // Refresh due-state without requiring a click; only poll the API while visible.
    const clock = window.setInterval(() => {
      if (document.visibilityState === "visible") setNow(new Date());
    }, 15_000);
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible" && !mutationActive.current) void load(true);
    }, 60_000);
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      ++loadVersion.current;
      window.clearInterval(clock);
      window.clearInterval(poll);
      window.removeEventListener("focus", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, []);

  const visibleTasks = filterTasksForView(tasks, view, search, now);
  const projectNameFor = (id: string) => projects.find(project => project.id === id)?.name ?? "Project task";
  const begin = (task?: Task) => {
    editingBaseline.current = task ?? null;
    setEditingId(task?.id ?? "new");
    setDraft(task ? draftFromTask(task) : blankTaskDraft());
    setError(""); setNotice("");
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mutationActive.current || !draft.title.trim() || !editingId) return;
    mutationActive.current = true;
    ++mutationVersion.current;
    setBusyId(editingId); setError(""); setNotice("");
    try {
      const isNew = editingId === "new";
      const payload = taskPayload(draft, isNew ? undefined : editingBaseline.current ?? undefined);
      if (!isNew && Object.keys(payload).length === 0) {
        setEditingId(null); setNotice("No changes to save."); return;
      }
      const saved = await request<Task>(isNew ? "/tasks" : `/tasks/${editingId}`, {
        method: isNew ? "POST" : "PATCH", body: JSON.stringify(payload),
      });
      setTasks(current => isNew ? [saved, ...current] : current.map(item => item.id === saved.id ? saved : item));
      onTaskSaved?.(saved);
      setTaskRevision(value => value + 1);
      setEditingId(null); setNotice(isNew ? "Task created." : "Task updated.");
    } catch (value) { setError(errorMessage(value, "The task could not be saved.")); }
    finally { ++mutationVersion.current; mutationActive.current = false; setBusyId(""); }
  };
  const changeStatus = async (task: Task, requestedStatus?: Task["status"]) => {
    if (mutationActive.current) return;
    mutationActive.current = true;
    ++mutationVersion.current;
    setBusyId(task.id); setError(""); setNotice("");
    try {
      const updated = await request<Task>(`/tasks/${task.id}`, {
        method: "PATCH", body: JSON.stringify({ status: requestedStatus ?? nextTaskStatus(task) }),
      });
      setTasks(current => current.map(item => item.id === updated.id ? updated : item));
      onTaskSaved?.(updated);
      setTaskRevision(value => value + 1);
    } catch (value) { setError(errorMessage(value, "That task could not be updated.")); }
    finally { ++mutationVersion.current; mutationActive.current = false; setBusyId(""); }
  };

  return <section className="focus-card focus-task-collection" aria-labelledby="task-collection-heading">
    <div className="focus-task-heading">
      <div><span className="focus-eyebrow">PLAN AND FOLLOW THROUGH</span><h1 id="task-collection-heading">Tasks</h1><p>Everything you need to do, in one place.</p></div>
      <button type="button" className="focus-primary" onClick={() => begin()} disabled={Boolean(busyId)}><Plus size={17} /> New task</button>
    </div>
    <nav className="focus-task-views" aria-label="Task views">{views.map(([id, label]) =>
      <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
        {label}<span>{filterTasksForView(tasks, id, "", now).length}</span>
      </button>)}</nav>
    <PriorityOverview tasks={tasks} activeWorkspaceId={activeWorkspaceId} mode={priorityGuidanceMode} now={now}
      onEditTask={begin} onScheduleTask={onScheduleTask}
      onStartTask={task => { void changeStatus(task, "in_progress"); }}
      onCompleteTask={task => { void changeStatus(task, "done"); }}
      actionsBusy={Boolean(busyId)} taskRevision={taskRevision} />
    <label className="focus-task-search-label" htmlFor="focus-task-search">Search tasks</label>
    <input id="focus-task-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search all task titles and descriptions" />
    {error && <p className="focus-error" role="alert">{error} <button type="button" className="focus-text-button" onClick={() => void load()}>Reload</button></p>}
    {notice && <p role="status" className="focus-quiet-message">{notice}</p>}
    {editingId && <form className="focus-task-editor" onSubmit={event => void save(event)} aria-label={editingId === "new" ? "Create task" : "Edit task"}>
      <div className="focus-task-editor-heading"><h2>{editingId === "new" ? "New task" : "Edit task"}</h2><button type="button" aria-label="Close task editor" onClick={() => setEditingId(null)}><X size={17} /></button></div>
      <label htmlFor="task-editor-title">Task name</label>
      <input id="task-editor-title" autoFocus required maxLength={240} value={draft.title} onChange={event => setDraft(current => ({ ...current, title: event.target.value }))} placeholder="What needs to be done?" />
      <label htmlFor="task-editor-description">Notes (optional)</label>
      <textarea id="task-editor-description" rows={2} value={draft.description} onChange={event => setDraft(current => ({ ...current, description: event.target.value }))} placeholder="Context or next steps" />
      <div className="focus-task-editor-grid">
        <div><label htmlFor="task-editor-due">Due date and time (local)</label><input id="task-editor-due" type="datetime-local" value={draft.due} onChange={event => setDraft(current => ({ ...current, due: event.target.value }))} /></div>
        <div><label htmlFor="task-editor-status">Status</label><select id="task-editor-status" value={draft.status} onChange={event => setDraft(current => ({ ...current, status: event.target.value as Task["status"] }))}><option value="todo">To do</option><option value="in_progress">In progress</option><option value="blocked">Blocked</option><option value="done">Completed</option><option value="cancelled">Cancelled</option></select></div>
        <div><label htmlFor="task-editor-priority">Priority</label><select id="task-editor-priority" value={draft.priority} onChange={event => setDraft(current => ({ ...current, priority: event.target.value as Task["priority"] }))}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></div>
        <div><label htmlFor="task-editor-estimate">Estimated duration (minutes)</label><input id="task-editor-estimate" type="number" min="1" max="1440" step="1" value={draft.estimated_minutes} onChange={event => setDraft(current => ({ ...current, estimated_minutes: event.target.value }))} placeholder="Optional" /></div>
        <div><label htmlFor="task-editor-project">Project</label><select id="task-editor-project" value={draft.project_id} disabled={Boolean(projectError)} onChange={event => setDraft(current => ({ ...current, project_id: event.target.value }))}><option value="">No project</option>{draft.project_id && !projects.some(project => project.id === draft.project_id) && <option value={draft.project_id}>Current project (not loaded)</option>}{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div>
      </div>
      {projectError && <p role="alert" className="focus-error">Project choices unavailable: {projectError} Existing task links will be preserved. <button type="button" className="focus-text-button" onClick={() => void loadProjects()}>Retry projects</button></p>}
      <p className="focus-task-hint">Due times use your device timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}). Task reminders appear in Orin when enabled, up to 30 minutes before the deadline. Native device delivery is not guaranteed.</p>
      <div className="focus-task-editor-actions"><button type="button" className="focus-secondary" onClick={() => setEditingId(null)}>Cancel</button><button type="submit" className="focus-primary" disabled={Boolean(busyId) || !draft.title.trim()}>{busyId ? "Saving…" : "Save task"}</button></div>
    </form>}
    {loading ? <p role="status">Loading tasks…</p> : visibleTasks.length === 0 ?
      <div className="focus-task-empty"><h2>{tasks.length === 0 ? "No tasks yet" : "Nothing in this view"}</h2><p>{tasks.length === 0 ? "Create your first task to start planning." : "Try another view or search."}</p></div> :
      <ul className="focus-task-list">{visibleTasks.map(task => <li key={task.id}>
        <button type="button" className="focus-task-status" aria-label={`${task.status === "done" || task.status === "cancelled" ? "Reopen" : "Complete"} ${task.title}`} disabled={Boolean(busyId)} onClick={() => void changeStatus(task)}>{task.status === "done" || task.status === "cancelled" ? <RotateCcw size={16} /> : <Check size={16} />}</button>
        <div className="focus-task-row-content"><strong className={task.status === "done" ? "focus-task-done" : ""}>{task.title}</strong>
          <span>{task.project_id ? (onOpenProject && projects.some(project => project.id === task.project_id)
            ? <button type="button" className="focus-task-project-link"
                aria-label={`Open project ${projectNameFor(task.project_id)}`}
                onClick={() => onOpenProject(task.project_id!)}>{projectNameFor(task.project_id)}</button>
            : projectNameFor(task.project_id)) : "Personal"}
            {task.due_at ? ` · Due ${new Date(task.due_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : " · No due date"}
            {task.priority !== "normal" ? ` · ${task.priority} priority` : ""}
            {task.status !== "todo" ? ` · ${task.status.replace("_", " ")}` : ""}</span>
        </div>
        <div className="focus-task-row-actions">
          <button type="button" className="focus-task-schedule" aria-label={`Edit ${task.title}`} disabled={Boolean(busyId)} onClick={() => begin(task)}><Pencil size={15} /> Edit</button>
          {onScheduleTask && task.status !== "done" && task.status !== "cancelled" && <button type="button" className="focus-task-schedule" onClick={() => onScheduleTask(task.id)}>Calendar</button>}
        </div>
      </li>)}</ul>}
    <p className="focus-task-hint">{loading ? "Loading…" : `Showing ${visibleTasks.length} of ${tasks.length} tasks`}</p>
  </section>;
}
