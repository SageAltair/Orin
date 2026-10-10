import { ArrowDown, ArrowUp, ChevronDown } from "lucide-react";
import type { FocusTask, TodayPlan, Energy } from "./types";

const energies: Array<{ value: Energy; label: string; note: string }> = [
  { value: "low", label: "Low", note: "Keep it gentle" },
  { value: "medium", label: "Medium", note: "A steady pace" },
  { value: "high", label: "High", note: "More room today" },
];

export function TodaysThree({ plan, later, onEnergy, onReplace, onOpenLater, onSettings, onSkipEnergy, onScheduleTask }: {
  plan: TodayPlan | null; later: FocusTask[]; onEnergy: (energy: Energy) => void;
  onReplace: (tasks: Array<{ task_id: string; is_anchor: boolean }>) => void;
  onOpenLater: () => void; onSettings: () => void; onSkipEnergy: () => void; onScheduleTask?: (taskId: string) => void;
}) {
  const tasks = plan?.tasks ?? [];
  const move = (index: number, delta: number) => {
    const next = [...tasks]; const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onReplace(next.map(task => ({ task_id: task.id, is_anchor: task.is_anchor ?? false })));
  };
  const replace = (index: number, task: FocusTask) => {
    const next = [...tasks]; next[index] = { ...task, is_anchor: tasks[index].is_anchor };
    onReplace(next.map(item => ({ task_id: item.id, is_anchor: item.is_anchor ?? false })));
  };
  return <section className="focus-card focus-today" aria-labelledby="today-heading">
    <span className="focus-eyebrow">TODAY</span><h1 id="today-heading">A good day = one thing.</h1>
    <p>Choose the energy you have. You can change this any time.</p>
    <div className="focus-energy-picker" role="group" aria-label="Choose today's energy">
      {energies.map(energy => <button type="button" key={energy.value} className={`focus-energy ${plan?.energy_level === energy.value ? "selected" : ""}`} aria-pressed={plan?.energy_level === energy.value} onClick={() => onEnergy(energy.value)}><strong>{energy.label}</strong><small>{energy.note}</small></button>)}
    </div>
    <button className="focus-text-button" type="button" onClick={onSkipEnergy}>Skip for now</button>
    <h2>Today's three</h2>
    {tasks.length ? <ol className="focus-plan-list">{tasks.map((task, index) => <li key={task.id} className="focus-plan-item"><div><strong>{task.title}</strong>{task.is_anchor && <span className="focus-anchor">Anchor</span>}<small>{task.first_step || "One small step"}</small></div><div className="focus-order-actions"><button type="button" aria-label={`Move ${task.title} up`} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={17} /></button><button type="button" aria-label={`Move ${task.title} down`} disabled={index === tasks.length - 1} onClick={() => move(index, 1)}><ArrowDown size={17} /></button></div><label className="focus-replace"><span className="sr-only">Replace {task.title} from Later</span><select value="" aria-label={`Replace ${task.title} from Later`} onChange={event => { const picked = later.find(item => item.id === event.target.value); if (picked) replace(index, picked); }}><option value="">Replace</option>{later.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>{onScheduleTask && <button type="button" className="focus-text-button" onClick={() => onScheduleTask(task.id)}>Schedule</button>}</li>)}</ol> : <p className="focus-calm-empty">Nothing selected yet. You can leave this empty.</p>}
    <button className="focus-later-toggle" type="button" onClick={onOpenLater}><ChevronDown size={18} /> Browse Later</button>
    <details className="focus-settings"><summary>Settings</summary><p>Reminders are not delivered yet. No reminders are being sent.</p><button type="button" className="focus-text-button" onClick={onSettings}>Appearance and focus options</button></details>
  </section>;
}
