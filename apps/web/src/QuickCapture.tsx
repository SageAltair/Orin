import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionIcon } from "./ActionIcon";
import { ApiError, request, type Task } from "./api";

export function QuickCapture({ onClose, onSaved }: { onClose: () => void; onSaved: (task: Task) => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    ) ?? []).filter(element => element.getClientRects().length > 0);
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (!elements.length) { event.preventDefault(); return; }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [onClose]);
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
    <section ref={dialogRef} className="quick-capture" role="dialog" aria-modal="true" aria-labelledby="quick-capture-title">
      <header><h2 id="quick-capture-title">{saved ? "Captured" : "Quick capture"}</h2><button type="button" aria-label="Close capture" onClick={onClose}><ActionIcon name="close" size={18} /></button></header>
      {saved ? <><p role="status">Saved to your Inbox. You can sort it out when you’re ready.</p><button type="button" className="primary-button" onClick={onClose}>Done</button></> : <form onSubmit={save}>
        <label htmlFor="quick-capture-text">What do you want to remember?</label>
        <textarea id="quick-capture-text" rows={4} maxLength={4000} value={text} onChange={event => setText(event.target.value)} placeholder="A task, an idea, or something to come back to…" />
        {error && <p role="alert" className="api-error">{error}</p>}
        <div><span>Save now. Organize later.</span><button type="submit" className="primary-button" disabled={busy || !text.trim()}>{busy ? "Saving…" : <><ActionIcon name="add" size={15} /> Capture</>}</button></div>
      </form>}
    </section>
  </div>;
}
