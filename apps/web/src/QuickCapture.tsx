import { useEffect, useState, type FormEvent } from "react";
import { Plus, X } from "lucide-react";
import { ApiError, request, type Task } from "./api";

export function QuickCapture({ onClose, onSaved }: { onClose: () => void; onSaved: (task: Task) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => { const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", closeOnEscape); return () => window.removeEventListener("keydown", closeOnEscape); }, [onClose]);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const task = await request<Task>("/focus/capture", { method: "POST", body: JSON.stringify({ title: text.trim() }) });
      onSaved(task); setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save this capture. Please try again.");
    } finally { setBusy(false); }
  };
  return <div className="quick-capture-scrim" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="quick-capture" role="dialog" aria-modal="true" aria-labelledby="quick-capture-title">
      <header><h2 id="quick-capture-title">{saved ? "Captured" : "Quick capture"}</h2><button type="button" aria-label="Close capture" onClick={onClose}><X size={18} /></button></header>
      {saved ? <><p role="status">Saved to your Inbox. You can sort it out when you’re ready.</p><button type="button" className="primary-button" onClick={onClose}>Done</button></> : <form onSubmit={save}>
        <label htmlFor="quick-capture-text">What do you want to remember?</label>
        <textarea id="quick-capture-text" autoFocus rows={4} maxLength={4000} value={text} onChange={event => setText(event.target.value)} placeholder="A task, an idea, or something to come back to…" />
        {error && <p role="alert" className="api-error">{error}</p>}
        <div><span>Save now. Organize later.</span><button type="submit" className="primary-button" disabled={busy || !text.trim()}>{busy ? "Saving…" : <><Plus size={15} /> Capture</>}</button></div>
      </form>}
    </section>
  </div>;
}
