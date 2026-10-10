import { useEffect, useState } from "react";
import { ArrowDown, Check, Play, SkipForward } from "lucide-react";
import type { NowState } from "./types";

export function Now({ state, busy, onStart, onSmaller, onSuggestSmaller, onSwap, onCapture, onComplete, onLogDrift, onRecovery, checkInInterval, reducedMotion, hideNumbers }: {
  state: NowState | null; busy: boolean; onStart: () => void; onSmaller: (step: string) => Promise<void>;
  onSuggestSmaller: () => Promise<string | null>;
  onSwap: () => Promise<{ swapped: boolean; limit_reached: boolean; message?: string } | null>;
  onCapture: () => void; onComplete: () => void; onLogDrift: (trigger: "app" | "thought" | "emotion" | "person" | "tired" | "other") => Promise<void>; onRecovery: () => void; checkInInterval: number | null; reducedMotion: boolean; hideNumbers: boolean;
}) {
  const [smallerOpen, setSmallerOpen] = useState(false);
  const [step, setStep] = useState("");
  const [message, setMessage] = useState("");
  const [remaining, setRemaining] = useState(1);
  const [elapsedMinutes, setElapsedMinutes] = useState(0);
  const [checkInDismissedAt, setCheckInDismissedAt] = useState(0);
  const task = state?.task;
  const active = Boolean(state?.focus_session && state.focus_session.task_id === task?.id);
  useEffect(() => {
    const tick = () => {
      if (!state?.focus_session) { setRemaining(1); return; }
      const started = new Date(state.focus_session.started_at).getTime();
      const end = started + state.focus_session.duration_minutes * 60_000;
      setElapsedMinutes(Math.max(0, Math.floor((Date.now() - started) / 60_000)));
      setRemaining(Math.max(0, Math.min(1, (end - Date.now()) / (state.focus_session.duration_minutes * 60_000))));
    };
    tick(); const timer = window.setInterval(tick, 30_000); return () => window.clearInterval(timer);
  }, [state?.focus_session?.id, state?.focus_session?.started_at, state?.focus_session?.duration_minutes]);

  if (!task) return <section className="focus-card focus-now-empty" aria-labelledby="now-heading"><span className="focus-eyebrow">START HERE</span><h1 id="now-heading">What’s one thing on your mind?</h1><p>Add a task, a worry, or an idea. Orin will keep it safe. Then you can start with one small step.</p><button className="focus-primary" type="button" onClick={onCapture}>Add one thing</button><details className="focus-settings"><summary>What happens next?</summary><p>Write anything and save it. Your task will appear here. Press <strong>Start</strong> when you’re ready; you can change or pause your plan at any time.</p><button type="button" className="focus-text-button" onClick={onRecovery}>Progress and task review</button><a className="focus-text-link" href="/focus-help.html">Read the short guide</a></details></section>;

  const swap = async () => { const result = await onSwap(); setMessage(result?.message ?? ""); };
  const suggestSmaller = async () => {
    const suggestion = await onSuggestSmaller();
    if (suggestion) { setStep(suggestion); setMessage("Suggestion ready to edit. You can also write your own step."); }
    else setMessage("A suggestion is unavailable. You can still write a smaller step yourself.");
  };
  if (active) return <section className="focus-card focus-mode" aria-labelledby="focus-mode-heading">
    <span className="focus-eyebrow">FOCUS MODE</span><h1 id="focus-mode-heading">{task.title}</h1>
    <div className="focus-first-step"><span>Next small step</span><p>{task.first_step || "Choose one small way to begin."}</p></div>
    <div className="focus-timer" aria-label="Focus timer"><div className="focus-timer-track" role="progressbar" aria-label="Focus time remaining" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remaining * 100)}><span style={{ width: `${remaining * 100}%`, transition: reducedMotion ? "none" : "width 1s ease" }} /></div>{!hideNumbers && <span className="focus-timer-label" role="status" aria-live="polite">{Math.ceil(state!.focus_session!.duration_minutes * remaining)} min left</span>}</div>
    {checkInInterval && elapsedMinutes >= checkInInterval && elapsedMinutes - checkInDismissedAt >= checkInInterval && <div className="focus-checkin" role="group" aria-label="Optional focus check-in"><p>Still feel okay to continue?</p><button type="button" className="focus-text-button" onClick={() => setCheckInDismissedAt(elapsedMinutes)}>Keep going</button><div className="focus-trigger-grid">{(["app", "thought", "emotion", "person", "tired", "other"] as const).map(trigger => <button key={trigger} type="button" onClick={() => { void onLogDrift(trigger); setCheckInDismissedAt(elapsedMinutes); }}>I drifted: {trigger}</button>)}</div><p>Choose any reason, then return to your step.</p></div>}
    <div className="focus-action-row"><button type="button" className="focus-primary" onClick={onComplete} disabled={busy}><Check size={18} /> Done</button><button type="button" className="focus-secondary" onClick={onCapture}>Capture</button></div>
  </section>;
  return <section className="focus-card focus-now" aria-labelledby="now-heading">
    <span className="focus-eyebrow">ONE SMALL STEP</span><h1 id="now-heading">{task.title}</h1>
    <div className="focus-first-step"><span>Smallest first step</span><p>{task.first_step || "Choose one small way to begin."}</p></div>
    {task.why && <p className="focus-why">{task.why}</p>}
    <div className="focus-timer" aria-label={active ? "Focus timer running" : "Focus timer ready"}>
      <div className="focus-timer-track" role="progressbar" aria-label="Focus time remaining" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remaining * 100)}><span style={{ width: `${remaining * 100}%`, transition: reducedMotion ? "none" : "width 1s ease" }} /></div>
      {!hideNumbers && <span className="focus-timer-label" role="status" aria-live="polite">{active ? `${Math.ceil((state!.focus_session!.duration_minutes * remaining))} min left` : `${task.estimated_minutes ?? 25} min, at your pace`}</span>}
    </div>
    <div className="focus-action-row focus-now-actions">
      <button className="focus-primary" onClick={active ? onComplete : onStart} disabled={busy}>{active ? <Check size={18} /> : <Play size={18} />}{active ? "Done" : "Start"}</button>
      {!active && <button className="focus-secondary" onClick={() => { setStep(task.first_step ?? ""); setSmallerOpen(value => !value); setMessage(""); }}><ArrowDown size={18} /> Smaller</button>}
      <button className="focus-secondary" onClick={() => void swap()} disabled={busy}><SkipForward size={18} /> Not now</button>
    </div>
    <p className="focus-guidance">Start when you’re ready. <strong>Smaller</strong> makes the first step easier; <strong>Not now</strong> finds another task.</p>
    <button type="button" className="focus-text-button" onClick={onRecovery}>Progress and task review</button>
    <a className="focus-text-link" href="/focus-help.html">Read the short guide</a>
    {smallerOpen && <form className="focus-smaller" onSubmit={async event => { event.preventDefault(); if (!step.trim()) return; await onSmaller(step.trim()); setSmallerOpen(false); }}><label htmlFor="smaller-step">What is a smaller first step?</label><input id="smaller-step" value={step} onChange={event => setStep(event.target.value)} /><div className="focus-action-row"><button type="button" className="focus-text-button" onClick={() => void suggestSmaller()}>Suggest a smaller step</button><button type="submit" className="focus-secondary" disabled={!step.trim()}>Save step</button></div></form>}
    {message && <p className="focus-quiet-message" role="status" aria-live="polite">{message}{message.includes("stay with") && <button type="button" className="focus-inline" onClick={() => setMessage("Rest is okay. Come back whenever you like.")}>Rest</button>}</p>}
  </section>;
}
