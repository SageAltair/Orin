import { useState, type FormEvent } from "react";
import { Check } from "lucide-react";
import { ApiError, request, type Project, type Task } from "../../api";
import { filterTasksForView, type TaskView } from "./taskViews";

export function LegacyTasks({ tasks, projects, onChange, onScheduleTask }: { tasks: Task[]; projects: Project[]; onChange: (tasks: Task[]) => void; onScheduleTask?: (taskId: string) => void }) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<TaskView>("all");
  const [search, setSearch] = useState("");
  const visibleTasks = filterTasksForView(tasks, view, search);
  const update = async (task: Task, patch: Partial<Pick<Task, "title" | "status" | "priority" | "due_at" | "project_id">>) => {
    setError("");
    try {
      const updated = await request<Task>(`/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify(patch) });
      onChange(tasks.map(item => item.id === updated.id ? updated : item));
    } catch (value) { setError(value instanceof ApiError ? value.message : "Unable to update this task. Try again."); }
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const task = await request<Task>("/tasks", { method: "POST", body: JSON.stringify({ title: title.trim() }) });
      onChange([task, ...tasks]); setTitle("");
    } catch (value) { setError(value instanceof ApiError ? value.message : "Unable to create this task. Try again."); }
    finally { setBusy(false); }
  };
  return <section aria-labelledby="legacy-tasks-heading">
    <div className="page-intro"><h2 id="legacy-tasks-heading">Tasks</h2><p>Capture work, choose what belongs today, and find completed tasks when you need them.</p></div>
    <form className="preference-controls" onSubmit={create}><label htmlFor="legacy-task-title">New task</label><input id="legacy-task-title" value={title} maxLength={240} onChange={event => setTitle(event.target.value)} /><button className="primary-button" disabled={busy || !title.trim()}>Add task</button></form>
    {error && <p role="alert" className="api-error">{error}</p>}
    <nav className="task-view-tabs" aria-label="Task views">{([ ["all", "All"], ["inbox", "Inbox"], ["today", "Today"], ["upcoming", "Upcoming"], ["completed", "Completed"] ] as const).map(([id, label]) => <button type="button" key={id} aria-pressed={view === id} onClick={() => setView(id)}>{label}{id !== "all" && <span>{filterTasksForView(tasks, id, "").length}</span>}</button>)}</nav>
    <label className="task-search-label" htmlFor="task-list-search">Search tasks</label><input className="task-list-search" id="task-list-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search titles and descriptions" />
    {visibleTasks.length === 0 ? <div className="empty-state"><h3>{tasks.length === 0 ? "No tasks yet" : `No ${view === "all" ? "matching" : view} tasks`}</h3><p>{tasks.length === 0 ? "Capture a task now and organize it later." : view === "inbox" ? "Your Inbox is clear. New captures will appear here." : view === "upcoming" ? "Tasks with real due dates will appear here." : view === "completed" ? "Completed tasks will stay searchable here." : "Try another search or task view."}</p></div> : <div className="data-list">{visibleTasks.map(task => <article id={`task-${task.id}`} className="data-row" key={task.id}>
      <button type="button" className={`complete-button ${task.status === "done" ? "done" : ""}`} aria-label={`${task.status === "done" ? "Reopen" : "Complete"} ${task.title}`} onClick={() => void update(task, { status: task.status === "done" ? "todo" : "done" })}>{task.status === "done" ? <Check size={15} /> : null}</button>
      <div className="data-main"><input className={`task-title ${task.status === "done" ? "task-done" : ""}`} aria-label={`Edit ${task.title}`} defaultValue={task.title} onBlur={event => { const value = event.currentTarget.value.trim(); if (value && value !== task.title) void update(task, { title: value }); }} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); }} /><small>{task.status.replace("_", " ")} · {task.priority}</small></div>
      {onScheduleTask && !["done", "cancelled"].includes(task.status) && <button type="button" className="secondary-button" onClick={() => onScheduleTask(task.id)}>Schedule</button>}
      <select aria-label={`Priority for ${task.title}`} value={task.priority} onChange={event => void update(task, { priority: event.target.value as Task["priority"] })}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select>
      <input aria-label={`Due date for ${task.title}`} type="date" value={task.due_at?.slice(0, 10) ?? ""} onChange={event => void update(task, { due_at: event.target.value ? new Date(`${event.target.value}T00:00:00`).toISOString() : null })} />
      <select aria-label={`Project for ${task.title}`} value={task.project_id ?? ""} onChange={event => void update(task, { project_id: event.target.value || null })}><option value="">No project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
    </article>)}</div>}
  </section>;
}
