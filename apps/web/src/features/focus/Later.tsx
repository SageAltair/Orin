import { ArrowLeft } from "lucide-react";
import type { FocusTask } from "./types";

export function Later({ tasks, onBack, onChoose }: { tasks: FocusTask[]; onBack: () => void; onChoose: (task: FocusTask) => void }) {
  return <section className="focus-card focus-later" aria-labelledby="later-heading"><button type="button" className="focus-text-button focus-back" onClick={onBack}><ArrowLeft size={17} /> Back</button><span className="focus-eyebrow">LATER</span><h1 id="later-heading">When it feels right.</h1>
    {tasks.length ? <ul className="focus-later-list">{tasks.map(task => <li key={task.id}><button type="button" onClick={() => onChoose(task)}><span><strong>{task.title}</strong><small>{task.first_step || "No first step yet"}</small></span><span aria-hidden="true">Choose</span></button></li>)}</ul> : <p className="focus-calm-empty">Nothing waiting here. You can leave it that way.</p>}
  </section>;
}
