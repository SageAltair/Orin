import { useState } from "react";
import type { CloseState, DriftTrigger, FocusTask } from "./types";

const triggers: Array<{ value: DriftTrigger; label: string }> = [
  { value: "app", label: "An app" }, { value: "thought", label: "A thought" },
  { value: "emotion", label: "A feeling" }, { value: "person", label: "Someone" },
  { value: "tired", label: "Tired" }, { value: "other", label: "Something else" },
];

export function Close({ value, later, busy, onSave, onSkip }: { value: CloseState | null; later: FocusTask[]; busy: boolean; onSave: (input: { drift_triggers: DriftTrigger[]; tomorrow_task_id: string | null }) => void; onSkip: () => void }) {
  const [step, setStep] = useState(1);
  const [drifts, setDrifts] = useState<DriftTrigger[]>([]);
  const [tomorrow, setTomorrow] = useState("");
  const toggle = (trigger: DriftTrigger) => setDrifts(current => current.includes(trigger) ? current.filter(item => item !== trigger) : [...current, trigger]);
  return <section className="focus-card focus-close" aria-labelledby="close-heading"><span className="focus-eyebrow">CLOSE · {step} OF 3</span>
    {step === 1 && <><h1 id="close-heading">What did you do today?</h1><p>Done list first. One thing counts.</p>{value?.done_list.length ? <ul className="focus-done-list">{value.done_list.map(item => <li key={item.id}><span aria-hidden="true">✓</span>{item.title}</li>)}</ul> : <p className="focus-calm-empty">Nothing needs to be added. Rest counts too.</p>}<button className="focus-primary" type="button" onClick={() => setStep(2)}>Continue</button></>}
    {step === 2 && <><h1 id="close-heading">What pulled you away?</h1><p>Only if you want to notice.</p><div className="focus-trigger-grid">{triggers.map(trigger => <button key={trigger.value} type="button" className={drifts.includes(trigger.value) ? "selected" : ""} aria-pressed={drifts.includes(trigger.value)} onClick={() => toggle(trigger.value)}>{trigger.label}</button>)}</div><div className="focus-action-row"><button className="focus-secondary" type="button" onClick={() => setStep(1)}>Back</button><button className="focus-primary" type="button" onClick={() => setStep(3)}>Continue</button></div></>}
    {step === 3 && <><h1 id="close-heading">One thing for tomorrow?</h1><p>You can change this later.</p><label className="focus-field-label" htmlFor="tomorrow-task">Choose a task, or leave it blank</label><select id="tomorrow-task" value={tomorrow} onChange={event => setTomorrow(event.target.value)}><option value="">No task chosen</option>{later.map(task => <option value={task.id} key={task.id}>{task.title}</option>)}</select><p className="focus-quiet-message">A small step is enough. You can stop here.</p><div className="focus-action-row"><button className="focus-secondary" type="button" onClick={() => setStep(2)}>Back</button><button className="focus-primary" type="button" disabled={busy} onClick={() => onSave({ drift_triggers: drifts, tomorrow_task_id: tomorrow || null })}>Save and close</button></div></>}
    <button type="button" className="focus-text-button focus-skip-close" onClick={onSkip}>Skip for today</button>
  </section>;
}
