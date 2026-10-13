import { useEffect, useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import { ApiError, request, type Task } from "../../api";
import { filterTasksForView, type TaskView } from "./taskViews";

const views: Array<[TaskView, string]> = [["all", "All"], ["inbox", "Inbox"], ["today", "Today"], ["upcoming", "Upcoming"], ["completed", "Completed"]];

export function TaskCollection({ onScheduleTask }: { onScheduleTask?: (taskId: string) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [view, setView] = useState<TaskView>("inbox");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true); setError("");
    try { setTasks(await request<Task[]>("/tasks?limit=100")); }
    catch (value) { setError(value instanceof ApiError ? value.message : "Tasks could not be loaded. Try again."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const visibleTasks = filterTasksForView(tasks, view, search);
  const changeStatus = async (task: Task) => {
    setBusyId(task.id); setError("");
    try {
      const updated = await request<Task>(`/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: task.status === "done" ? "todo" : "done" }) });
      setTasks(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (value) { setError(value instanceof ApiError ? value.message : "That task could not be updated. Try again."); }
    finally { setBusyId(""); }
  };
  return <section className="focus-card focus-task-collection" aria-labelledby="task-collection-heading">
    <span className="focus-eyebrow">YOUR TASKS</span><h1 id="task-collection-heading">Your tasks, in view.</h1>
    <nav className="focus-task-views" aria-label="Task views">{views.map(([id, label]) => <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>{label}<span>{filterTasksForView(tasks, id, "").length}</span></button>)}</nav>
    <label className="focus-task-search-label" htmlFor="focus-task-search">Search tasks</label><input id="focus-task-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search titles and descriptions" />
    {error && <p className="focus-error" role="alert">{error} <button type="button" className="focus-text-button" onClick={() => void load()}>Retry</button></p>}
    {loading ? <p role="status">Loading tasks…</p> : visibleTasks.length === 0 ? <div className="focus-task-empty"><h2>{tasks.length === 0 ? "No tasks yet" : `No ${view === "all" ? "matching" : view} tasks`}</h2><p>{view === "inbox" ? "New captures will be ready here whenever you need them." : view === "upcoming" ? "Tasks with real due dates will appear here." : view === "completed" ? "Finished work will stay searchable here." : "Try another view or search."}</p></div> : <ul className="focus-task-list">{visibleTasks.map(task => <li key={task.id}>
      <button type="button" className="focus-task-status" aria-label={`${task.status === "done" ? "Reopen" : "Complete"} ${task.title}`} disabled={busyId === task.id} onClick={() => void changeStatus(task)}>{task.status === "done" ? <RotateCcw size={16} /> : <Check size={16} />}</button>
      <div><strong className={task.status === "done" ? "focus-task-done" : ""}>{task.title}</strong><span>{task.project_id ? "Project task" : task.focus_state === "inbox" ? "Inbox" : task.focus_state === "active" ? "In progress" : task.status.replace("_", " ")}{task.due_at ? ` · Due ${new Date(task.due_at).toLocaleDateString()}` : ""}</span></div>
      {onScheduleTask && task.status !== "done" && task.status !== "cancelled" && <button type="button" className="focus-task-schedule" onClick={() => onScheduleTask(task.id)}>Schedule</button>}
    </li>)}</ul>}
  </section>;
}
