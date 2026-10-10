import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import { ApiError, request, type CalendarEvent, type Project, type Task, type TaskBlock } from "./api";

type View = "month" | "week" | "day" | "agenda";
type Draft = { id?: string; title: string; description: string; isAllDay: boolean; date: string; endDate: string; start: string; end: string; projectId: string; reminderMinutes: string };
const viewKey = "orin.calendar.view.v1";
const localZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const dateKeyForZone = (date: Date, zone: string) => new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
const fromKey = (key: string) => { const [year, month, day] = key.split("-").map(Number); return new Date(year, month - 1, day, 12); };
const addDays = (key: string, amount: number) => { const date = fromKey(key); date.setDate(date.getDate() + amount); return dateKey(date); };
const zoneDateTime = (date: Date, zone: string) => {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(date);
  const value = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`;
};
const instantFromZoneInput = (value: string, zone: string) => {
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  const requested = Date.UTC(year, month - 1, day, hour, minute);
  let guess = requested;
  for (let attempt = 0; attempt < 3; attempt++) {
    const represented = zoneDateTime(new Date(guess), zone);
    const [representedDate, representedTime] = represented.split("T");
    const [ry, rm, rd] = representedDate.split("-").map(Number);
    const [rh, rmin] = representedTime.split(":").map(Number);
    guess += requested - Date.UTC(ry, rm - 1, rd, rh, rmin);
  }
  const instant = new Date(guess);
  if (zoneDateTime(instant, zone) !== value) throw new Error("That local time does not exist because of a daylight saving change.");
  return instant.toISOString();
};
const eventStartDay = (event: CalendarEvent, zone: string) => event.is_all_day ? event.start_date! : new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(event.start_at!));
const eventEndDay = (event: CalendarEvent, zone: string) => event.is_all_day ? event.end_date! : new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(event.end_at!));
const minuteOfDay = (instant: string, zone: string) => { const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(instant)); const values = Object.fromEntries(parts.map(part => [part.type, part.value])); return Number(values.hour) * 60 + Number(values.minute); };
const formatDay = (key: string, options: Intl.DateTimeFormatOptions = { weekday: "long", month: "long", day: "numeric" }) => fromKey(key).toLocaleDateString(undefined, options);
const errorMessage = (error: unknown) => error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Could not load calendar events.";
const emptyDraft = (key: string): Draft => ({ title: "", description: "", isAllDay: false, date: key, endDate: key, start: `${key}T09:00`, end: `${key}T10:00`, projectId: "", reminderMinutes: "" });

export function CalendarWorkspace({ projects, scheduleTaskId, onTaskScheduled, onOpenTask }: { projects: Project[]; scheduleTaskId?: string | null; onTaskScheduled?: () => void; onOpenTask?: (taskId: string) => void }) {
  const [selectedDay, setSelectedDay] = useState(() => dateKeyForZone(new Date(), localZone()));
  const [month, setMonth] = useState(() => { const [year, month] = dateKeyForZone(new Date(), localZone()).split("-").map(Number); return new Date(year, month - 1, 1, 12); });
  const [view, setView] = useState<View>(() => { const saved = localStorage.getItem(viewKey); return saved === "week" || saved === "day" || saved === "agenda" ? saved : "month"; });
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [blocks, setBlocks] = useState<TaskBlock[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [searchText, setSearchText] = useState("");
  const [itemFilter, setItemFilter] = useState<"all" | "events" | "tasks">("all");
  const [projectFilter, setProjectFilter] = useState("");
  const [showCompleted, setShowCompleted] = useState(true);
  const [taskDraft, setTaskDraft] = useState<{ taskId: string; start: string; end: string; minutes: number; allowOverlap: boolean } | null>(null);
  const [zone, setZone] = useState(localZone);
  const [now, setNow] = useState(() => new Date());
  const dialogTrigger = useRef<HTMLElement | null>(null);
  const today = dateKeyForZone(new Date(), zone);
  const currentDay = dateKeyForZone(now, zone);
  const currentMinute = minuteOfDay(now.toISOString(), zone);
  const monthStartKey = dateKey(new Date(month.getFullYear(), month.getMonth(), 1, 12));
  const monthOffset = (fromKey(monthStartKey).getDay());
  const gridStart = addDays(monthStartKey, -monthOffset);
  const weekStart = addDays(selectedDay, -fromKey(selectedDay).getDay());
  const rangeStart = view === "month" ? gridStart : view === "week" ? weekStart : selectedDay;
  const rangeEnd = view === "month" ? addDays(gridStart, 41) : view === "week" ? addDays(weekStart, 6) : view === "agenda" ? addDays(selectedDay, 13) : selectedDay;

  useEffect(() => {
    request<{ timezone: string }>("/focus/settings", { headers: { "X-Timezone": localZone() } }).then(settings => {
      if (!settings.timezone || settings.timezone === zone) return;
      setZone(settings.timezone);
      const key = dateKeyForZone(new Date(), settings.timezone);
      setSelectedDay(key);
      const [year, month] = key.split("-").map(Number);
      setMonth(new Date(year, month - 1, 1, 12));
    }).catch(() => undefined);
  }, []);

  useEffect(() => { let active = true; setLoading(true); setError("");
    const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone });
    Promise.all([request<CalendarEvent[]>(`/calendar/events?${query}`), request<TaskBlock[]>(`/calendar/schedule?${query}`), request<Task[]>("/tasks?limit=100")])
      .then(([eventResult, blockResult, taskResult]) => { if (active) { setEvents(eventResult); setBlocks(blockResult); setTasks(taskResult); } })
      .catch(cause => { if (active) setError(errorMessage(cause)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [rangeStart, rangeEnd, zone]);
  useEffect(() => {
    if (view !== "day" && view !== "week") return;
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, [view]);
  useEffect(() => {
    if (!draft && !taskDraft) return;
    const previous = dialogTrigger.current;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? []);
    (dialog?.querySelector<HTMLElement>('input:not([type="checkbox"]), select, textarea') ?? focusable()[0])?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { setDraft(null); setTaskDraft(null); }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previous?.focus(); };
  }, [Boolean(draft), Boolean(taskDraft)]);
  const monthLabel = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const monthDays = useMemo(() => Array.from({ length: 42 }, (_, index) => addDays(gridStart, index)), [gridStart]);
  const openNew = (key: string, hour = 9, minute = 0) => { dialogTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setNotice(""); setError(""); const [year, month, day] = key.split("-").map(Number); const start = Date.UTC(year, month - 1, day, hour, minute); const toInput = (instant: number) => { const date = new Date(instant); return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}T${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`; }; const value = emptyDraft(key); value.start = toInput(start); value.end = toInput(start + 60 * 60_000); setDraft(value); };
  const openEdit = (event: CalendarEvent) => {
    dialogTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const start = event.is_all_day ? null : new Date(event.start_at!);
    const end = event.is_all_day ? null : new Date(event.end_at!);
    setNotice(""); setDraft({ id: event.id, title: event.title, description: event.description ?? "", isAllDay: event.is_all_day,
      date: event.is_all_day ? event.start_date! : dateKey(start!), endDate: event.is_all_day ? event.end_date! : dateKey(end!),
      start: start ? zoneDateTime(start, zone) : "", end: end ? zoneDateTime(end, zone) : "", projectId: event.project_id ?? "", reminderMinutes: event.reminder_minutes ? String(event.reminder_minutes) : "" });
  };
  const selectDate = (key: string) => { setSelectedDay(key); const date = fromKey(key); setMonth(new Date(date.getFullYear(), date.getMonth(), 1, 12)); };
  const save = async (formEvent: FormEvent) => {
    formEvent.preventDefault(); if (!draft) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const payload = draft.isAllDay
        ? { title: draft.title, description: draft.description || null, project_id: draft.projectId || null, is_all_day: true, start_date: draft.date, end_date: draft.endDate, start_at: null, end_at: null, timezone: zone, reminder_minutes: draft.reminderMinutes ? Number(draft.reminderMinutes) : null }
        : { title: draft.title, description: draft.description || null, project_id: draft.projectId || null, is_all_day: false, start_at: instantFromZoneInput(draft.start, zone), end_at: instantFromZoneInput(draft.end, zone), start_date: null, end_date: null, timezone: zone, reminder_minutes: draft.reminderMinutes ? Number(draft.reminderMinutes) : null };
      await request<CalendarEvent>(draft.id ? `/calendar/events/${draft.id}` : "/calendar/events", { method: draft.id ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setDraft(null); setNotice(draft.id ? "Event updated." : "Event saved.");
      const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone });
      setEvents(await request<CalendarEvent[]>(`/calendar/events?${query}`));
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!draft?.id || !window.confirm("Delete this event?")) return;
    setBusy(true); setError("");
    try { await request<void>(`/calendar/events/${draft.id}`, { method: "DELETE" }); setDraft(null); setNotice("Event deleted."); const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone }); setEvents(await request<CalendarEvent[]>(`/calendar/events?${query}`)); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const normalizedSearch = searchText.trim().toLocaleLowerCase();
  const visibleEvents = events.filter(event => itemFilter !== "tasks" && (!projectFilter || event.project_id === projectFilter) && (!normalizedSearch || `${event.title} ${event.description ?? ""} ${projects.find(project => project.id === event.project_id)?.name ?? ""}`.toLocaleLowerCase().includes(normalizedSearch)));
  const visibleBlocks = blocks.filter(block => itemFilter !== "events" && (showCompleted || block.status !== "done") && (!projectFilter || block.project_id === projectFilter) && (!normalizedSearch || `${block.title} ${block.description ?? ""} ${block.project_name ?? ""}`.toLocaleLowerCase().includes(normalizedSearch)));
  const hasFilters = Boolean(normalizedSearch || itemFilter !== "all" || projectFilter || !showCompleted);
  const dayEvents = (key: string) => visibleEvents.filter(event => eventStartDay(event, zone) <= key && eventEndDay(event, zone) >= key);
  const dayBlocks = (key: string) => visibleBlocks.filter(block => dateKeyForZone(new Date(block.start_at), zone) === key);
  const unscheduledTasks = tasks.filter(task => !["done", "cancelled"].includes(task.status) && !blocks.some(block => block.task_id === task.id));
  const openTaskBlock = useCallback((key: string, hour = 9, block?: TaskBlock, taskId?: string) => {
    dialogTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const start = block ? zoneDateTime(new Date(block.start_at), zone) : `${key}T${String(hour).padStart(2, "0")}:00`;
    const minutes = block?.estimated_minutes ?? 60;
    const [datePart, timePart] = start.split("T"); const [y, m, d] = datePart.split("-").map(Number); const [h, min] = timePart.split(":").map(Number);
    const endDate = new Date(Date.UTC(y, m - 1, d, h, min + minutes));
    const end = `${endDate.toISOString().slice(0, 10)}T${endDate.toISOString().slice(11, 16)}`;
    setError(""); setTaskDraft({ taskId: block?.task_id ?? taskId ?? "", start, end, minutes, allowOverlap: false });
  }, [zone]);
  useEffect(() => {
    if (!scheduleTaskId) return;
    openTaskBlock(selectedDay, 9, undefined, scheduleTaskId);
  }, [openTaskBlock, scheduleTaskId, selectedDay]);
  const saveTaskBlock = async (formEvent: FormEvent) => {
    formEvent.preventDefault(); if (!taskDraft?.taskId) { setError("Choose a task to schedule."); return; }
    setBusy(true); setError("");
    try {
      const payload = { start_at: instantFromZoneInput(taskDraft.start, zone), end_at: instantFromZoneInput(taskDraft.end, zone), estimated_minutes: taskDraft.minutes, timezone: zone, allow_overlap: taskDraft.allowOverlap };
      await request<TaskBlock>(`/calendar/tasks/${taskDraft.taskId}/schedule`, { method: "PUT", body: JSON.stringify(payload) });
      setTaskDraft(null); setNotice("Task scheduled."); onTaskScheduled?.();
      const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone });
      const [nextBlocks, nextTasks] = await Promise.all([request<TaskBlock[]>(`/calendar/schedule?${query}`), request<Task[]>("/tasks?limit=100")]); setBlocks(nextBlocks); setTasks(nextTasks);
    } catch (cause) {
      const message = errorMessage(cause); setError(message);
      if (cause instanceof ApiError && cause.status === 409 && taskDraft) setTaskDraft({ ...taskDraft, allowOverlap: true });
    } finally { setBusy(false); }
  };
  const unschedule = async (taskId: string) => {
    try { await request<void>(`/calendar/tasks/${taskId}/schedule`, { method: "DELETE" }); setNotice("Task removed from the calendar."); const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone }); const next = await request<TaskBlock[]>(`/calendar/schedule?${query}`); setBlocks(next); }
    catch (cause) { setError(errorMessage(cause)); }
  };
  const completeScheduled = async (block: TaskBlock) => {
    try { await request<Task>(`/tasks/${block.task_id}`, { method: "PATCH", body: JSON.stringify({ status: "done" }) }); setNotice("Task completed."); const query = new URLSearchParams({ start: rangeStart, end: rangeEnd, timezone: zone }); const [next, allTasks] = await Promise.all([request<TaskBlock[]>(`/calendar/schedule?${query}`), request<Task[]>("/tasks?limit=100")]); setBlocks(next); setTasks(allTasks); }
    catch (cause) { setError(errorMessage(cause)); }
  };
  const startTaskFocus = async (block: TaskBlock) => {
    try { await request("/focus-sessions", { method: "POST", body: JSON.stringify({ task_id: block.task_id, project_id: block.project_id, objective: block.title, duration_minutes: Math.min(480, Math.max(5, block.estimated_minutes)) }) }); setNotice("Focus session started."); window.dispatchEvent(new Event("orin:focus-updated")); }
    catch (cause) { setError(errorMessage(cause)); }
  };
  const movePeriod = (amount: number) => {
    if (view === "agenda" || view === "week") { selectDate(addDays(selectedDay, amount * 7)); return; }
    if (view === "day") { selectDate(addDays(selectedDay, amount)); return; }
    setMonth(current => new Date(current.getFullYear(), current.getMonth() + amount, 1, 12));
  };
  const chooseView = (value: View) => { setView(value); localStorage.setItem(viewKey, value); };
  const openToday = () => selectDate(today);
  const agendaKeys = Array.from({ length: 14 }, (_, index) => addDays(selectedDay, index));
  const weekKeys = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
  const dayIntervals = [
    ...dayEvents(selectedDay).filter(event => !event.is_all_day).map(event => [minuteOfDay(event.start_at!, zone), minuteOfDay(event.end_at!, zone)] as [number, number]),
    ...dayBlocks(selectedDay).map(block => [minuteOfDay(block.start_at, zone), minuteOfDay(block.end_at, zone)] as [number, number]),
  ].map(([start, end]) => [Math.max(8 * 60, start), Math.min(18 * 60, end)] as [number, number]).filter(([start, end]) => end > start).sort((a, b) => a[0] - b[0]);
  const freeGaps: string[] = [];
  let gapCursor = 8 * 60;
  for (const [start, end] of dayIntervals) { if (start > gapCursor) freeGaps.push(`${Math.floor((start - gapCursor) / 60)}h ${((start - gapCursor) % 60) || ""}${(start - gapCursor) % 60 ? "m" : ""} open before ${String(Math.floor(start / 60)).padStart(2, "0")}:${String(start % 60).padStart(2, "0")}`); gapCursor = Math.max(gapCursor, end); }
  if (gapCursor < 18 * 60) freeGaps.push(`${Math.floor((18 * 60 - gapCursor) / 60)}h ${(18 * 60 - gapCursor) % 60 ? `${(18 * 60 - gapCursor) % 60}m` : ""} open after ${String(Math.floor(gapCursor / 60)).padStart(2, "0")}:${String(gapCursor % 60).padStart(2, "0")}`);

  return <section className="calendar-workspace" aria-label="Calendar">
    <div className="calendar-toolbar">
      <div className="calendar-date-controls"><button type="button" className="secondary-button" onClick={openToday}>Today</button><button type="button" className="calendar-icon-button" aria-label={view === "month" ? "Previous month" : view === "day" ? "Previous day" : "Previous week"} onClick={() => movePeriod(-1)}><ChevronLeft size={17} /></button><button type="button" className="calendar-icon-button" aria-label={view === "month" ? "Next month" : view === "day" ? "Next day" : "Next week"} onClick={() => movePeriod(1)}><ChevronRight size={17} /></button><h2>{view === "month" ? monthLabel : view === "week" ? `${formatDay(weekStart, { month: "short", day: "numeric" })} â€“ ${formatDay(addDays(weekStart, 6), { month: "short", day: "numeric", year: "numeric" })}` : `${formatDay(selectedDay, { month: "long", year: "numeric" })}`}</h2><label className="calendar-date-jump"><span className="sr-only">Go to date</span><input aria-label="Go to date" type="date" value={selectedDay} onChange={event => { if (event.target.value) selectDate(event.target.value); }} /></label></div>
      <div className="calendar-toolbar-actions"><div className="calendar-view-switch" role="group" aria-label="Calendar view">{(["month", "week", "day", "agenda"] as const).map(item => <button type="button" key={item} aria-pressed={view === item} onClick={() => chooseView(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</div><button type="button" className="secondary-button" onClick={() => openTaskBlock(selectedDay)}><Plus size={14} /> Schedule task</button><button type="button" className="primary-button" onClick={() => openNew(selectedDay)}><Plus size={15} /> New event</button></div>
    </div>
    <details className="calendar-filters" open={hasFilters}>
      <summary><SlidersHorizontal size={14} /> Search and filters{hasFilters ? <span>Active</span> : null}</summary>
      <div className="calendar-filter-controls">
        <label className="calendar-search"><Search size={15} /><input type="search" aria-label="Search calendar" placeholder="Search titles, descriptions, projects" value={searchText} onChange={event => setSearchText(event.target.value)} /></label>
        <label>Show<select aria-label="Filter calendar items" value={itemFilter} onChange={event => setItemFilter(event.target.value as typeof itemFilter)}><option value="all">Events and tasks</option><option value="events">Events only</option><option value="tasks">Tasks only</option></select></label>
        <label>Project<select aria-label="Filter by project" value={projectFilter} onChange={event => setProjectFilter(event.target.value)}><option value="">All projects</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <label className="calendar-completed-filter"><input type="checkbox" checked={showCompleted} onChange={event => setShowCompleted(event.target.checked)} /> Include completed tasks</label>
        {hasFilters && <button type="button" className="text-action" onClick={() => { setSearchText(""); setItemFilter("all"); setProjectFilter(""); setShowCompleted(true); }}>Clear filters</button>}
      </div>
      {normalizedSearch && <p className="calendar-filter-summary" role="status">Searching loaded items for "{searchText.trim()}" in this date range. {visibleEvents.length + visibleBlocks.length} matches.</p>}
    </details>
    {error && <p className="api-error" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
    {loading && <p className="calendar-loading" role="status">Loading calendarâ€¦</p>}
    {view === "month" ? <div className="calendar-month" aria-label={monthLabel}>
      <div className="calendar-weekdays" aria-hidden="true">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => <span key={day}>{day}</span>)}</div>
      <div className="calendar-grid">{monthDays.map(key => { const items = dayEvents(key); const scheduled = dayBlocks(key); const total = items.length + scheduled.length; return <div key={key} className={`calendar-day ${fromKey(key).getMonth() !== month.getMonth() ? "outside-month" : ""} ${key === selectedDay ? "selected-day" : ""} ${key === today ? "current-day" : ""}`}>
        <button type="button" className="calendar-day-button" onClick={() => selectDate(key)} aria-label={`${formatDay(key)}, ${total} calendar items`} aria-pressed={key === selectedDay}><span className="calendar-day-number">{fromKey(key).getDate()}</span></button>{items.slice(0, 2).map(event => <button type="button" key={event.id} className={`calendar-event-chip ${event.is_all_day ? "all-day" : ""}`} onClick={() => openEdit(event)} aria-label={`Edit ${event.title}`}>{event.title}</button>)}{scheduled.slice(0, Math.max(0, 2 - items.length)).map(block => <button type="button" key={block.id} className="calendar-event-chip task-chip" onClick={() => openTaskBlock(key, 9, block)} aria-label={`Reschedule ${block.title}`}>{block.title}</button>)}{total > 2 && <span className="calendar-overflow">+{total - 2} more</span>}
      </div>; })}</div>
      <section className="calendar-selected-day"><div className="calendar-section-heading"><div><span className="eyebrow">SELECTED DAY</span><h3>{formatDay(selectedDay)}</h3></div><div className="calendar-day-actions"><button type="button" className="text-action" onClick={() => openTaskBlock(selectedDay)}><Plus size={14} /> Schedule task</button><button type="button" className="text-action" onClick={() => openNew(selectedDay)}><Plus size={14} /> Add event</button></div></div>{dayEvents(selectedDay).length || dayBlocks(selectedDay).length ? <div className="calendar-event-list">{dayEvents(selectedDay).map(event => <EventRow key={event.id} event={event} projectName={projects.find(project => project.id === event.project_id)?.name} zone={zone} onOpen={() => openEdit(event)} />)}{dayBlocks(selectedDay).map(block => <TaskBlockCard key={block.id} block={block} zone={zone} onOpenTask={() => onOpenTask?.(block.task_id)} onEdit={() => openTaskBlock(selectedDay, 9, block)} onRemove={() => void unschedule(block.task_id)} onComplete={() => void completeScheduled(block)} onFocus={() => void startTaskFocus(block)} />)}</div> : <p className="calendar-empty">Nothing planned for this day.</p>}</section>
    </div> : view === "week" ? <TimeSlice days={weekKeys} selectedDay={selectedDay} zone={zone} today={currentDay} currentMinute={currentMinute} events={visibleEvents} blocks={visibleBlocks} onSelectDay={setSelectedDay} onCreateEvent={openNew} onScheduleTask={(key, hour) => openTaskBlock(key, hour)} onOpenEvent={openEdit} onOpenTask={taskId => onOpenTask?.(taskId)} onFocusTask={block => void startTaskFocus(block)} onCompleteTask={block => void completeScheduled(block)} onEditTask={(key, block) => openTaskBlock(key, 9, block)} onRemoveTask={taskId => void unschedule(taskId)} /> : view === "day" ? <section className="calendar-day-view"><header className="calendar-day-summary"><div><span className="eyebrow">DAY SUMMARY</span><h3>{formatDay(selectedDay)}</h3></div><span>{dayEvents(selectedDay).length + dayBlocks(selectedDay).length} commitments</span></header><div className="calendar-free-time"><strong>Open time, 8 AM–6 PM</strong>{freeGaps.length ? <span>{freeGaps.join(" · ")}</span> : <span>No open gaps in this window.</span>}</div><TimeSlice days={[selectedDay]} selectedDay={selectedDay} zone={zone} today={currentDay} currentMinute={currentMinute} events={visibleEvents} blocks={visibleBlocks} onSelectDay={setSelectedDay} onCreateEvent={openNew} onScheduleTask={(key, hour) => openTaskBlock(key, hour)} onOpenEvent={openEdit} onOpenTask={taskId => onOpenTask?.(taskId)} onFocusTask={block => void startTaskFocus(block)} onCompleteTask={block => void completeScheduled(block)} onEditTask={(key, block) => openTaskBlock(key, 9, block)} onRemoveTask={taskId => void unschedule(taskId)} /><div className="calendar-day-actions"><button type="button" className="secondary-button" onClick={() => openNew(selectedDay)}>Add event</button><button type="button" className="secondary-button" onClick={() => openTaskBlock(selectedDay)}>Schedule task</button></div></section> : <div className="calendar-agenda">{agendaKeys.map(key => { const items = dayEvents(key); const scheduled = dayBlocks(key); return <section className="calendar-agenda-day" key={key}><h3>{formatDay(key)}</h3>{items.length || scheduled.length ? <div className="calendar-event-list">{items.map(event => <EventRow key={event.id} event={event} projectName={projects.find(project => project.id === event.project_id)?.name} zone={zone} onOpen={() => openEdit(event)} />)}{scheduled.map(block => <TaskBlockCard key={block.id} block={block} zone={zone} onOpenTask={() => onOpenTask?.(block.task_id)} onEdit={() => openTaskBlock(key, 9, block)} onRemove={() => void unschedule(block.task_id)} onComplete={() => void completeScheduled(block)} onFocus={() => void startTaskFocus(block)} />)}</div> : <p className="calendar-empty">No events</p>}</section>; })}</div>}    {draft && <div className="calendar-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) setDraft(null); }}><form className="calendar-dialog" role="dialog" aria-modal="true" aria-labelledby="calendar-dialog-title" onSubmit={save}>
      <div className="calendar-dialog-heading"><h2 id="calendar-dialog-title">{draft.id ? "Edit event" : "New event"}</h2><button type="button" className="calendar-icon-button" aria-label="Close event editor" onClick={() => setDraft(null)}><X size={17} /></button></div>
      {error && <p className="api-error" role="alert">{error}</p>}
      <label>Title<input autoFocus required maxLength={240} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label className="calendar-all-day"><input type="checkbox" checked={draft.isAllDay} onChange={event => setDraft({ ...draft, isAllDay: event.target.checked })} /> All-day</label>
      {draft.isAllDay ? <div className="calendar-form-row"><label>Starts<input type="date" required value={draft.date} onChange={event => setDraft({ ...draft, date: event.target.value })} /></label><label>Ends<input type="date" required value={draft.endDate} onChange={event => setDraft({ ...draft, endDate: event.target.value })} /></label></div> : <div className="calendar-form-row"><label>Starts<input type="datetime-local" required value={draft.start} onChange={event => setDraft({ ...draft, start: event.target.value })} /></label><label>Ends<input type="datetime-local" required value={draft.end} onChange={event => setDraft({ ...draft, end: event.target.value })} /></label></div>}
      <label>Project, optional<select value={draft.projectId} onChange={event => setDraft({ ...draft, projectId: event.target.value })}><option value="">No project</option>{projects.map(project => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
      <label>Description, optional<textarea rows={3} maxLength={10000} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
      <label>Reminder<select value={draft.reminderMinutes} onChange={event => setDraft({ ...draft, reminderMinutes: event.target.value })}><option value="">No reminder</option>{[5, 10, 15, 30, 60].map(minutes => <option key={minutes} value={minutes}>{minutes} minutes before</option>)}</select></label>
      <p className="calendar-timezone-note">Reminder preferences are saved with this event. Delivery is unavailable until a notification provider is configured.</p>
      <p className="calendar-timezone-note">Times use {zone}.</p>
      <div className="calendar-dialog-actions">{draft.id && <button type="button" className="secondary-button calendar-delete-button" disabled={busy} onClick={() => void remove()}>Delete</button>}<button type="button" className="secondary-button" disabled={busy} onClick={() => setDraft(null)}>Cancel</button><button type="submit" className="primary-button" disabled={busy}>{busy ? "Savingâ€¦" : "Save event"}</button></div>
    </form></div>}
    {taskDraft && <div className="calendar-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) setTaskDraft(null); }}><form className="calendar-dialog" role="dialog" aria-modal="true" aria-labelledby="task-block-title" onSubmit={saveTaskBlock}>
      <div className="calendar-dialog-heading"><h2 id="task-block-title">{blocks.some(block => block.task_id === taskDraft.taskId) ? "Reschedule task" : "Schedule a task"}</h2><button type="button" className="calendar-icon-button" aria-label="Close task scheduler" onClick={() => setTaskDraft(null)}><X size={17} /></button></div>
      {error && <p className="api-error" role="alert">{error}</p>}
      <label>Task<select required value={taskDraft.taskId} onChange={event => setTaskDraft({ ...taskDraft, taskId: event.target.value })}><option value="">Choose an open task</option>{[...unscheduledTasks, ...tasks.filter(task => task.id === taskDraft.taskId && !unscheduledTasks.some(open => open.id === task.id)), ...blocks.filter(block => block.task_id === taskDraft.taskId && !tasks.some(task => task.id === block.task_id)).map(block => ({ id: block.task_id, title: block.title, status: block.status, estimated_minutes: block.estimated_minutes } as Task))].map(task => <option key={task.id} value={task.id}>{task.title}</option>)}</select></label>
      <label>Starts<input type="datetime-local" required value={taskDraft.start} onChange={event => { const start = event.target.value; setTaskDraft({ ...taskDraft, start, end: start ? addMinutesToLocal(start, taskDraft.minutes) : "" }); }} /></label>
      <label>Duration in minutes<input type="number" min={1} max={1440} required value={taskDraft.minutes} onChange={event => { const minutes = Number(event.target.value); setTaskDraft({ ...taskDraft, minutes, end: addMinutesToLocal(taskDraft.start, minutes) }); }} /></label>
      <p className="calendar-timezone-note">Times use {zone}. Scheduling does not change task status or its due date.</p>
      <div className="calendar-dialog-actions"><button type="button" className="secondary-button" disabled={busy} onClick={() => setTaskDraft(null)}>Cancel</button><button type="submit" className="primary-button" disabled={busy || !taskDraft.taskId}>{taskDraft.allowOverlap ? "Keep overlap" : "Save schedule"}</button></div>
    </form></div>}
  </section>;
}

function addMinutesToLocal(value: string, minutes: number): string {
  if (!value) return "";
  const [datePart, timePart] = value.split("T"); const [year, month, day] = datePart.split("-").map(Number); const [hour, minute] = timePart.split(":").map(Number);
  const result = new Date(Date.UTC(year, month - 1, day, hour, minute + minutes));
  return `${result.toISOString().slice(0, 10)}T${result.toISOString().slice(11, 16)}`;
}

function TaskBlockCard({ block, zone, onEdit, onOpenTask, onRemove, onComplete, onFocus }: { block: TaskBlock; zone: string; onEdit: () => void; onOpenTask?: () => void; onRemove: () => void; onComplete: () => void; onFocus: () => void }) {
  const start = new Intl.DateTimeFormat(undefined, { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(new Date(block.start_at));
  const end = new Intl.DateTimeFormat(undefined, { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(new Date(block.end_at));
  return <article className={`calendar-task-block ${block.status === "done" ? "completed" : ""}`}><div className="calendar-task-block-time">{start}â€“{end}</div><div className="calendar-task-block-main"><button type="button" className="calendar-task-title" onClick={onOpenTask ?? onEdit}>{block.title}</button><small>{block.project_name ? `${block.project_name} Â· ` : ""}{block.estimated_minutes} min Â· Task</small></div><div className="calendar-task-actions">{block.status !== "done" && <><button type="button" onClick={onFocus}>Focus</button><button type="button" onClick={onComplete}>Complete</button></>}<button type="button" onClick={onEdit}>Reschedule</button><button type="button" onClick={onRemove}>Remove block</button></div></article>;
}

type TimeSliceProps = {
  days: string[]; selectedDay: string; zone: string; today: string; currentMinute: number;
  events: CalendarEvent[]; blocks: TaskBlock[];
  onSelectDay: (key: string) => void; onCreateEvent: (key: string, hour?: number, minute?: number) => void;
  onScheduleTask: (key: string, hour?: number) => void; onOpenEvent: (event: CalendarEvent) => void;
  onOpenTask: (taskId: string) => void; onFocusTask: (block: TaskBlock) => void;
  onCompleteTask: (block: TaskBlock) => void; onEditTask: (key: string, block: TaskBlock) => void;
  onRemoveTask: (taskId: string) => void;
};

function TimeSlice({ days, selectedDay, zone, today, currentMinute, events, blocks, onSelectDay, onCreateEvent, onScheduleTask, onOpenEvent, onOpenTask, onFocusTask, onCompleteTask, onEditTask, onRemoveTask }: TimeSliceProps) {
  const hours = Array.from({ length: 24 }, (_, hour) => hour);
  const dayItems = days.map(day => {
    const allDay = events.filter(event => event.is_all_day && eventStartDay(event, zone) <= day && eventEndDay(event, zone) >= day);
    const items: Array<{ kind: "event"; id: string; title: string; start: number; end: number; event: CalendarEvent; lane: number } | { kind: "task"; id: string; title: string; start: number; end: number; block: TaskBlock; lane: number }> = [];
    const interval = (startAt: string, endAt: string) => {
      const startDay = dateKeyForZone(new Date(startAt), zone);
      const endDay = dateKeyForZone(new Date(endAt), zone);
      if (startDay > day || endDay < day || (startDay < day && endDay === day && minuteOfDay(endAt, zone) === 0)) return null;
      return { start: startDay < day ? 0 : minuteOfDay(startAt, zone), end: endDay > day ? 1440 : minuteOfDay(endAt, zone) };
    };
    for (const event of events) {
      if (event.is_all_day || !event.start_at || !event.end_at) continue;
      const range = interval(event.start_at, event.end_at);
      if (range && range.end >= range.start) items.push({ kind: "event", id: event.id, title: event.title, ...range, event, lane: 0 });
    }
    for (const block of blocks) {
      const range = interval(block.start_at, block.end_at);
      if (range && range.end >= range.start) items.push({ kind: "task", id: block.id, title: block.title, ...range, block, lane: 0 });
    }
    items.sort((left, right) => left.start - right.start || (right.end - right.start) - (left.end - left.start));
    const laneEnds: number[] = [];
    for (const item of items) {
      let lane = laneEnds.findIndex(end => end <= item.start);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = item.end;
      item.lane = lane;
    }
    return { day, allDay, items, laneCount: Math.max(1, laneEnds.length) };
  });
  const dayLabel = (key: string) => formatDay(key, { weekday: "short", month: "short", day: "numeric" });
  const clockLabel = (minutes: number) => `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  return <section className={`calendar-time-slice ${days.length === 1 ? "single-day" : "week-slice"}`} style={{ "--calendar-days": days.length } as CSSProperties} aria-label={days.length === 1 ? `Time schedule for ${formatDay(days[0])}` : "Week time schedule"}>
    {days.length > 1 && <div className="calendar-mobile-day-switch" role="group" aria-label="Select day in week">{days.map(day => <button type="button" key={day} aria-pressed={selectedDay === day} onClick={() => onSelectDay(day)}><span>{formatDay(day, { weekday: "short" })}</span><strong>{fromKey(day).getDate()}</strong></button>)}</div>}
    <div className="calendar-time-header"><span aria-hidden="true" />{dayItems.map(({ day }) => <div className={`calendar-time-heading ${day === today ? "is-today" : ""}`} key={day}><button type="button" onClick={() => onSelectDay(day)} aria-pressed={selectedDay === day}>{dayLabel(day)}</button>{days.length > 1 && <button type="button" className="calendar-time-add-task" onClick={() => onScheduleTask(day, 9)} aria-label={`Schedule task on ${dayLabel(day)}`}>+ Task</button>}</div>)}</div>
    <div className="calendar-time-all-day"><strong>All day</strong>{dayItems.map(({ day, allDay }) => <div className={`calendar-time-all-day-cell ${day === selectedDay ? "selected-day" : ""}`} key={day}>{allDay.map(event => <button key={event.id} type="button" onClick={() => onOpenEvent(event)} title={event.title}>{event.title}</button>)}</div>)}</div>
    <div className="calendar-time-scroll"><div className="calendar-time-body">
      <div className="calendar-time-axis" aria-hidden="true">{hours.map(hour => <span key={hour}>{clockLabel(hour * 60)}</span>)}</div>
      <div className="calendar-time-columns">{dayItems.map(({ day, items, laneCount }) => <div className={`calendar-time-column ${day === selectedDay ? "selected-day" : ""}`} key={day}>
        {hours.map(hour => <button key={hour} type="button" className="calendar-time-slot" style={{ top: `${hour * 48}px` }} aria-label={`Create event on ${dayLabel(day)} at ${String(hour).padStart(2, "0")}:00`} onClick={event => { const halfHour = event.nativeEvent.offsetY >= 24 ? 30 : 0; onCreateEvent(day, hour, halfHour); }} />)}
        {day === today && <span className="calendar-current-time" style={{ top: `${currentMinute * 2}px` }} aria-label={`Current time ${clockLabel(currentMinute)}`} />}
        {items.map(item => {
          const style = { top: `${item.start * 2}px`, height: `${Math.max(30, (item.end - item.start) * 2)}px`, left: `calc(${item.lane * 100 / laneCount}% + 2px)`, width: `calc(${100 / laneCount}% - 4px)` };
          if (item.kind === "event") return <button key={`event-${item.id}`} className="calendar-time-item calendar-time-event" style={style} type="button" onClick={() => onOpenEvent(item.event)} title={item.title} aria-label={`${item.title}, ${clockLabel(item.start)} to ${clockLabel(item.end)}`}><small>{clockLabel(item.start)}–{clockLabel(item.end)}</small><strong>{item.title}</strong></button>;
          const block = item.block;
          return <article key={`task-${item.id}`} className={`calendar-time-item calendar-time-task ${block.status === "done" ? "completed" : ""}`} style={style}><button type="button" className="calendar-time-item-main" onClick={() => onOpenTask(block.task_id)} title={`Open task ${block.title}`}><small>{clockLabel(item.start)}–{clockLabel(item.end)}</small><strong>{block.title}</strong></button>{block.status !== "done" && <button type="button" className="calendar-time-focus" onClick={() => onFocusTask(block)} aria-label={`Focus on ${block.title}`}>Focus</button>}<details className="calendar-time-more"><summary aria-label={`More actions for ${block.title}`}>•••</summary><div><button type="button" onClick={() => onEditTask(day, block)}>Reschedule</button>{block.status !== "done" && <button type="button" onClick={() => onCompleteTask(block)}>Complete</button>}<button type="button" onClick={() => onRemoveTask(block.task_id)}>Remove block</button></div></details></article>;
        })}
      </div>)}</div>
    </div></div>
  </section>;
}

function EventRow({ event, projectName, zone, onOpen }: { event: CalendarEvent; projectName?: string; zone: string; onOpen: () => void }) {
  const time = event.is_all_day ? "All day" : new Intl.DateTimeFormat(undefined, { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(new Date(event.start_at!));
  const end = event.is_all_day ? "" : new Intl.DateTimeFormat(undefined, { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(new Date(event.end_at!));
  return <button type="button" className="calendar-event-row" onClick={onOpen}><span className="calendar-event-time">{time}{end && `â€“${end}`}</span><span className="calendar-event-body"><strong>{event.title}</strong><small>{projectName ? `${projectName} Â· ` : ""}{event.description || (event.is_all_day && event.start_date !== event.end_date ? `Through ${formatDay(event.end_date!, { month: "short", day: "numeric" })}` : "Event")}</small></span><ChevronRight size={15} /></button>;
}
