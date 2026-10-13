import { useEffect, useState } from "react";
import { request } from "../../api";
import type { FocusTask } from "./types";

type Progress = { completed_days: number; days_in_window: number; rest_day: boolean; gentle_nudge: boolean; reentry: { show: boolean }; drift_insights: { sample_size: number; triggers: Record<string, number> } | null };
type Meaning = { groups: Array<{ why: string; tasks: Array<{ task_id: string; title: string }> }> };

export function Recovery({ onBack, onChanged }: { onBack: () => void; onChanged: () => void }) {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [reviews, setReviews] = useState<FocusTask[]>([]);
  const [meaning, setMeaning] = useState<Meaning | null>(null);
  const [message, setMessage] = useState("");
  const [released, setReleased] = useState<{ id: string; title: string } | null>(null);
  const [prompts, setPrompts] = useState<Array<{ title: string; trigger: string; form: string }>>([]);
  const [smallSteps, setSmallSteps] = useState<Record<string, string>>({});
  const [contact, setContact] = useState("");
  const [contactConsent, setContactConsent] = useState(false);
  const [restDay, setRestDay] = useState("");
  const [interval, setInterval] = useState("");
  const [bodyDoubling, setBodyDoubling] = useState(false);
  const [routineName, setRoutineName] = useState("");
  const [routineTime, setRoutineTime] = useState("");

  const load = async () => {
    const [p, r, m, s, promptResult] = await Promise.all([
      request<Progress>("/focus/progress"), request<FocusTask[]>("/focus/review"),
      request<Meaning>("/focus/weekly-meaning"), request<Record<string, unknown>>("/focus/settings"),
      request<{ items: Array<{ title: string; trigger: string; form: string }> }>("/focus/prompts"),
    ]);
    setProgress(p); setReviews(r); setMeaning(m); setPrompts(promptResult.items);
    setRestDay(s.weekly_rest_day == null ? "" : String(s.weekly_rest_day));
    setInterval(s.check_in_interval == null ? "" : String(s.check_in_interval));
    setBodyDoubling(Boolean(s.body_doubling_enabled));
    setContact(typeof s.accountability_contact === "string" ? s.accountability_contact : "");
    const routines = Array.isArray(s.routines) ? s.routines as Array<{ name: string; time?: string | null }> : [];
    setRoutineName(routines[0]?.name ?? ""); setRoutineTime(routines[0]?.time ?? "");
  };
  useEffect(() => { void load().catch(() => setMessage("Recovery details are unavailable right now.")); }, []);

  const review = async (task: FocusTask, outcome: "keep" | "shrink" | "release") => {
    if (outcome === "release" && !window.confirm(`Release “${task.title}”? You can restore it from the task list later.`)) return;
    if (outcome === "shrink" && !smallSteps[task.id]?.trim()) { setMessage("Add a smaller first step first."); return; }
    try {
      await request(`/focus/review/${task.id}`, { method: "POST", body: JSON.stringify({ outcome, first_step: outcome === "shrink" ? smallSteps[task.id].trim() : undefined }) });
      if (outcome === "release") setReleased({ id: task.id, title: task.title });
      await load(); onChanged(); setMessage(outcome === "release" ? "Released. You can undo that below." : "Saved.");
    } catch { setMessage("Could not save that review. Please try again."); }
  };
  const savePreferences = async () => {
    if (contact.trim() && !contactConsent) { setMessage("Confirm you have permission before saving an accountability contact."); return; }
    try {
      await request("/focus/settings", { method: "PUT", body: JSON.stringify({ weekly_rest_day: restDay === "" ? null : Number(restDay), check_in_interval: interval === "" ? null : Number(interval), body_doubling_enabled: bodyDoubling, accountability_contact: contact.trim() || null, routines: routineName.trim() ? [{ name: routineName.trim(), time: routineTime || null }] : [] }) });
      setMessage("Preferences saved. Orin does not send reminders or contact anyone.");
    } catch { setMessage("Could not save preferences. Check the values and try again."); }
  };

  const exportPrivateData = async () => {
    try {
      const data = await request<Record<string, unknown>>("/focus/privacy/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "orin-focus-data.json"; link.click();
      URL.revokeObjectURL(url);
      setMessage("Your private focus data export is ready.");
    } catch { setMessage("Could not export your focus data. Please try again."); }
  };

  const deletePrivateData = async () => {
    if (!window.confirm("Delete your focus settings, daily plans, drift notes, and reflections? Your tasks and account will stay.")) return;
    try {
      await request<void>("/focus/privacy/data", { method: "DELETE" });
      await load(); onChanged();
      setMessage("Your focus settings, plans, drift notes, and reflections were deleted. Your tasks and account are still here.");
    } catch { setMessage("Could not delete your focus data. Please try again."); }
  };

  return <section className="focus-card focus-recovery" aria-labelledby="recovery-heading">
    <button type="button" className="focus-text-button" onClick={onBack}>Back to Now</button>
    <span className="focus-eyebrow">GENTLE REVIEW</span><h1 id="recovery-heading">A little room to reset.</h1>
    {released && <p className="focus-quiet-message" role="status">Released “{released.title}”. <button type="button" className="focus-inline" onClick={() => void request(`/focus/review/${released.id}/restore`, { method: "POST" }).then(() => { setReleased(null); return load(); }).then(onChanged).catch(() => setMessage("Could not restore that task."))}>Undo release</button></p>}
    {prompts.map((prompt, index) => <div className="focus-reentry" key={`${prompt.title}-${index}`}><strong>{prompt.title}</strong><p>{prompt.form === "start" ? `When ${prompt.trigger}, take one small step.` : `If you have a moment, begin ${prompt.trigger.toLowerCase()}.`}</p></div>)}
    <section aria-label="Completion summary"><h2>Your last seven days</h2><p>{progress ? `${progress.completed_days} of 7 days included a completed task.` : "Loading…"}</p>{progress?.rest_day && <p className="focus-quiet-message">Today is your chosen rest day.</p>}{progress?.gentle_nudge && <p className="focus-quiet-message">Welcome back. Choose one small thing, or take more time.</p>}</section>
    {progress?.reentry.show && <section className="focus-reentry"><h2>Welcome back.</h2><p>Your tasks are still here. Start with what feels useful today.</p><button type="button" className="focus-secondary" onClick={() => void request("/focus/reentry/dismiss", { method: "POST" }).then(() => load())}>Continue</button></section>}
    <section><h2>Tasks to review</h2>{reviews.length ? reviews.map(task => <article className="focus-review-item" key={task.id}><strong>{task.title}</strong><div className="focus-action-row"><button type="button" className="focus-secondary" onClick={() => void review(task, "keep")}>Keep</button><button type="button" className="focus-secondary" onClick={() => setSmallSteps(current => ({ ...current, [task.id]: task.first_step ?? "" }))}>Shrink</button><button type="button" className="focus-secondary" onClick={() => void review(task, "release")}>Release</button></div>{smallSteps[task.id] !== undefined && <div><label className="focus-field-label" htmlFor={`shrink-${task.id}`}>A smaller step</label><input id={`shrink-${task.id}`} value={smallSteps[task.id]} onChange={event => setSmallSteps(current => ({ ...current, [task.id]: event.target.value }))} /><button type="button" className="focus-text-button" onClick={() => void review(task, "shrink")}>Save smaller step</button></div>}</article>) : <p className="focus-calm-empty">No tasks need a review right now.</p>}</section>
    <section><h2>Meaning this week</h2>{meaning?.groups.length ? meaning.groups.map(group => <p key={group.why}><strong>{group.why}</strong> · {group.tasks.map(task => task.title).join(", ")}</p>) : <p className="focus-calm-empty">No completed tasks to review yet. This is optional.</p>}</section>
    <details className="focus-settings"><summary>Routines and preferences</summary>
      <label>Weekly rest day<select value={restDay} onChange={event => setRestDay(event.target.value)}><option value="">No set day</option>{["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
      <label>Focus check-in<select value={interval} onChange={event => setInterval(event.target.value)}><option value="">Off</option>{[15, 25, 30, 45, 60, 90, 120].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label>
      <label>If-then routine name<input value={routineName} onChange={event => setRoutineName(event.target.value)} placeholder="After my morning coffee" /></label>
      {routineName && <label>Usual time<input type="time" value={routineTime} onChange={event => setRoutineTime(event.target.value)} /></label>}
      <label className="focus-toggle"><input type="checkbox" checked={bodyDoubling} onChange={event => setBodyDoubling(event.target.checked)} /> Body doubling preference (no session service is connected)</label>
      <label>Accountability contact (optional)<input value={contact} onChange={event => setContact(event.target.value)} placeholder="Name or contact" /></label>
      {contact && <label className="focus-toggle"><input type="checkbox" checked={contactConsent} onChange={event => setContactConsent(event.target.checked)} /> I have this person's permission to store their contact</label>}
      <p className="focus-quiet-message">No notifications or messages are sent. Routine prompts appear only while Orin is open and outside quiet hours.</p>
      <button type="button" className="focus-primary" onClick={() => void savePreferences()}>Save preferences</button>
    </details>
    <details className="focus-settings"><summary>Your private focus data</summary>
      <p>Export or delete your energy settings, daily plans, drift notes, and reflections. Deleting them does not delete your tasks or account.</p>
      <div className="focus-action-row"><button type="button" className="focus-secondary" onClick={() => void exportPrivateData()}>Export my focus data</button><button type="button" className="focus-secondary" onClick={() => void deletePrivateData()}>Delete my focus data</button></div>
    </details>
    {progress?.drift_insights && <p className="focus-quiet-message">Optional drift patterns from {progress.drift_insights.sample_size} recent check-ins are available in your private focus data.</p>}
    {message && <p className="focus-quiet-message" role="status">{message}</p>}
  </section>;
}
