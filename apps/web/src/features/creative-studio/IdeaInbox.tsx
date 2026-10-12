import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { CreativeIdea } from "@orin/contracts";
import { createIdea, errorText, fetchIdeas, updateIdea } from "./studioApi";

type IdeaFilter = "active" | "archived";

export function IdeaInbox({ onOpenCanvas }: { onOpenCanvas?: (idea: CreativeIdea) => void }) {
  const [ideas, setIdeas] = useState<CreativeIdea[]>([]);
  const [filter, setFilter] = useState<IdeaFilter>("active");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async (status: IdeaFilter) => {
    try {
      setIdeas(await fetchIdeas(status));
      setError("");
    } catch (e) { setError(errorText(e)); }
  }, []);

  useEffect(() => { void refresh(filter); }, [filter, refresh]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setError("");
    try {
      const idea = await createIdea(value);
      setText("");
      setMessage("Idea captured.");
      setFilter("active");
      await refresh("active");
      setSelectedId(idea.id);
      setEditingText(idea.content ?? "");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  const select = (idea: CreativeIdea) => { setSelectedId(idea.id); setEditingText(idea.content ?? ""); setMessage(""); };
  const selected = ideas.find(idea => idea.id === selectedId) ?? null;

  const saveEdit = async () => {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const updated = await updateIdea(selected.id, editingText);
      setIdeas(current => current.map(item => item.id === updated.id ? updated : item));
      setMessage("Idea saved.");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <section className="studio-inbox" aria-label="Idea inbox">
      <header className="studio-inbox-header">
        <div>
          <span className="eyebrow">IDEA INBOX</span>
          <h2>Catch it before it slips</h2>
        </div>
        <div className="studio-inbox-filters" role="group" aria-label="Filter ideas">
          <button type="button" className={filter === "active" ? "active" : ""} onClick={() => setFilter("active")}>Active</button>
          <button type="button" className={filter === "archived" ? "active" : ""} onClick={() => setFilter("archived")}>Archived</button>
        </div>
      </header>
      <form className="studio-inbox-capture" onSubmit={submit}>
        <label htmlFor="studio-idea-input">New idea</label>
        <textarea id="studio-idea-input" value={text} onChange={e => setText(e.target.value)} placeholder="A line, a scene, a question…" rows={3} />
        <div className="studio-inbox-actions">
          <span role="status">{message}</span>
          <button type="submit" className="primary-button" disabled={busy || !text.trim()}>{busy ? "Saving…" : "Capture idea"}</button>
        </div>
        {error && <p className="api-error" role="alert">{error}</p>}
      </form>
      <nav className="studio-inbox-list" aria-label="Ideas">
        {ideas.map(idea => (
          <button key={idea.id} type="button" className={`studio-inbox-idea ${selectedId === idea.id ? "selected" : ""}`} onClick={() => select(idea)}>
            <strong>{idea.title}</strong>
            <span>{(idea.content ?? "").replace(/[#>*_`\[\]-]/g, " ").trim().slice(0, 80) || "No detail yet"}</span>
            <small>{idea.linked_document_ids.length ? `${idea.linked_document_ids.length} linked` : "Not linked"}</small>
          </button>
        ))}
        {!ideas.length && <p className="studio-empty">{filter === "active" ? "No active ideas yet." : "No archived ideas."}</p>}
      </nav>
      {selected && (
        <div className="studio-inbox-detail">
          <header>
            <h3>{selected.title}</h3>
            <button type="button" className="text-action" onClick={() => onOpenCanvas?.(selected)}>Open in canvas</button>
          </header>
          <textarea aria-label="Idea detail" value={editingText} onChange={e => setEditingText(e.target.value)} rows={6} />
          <div className="studio-inbox-actions">
            <span role="status">{message}</span>
            <button type="button" className="primary-button" onClick={() => void saveEdit()} disabled={busy || editingText === (selected.content ?? "")}>Save idea</button>
          </div>
        </div>
      )}
    </section>
  );
}
