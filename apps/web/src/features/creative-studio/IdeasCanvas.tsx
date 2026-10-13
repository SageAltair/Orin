import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  CreativeIdea,
  IdeaLinkType,
  KnowledgeDocumentRecord,
} from "@orin/contracts";
import { ApiError, request } from "../../api";
import {
  createIdea,
  errorText,
  fetchIdeaLinks,
  fetchIdeas,
  linkIdeaToDocument,
  suggestIdeas,
  unlinkIdeaFromDocument,
  updateIdea,
  type StudioSuggestion,
} from "./studioApi";

interface IdeaLinkView {
  idea_id: string;
  document_id: string;
  link_type: IdeaLinkType;
  note: string | null;
}

export function IdeasCanvas({
  documents,
  onCreated,
}: {
  documents?: KnowledgeDocumentRecord[];
  onCreated?: (idea: CreativeIdea) => void;
}) {
  const [fetchedDocuments, setFetchedDocuments] = useState<
    KnowledgeDocumentRecord[]
  >([]);
  const availableDocuments = documents ?? fetchedDocuments;
  const [ideas, setIdeas] = useState<CreativeIdea[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [links, setLinks] = useState<IdeaLinkView[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [targetDocumentId, setTargetDocumentId] = useState("");
  const [linkType, setLinkType] = useState<IdeaLinkType>("inspires");
  const [suggestions, setSuggestions] = useState<StudioSuggestion[]>([]);

  const refresh = useCallback(async () => {
    try {
      setIdeas(await fetchIdeas("active"));
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (documents) return;
    let cancelled = false;
    void request<KnowledgeDocumentRecord[]>("/knowledge/documents")
      .then((rows) => {
        if (!cancelled) setFetchedDocuments(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [documents]);

  const runSuggestions = () =>
    setSuggestions(suggestIdeas(text || selected?.content || ""));
  const applySuggestion = (prompt: string) => {
    setText((current) =>
      current.trim() ? `${current.trimEnd()}\n\n${prompt}\n` : `${prompt}\n`,
    );
    setMessage("Prompt added to your idea.");
  };

  const selected = useMemo(
    () => ideas.find((idea) => idea.id === selectedId) ?? null,
    [ideas, selectedId],
  );

  useEffect(() => {
    if (!selected) {
      setLinks([]);
      return;
    }
    let cancelled = false;
    void fetchIdeaLinks(selected.id)
      .then((rows) => {
        if (!cancelled) setLinks(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e));
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    if (selected) setText(selected.content ?? "");
  }, [selected]);

  const capture = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const idea = await createIdea(text.trim());
      setText("");
      setMessage("Idea captured.");
      await refresh();
      setSelectedId(idea.id);
      onCreated?.(idea);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await updateIdea(selected.id, text);
      setIdeas((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setMessage("Idea saved.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const connect = async () => {
    if (!selected || !targetDocumentId) return;
    setBusy(true);
    setError("");
    try {
      await linkIdeaToDocument(selected.id, targetDocumentId, linkType);
      setLinks(await fetchIdeaLinks(selected.id));
      setTargetDocumentId("");
      setMessage("Linked to note.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not link this idea.");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async (documentId: string, relationship: IdeaLinkType) => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await unlinkIdeaFromDocument(selected.id, documentId, relationship);
      setLinks(await fetchIdeaLinks(selected.id));
      setMessage("Link removed.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const docTitle = (documentId: string) =>
    availableDocuments.find((doc) => doc.id === documentId)?.title ??
    documentId.slice(0, 8);

  return (
    <section className="studio-canvas" aria-label="Idea canvas">
      <header className="studio-canvas-header">
        <div>
          <span className="eyebrow">IDEA CANVAS</span>
          <h2>Grow ideas into writing</h2>
          <p>Capture a thought, then connect it to the notes it draws from.</p>
        </div>
        <span role="status" className="studio-canvas-status">
          {message}
        </span>
      </header>

      {error && (
        <p className="api-error" role="alert">
          {error}
        </p>
      )}

      <div className="studio-canvas-grid">
        <form
          className="studio-canvas-capture"
          onSubmit={(event) => {
            event.preventDefault();
            void (selected ? save() : capture());
          }}
        >
          <label htmlFor="studio-canvas-input">
            {selected ? "Develop this idea" : "New idea"}
          </label>
          <textarea
            id="studio-canvas-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            placeholder="What are you circling?"
          />
          <div className="studio-canvas-actions">
            <button
              type="button"
              className="text-action"
              onClick={() => {
                if (selected && text !== (selected.content ?? "")) {
                  setError("Save this idea before creating another.");
                  return;
                }
                setSelectedId(null);
                setText("");
                setError("");
              }}
            >
              New idea
            </button>
            <button
              type="submit"
              className="primary-button"
              disabled={busy || !text.trim()}
            >
              {busy ? "Saving…" : selected ? "Save idea" : "Capture idea"}
            </button>
            <button
              type="button"
              className="text-action"
              onClick={runSuggestions}
            >
              Suggest prompts
            </button>
            <button
              type="button"
              className="text-action"
              onClick={() => void save()}
              disabled={!selected || busy}
            >
              Save changes
            </button>
          </div>
        </form>

        <div className="studio-canvas-columns">
          <nav className="studio-canvas-ideas" aria-label="Ideas">
            <span className="eyebrow">ACTIVE IDEAS</span>
            {ideas.map((idea) => (
              <button
                key={idea.id}
                type="button"
                className={`studio-canvas-idea ${selectedId === idea.id ? "selected" : ""}`}
                onClick={() => {
                  if (selected && text !== (selected.content ?? "")) {
                    setError("Save this idea before opening another.");
                    return;
                  }
                  setSelectedId(idea.id);
                }}
              >
                <strong>{idea.title}</strong>
                <span>
                  {(idea.content ?? "")
                    .replace(/[#>*_`[\]-]/g, " ")
                    .trim()
                    .slice(0, 90) || "No detail yet"}
                </span>
                <small>
                  {idea.linked_document_ids.length
                    ? `${idea.linked_document_ids.length} linked`
                    : "Not linked"}
                </small>
              </button>
            ))}
            {!ideas.length && (
              <p className="studio-empty">
                No active ideas yet. Capture one to start.
              </p>
            )}
          </nav>

          <div className="studio-canvas-detail">
            <span className="eyebrow">CONNECTIONS</span>
            {selected ? (
              <>
                <h3>{selected.title}</h3>
                <ul className="studio-canvas-links">
                  {links.map((link) => (
                    <li
                      key={`${link.idea_id}-${link.document_id}-${link.link_type}`}
                    >
                      <strong>{docTitle(link.document_id)}</strong>
                      <span>{link.link_type}</span>
                      <button
                        type="button"
                        className="text-action"
                        onClick={() => void disconnect(link.document_id, link.link_type)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                  {!links.length && (
                    <li className="studio-empty">No notes linked yet.</li>
                  )}
                </ul>
                <div className="studio-canvas-link-form">
                  <label htmlFor="studio-link-document">Link a note</label>
                  <select
                    id="studio-link-document"
                    value={targetDocumentId}
                    onChange={(e) => setTargetDocumentId(e.target.value)}
                  >
                    <option value="">Choose a note…</option>
                    {availableDocuments.map((doc) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.title}
                      </option>
                    ))}
                  </select>
                  <label htmlFor="studio-link-type">Relationship</label>
                  <select
                    id="studio-link-type"
                    value={linkType}
                    onChange={(e) =>
                      setLinkType(e.target.value as IdeaLinkType)
                    }
                  >
                    <option value="inspires">Inspires</option>
                    <option value="contrasts">Contrasts</option>
                    <option value="extends">Extends</option>
                    <option value="supports">Supports</option>
                  </select>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void connect()}
                    disabled={busy || !targetDocumentId}
                  >
                    Link note
                  </button>
                </div>
              </>
            ) : (
              <p className="studio-empty">
                Select an idea to connect it to your notes.
              </p>
            )}

            {suggestions.length > 0 && (
              <ul className="studio-canvas-suggestions" aria-label="Prompts">
                {suggestions.map((item) => (
                  <li key={item.kind}>
                    <span className="eyebrow">{item.label}</span>
                    <p>{item.prompt}</p>
                    <button
                      type="button"
                      className="text-action"
                      onClick={() => applySuggestion(item.prompt)}
                    >
                      Add to idea
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
