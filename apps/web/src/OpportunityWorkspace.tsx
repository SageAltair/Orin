import { useEffect, useMemo, useState } from "react";
import { ActionIcon } from "./ActionIcon";
import type { OpportunityRecord, RiskRecord } from "@orin/contracts";
import { ApiError, request, type Project } from "./api";
import { PlanningForm } from "./PlanningForm";
import "./planning.css";
const today = () => new Date().toLocaleDateString("en-CA");
const stages = [
  "inbox",
  "exploring",
  "pursuing",
  "waiting",
  "won",
  "closed",
] as const;
const blankOpportunity = (): Omit<OpportunityRecord, "id" | "task_id"> => ({
  title: "",
  project_id: null,
  category: "other",
  stage: "inbox",
  description: "",
  source_url: "",
  contact: "",
  next_action: "",
  decision_notes: "",
  deadline: null,
  review_on: null,
  value: 3,
  fit: 3,
  effort: 3,
});
const blankRisk = (): Omit<RiskRecord, "id"> => ({
  title: "",
  opportunity_id: null,
  project_id: null,
  likelihood: 3,
  impact: 3,
  status: "open",
  response: "reduce",
  trigger: "",
  mitigation: "",
  review_on: null,
});
export function OpportunityWorkspace({
  projects,
  onOpenTask,
}: {
  projects: Project[];
  onOpenTask: (id: string) => void;
}) {
  const [opportunities, setOpportunities] = useState<OpportunityRecord[]>([]);
  const [risks, setRisks] = useState<RiskRecord[]>([]);
  const [tab, setTab] = useState<"opportunities" | "risks">("opportunities");
  const [query, setQuery] = useState("");
  const [review, setReview] = useState(false);
  const [stage, setStage] = useState("active");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [op, setOp] = useState<ReturnType<typeof blankOpportunity> | null>(
    null,
  );
  const [risk, setRisk] = useState<ReturnType<typeof blankRisk> | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const refresh = async () => {
    const load = async <T,>(path: string) => {
      const all: T[] = [];
      for (let offset = 0; ; offset += 200) {
        const rows = await request<T[]>(`${path}?limit=200&offset=${offset}`);
        all.push(...rows);
        if (rows.length < 200) return all;
      }
    };
    const [o, r] = await Promise.all([
      load<OpportunityRecord>("/opportunities"),
      load<RiskRecord>("/risks"),
    ]);
    setOpportunities(o);
    setRisks(r);
  };
  useEffect(() => {
    void refresh()
      .catch((e) =>
        setError(
          e instanceof ApiError ? e.message : "Could not load your plans.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);
  const matches = (title: string, date: string | null) =>
    title.toLowerCase().includes(query.toLowerCase()) &&
    (!review || (!!date && date <= today()));
  const visible = useMemo(
    () =>
      opportunities
        .filter(
          (o) =>
            matches(`${o.title} ${o.contact} ${o.description}`, o.review_on) &&
            (stage === "all" ||
              (stage === "active"
                ? !["won", "closed"].includes(o.stage)
                : o.stage === stage)),
        )
        .sort(
          (a, b) => b.value + b.fit - b.effort - (a.value + a.fit - a.effort),
        ),
    [opportunities, query, review, stage],
  );
  const visibleRisks = risks
    .filter(
      (r) =>
        matches(`${r.title} ${r.mitigation}`, r.review_on) &&
        (stage === "all" || r.status !== "resolved"),
    )
    .sort((a, b) => b.impact * b.likelihood - a.impact * a.likelihood);
  const editOpportunity = (o: OpportunityRecord) => {
    const { id, task_id, ...fields } = o;
    void task_id;
    setEditing(id);
    setOp(fields);
  };
  const editRisk = (r: RiskRecord) => {
    const { id, ...fields } = r;
    setEditing(id);
    setRisk(fields);
  };
  const createTask = async (o: OpportunityRecord) => {
    setBusy(o.id);
    setError("");
    try {
      const result = await request<{ task_id: string }>(
        `/opportunities/${o.id}/next-task`,
        { method: "POST" },
      );
      await refresh();
      setNotice("Next action is in Tasks. One step is enough to begin.");
      onOpenTask(result.task_id);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not create next action.",
      );
    } finally {
      setBusy(null);
    }
  };
  const save = async (path: string, data: object) => {
    await request(path + (editing ? `/${editing}` : ""), {
      method: editing ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    await refresh();
    setNotice("Saved.");
  };
  return (
    <section
      className="planning-workspace"
      aria-label="Opportunities and risks"
    >
      <header className="planning-heading">
        <div>
          <span className="eyebrow">POSSIBILITY, WITH PERSPECTIVE</span>
          <h2>Choose your next opening</h2>
          <p>
            Keep possibilities visible. Take one small step. Protect what
            matters.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setEditing(null);
            tab === "opportunities"
              ? setOp(blankOpportunity())
              : setRisk(blankRisk());
          }}
        >
          <ActionIcon name="add" size={16} />{" "}
          {tab === "opportunities" ? "Capture opportunity" : "Add risk"}
        </button>
      </header>
      <div className="planning-summary">
        <span>
          <ActionIcon name="insight" size={17} />
          <strong>
            {opportunities.filter((o) => o.stage === "pursuing").length}
          </strong>{" "}
          pursuing
        </span>
        <span>
          <ActionIcon name="shield" size={17} />
          <strong>
            {
              risks.filter(
                (r) => r.status !== "resolved" && r.impact * r.likelihood >= 15,
              ).length
            }
          </strong>{" "}
          high-priority risks
        </span>
        <span>
          <strong>
            {
              [...opportunities, ...risks].filter(
                (r) => r.review_on && r.review_on <= today(),
              ).length
            }
          </strong>{" "}
          ready for review
        </span>
      </div>
      <div className="planning-controls">
        <div role="tablist" aria-label="Planning view">
          {(["opportunities", "risks"] as const).map((t) => (
            <button
              role="tab"
              aria-selected={tab === t}
              key={t}
              onClick={() => {
                setTab(t);
                setStage("active");
              }}
              className={tab === t ? "selected" : ""}
            >
              {t === "opportunities" ? "Opportunities" : "Risk register"}
            </button>
          ))}
        </div>
        <label className="planning-search">
          <ActionIcon name="search" size={16} />
          <input
            aria-label="Search opportunities and risks"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a possibility…"
          />
        </label>
        <select
          aria-label="Opportunity stage"
          value={stage}
          onChange={(e) => setStage(e.target.value)}
        >
          <option value="active">Active</option>
          <option value="all">All records</option>
          {tab === "opportunities" &&
            stages.map((s) => <option key={s}>{s}</option>)}
        </select>
        <label className="planning-check">
          <input
            type="checkbox"
            checked={review}
            onChange={(e) => setReview(e.target.checked)}
          />{" "}
          Review now
        </label>
      </div>
      {error && (
        <p role="alert" className="api-error">
          {error}{" "}
          <button
            className="text-action"
            onClick={() =>
              void refresh()
                .then(() => setError(""))
                .catch(() => setError("Could not reload. Try again."))
            }
          >
            Retry
          </button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {loading ? (
        <p role="status">Loading your possibilities…</p>
      ) : tab === "opportunities" ? (
        <div className="planning-list">
          {visible.map((o) => (
            <article key={o.id}>
              <div className="planning-row-heading">
                <button
                  className="planning-title"
                  onClick={() => editOpportunity(o)}
                >
                  {o.title}
                </button>
                <span className="planning-badge">{o.stage}</span>
              </div>
              <p>
                {o.next_action || "Choose a next action small enough to start."}
              </p>
              <div className="planning-row-meta">
                <span>{o.category}</span>
                {o.deadline && <span>Deadline · {o.deadline}</span>}
                {o.review_on && <span>Review · {o.review_on}</span>}
                <span>
                  {
                    risks.filter(
                      (r) =>
                        r.opportunity_id === o.id && r.status !== "resolved",
                    ).length
                  }{" "}
                  open risks
                </span>
              </div>
              <div className="planning-row-actions">
                <button
                  className="text-action"
                  onClick={() => editOpportunity(o)}
                >
                  Review & edit
                </button>
                <button
                  className="text-action"
                  onClick={() => {
                    setEditing(null);
                    setRisk({
                      ...blankRisk(),
                      opportunity_id: o.id,
                      project_id: o.project_id,
                    });
                  }}
                >
                  Consider a risk
                </button>
                {o.source_url && (
                  <a
                    href={o.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Source <ActionIcon name="external" size={14} />
                  </a>
                )}
                <button
                  className="secondary-button"
                  disabled={!o.next_action || busy === o.id}
                  onClick={() => void createTask(o)}
                >
                  {o.task_id ? "Continue next action" : "Make next action a task"}
                </button>
              </div>
            </article>
          ))}
          {!visible.length && (
            <div className="planning-empty">
              <ActionIcon name="insight" size={28} />
              <h3>A little possibility goes a long way</h3>
              <p>
                Capture a job, collaboration, idea, course, or business opening.
                You can decide later.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="planning-list">
          {visibleRisks.map((r) => (
            <article key={r.id}>
              <div className="planning-row-heading">
                <button className="planning-title" onClick={() => editRisk(r)}>
                  {r.title}
                </button>
                <span className="planning-badge">
                  {r.likelihood * r.impact >= 15
                    ? "High"
                    : r.likelihood * r.impact >= 8
                      ? "Medium"
                      : "Low"}{" "}
                  priority · {r.status}
                </span>
              </div>
              <p>
                {r.mitigation ||
                  "Name one action that would reduce the downside."}
              </p>
              <div className="planning-row-meta">
                <span>{r.response}</span>
                {r.opportunity_id && (
                  <span>
                    {
                      opportunities.find((o) => o.id === r.opportunity_id)
                        ?.title
                    }
                  </span>
                )}
                {r.review_on && <span>Review · {r.review_on}</span>}
              </div>
              <button className="text-action" onClick={() => editRisk(r)}>
                Review risk
              </button>
            </article>
          ))}
          {!visibleRisks.length && (
            <div className="planning-empty">
              <ActionIcon name="shield" size={28} />
              <h3>Plan for the downside, then move forward</h3>
              <p>
                Capture a concern, its warning sign, and a practical response.
              </p>
            </div>
          )}
        </div>
      )}
      <p className="planning-footnote">
        Priorities use your own ratings, not predictions. Value + fit − effort
        orders opportunities; likelihood × impact orders risks.
      </p>
      {op && (
        <PlanningForm
          title={editing ? "Review opportunity" : "Capture opportunity"}
          onClose={() => setOp(null)}
          onSave={() => save("/opportunities", op)}
          onDelete={
            editing
              ? async () => {
                  await request(`/opportunities/${editing}`, {
                    method: "DELETE",
                  });
                  await refresh();
                }
              : undefined
          }
        >
          <label>
            Opportunity title
            <input
              required
              maxLength={240}
              value={op.title}
              onChange={(e) => setOp({ ...op, title: e.target.value })}
            />
          </label>
          <div className="planning-form-grid">
            <label>
              Category
              <select
                value={op.category}
                onChange={(e) =>
                  setOp({
                    ...op,
                    category: e.target.value as typeof op.category,
                  })
                }
              >
                {[
                  "job",
                  "business",
                  "learning",
                  "creative",
                  "ministry",
                  "other",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Stage
              <select
                value={op.stage}
                onChange={(e) =>
                  setOp({ ...op, stage: e.target.value as typeof op.stage })
                }
              >
                {stages.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Small next action
            <input
              maxLength={240}
              placeholder="Open the brief and write one question"
              value={op.next_action}
              onChange={(e) => setOp({ ...op, next_action: e.target.value })}
            />
          </label>
          <label>
            Why it matters
            <textarea
              maxLength={10000}
              value={op.description}
              onChange={(e) => setOp({ ...op, description: e.target.value })}
            />
          </label>
          <div className="planning-form-grid">
            <label>
              Deadline
              <input
                type="date"
                value={op.deadline || ""}
                onChange={(e) =>
                  setOp({ ...op, deadline: e.target.value || null })
                }
              />
            </label>
            <label>
              Review on
              <input
                type="date"
                value={op.review_on || ""}
                onChange={(e) =>
                  setOp({ ...op, review_on: e.target.value || null })
                }
              />
            </label>
          </div>
          <details>
            <summary>Context & decision</summary>
            <label>
              Project
              <select
                value={op.project_id || ""}
                onChange={(e) =>
                  setOp({ ...op, project_id: e.target.value || null })
                }
              >
                <option value="">Independent</option>
                {projects.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source URL
              <input
                type="url"
                value={op.source_url}
                onChange={(e) => setOp({ ...op, source_url: e.target.value })}
              />
            </label>
            <label>
              Contact
              <input
                maxLength={240}
                value={op.contact}
                onChange={(e) => setOp({ ...op, contact: e.target.value })}
              />
            </label>
            <div className="planning-form-grid">
              {(["value", "fit", "effort"] as const).map((key) => (
                <label key={key}>
                  {key} (1–5)
                  <select
                    value={op[key]}
                    onChange={(e) =>
                      setOp({ ...op, [key]: Number(e.target.value) })
                    }
                  >
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <label>
              Decision notes
              <textarea
                value={op.decision_notes}
                onChange={(e) =>
                  setOp({ ...op, decision_notes: e.target.value })
                }
              />
            </label>
          </details>
        </PlanningForm>
      )}
      {risk && (
        <PlanningForm
          title={editing ? "Review risk" : "Consider a risk"}
          onClose={() => setRisk(null)}
          onSave={() => save("/risks", risk)}
          onDelete={
            editing
              ? async () => {
                  await request(`/risks/${editing}`, { method: "DELETE" });
                  await refresh();
                }
              : undefined
          }
        >
          <label>
            Risk title
            <input
              required
              maxLength={240}
              value={risk.title}
              onChange={(e) => setRisk({ ...risk, title: e.target.value })}
            />
          </label>
          <label>
            Opportunity
            <select
              value={risk.opportunity_id || ""}
              onChange={(e) =>
                setRisk({ ...risk, opportunity_id: e.target.value || null })
              }
            >
              <option value="">Independent risk</option>
              {opportunities.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Project
            <select
              value={risk.project_id || ""}
              onChange={(e) =>
                setRisk({ ...risk, project_id: e.target.value || null })
              }
            >
              <option value="">Independent</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <div className="planning-form-grid">
            {(["likelihood", "impact"] as const).map((key) => (
              <label key={key}>
                {key} (1–5)
                <select
                  value={risk[key]}
                  onChange={(e) =>
                    setRisk({ ...risk, [key]: Number(e.target.value) })
                  }
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <label>
            Warning sign
            <input
              maxLength={500}
              value={risk.trigger}
              onChange={(e) => setRisk({ ...risk, trigger: e.target.value })}
            />
          </label>
          <label>
            Response plan
            <textarea
              maxLength={10000}
              value={risk.mitigation}
              onChange={(e) => setRisk({ ...risk, mitigation: e.target.value })}
            />
          </label>
          <div className="planning-form-grid">
            <label>
              Response
              <select
                value={risk.response}
                onChange={(e) =>
                  setRisk({
                    ...risk,
                    response: e.target.value as typeof risk.response,
                  })
                }
              >
                {["reduce", "avoid", "accept", "transfer"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Risk status
              <select
                value={risk.status}
                onChange={(e) =>
                  setRisk({
                    ...risk,
                    status: e.target.value as typeof risk.status,
                  })
                }
              >
                {["open", "watching", "resolved", "occurred"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Review date
              <input
                type="date"
                value={risk.review_on || ""}
                onChange={(e) =>
                  setRisk({ ...risk, review_on: e.target.value || null })
                }
              />
            </label>
          </div>
        </PlanningForm>
      )}
    </section>
  );
}
