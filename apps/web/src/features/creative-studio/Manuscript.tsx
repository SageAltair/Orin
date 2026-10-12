import { useEffect, useState, type FormEvent } from "react";
import { Plus, Layers, FileText, ArrowUp, ArrowDown } from "lucide-react";
import type { Project } from "../../api";
import {
  createCard,
  createOutlineItem,
  fetchCards,
  fetchOutline,
  updateCard,
  updateOutlineItem,
  errorText,
  type CreativeDocumentCard,
  type CreativeOutlineItem,
  type OutlineItemKind,
  type DocumentCardStatus,
} from "./studioApi";

export function Manuscript({ projects }: { projects: Project[] }) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [outline, setOutline] = useState<CreativeOutlineItem[]>([]);
  const [cards, setCards] = useState<CreativeDocumentCard[]>([]);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<OutlineItemKind>("chapter");
  const [parentId, setParentId] = useState("");
  const [cardTitle, setCardTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  useEffect(() => { if (!projectId && projects[0]) setProjectId(projects[0].id); }, [projects, projectId]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    if (!projectId) return;
    const [a, b] = await Promise.all([
      fetchOutline(projectId),
      fetchCards(projectId),
    ]);
    setOutline(a);
    setCards(b);
  };
  useEffect(() => {
    let active = true;
    setOutline([]);
    setCards([]);
    setParentId("");
    setError("");
    if (projectId)
      Promise.all([fetchOutline(projectId), fetchCards(projectId)])
        .then(([a, b]) => {
          if (active) {
            setOutline(a);
            setCards(b);
          }
        })
        .catch((e) => {
          if (active) setError(errorText(e));
        });
    return () => {
      active = false;
    };
  }, [projectId]);
  const run = async (action: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const addOutline = (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    void run(async () => {
      await createOutlineItem(projectId, {
        title: title.trim(),
        kind,
        position: outline.length,
        parent_id: parentId || null,
      });
      setTitle("");
    });
  };
  const addCard = (event: FormEvent) => {
    event.preventDefault();
    if (!cardTitle.trim()) return;
    void run(async () => {
      await createCard(projectId, {
        title: cardTitle.trim(),
        purpose: purpose.trim() || null,
        position: cards.length,
      });
      setCardTitle("");
      setPurpose("");
    });
  };
  return (
    <section className="manuscript-workspace" aria-label="Manuscript">
      <header className="studio-section-heading">
        <div>
          <span className="eyebrow">MANUSCRIPT</span>
          <h2>Give your writing a shape.</h2>
          <p>Arrange chapters, scenes and working cards around one project.</p>
        </div>
        <label>
          Project
          <select
            aria-label="Manuscript project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
      </header>
      {error && (
        <p className="api-error" role="alert">
          {error}
        </p>
      )}
      {!projectId ? (
        <div className="studio-empty-state">
          <Layers size={32} />
          <h3>Start with a project</h3>
          <p>Create a project, then return here to plan its manuscript.</p>
        </div>
      ) : (
        <div className="manuscript-columns">
          <section>
            <header>
              <Layers size={18} />
              <h3>Outline</h3>
              <small>{outline.length} sections</small>
            </header>
            <form className="studio-inline-form" onSubmit={addOutline}>
              <label>
                Section title
                <input
                  aria-label="Outline title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  maxLength={240}
                  placeholder="A chapter, scene or turning point"
                />
              </label>
              <div className="studio-form-row">
                <label>
                  Kind
                  <select
                    aria-label="Outline kind"
                    value={kind}
                    onChange={(e) => setKind(e.target.value as OutlineItemKind)}
                  >
                    {[
                      "section",
                      "chapter",
                      "scene",
                      "verse",
                      "stanza",
                      "beat",
                      "act",
                      "note",
                    ].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Inside
                  <select
                    aria-label="Parent section"
                    value={parentId}
                    onChange={(e) => setParentId(e.target.value)}
                  >
                    <option value="">Top level</option>
                    {outline.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="primary-button"
                  disabled={busy || !title.trim()}
                >
                  <Plus size={16} /> Add
                </button>
              </div>
            </form>
            <ol className="manuscript-outline">
              {outline.map((item, index) => (
                <li
                  key={item.id}
                  className={item.parent_id ? "outline-child" : ""}
                >
                  <div>
                    <span className="manuscript-number">{index + 1}</span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.kind}</small>
                    </div>
                  </div>
                  <div className="manuscript-item-actions">
                    <select
                      aria-label={`Status of ${item.title}`}
                      value={item.status}
                      onChange={(e) =>
                        void run(() =>
                          updateOutlineItem(projectId, item.id, {
                            status: e.target.value as
                              "planned" | "drafted" | "revised" | "done",
                          }),
                        )
                      }
                    >
                      {["planned", "drafted", "revised", "done"].map(
                        (status) => (
                          <option key={status}>{status}</option>
                        ),
                      )}
                    </select>
                    <button
                      className="icon-button"
                      aria-label={`Move ${item.title} up`}
                      disabled={busy || index === 0}
                      onClick={() =>
                        void run(async () => {
                          const previous = outline[index - 1];
                          await updateOutlineItem(projectId, item.id, {
                            position: previous.position,
                          });
                          await updateOutlineItem(projectId, previous.id, {
                            position: item.position,
                          });
                        })
                      }
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`Move ${item.title} down`}
                      disabled={busy || index === outline.length - 1}
                      onClick={() =>
                        void run(async () => {
                          const next = outline[index + 1];
                          await updateOutlineItem(projectId, item.id, {
                            position: next.position,
                          });
                          await updateOutlineItem(projectId, next.id, {
                            position: item.position,
                          });
                        })
                      }
                    >
                      <ArrowDown size={14} />
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            {!outline.length && (
              <p className="studio-empty">
                Your first section is a good place to begin.
              </p>
            )}
          </section>
          <section>
            <header>
              <FileText size={18} />
              <h3>Working cards</h3>
              <small>{cards.length} cards</small>
            </header>
            <form className="studio-inline-form" onSubmit={addCard}>
              <label>
                Card title
                <input
                  aria-label="Card title"
                  value={cardTitle}
                  onChange={(e) => setCardTitle(e.target.value)}
                  required
                  maxLength={240}
                  placeholder="What belongs in this piece?"
                />
              </label>
              <label>
                Purpose
                <textarea
                  aria-label="Card purpose"
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  rows={2}
                  placeholder="What should this section accomplish?"
                />
              </label>
              <button
                className="secondary-button"
                disabled={busy || !cardTitle.trim()}
              >
                <Plus size={16} /> Add card
              </button>
            </form>
            <div className="manuscript-cards">
              {cards.map((card) => (
                <article key={card.id}>
                  <strong>{card.title}</strong>
                  {card.purpose && <p>{card.purpose}</p>}
                  <label>
                    Status
                    <select
                      aria-label={`Status of card ${card.title}`}
                      value={card.status}
                      onChange={(e) =>
                        void run(() =>
                          updateCard(projectId, card.id, {
                            status: e.target.value as DocumentCardStatus,
                          }),
                        )
                      }
                    >
                      {[
                        "todo",
                        "drafting",
                        "revised",
                        "polished",
                        "ready",
                        "published",
                      ].map((status) => (
                        <option key={status}>{status}</option>
                      ))}
                    </select>
                  </label>
                </article>
              ))}
            </div>
            {!cards.length && (
              <p className="studio-empty">
                Keep each piece's purpose close to the draft.
              </p>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
