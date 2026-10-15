import { useEffect, useState } from "react";
import { ArrowUpRight, Check, Sparkles, X } from "lucide-react";
import { request } from "./api";

type Briefing = { one_move: { task_id: string; title: string; first_step: string | null; reason: string; return_point: { next_action: string | null; stopped_at: string | null; blocker: string | null } | null } | null; findings: Array<{ kind: string; title: string; detail: string; suggested_prompt: string; evidence: Array<Record<string, unknown>> }>; progress: { completed_tasks: number; advanced_projects: string[] }; scope: { open_tasks_reviewed: number } };

export function ProactiveBriefing({ onOpenTask, onAsk }: { onOpenTask: (id: string) => void; onAsk: (prompt: string) => void }) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [dismissed, setDismissed] = useState<string[]>([]);
  useEffect(() => { void request<Briefing>("/intelligence/briefing").then(setBriefing).catch(() => setBriefing(null)); }, []);
  if (!briefing || (!briefing.one_move && !briefing.findings.length && !briefing.progress.completed_tasks)) return null;
  const findings = briefing.findings.filter(item => !dismissed.includes(item.kind));
  return <section className="proactive-briefing" aria-label="Orin intelligence briefing">
    {briefing.one_move && <article className="one-move-card"><span className="eyebrow"><Sparkles size={12} /> ONE USEFUL MOVE</span><h2>{briefing.one_move.title}</h2><p>{briefing.one_move.return_point?.next_action || briefing.one_move.first_step || "Open this task and choose the smallest concrete next step."}</p><small>{briefing.one_move.reason}</small><button className="primary-button" onClick={() => onOpenTask(briefing.one_move!.task_id)}>Start here <ArrowUpRight size={14} /></button></article>}
    {(briefing.progress.completed_tasks > 0 || briefing.progress.advanced_projects.length > 0) && <article className="progress-evidence"><Check size={17} /><div><strong>Progress from the last seven days</strong><p>{briefing.progress.completed_tasks} completed task{briefing.progress.completed_tasks === 1 ? "" : "s"}{briefing.progress.advanced_projects.length ? ` advanced ${briefing.progress.advanced_projects.join(", ")}` : ""}.</p></div></article>}
    {findings.length > 0 && <div className="proactive-findings">{findings.map(item => <article key={item.kind}><button className="toolbar-icon" aria-label={`Dismiss ${item.title}`} onClick={() => setDismissed(current => [...current, item.kind])}><X size={14} /></button><span className="eyebrow">{item.kind.replaceAll("_", " ")}</span><h3>{item.title}</h3><p>{item.detail}</p><button className="text-action" onClick={() => onAsk(item.suggested_prompt)}>Review with Orin <ArrowUpRight size={13} /></button></article>)}</div>}
  </section>;
}
