import { useEffect, useState } from "react";
import { ArrowDown, Check, Play, SkipForward } from "lucide-react";
import type { NowState } from "./types";

export function Now({ state, busy, onStart, onSmaller, onSwap, onCapture, onChooseEnergy, onComplete, reducedMotion, hideNumbers }: {
  state: NowState | null; busy: boolean; onStart: () => void; onSmaller: (step: string) => Promise<void>;
  onSwap: () => Promise<{ swapped: boolean; limit_reached: boolean; message?: string } | null>;
  onCapture: () => void; onChooseEnergy: () => void; onComplete: () => void; reducedMotion: boolean; hideNumbers: boolean;
}) {
  const [smallerOpen, setSmallerOpen] = useState(false);
  const [step, setStep] = useState("");
  const [message, setMessage] = useState("");
  const [remaining, setRemaining] = useState(1);
  const task = state?.task;
  const active = Boolean(state?.focus_session && state.focus_session.task_id === task?.id);
  useEffect(() => {
    const tick = () => {
      if (!state?.focus_session) { setRemaining(1); return; }
      const started = new Date(state.focus_session.started_at).getTime();
      const end = started + state.focus_session.duration_minutes * 60_000;
      setRemaining(Math.max(0, Math.min(1, (end - Date.now()) / (state.focus_session.duration_minutes * 60_000))));
    };
    tick(); const timer = window.setInterval(tick, 30_000); return () => window.clearInterval(timer);
  }, [state?.focus_session?.id, state?.focus_session?.started_at, state?.focus_session?.duration_minutes]);

  if (!task) return <section className="focus-card focus-now-empty" aria-labelledby="now-heading"><span className="focus-eyebrow">NOW</span><h1 id="now-heading">Nothing needs you right now.</h1><p>You can capture a thought or choose your energy when you’re ready.</p><div className="focus-action-row"><button className="focus-primary" onClick={onCapture}>Capture</button><button className="focus-secondary" onClick={onChooseEnergy}>Choose energy</button></div></section>;

  const swap = async () => { const result = await onSwap(); setMessage(result?.message ?? ""); };
  return <section className="focus-card focus-now" aria-labelledby="now-heading">
    <span className="focus-eyebrow">ONE SMALL STEP</span><h1 id="now-heading">{task.title}</h1>
    <div className="focus-first-step"><span>Smallest first step</span><p>{task.first_step || "Choose one small way to begin."}</p></div>
    {task.why && <p className="focus-why">{task.why}</p>}
    <div className="focus-timer" aria-label={active ? "Focus timer running" : "Focus timer ready"}>
      <div className="focus-timer-track" role="progressbar" aria-label="Focus time remaining" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remaining * 100)}><span style={{ width: `${remaining * 100}%`, transition: reducedMotion ? "none" : "width 1s ease" }} /></div>
      {!hideNumbers && <span className="focus-timer-label">{active ? `${Math.ceil((state!.focus_session!.duration_minutes * remaining))} min left` : `${task.estimated_minutes ?? 25} min, at your pace`}</span>}
    </div>
    <div className="focus-action-row focus-now-actions">
      <button className="focus-primary" onClick={active ? onComplete : onStart} disabled={busy}>{active ? <Check size={18} /> : <Play size={18} />}{active ? "Done" : "Start"}</button>
      {!active && <button className="focus-secondary" onClick={() => { setStep(task.first_step ?? ""); setSmallerOpen(value => !value); setMessage(""); }}><ArrowDown size={18} /> Smaller</button>}
      <button className="focus-secondary" onClick={() => void swap()} disabled={busy}><SkipForward size={18} /> Not now</button>
    </div>
    {smallerOpen && <form className="focus-smaller" onSubmit={async event => { event.preventDefault(); if (!step.trim()) return; await onSmaller(step.trim()); setSmallerOpen(false); }}><label htmlFor="smaller-step">What is a smaller first step?</label><input id="smaller-step" value={step} onChange={event => setStep(event.target.value)} /><button type="submit" className="focus-secondary">Save step</button></form>}
    {message && <p className="focus-quiet-message" role="status">{message}{message.includes("stay with") && <button type="button" className="focus-inline" onClick={() => setMessage("Rest is okay. Come back whenever you like.")}>Rest</button>}</p>}
  </section>;
}
