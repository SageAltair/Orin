import { useState, type FormEvent } from "react";
import { Brain, SearchCheck } from "lucide-react";
import { request } from "./api";

type Missing = { findings: Array<{ kind: string; confidence: string; title: string; detail: string; suggested_action: string }>; changes_applied: false };
type Reflection = { period: string; accomplishments: Array<{ title: string }>; projects_advanced: Array<{ name: string }>; decisions: Array<{ title: string }>; reflection: string };
type BrainDump = { items: Array<{ text: string; kind: string; confidence: string }>; changes_applied: boolean; execution?: { status: string; completed_steps: number } };

export function IntelligenceReview() {
  const [missing, setMissing] = useState<Missing | null>(null); const [reflection, setReflection] = useState<Reflection | null>(null);
  const [dump, setDump] = useState(""); const [organized, setOrganized] = useState<BrainDump | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const loadMissing = async () => { setError(""); try { setMissing(await request<Missing>("/intelligence/missing")); } catch { setError("The workspace review could not be prepared."); } };
  const loadReflection = async (period: "daily" | "weekly") => { setError(""); try { setReflection(await request<Reflection>(`/intelligence/reflection?period=${period}`)); } catch { setError("The reflection could not be prepared."); } };
  const organize = async (event: FormEvent, execute = false) => { event.preventDefault(); setBusy(true); setError(""); try { setOrganized(await request<BrainDump>("/intelligence/brain-dump", { method: "POST", body: JSON.stringify({ text: dump, execute }) })); } catch { setError("The brain dump could not be organized."); } finally { setBusy(false); } };
  return <section className="intelligence-review" aria-label="Review and capture intelligence"><div className="intelligence-review-actions"><button onClick={() => void loadMissing()}><SearchCheck size={17} /><span><strong>What am I missing?</strong><small>Evidence-based gaps and dependencies</small></span></button><button onClick={() => void loadReflection("daily")}>Daily reflection</button><button onClick={() => void loadReflection("weekly")}>Weekly reflection</button></div>
    {error && <p className="api-error" role="alert">{error}</p>}
    {missing && <div className="review-results"><h3>Priority findings</h3>{missing.findings.length ? missing.findings.map(item => <article key={`${item.kind}-${item.title}`}><strong>{item.title}</strong><small>{item.confidence}</small><p>{item.detail}</p><p>{item.suggested_action}</p></article>) : <p>No evidence-backed gaps were found in the reviewed scope.</p>}</div>}
    {reflection && <div className="review-results"><h3>{reflection.period === "daily" ? "Daily" : "Weekly"} reflection</h3><p>{reflection.reflection}</p><p>{reflection.accomplishments.length} accomplishments · {reflection.projects_advanced.length} projects advanced · {reflection.decisions.length} decisions recorded</p></div>}
    <form className="brain-dump" onSubmit={event => void organize(event)}><label><Brain size={16} /> Brain dump<textarea required minLength={3} value={dump} onChange={event => setDump(event.target.value)} placeholder="I have an idea for a short film; call Daniel tomorrow; finish the website." /></label><button className="secondary-button" disabled={busy}>Organize without changing anything</button>{organized && !organized.changes_applied && <button className="primary-button" onClick={event => void organize(event, true)} disabled={busy}>Apply this plan</button>}</form>
    {organized && <div className="review-results"><h3>{organized.changes_applied ? "Applied items" : "Proposed items"}</h3>{organized.items.map((item, index) => <p key={`${index}-${item.text}`}><strong>{item.kind}:</strong> {item.text} <small>{item.confidence}</small></p>)}{organized.execution && <p>{organized.execution.completed_steps} step(s) completed · {organized.execution.status.replaceAll("_", " ")}</p>}</div>}
  </section>;
}
