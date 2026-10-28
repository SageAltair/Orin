import { ActionIcon } from "./ActionIcon";
import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  KnowledgeAskResult,
  KnowledgeDocumentRecord,
  KnowledgeDocumentVersionRecord,
  KnowledgeInsightRecord,
  KnowledgeReport,
  KnowledgeReviewRecord,
} from "@orin/contracts";
import { ApiError, type Project, request } from "./api";

type Document = KnowledgeDocumentRecord;
type Draft = Pick<
  Document,
  | "title"
  | "content"
  | "document_type"
  | "tags"
  | "status"
  | "project_id"
  | "exclude_from_ai"
  | "review_at"
>;
type Recovery = { version: number; draft: Draft };
const documentDraft = (doc: Document): Draft => ({
  title: doc.title,
  content: doc.content,
  document_type: doc.document_type,
  tags: doc.tags,
  status: doc.status,
  project_id: doc.project_id,
  exclude_from_ai: doc.exclude_from_ai,
  review_at: doc.review_at
    ? new Date(
        /[zZ]|[+-]\d\d:\d\d$/.test(doc.review_at)
          ? doc.review_at
          : doc.review_at + "Z",
      ).toISOString()
    : null,
});
const localDateTime = (instant: string) => {
  const d = new Date(
    /[zZ]|[+-]\d\d:\d\d$/.test(instant) ? instant : instant + "Z",
  );
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};
type Version = KnowledgeDocumentVersionRecord;
type Links = {
  links: Array<{ id: string; title: string }>;
  backlinks: Array<{ id: string; title: string }>;
};
type ExtractionState = {
  status: NonNullable<Document["extraction_status"]>;
  extracted_data: Document["extracted_data"];
  job: { error: string | null } | null;
};
const readable = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
const relativeTime = (value: string) => {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes} min ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)} hr ago`
        : new Date(value).toLocaleDateString();
};

export function KnowledgeWorkspace({
  projects,
  userId = "local",
  onSaveReady,
  onOpenTask,
}: {
  projects: Project[];
  userId?: string;
  onSaveReady?: (save: () => Promise<boolean>) => void;
  onOpenTask?: (taskId: string) => void;
}) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selected, setSelected] = useState<Document | null>(null);
  const [mobileEditor, setMobileEditor] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [type, setType] = useState("quick_note");
  const [tagsInput, setTagsInput] = useState("");
  const [status, setStatus] = useState("inbox");
  const [projectId, setProjectId] = useState("");
  const [reviewAt, setReviewAt] = useState("");
  const [excludeAI, setExcludeAI] = useState(false);
  const [query, setQuery] = useState("");
  const [documentTypeFilter, setDocumentTypeFilter] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [links, setLinks] = useState<Links>({ links: [], backlinks: [] });
  const [linkTarget, setLinkTarget] = useState("");
  const [preview, setPreview] = useState(false);
  const [insights, setInsights] = useState<KnowledgeInsightRecord[]>([]);
  const [reviews, setReviews] = useState<KnowledgeReviewRecord[]>([]);
  const [intelligenceError, setIntelligenceError] = useState("");
  const [question, setQuestion] = useState("");
  const [askResult, setAskResult] = useState<KnowledgeAskResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [reportType, setReportType] = useState("weekly");
  const [reportTopic, setReportTopic] = useState("");
  const [weeklyReport, setWeeklyReport] = useState<KnowledgeReport | null>(
    null,
  );
  const [reporting, setReporting] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const activeDocumentId = useRef<string | null>(null);
  const draft: Draft = {
    title: title.trim() || "Untitled",
    content,
    document_type: type as Document["document_type"],
    tags: [
      ...new Set(
        tagsInput
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      ),
    ],
    status: status as Document["status"],
    project_id: projectId || null,
    exclude_from_ai: excludeAI,
    review_at: reviewAt ? new Date(reviewAt).toISOString() : null,
  };
  const latest = useRef<{ selected: Document | null; draft: Draft }>({
    selected,
    draft,
  });
  latest.current = { selected, draft };
  const pendingSave = useRef<Promise<boolean> | null>(null);
  const failedDraft = useRef<string | null>(null);
  const draftKey = (id: string) => `orin:writing:draft:${userId}:${id}`;
  const dirty =
    !!selected &&
    JSON.stringify(draft) !== JSON.stringify(documentDraft(selected));
  useEffect(() => {
    if (!selected || !dirty) return;
    try {
      localStorage.setItem(
        draftKey(selected.id),
        JSON.stringify({ version: selected.version, draft }),
      );
    } catch {
      /* Server save remains available. */
    }
  }, [
    selected,
    title,
    content,
    type,
    tagsInput,
    status,
    projectId,
    excludeAI,
    reviewAt,
  ]);
  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      const current = latest.current;
      if (
        current.selected &&
        JSON.stringify(current.draft) !==
          JSON.stringify(documentDraft(current.selected))
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, []);
  const pollExtraction = async (documentId: string) => {
    const state = await request<ExtractionState>(
      `/knowledge/documents/${documentId}/extraction`,
    );
    if (activeDocumentId.current !== documentId) return;
    setSelected((current) =>
      current?.id === documentId
        ? {
            ...current,
            extraction_status: state.status,
            extracted_data: state.extracted_data,
            extraction_error: state.job?.error ?? null,
          }
        : current,
    );
  };
  useEffect(() => {
    if (
      !selected ||
      !["queued", "processing"].includes(selected.extraction_status ?? "")
    )
      return;
    const documentId = selected.id;
    const timer = window.setInterval(() => {
      void pollExtraction(documentId).catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [selected?.id, selected?.extraction_status]);
  const refreshIntelligence = async () => {
    try {
      const [foundInsights, foundReviews] = await Promise.all([
        request<KnowledgeInsightRecord[]>("/knowledge/insights"),
        request<KnowledgeReviewRecord[]>("/knowledge/reviews"),
      ]);
      setInsights(foundInsights);
      setReviews(foundReviews);
      setIntelligenceError("");
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError
          ? e.message
          : "Writing signals could not be loaded.",
      );
    }
  };
  useEffect(() => {
    void refreshIntelligence();
  }, []);
  const runAsk = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setAsking(true);
    setIntelligenceError("");
    try {
      setAskResult(
        await request<KnowledgeAskResult>("/knowledge/ask", {
          method: "POST",
          body: JSON.stringify({ question: question.trim() }),
        }),
      );
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Search failed.",
      );
    } finally {
      setAsking(false);
    }
  };
  const openSource = async (id: string) => {
    try {
      const source =
        documents.find((row) => row.id === id) ??
        (await request<Document>(`/knowledge/documents/${id}`));
      await open(source);
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Source could not be opened.",
      );
    }
  };
  const insightAction = async (
    id: string,
    action: "snooze" | "dismiss" | "resolve" | "reopen",
  ) => {
    try {
      await request(`/knowledge/insights/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ action }),
      });
      await refreshIntelligence();
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Could not update signal.",
      );
    }
  };
  const reviewAction = async (
    id: string,
    action: "snooze" | "dismiss" | "resolve" | "resume",
  ) => {
    try {
      await request(`/knowledge/reviews/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ action }),
      });
      await refreshIntelligence();
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Could not update review.",
      );
    }
  };
  const recordFeedback = async (
    insight_id: string,
    feedback_type: "helpful" | "incorrect",
  ) => {
    try {
      await request("/knowledge/feedback", {
        method: "POST",
        body: JSON.stringify({ insight_id, feedback_type }),
      });
      setIntelligenceError("Feedback saved.");
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Feedback could not be saved.",
      );
    }
  };
  const generateReport = async () => {
    setReporting(true);
    setIntelligenceError("");
    try {
      const topic =
        reportType === "topic"
          ? `?topic=${encodeURIComponent(reportTopic)}`
          : "";
      setWeeklyReport(
        await request<KnowledgeReport>(
          `/knowledge/reports/${reportType}${topic}`,
        ),
      );
    } catch (e) {
      setIntelligenceError(
        e instanceof ApiError ? e.message : "Report could not be generated.",
      );
    } finally {
      setReporting(false);
    }
  };
  const [hasMore, setHasMore] = useState(false);
  const refresh = async (append = false) => {
    const params = new URLSearchParams({
      include_archived: String(includeArchived),
    });
    if (query.trim()) params.set("q", query.trim());
    if (documentTypeFilter) params.set("document_type", documentTypeFilter);
    params.set("offset", String(append ? documents.length : 0));
    const rows = await request<Document[]>(`/knowledge/documents?${params}`);
    setHasMore(rows.length === 200);
    setDocuments((current) =>
      append
        ? [
            ...current,
            ...rows.filter(
              (row) => !current.some((item) => item.id === row.id),
            ),
          ]
        : rows,
    );
  };
  useEffect(() => {
    void refresh().catch((e) =>
      setError(
        e instanceof ApiError ? e.message : "Writing could not be loaded.",
      ),
    );
  }, [query, includeArchived, documentTypeFilter]);
  const open = async (doc: Document) => {
    if (!(await save())) return;
    activeDocumentId.current = doc.id;
    setSelected(null);
    setRecovery(null);
    setMobileEditor(true);
    setError("");
    try {
      const [full, history, relations] = await Promise.all([
        request<Document>(`/knowledge/documents/${doc.id}`),
        request<Version[]>(`/knowledge/documents/${doc.id}/versions`),
        request<Links>(`/knowledge/documents/${doc.id}/links`),
      ]);
      if (activeDocumentId.current !== doc.id) return;
      let recoverable: Recovery | null = null;
      try {
        recoverable = JSON.parse(
          localStorage.getItem(draftKey(full.id)) ?? "null",
        );
      } catch {
        /* Ignore malformed storage without deleting it. */
      }
      if (!recoverable) {
        // The authenticated fetch proves ownership before migrating the previous cache format.
        try {
          const legacy = JSON.parse(localStorage.getItem(`orin:writing:draft:${full.id}`) ?? "null");
          if (legacy && typeof legacy.title === "string" && typeof legacy.content === "string") {
            recoverable = {version: legacy.version, draft: {...documentDraft(full), title:legacy.title, content:legacy.content}};
            localStorage.setItem(draftKey(full.id), JSON.stringify(recoverable));
          }
        } catch { /* Preserve malformed legacy bytes for manual recovery. */ }
      }
      setRecovery(
        recoverable?.draft &&
          JSON.stringify(recoverable.draft) !==
            JSON.stringify(documentDraft(full))
          ? recoverable
          : null,
      );
      failedDraft.current = null;
      setSelected(full);
      setTitle(full.title);
      setContent(full.content);
      setType(full.document_type);
      setTagsInput(full.tags.join(", "));
      setStatus(full.status);
      setProjectId(full.project_id ?? "");
      setExcludeAI(full.exclude_from_ai);
      setReviewAt(full.review_at ? localDateTime(full.review_at) : "");
      setVersions(history);
      setLinks(relations);
      setMessage("Saved");
      setPreview(false);
    } catch (e) {
      if (activeDocumentId.current === doc.id)
        setError(
          e instanceof ApiError ? e.message : "Note could not be opened.",
        );
    }
  };
  const create = async (template?: {
    title: string;
    content: string;
    document_type: string;
  }) => {
    if (creating || !(await save())) return;
    setCreating(true);
    activeDocumentId.current = null;
    setSelected(null);
    setMobileEditor(true);
    setError("");
    try {
      const doc = await request<Document>("/knowledge/documents", {
        method: "POST",
        body: JSON.stringify({
          title: template?.title ?? "Untitled",
          content: template?.content ?? "",
          document_type: template?.document_type ?? "quick_note",
          status: template ? "developing" : "inbox",
        }),
      });
      await refresh();
      if (activeDocumentId.current === null) await open(doc);
      setMessage("Saved");
      requestAnimationFrame(() => editor.current?.focus());
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Note could not be created.",
      );
    } finally {
      setCreating(false);
    }
  };
  const save = (): Promise<boolean> => {
    if (pendingSave.current) return pendingSave.current;
    const current = latest.current;
    if (
      !current.selected ||
      JSON.stringify(current.draft) ===
        JSON.stringify(documentDraft(current.selected))
    )
      return Promise.resolve(true);
    const operation = async () => {
      setSaving(true);
      setError("");
      setMessage("Saving…");
      try {
        while (latest.current.selected) {
          const { selected: base, draft: snapshot } = latest.current;
          if (JSON.stringify(snapshot) === JSON.stringify(documentDraft(base)))
            break;
          const updated = await request<Document>(
            `/knowledge/documents/${base.id}`,
            {
              method: "PATCH",
              body: JSON.stringify({
                ...snapshot,
                expected_version: base.version,
              }),
            },
          );
          // Update the version immediately, then save edits typed during the request against that version.
          latest.current = { ...latest.current, selected: updated };
          setSelected(updated);
          if (
            JSON.stringify(latest.current.draft) === JSON.stringify(snapshot)
          ) {
            try {
              localStorage.removeItem(draftKey(base.id));
              localStorage.removeItem(`orin:writing:draft:${base.id}`);
            } catch {
              /* Storage can be restricted. */
            }
          } else {
            try {
              localStorage.setItem(
                draftKey(base.id),
                JSON.stringify({
                  version: updated.version,
                  draft: latest.current.draft,
                }),
              );
            } catch {
              /* Server retry remains available. */
            }
          }
        }
        failedDraft.current = null;
        setConflict(false);
        setMessage("Saved");
        void refresh().catch(() => undefined);
        return true;
      } catch (e) {
        failedDraft.current = JSON.stringify(latest.current.draft);
        setConflict(e instanceof ApiError && e.status === 409);
        setMessage("Save failed");
        setError(
          e instanceof ApiError
            ? e.message +
                " Your local draft is preserved. Retry or export it before leaving."
            : "Save failed. Your local draft is preserved.",
        );
        return false;
      } finally {
        setSaving(false);
        pendingSave.current = null;
      }
    };
    pendingSave.current = operation();
    return pendingSave.current;
  };
  useEffect(() => {
    onSaveReady?.(save);
  });
  const saveOnExit = useRef(save);
  saveOnExit.current = save;
  useEffect(
    () => () => {
      void saveOnExit.current();
    },
    [],
  );
  useEffect(() => {
    if (
      !dirty ||
      saving ||
      recovery ||
      failedDraft.current === JSON.stringify(draft)
    )
      return;
    const timer = window.setTimeout(() => void save(), 800);
    return () => window.clearTimeout(timer);
  }, [
    selected,
    title,
    content,
    type,
    tagsInput,
    status,
    projectId,
    excludeAI,
    reviewAt,
    saving,
    recovery,
  ]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void create();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });
  const format = (prefix: string, suffix = "", placeholder = "text") => {
    const area = editor.current;
    if (!area) return;
    const start = area.selectionStart;
    const end = area.selectionEnd;
    const value = content.slice(start, end) || placeholder;
    setContent(
      `${content.slice(0, start)}${prefix}${value}${suffix}${content.slice(end)}`,
    );
    setMessage("Unsaved changes");
    requestAnimationFrame(() => {
      area.focus();
      area.setSelectionRange(
        start + prefix.length,
        start + prefix.length + value.length,
      );
    });
  };
  const archive = async () => {
    if (!selected || !(await save())) return;
    try {
      await request(`/knowledge/documents/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          archived: !selected.archived,
          expected_version:
            latest.current.selected?.version ?? selected.version,
        }),
      });
      setSelected(null);
      setMessage(selected.archived ? "Note restored." : "Note archived.");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update note.");
    }
  };
  const addLink = async () => {
    if (!selected || !linkTarget) return;
    try {
      await request(`/knowledge/documents/${selected.id}/links`, {
        method: "POST",
        body: JSON.stringify({ target_id: linkTarget }),
      });
      setLinks(
        await request<Links>(`/knowledge/documents/${selected.id}/links`),
      );
      setLinkTarget("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not link notes.");
    }
  };
  const extractKnowledge = async () => {
    if (!(await save())) return;
    if (!selected || extracting || excludeAI) return;
    setExtracting(true);
    setError("");
    try {
      const job = await request<{
        status: NonNullable<Document["extraction_status"]>;
        error?: string | null;
      }>(`/knowledge/documents/${selected.id}/extract`, { method: "POST" });
      setSelected((current) =>
        current?.id === selected.id
          ? {
              ...current,
              extraction_status: job.status,
              extraction_error: job.error ?? null,
            }
          : current,
      );
      setMessage(
        job.status === "succeeded"
          ? "Knowledge already extracted"
          : job.status === "failed"
            ? job.error || "Extraction failed"
            : "Extraction queued",
      );
      await pollExtraction(selected.id);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Knowledge extraction could not be started.",
      );
    } finally {
      setExtracting(false);
    }
  };
  const reviewConflict = async () => {
    const current = latest.current;
    if (!current.selected || pendingSave.current) return;
    try {
      const full = await request<Document>(`/knowledge/documents/${current.selected.id}`);
      setRecovery({version: current.selected.version, draft: current.draft});
      setSelected(full); setTitle(full.title); setContent(full.content);
      setType(full.document_type); setTagsInput(full.tags.join(", ")); setStatus(full.status);
      setProjectId(full.project_id ?? ""); setExcludeAI(full.exclude_from_ai);
      setReviewAt(full.review_at ? localDateTime(full.review_at) : "");
      failedDraft.current = null; setConflict(false); setError(""); setMessage("Newer version loaded");
    } catch (e) { setError(e instanceof ApiError ? e.message : "The newer note could not be loaded."); }
  };
  const candidates = documents.filter((item) => item.id !== selected?.id);
  const wordCount = content.trim() ? content.trim().split(/\s+/u).length : 0;
  const characterCount = content.length;
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 200));
  const downloadDocument = () => {
    if (!selected) return;
    const blob = new Blob([`# ${title.trim() || "Untitled"}\n\n${content}`], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${(title.trim() || "untitled").replace(/[\\/:*?\"<>|]/g, "-")}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const restoreVersion = async (version: Version) => {
    if (!selected || !(await save())) return;
    setSaving(true);
    setMessage("Restoring version…");
    setError("");
    try {
      const restored = await request<Document>(
        `/knowledge/documents/${selected.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            title: version.title,
            content: version.content,
            expected_version:
              latest.current.selected?.version ?? selected.version,
          }),
        },
      );
      setSelected(restored);
      setTitle(restored.title);
      setContent(restored.content);
      setVersions(
        await request<Version[]>(
          `/knowledge/documents/${restored.id}/versions`,
        ),
      );
      setMessage(`Restored version ${version.version}`);
      await refresh();
    } catch (e) {
      setMessage("Save failed");
      setError(
        e instanceof ApiError
          ? e.message
          : "This version could not be restored. Your current text is still here.",
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <section
      className={`writing-workspace ${mobileEditor ? "writing-mobile-editor" : ""} ${focusMode ? "writing-focus-mode" : ""}`}
      aria-label="Creative Studio"
    >
      <aside className="writing-list">
        <header className="writing-list-header">
          <div className="writing-brand">
            <ActionIcon name="edit" aria-hidden="true" size={20} />
            <div>
              <h2>Notes</h2>
              <p>Capture thoughts and develop ideas.</p>
            </div>
          </div>
          <button
            className="writing-new"
            disabled={creating}
            onClick={() => void create()}
          >
            <ActionIcon name="add" aria-hidden="true" size={16} /> New note <kbd>Ctrl N</kbd>
          </button>
          <details className="writing-template-menu">
            <summary>Start from a template</summary>
            <button
              type="button"
              onClick={() =>
                void create({
                  title: "Story outline",
                  content:
                    "# Premise\n\n# Characters\n\n# Beginning\n\n# Turning points\n\n# Ending\n",
                  document_type: "draft",
                })
              }
            >
              Story outline
            </button>
            <button
              type="button"
              onClick={() =>
                void create({
                  title: "Poem",
                  content: "",
                  document_type: "draft",
                })
              }
            >
              Poetry draft
            </button>
            <button
              type="button"
              onClick={() =>
                void create({
                  title: "Research article",
                  content: "# Question\n\n# Sources\n\n# Findings\n\n# Draft\n",
                  document_type: "research",
                })
              }
            >
              Research article
            </button>
            <button
              type="button"
              onClick={() =>
                void create({
                  title: "Essay",
                  content:
                    "# Working thesis\n\n# Supporting points\n\n# Draft\n",
                  document_type: "draft",
                })
              }
            >
              Essay
            </button>
          </details>
          <div className="writing-search">
            <ActionIcon name="search" aria-hidden="true" size={14} />
            <input
              aria-label="Search documents"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search notes…"
            />
          </div>
          <div className="writing-list-tools">
            <label>
              Show
              <select
                aria-label="Filter notes"
                value={documentTypeFilter}
                onChange={(e) => setDocumentTypeFilter(e.target.value)}
              >
                <option value="">All notes</option>
                <option value="idea">Idea inbox</option>
                <option value="draft">Drafts</option>
                <option value="research">Research</option>
                <option value="quick_note">Quick notes</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
              />{" "}
              Archived
            </label>
          </div>
        </header>
        <nav className="writing-documents" aria-label="Notes">
          {documents.map((doc) => (
            <button
              key={doc.id}
              className={`writing-document ${selected?.id === doc.id ? "selected" : ""}`}
              onClick={() => void open(doc)}
            >
              <span className="writing-document-icon" aria-hidden="true">
                <ActionIcon name="document" size={16} />
              </span>
              <span className="writing-document-copy">
                <strong>{doc.title || "Untitled"}</strong>
                <span>
                  {doc.content
                    .replace(/[#>*_`\[\]-]/g, " ")
                    .trim()
                    .slice(0, 90) || "Start writing…"}
                </span>
                <small>
                  {relativeTime(doc.updated_at)}
                  {doc.archived ? " · Archived" : ""}
                </small>
              </span>
            </button>
          ))}
          {hasMore && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void refresh(true)}
            >
              Load more notes
            </button>
          )}
          {!documents.length && (
            <p className="writing-empty-list">
              {query
                ? "No notes match your search."
                : "Your notes will appear here."}
            </p>
          )}
        </nav>
        <details className="writing-tools">
          <summary>
            Writing tools{" "}
            <span>
              {reviews.filter((item) => item.status === "pending").length || ""}
            </span>
          </summary>
          <div className="writing-tools-content">
            <form className="writing-ask" onSubmit={runAsk}>
              <label htmlFor="writing-question">Ask your notes</label>
              <input
                id="writing-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What have I written about?"
                maxLength={500}
              />
              <button
                type="submit"
                disabled={asking || question.trim().length < 2}
              >
                {asking ? "Searching…" : "Ask"}
              </button>
            </form>
            {askResult && (
              <article className="writing-tool-result">
                <p>{askResult.answer}</p>
                <small>
                  {askResult.mode === "keyword_only"
                    ? "Keyword retrieval"
                    : "AI synthesis"}
                  {askResult.limitations.map((item) => ` · ${item}`).join("")}
                </small>
                {askResult.citations.map((source) => (
                  <button
                    key={source.document_id}
                    onClick={() => void openSource(source.document_id)}
                  >
                    {source.title}
                  </button>
                ))}
              </article>
            )}
            <div className="writing-report-controls">
              <label>
                Reports
                <select
                  aria-label="Report type"
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value)}
                >
                  {[
                    "weekly",
                    "daily",
                    "monthly",
                    "topic",
                    "writing",
                    "decisions",
                  ].map((item) => (
                    <option key={item} value={item}>
                      {readable(item)}
                    </option>
                  ))}
                </select>
              </label>
              {reportType === "topic" && (
                <input
                  aria-label="Report topic"
                  value={reportTopic}
                  onChange={(e) => setReportTopic(e.target.value)}
                  placeholder="Topic"
                />
              )}
              <button
                onClick={() => void generateReport()}
                disabled={
                  reporting || (reportType === "topic" && !reportTopic.trim())
                }
              >
                {reporting
                  ? "Generating…"
                  : reportType === "weekly"
                    ? "Weekly report"
                    : "Generate report"}
              </button>
              <button
                onClick={async () => {
                  try {
                    await request("/knowledge/intelligence/evaluate", {
                      method: "POST",
                    });
                    await refreshIntelligence();
                  } catch (e) {
                    setIntelligenceError(
                      e instanceof ApiError
                        ? e.message
                        : "Signals could not be refreshed.",
                    );
                  }
                }}
              >
                Refresh signals
              </button>
            </div>
            {weeklyReport && (
              <article className="writing-tool-result">
                <strong>{readable(reportType)} report</strong>
                <small>
                  Generated{" "}
                  {new Date(weeklyReport.generated_at).toLocaleString()}
                </small>
                {weeklyReport.observations.map((item, index) => (
                  <p key={`${item.kind}-${index}`}><b>{item.title}</b> — {item.detail}</p>
                ))}
                <div className="writing-report-sources" aria-label="Report sources">
                  {[...new Map(weeklyReport.observations.flatMap(item => item.evidence).map(source => [source.document_id, source])).values()].map(source => (
                    <button type="button" key={source.document_id} onClick={() => void openSource(source.document_id)}>{source.title}</button>
                  ))}
                </div>
                {weeklyReport.limitations.join(" ")}
              </article>
            )}
            <div className="writing-signal-list">
              <h3>Recurring topics</h3>
              {insights.length ? (
                insights.map((item) => (
                  <article key={item.id}>
                    <strong>{item.title}</strong>
                    <p>{item.explanation}</p>
                    <small>
                      {item.frequency} sources · Text-based signal
                    </small>
                    {item.evidence.map((source) =>
                      source.document_id ? (
                        <button
                          key={source.document_id}
                          onClick={() => void openSource(source.document_id!)}
                        >
                          {source.title}
                        </button>
                      ) : source.task_id ? (
                        <button
                          key={source.task_id}
                          onClick={() => onOpenTask?.(source.task_id!)}
                        >
                          {source.title}
                        </button>
                      ) : null,
                    )}
                    <div>
                      {item.status === "snoozed" ? (
                        <button
                          onClick={() => void insightAction(item.id, "reopen")}
                        >
                          Resume
                        </button>
                      ) : (
                        <button
                          onClick={() => void insightAction(item.id, "snooze")}
                        >
                          Snooze
                        </button>
                      )}
                      <button
                        onClick={() => void insightAction(item.id, "dismiss")}
                      >
                        Dismiss
                      </button>
                      <button
                        onClick={() => void insightAction(item.id, "resolve")}
                      >
                        Resolve
                      </button>
                      <button
                        onClick={() => void recordFeedback(item.id, "helpful")}
                      >
                        Helpful
                      </button>
                      <button
                        onClick={() =>
                          void recordFeedback(item.id, "incorrect")
                        }
                      >
                        Incorrect
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <p>No topic signals yet.</p>
              )}
              <h3>Ready to review</h3>
              {reviews.filter((item) => item.status === "pending").length ? (
                reviews
                  .filter((item) => item.status === "pending")
                  .map((item) => (
                    <article key={item.id}>
                      <button onClick={() => void openSource(item.document_id)}>
                        <strong>{item.title}</strong>
                      </button>
                      <small>
                        {readable(item.document_type)} · Due{" "}
                        {new Date(item.due_at).toLocaleDateString()}
                      </small>
                      <div>
                        <button
                          onClick={() => void reviewAction(item.id, "snooze")}
                        >
                          Snooze
                        </button>
                        <button
                          onClick={() => void reviewAction(item.id, "dismiss")}
                        >
                          Dismiss
                        </button>
                        <button
                          onClick={() => void reviewAction(item.id, "resolve")}
                        >
                          Done
                        </button>
                      </div>
                    </article>
                  ))
              ) : (
                <p>Nothing needs review.</p>
              )}
              {reviews.some((item) => item.status === "snoozed") && (
                <details>
                  <summary>
                    Snoozed (
                    {reviews.filter((item) => item.status === "snoozed").length}
                    )
                  </summary>
                  {reviews
                    .filter((item) => item.status === "snoozed")
                    .map((item) => (
                      <article key={item.id}>
                        <button
                          onClick={() => void openSource(item.document_id)}
                        >
                          {item.title}
                        </button>
                        <small>
                          Until{" "}
                          {item.snoozed_until
                            ? new Date(item.snoozed_until).toLocaleDateString()
                            : "next review"}
                        </small>
                        <button
                          onClick={() => void reviewAction(item.id, "resume")}
                        >
                          Resume
                        </button>
                        <button
                          onClick={() => void reviewAction(item.id, "dismiss")}
                        >
                          Dismiss
                        </button>
                      </article>
                    ))}
                </details>
              )}
            </div>
            {intelligenceError && (
              <p role="alert" className="api-error">
                {intelligenceError}
              </p>
            )}
          </div>
        </details>
      </aside>
      <main className="writing-editor">
        {error && (
          <p role="alert" className="api-error writing-error">
            {error}
            {conflict && <button type="button" onClick={() => void reviewConflict()}>Review newer version</button>}
            {message === "Save failed" && (
              <button type="button" onClick={() => void save()}>
                Retry save
              </button>
            )}
          </p>
        )}
        {selected ? (
          <>
            <header className="writing-toolbar-top">
              <button
                className="writing-back"
                type="button"
                onClick={() => setMobileEditor(false)}
                aria-label="Back to notes"
              >
                Back to notes
              </button>
              <div className="writing-breadcrumb">
                <span>Writing</span>
                <span>›</span>
                <strong>{title || "Untitled"}</strong>
              </div>
              <span
                role="status"
                className={`writing-save-status ${saving ? "is-saving" : ""}`}
              >
                {saving
                  ? "◌ Saving…"
                  : message === "Save failed"
                    ? "! Save failed"
                    : "✓ " + (message || "Saved")}
              </span>
              <button
                className="writing-quiet-action"
                type="button"
                onClick={downloadDocument}
              >
                Export .md
              </button>
              <button
                className="writing-quiet-action"
                type="button"
                aria-pressed={focusMode}
                onClick={() => setFocusMode((value) => !value)}
              >
                {focusMode ? "Exit focus" : "Focus"}
              </button>
              <button
                className="writing-quiet-action"
                type="button"
                onClick={() => void archive()}
              >
                {selected.archived ? "Restore" : "Archive"}
              </button>
            </header>
            <div className="writing-paper">
              {recovery && (
                <div className="writing-recovery" role="status">
                  <span>
                    A local draft is available. Restoring it replaces the
                    displayed note; the server keeps the previous version.
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setTitle(recovery.draft.title);
                      setContent(recovery.draft.content);
                      setType(recovery.draft.document_type);
                      setTagsInput(recovery.draft.tags.join(", "));
                      setStatus(recovery.draft.status);
                      setProjectId(recovery.draft.project_id ?? "");
                      setExcludeAI(recovery.draft.exclude_from_ai);
                      setReviewAt(
                        recovery.draft.review_at
                          ? localDateTime(recovery.draft.review_at)
                          : "",
                      );
                      failedDraft.current = null;
                      setRecovery(null);
                      setMessage("Unsaved changes");
                    }}
                  >
                    Restore draft
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (selected)
                        window.localStorage.removeItem(draftKey(selected.id));
                      setRecovery(null);
                    }}
                  >
                    Dismiss
                  </button>
                </div>
              )}
              <input
                className="writing-title"
                aria-label="Document title"
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  setMessage("Unsaved changes");
                }}
                placeholder="Untitled"
              />
              <div
                className="writing-formatbar"
                role="toolbar"
                aria-label="Markdown formatting"
              >
                {[
                  ["B", "**", "**"],
                  ["I", "*", "*"],
                  ["H1", "# ", ""],
                  ["H2", "## ", ""],
                  ["• List", "- ", ""],
                  ["☑", "- [ ] ", ""],
                  ["❝", "> ", ""],
                  ["Link", "[", "](https://)"],
                  [preview ? "Edit" : "Preview", "", ""],
                ].map(([label, prefix, suffix]) => (
                  <button
                    type="button"
                    key={label}
                    title={label}
                    aria-label={
                      label === "B"
                        ? "Bold"
                        : label === "I"
                          ? "Italic"
                          : label === "Preview"
                            ? "Preview formatting"
                            : label === "Edit"
                              ? "Edit markdown"
                              : label
                    }
                    onClick={() =>
                      label === "Preview" || label === "Edit"
                        ? setPreview(!preview)
                        : format(prefix, suffix)
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
              {preview ? (
                <article className="writing-preview">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {content}
                  </ReactMarkdown>
                </article>
              ) : (
                <textarea
                  ref={editor}
                  aria-label="Content"
                  value={content}
                  onChange={(e) => {
                    setContent(e.target.value);
                    setMessage("Unsaved changes");
                  }}
                  placeholder="Start writing…"
                  spellCheck
                />
              )}
              <div className="writing-manuscript-stats" aria-live="polite">
                <span>{wordCount.toLocaleString()} words</span>
                <span>{characterCount.toLocaleString()} characters</span>
                <span>{readingMinutes} min read</span>
              </div>
            </div>
            <details className="writing-details">
              <summary>Note details</summary>
              <div className="writing-details-grid">
                <label>
                  Type
                  <select
                    value={type}
                    onChange={(e) => {
                      setType(e.target.value);
                      setMessage("Unsaved changes");
                    }}
                  >
                    {[
                      "quick_note",
                      "knowledge",
                      "research",
                      "idea",
                      "draft",
                      "journal",
                      "meeting",
                      "decision",
                      "reference",
                    ].map((item) => (
                      <option key={item} value={item}>
                        {readable(item)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Status
                  <select
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value);
                      setMessage("Unsaved changes");
                    }}
                  >
                    {[
                      "inbox",
                      "developing",
                      "waiting",
                      "ready_to_resume",
                      "completed",
                      "parked",
                      "abandoned",
                    ].map((item) => (
                      <option key={item} value={item}>
                        {readable(item)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Tags
                  <input
                    aria-label="Tags, comma separated"
                    value={tagsInput}
                    onChange={(e) => {
                      setTagsInput(e.target.value);
                      setMessage("Unsaved changes");
                    }}
                    placeholder="story, character, draft"
                  />
                </label>
                <label>
                  Project
                  <select
                    value={projectId}
                    onChange={(e) => {
                      setProjectId(e.target.value);
                      setMessage("Unsaved changes");
                    }}
                  >
                    <option value="">Personal</option>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Review date
                  <input
                    type="datetime-local"
                    step="1"
                    value={reviewAt}
                    onChange={(e) => {
                      setReviewAt(e.target.value);
                      setMessage("Unsaved changes");
                    }}
                  />
                </label>
                <label className="writing-checkbox">
                  <input
                    type="checkbox"
                    checked={excludeAI}
                    onChange={(e) => {
                      setExcludeAI(e.target.checked);
                      setMessage("Unsaved changes");
                    }}
                  />
                  Exclude from AI
                </label>
              </div>
              <section className="writing-relations">
                <h3>Related notes</h3>
                {links.links.map((link) => (
                  <button
                    key={link.id}
                    onClick={() => {
                      const doc = documents.find((item) => item.id === link.id);
                      if (doc) void open(doc);
                    }}
                  >
                    {link.title}
                  </button>
                ))}
                {links.backlinks.map((link) => (
                  <button
                    key={link.id}
                    onClick={() => {
                      const doc = documents.find((item) => item.id === link.id);
                      if (doc) void open(doc);
                    }}
                  >
                    ↗ {link.title}
                  </button>
                ))}
                <div>
                  <select
                    aria-label="Link to"
                    value={linkTarget}
                    onChange={(e) => setLinkTarget(e.target.value)}
                  >
                    <option value="">Link to a note…</option>
                    {candidates.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.title}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => void addLink()}
                    disabled={!linkTarget}
                  >
                    Add link
                  </button>
                </div>
              </section>
              <section
                className="writing-extraction"
                aria-label="Extracted knowledge"
              >
                <h3>Extracted knowledge</h3>
                <p role="status">
                  {extracting ||
                  selected.extraction_status === "queued" ||
                  selected.extraction_status === "processing"
                    ? "Extracting knowledge…"
                    : selected.extraction_status === "succeeded"
                      ? "Knowledge extracted"
                      : selected.extraction_status === "failed"
                        ? "Extraction failed"
                        : selected.extraction_status === "superseded" ||
                            selected.extraction_status === "stale"
                          ? "This extraction is out of date"
                          : selected.extraction_status === "excluded" ||
                              excludeAI
                            ? "This note is excluded from AI"
                            : "No knowledge extracted yet"}
                </p>
                {selected.extraction_error &&
                  selected.extraction_status === "failed" && (
                    <p role="alert" className="api-error">
                      {selected.extraction_error}
                    </p>
                  )}
                <button
                  type="button"
                  onClick={() => void extractKnowledge()}
                  disabled={
                    extracting ||
                    excludeAI ||
                    selected.extraction_status === "queued" ||
                    selected.extraction_status === "processing" ||
                    selected.extraction_status === "succeeded"
                  }
                >
                  {extracting ||
                  selected.extraction_status === "queued" ||
                  selected.extraction_status === "processing"
                    ? "Extracting…"
                    : selected.extraction_status === "succeeded"
                      ? "Extracted"
                      : selected.extraction_status === "failed" ||
                          selected.extraction_status === "superseded"
                        ? "Retry extraction"
                        : "Extract knowledge"}
                </button>
                {selected.extracted_data && (
                  <div className="writing-extracted-data">
                    <p>{selected.extracted_data.summary}</p>
                    {(
                      [
                        ["Topics", selected.extracted_data.topics],
                        ["Entities", selected.extracted_data.entities],
                        ["Decisions", selected.extracted_data.decisions],
                        [
                          "Open questions",
                          selected.extracted_data.open_questions,
                        ],
                        [
                          "Candidate actions",
                          selected.extracted_data.candidate_actions,
                        ],
                        [
                          "Date mentions",
                          selected.extracted_data.date_mentions,
                        ],
                      ] as const
                    )
                      .filter(([, items]) => items.length > 0)
                      .map(([label, items]) => (
                        <div key={label}>
                          <strong>{label}</strong>
                          <ul>
                            {items.map((item, index) => (
                              <li key={`${label}-${index}`}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      ))}
                  </div>
                )}
              </section>
              <section className="writing-history">
                <h3>Version history</h3>
                {versions.slice(0, 5).map((version) => (
                  <article key={version.id}>
                    Version {version.version} ·{" "}
                    {new Date(version.created_at).toLocaleString()}
                    <button
                      type="button"
                      disabled={saving || version.version === selected.version}
                      onClick={() => void restoreVersion(version)}
                    >
                      Restore
                    </button>
                  </article>
                ))}
              </section>
            </details>
          </>
        ) : (
          <div className="writing-welcome">
            <ActionIcon name="edit" aria-hidden="true" size={20} />
            <h2>Your space to think.</h2>
            <p>Capture thoughts, take notes, and write your ideas.</p>
            <button
              className="writing-new"
              disabled={creating}
              onClick={() => void create()}
            >
              <ActionIcon name="add" aria-hidden="true" size={16} /> New note
            </button>
          </div>
        )}
      </main>
    </section>
  );
}

export function QuickKnowledgeCapture({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setBusy(true);
    setError("");
    try {
      await request("/knowledge/documents", {
        method: "POST",
        body: JSON.stringify({
          title: value.split("\n")[0].slice(0, 240) || "Quick note",
          content: value,
          document_type: "quick_note",
          status: "inbox",
        }),
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save this note.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="quick-capture-scrim" role="presentation">
      <section
        className="quick-capture"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-writing-title"
      >
        <header>
          <h2 id="quick-writing-title">Capture a thought</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <form onSubmit={submit}>
          <label htmlFor="quick-writing-text">Your note</label>
          <textarea
            id="quick-writing-text"
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Write it down…"
            required
          />
          {error && (
            <p className="api-error" role="alert">
              {error}
            </p>
          )}
          <div>
            <span>Saved to Writing</span>
            <button className="primary-button" disabled={busy || !text.trim()}>
              {busy ? "Saving…" : "Save note"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
