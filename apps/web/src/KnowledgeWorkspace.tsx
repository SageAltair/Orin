import { Pencil, Plus, Search, FileText, BookOpen, PanelLeftClose, PanelLeftOpen, SlidersHorizontal, Sparkles, Palette, FileSliders, X, MoreVertical, Bold, Italic, Underline, List, ListChecks, Quote, Link2, Minus, Table2, Columns3, ImagePlus, Highlighter, Heading2, AlignLeft, AlignCenter, AlignRight, ChevronDown, Eye, Trash2, Archive, FolderKanban, FileDown } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent as ReactPointerEvent } from "react";
import type {
  KnowledgeAskResult,
  KnowledgeDocumentRecord,
  KnowledgeDocumentVersionRecord,
  KnowledgeInsightRecord,
  KnowledgeReport,
  KnowledgeReviewRecord,
  WritingLiveReview,
  WritingReviewSuggestion,
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
const RICH_DOCUMENT_PREFIX = "<!--orin-rich-v1-->";
const escapeHtml = (value: string) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const richHtmlFromContent = (value: string) => {
  if (value.startsWith(RICH_DOCUMENT_PREFIX)) return value.slice(RICH_DOCUMENT_PREFIX.length);
  return value.split(/\n{2,}/).map(block => `<p>${escapeHtml(block).replaceAll("\n", "<br>") || "<br>"}</p>`).join("");
};
const richTextFromContent = (value: string) => {
  if (!value.startsWith(RICH_DOCUMENT_PREFIX) || typeof document === "undefined") return value;
  const parsed = new DOMParser().parseFromString(value.slice(RICH_DOCUMENT_PREFIX.length), "text/html");
  return parsed.body.textContent?.replace(/\s+/g, " ").trim() ?? "";
};
const sanitizeRichHtml = (value: string) => {
  const parsed = new DOMParser().parseFromString(value, "text/html");
  const allowed = new Set(["P","BR","H1","H2","H3","BLOCKQUOTE","UL","OL","LI","STRONG","B","EM","I","U","S","A","HR","TABLE","THEAD","TBODY","TR","TH","TD","SECTION","DIV","ASIDE","FIGURE","FIGCAPTION","IMG","SPAN","FONT"]);
  parsed.body.querySelectorAll("*").forEach(node => {
    if (!allowed.has(node.tagName)) { node.replaceWith(...node.childNodes); return; }
    [...node.attributes].forEach(attribute => {
      const name = attribute.name.toLowerCase();
      const permitted = ["class","href","target","rel","src","alt","face","color","size","style"].includes(name);
      if (!permitted || name.startsWith("on") || name === "id") node.removeAttribute(attribute.name);
    });
    if (node instanceof HTMLElement && node.classList.contains("is-editor-selected")) {
      node.classList.remove("is-editor-selected");
      if (!node.className) node.removeAttribute("class");
    }
    if (node instanceof HTMLElement && node.hasAttribute("style")) {
      const allowedStyles = new Set(["background-color","color","font-family","font-size","text-align","width","max-width","border-radius","padding","column-gap","object-fit"]);
      [...node.style].forEach(property => { if (!allowedStyles.has(property)) node.style.removeProperty(property); });
      if (!node.getAttribute("style")?.trim()) node.removeAttribute("style");
    }
    if (node instanceof HTMLAnchorElement && !/^(https?:|mailto:)/i.test(node.href)) node.removeAttribute("href");
    if (node instanceof HTMLImageElement && !/^data:image\/(?:png|jpe?g|webp|gif);base64,/i.test(node.src)) node.remove();
  });
  return parsed.body.innerHTML;
};
const replaceRichText = (content: string, original: string, replacement: string) => {
  if (!content.startsWith(RICH_DOCUMENT_PREFIX)) return content.replace(original, replacement);
  const parsed = new DOMParser().parseFromString(content.slice(RICH_DOCUMENT_PREFIX.length), "text/html");
  const walker = document.createTreeWalker(parsed.body, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let text = "";
  while (walker.nextNode()) { const node = walker.currentNode as Text; nodes.push(node); text += node.data; }
  const start = text.indexOf(original);
  if (start < 0) return content;
  let offset = 0;
  for (const node of nodes) {
    const end = offset + node.data.length;
    if (start >= offset && start + original.length <= end) {
      const local = start - offset;
      node.data = `${node.data.slice(0, local)}${replacement}${node.data.slice(local + original.length)}`;
      return RICH_DOCUMENT_PREFIX + parsed.body.innerHTML;
    }
    offset = end;
  }
  return content;
};
const suggestionDismissKey = (suggestion: WritingReviewSuggestion) => `${suggestion.category}|${suggestion.title.trim().toLowerCase()}|${(suggestion.original ?? "").trim().toLowerCase()}`;
const isLocalDraft = (document: Document | null) => document?.id.startsWith("local-draft:") ?? false;
const hasWrittenContent = (value: string) => richTextFromContent(value).trim().length > 0;
const localDraftDocument = (notebook: string): Document => {
  const now = new Date().toISOString();
  return { id: `local-draft:${crypto.randomUUID()}`, project_id: null, title: "Untitled", content: "", document_type: "quick_note", status: "inbox", tags: notebook ? [`notebook:${notebook}`] : [], archived: false, exclude_from_ai: false, review_at: null, version: 1, extraction_status: "not_requested", extraction_version: 0, extracted_data: null, extraction_error: null, created_at: now, updated_at: now };
};
const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
};
const EXPORT_STYLE_PROPERTIES = [
  "display", "box-sizing", "position", "float", "clear", "overflow", "overflow-wrap",
  "width", "min-width", "max-width", "height", "min-height", "max-height", "aspect-ratio",
  "margin", "padding", "gap", "column-gap", "columns", "grid-template-columns", "grid-template-rows",
  "align-items", "align-content", "justify-items", "justify-content", "place-items",
  "font", "font-family", "font-size", "font-style", "font-weight", "font-variant", "line-height",
  "letter-spacing", "text-align", "text-decoration", "text-transform", "text-indent", "white-space",
  "color", "background", "background-color", "border", "border-top", "border-right", "border-bottom",
  "border-left", "border-radius", "border-collapse", "border-spacing", "box-shadow", "opacity",
  "object-fit", "object-position", "vertical-align", "list-style", "list-style-position",
] as const;
const copyRenderedStyles = (source: HTMLElement, target: HTMLElement) => {
  const computed = window.getComputedStyle(source);
  EXPORT_STYLE_PROPERTIES.forEach(property => {
    const value = computed.getPropertyValue(property);
    if (value) target.style.setProperty(property, value);
  });
  target.removeAttribute("contenteditable");
  target.removeAttribute("role");
  target.removeAttribute("aria-label");
  target.removeAttribute("aria-multiline");
  target.removeAttribute("data-placeholder");
  const sourceChildren = [...source.children].filter((child): child is HTMLElement => child instanceof HTMLElement);
  const targetChildren = [...target.children].filter((child): child is HTMLElement => child instanceof HTMLElement);
  sourceChildren.forEach((child, index) => { if (targetChildren[index]) copyRenderedStyles(child, targetChildren[index]); });
};
const dataUrlBytes = (dataUrl: string) => {
  const binary = window.atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  return Uint8Array.from(binary, character => character.charCodeAt(0));
};
const splitCanvasIntoPages = (canvas: HTMLCanvasElement, background: string, pageAspect = 297 / 210) => {
  const pageHeight = Math.max(1, Math.floor(canvas.width * pageAspect));
  const pages: Array<{ data: Uint8Array; width: number; height: number }> = [];
  for (let top = 0; top < canvas.height; top += pageHeight) {
    const sliceHeight = Math.min(pageHeight, canvas.height - top);
    const page = document.createElement("canvas");
    page.width = canvas.width;
    page.height = sliceHeight;
    const context = page.getContext("2d");
    if (!context) throw new Error("Canvas export is unavailable.");
    context.fillStyle = background;
    context.fillRect(0, 0, page.width, page.height);
    context.drawImage(canvas, 0, top, canvas.width, sliceHeight, 0, 0, canvas.width, sliceHeight);
    pages.push({ data: dataUrlBytes(page.toDataURL("image/png")), width: page.width, height: page.height });
  }
  return pages;
};
function RichDocumentSurface({ documentId, initialHtml, editorRef, onChange, onSelect }: { documentId: string; initialHtml: string; editorRef: { current: HTMLDivElement | null }; onChange: () => void; onSelect: (target: EventTarget | null) => void }) {
  useEffect(() => {
    if (editorRef.current) editorRef.current.innerHTML = sanitizeRichHtml(initialHtml);
  }, [documentId]);
  return <div ref={editorRef} className="writing-rich-editor" role="textbox" aria-label="Content" aria-multiline="true" contentEditable suppressContentEditableWarning spellCheck onInput={onChange} onClick={event => onSelect(event.target)} data-placeholder="Start writing…" />;
}

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
  const [listCollapsed, setListCollapsed] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem("orin.writing-list-collapsed.v1") === "true",
  );
  const [listWidth, setListWidth] = useState(
    () => typeof window !== "undefined" ? Number(window.localStorage.getItem("orin.writing-list-width.v1")) || 320 : 320,
  );
  const [libraryMode, setLibraryMode] = useState<"notes" | "notebooks">("notes");
  const [fullScreen, setFullScreen] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(() => typeof window === "undefined" || window.innerWidth >= 1480);
  const [inspectorTab, setInspectorTab] = useState<"review" | "design" | "details">("review");
  const [liveReview, setLiveReview] = useState(() => typeof window === "undefined" || window.localStorage.getItem("orin.writing-live-review.v1") !== "false");
  const [reviewState, setReviewState] = useState<"idle" | "reviewing" | "ready" | "error">("idle");
  const [writingReview, setWritingReview] = useState<WritingLiveReview | null>(null);
  const [dismissedSuggestions, setDismissedSuggestions] = useState<string[]>([]);
  const [tableDialogOpen, setTableDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exporting, setExporting] = useState<"html" | "docx" | "md" | "pdf" | null>(null);
  const [tableRows, setTableRows] = useState(3);
  const [tableColumns, setTableColumns] = useState(3);
  const [selectedDesignKind, setSelectedDesignKind] = useState("");
  const [notebooks, setNotebooks] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(window.localStorage.getItem(`orin.writing-notebooks.${userId}.v1`) ?? "[]"); } catch { return []; }
  });
  const [notebookFilter, setNotebookFilter] = useState("");
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
  const editor = useRef<HTMLDivElement>(null);
  const replaceDocumentContent = (next: string) => {
    setContent(next);
    if (editor.current) editor.current.innerHTML = sanitizeRichHtml(richHtmlFromContent(next));
  };
  const writingDetailsRef = useRef<HTMLDetailsElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const selectedDesignElement = useRef<HTMLElement | null>(null);
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
  const visibleDocuments = useMemo(() => notebookFilter
    ? documents.filter(document => document.tags.includes(`notebook:${notebookFilter}`))
    : documents, [documents, notebookFilter]);
  const allNotebooks = useMemo(() => [...new Set([
    ...notebooks,
    ...documents.flatMap(document => document.tags.filter(tag => tag.startsWith("notebook:")).map(tag => tag.slice(9))),
  ])].filter(Boolean).sort((a, b) => a.localeCompare(b)), [notebooks, documents]);
  const createNotebook = () => {
    const name = window.prompt("Notebook name")?.trim();
    if (!name || notebooks.includes(name)) return;
    const next = [...notebooks, name].sort((a, b) => a.localeCompare(b));
    setNotebooks(next);
    setNotebookFilter(name);
    window.localStorage.setItem(`orin.writing-notebooks.${userId}.v1`, JSON.stringify(next));
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
    window.localStorage.setItem("orin.writing-live-review.v1", String(liveReview));
    const reviewText = richTextFromContent(content);
    if (!selected || !liveReview || excludeAI || reviewText.length < 40) {
      setReviewState("idle");
      setWritingReview(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setReviewState("reviewing");
      void request<WritingLiveReview>("/knowledge/review-live", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ title: title.trim() || "Untitled", content: reviewText }),
      }).then(result => {
        if (controller.signal.aborted) return;
        setWritingReview(result);
        setReviewState("ready");
      }).catch(cause => {
        if (controller.signal.aborted) return;
        setReviewState("error");
        if (!(cause instanceof ApiError && cause.status === 429)) setWritingReview(null);
      });
    }, 550);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [selected?.id, title, content, liveReview, excludeAI]);
  useEffect(() => {
    if (!selected) { setDismissedSuggestions([]); return; }
    try { setDismissedSuggestions(JSON.parse(localStorage.getItem(`orin.writing-dismissed.${userId}.${selected.id}`) ?? "[]")); }
    catch { setDismissedSuggestions([]); }
  }, [selected?.id, userId]);
  const dismissWritingSuggestion = (suggestion: WritingReviewSuggestion) => {
    const key = suggestionDismissKey(suggestion);
    setDismissedSuggestions(current => {
      const next = [...new Set([...current, key])].slice(-100);
      if (selected) localStorage.setItem(`orin.writing-dismissed.${userId}.${selected.id}`, JSON.stringify(next));
      return next;
    });
  };

  const applyWritingSuggestion = (suggestion: WritingReviewSuggestion) => {
    if (!suggestion.original || !suggestion.replacement) return;
    const next = replaceRichText(content, suggestion.original, suggestion.replacement);
    if (next === content) {
      setMessage("The draft changed, so this suggestion is no longer applicable.");
      return;
    }
    setContent(next);
    if (editor.current) editor.current.innerHTML = sanitizeRichHtml(richHtmlFromContent(next));
    dismissWritingSuggestion(suggestion);
    setMessage("Suggestion applied · Unsaved changes");
  };
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
    // A new note starts with collapsed metadata; autosaving its local draft
    // must not unexpectedly collapse details while the user edits them.
    if (writingDetailsRef.current) writingDetailsRef.current.open = false;
    setCreating(true);
    setMobileEditor(true);
    setError("");
    try {
      if (!template) {
        const local = localDraftDocument(notebookFilter);
        activeDocumentId.current = local.id;
        setSelected(local);
        setTitle(local.title);
        setContent("");
        setType(local.document_type);
        setTagsInput(local.tags.join(", "));
        setStatus(local.status);
        setProjectId("");
        setExcludeAI(false);
        setReviewAt("");
        setVersions([]);
        setLinks({ links: [], backlinks: [] });
        setRecovery(null);
        setMessage("Not saved yet");
        requestAnimationFrame(() => editor.current?.focus());
        return;
      }
      activeDocumentId.current = null;
      setSelected(null);
      const doc = await request<Document>("/knowledge/documents", {
        method: "POST",
        body: JSON.stringify({
          title: template?.title ?? "Untitled",
          content: template?.content ?? "",
          document_type: template?.document_type ?? "quick_note",
          status: template ? "developing" : "inbox",
          tags: notebookFilter ? [`notebook:${notebookFilter}`] : [],
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
        if (isLocalDraft(latest.current.selected)) {
          const snapshot = latest.current.draft;
          if (!hasWrittenContent(snapshot.content)) {
            setMessage("Not saved yet");
            return true;
          }
          const created = await request<Document>("/knowledge/documents", {
            method: "POST",
            body: JSON.stringify(snapshot),
          });
          latest.current = { selected: created, draft: documentDraft(created) };
          setSelected(created);
          activeDocumentId.current = created.id;
          setMessage("Saved");
          void refresh().catch(() => undefined);
          return true;
        }
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
      if (event.key === "Escape" && fullScreen) {
        setFullScreen(false);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void create();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [fullScreen]);
  const resizeList = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = listWidth;
    const move = (moveEvent: PointerEvent) => {
      const next = Math.min(480, Math.max(240, startWidth + moveEvent.clientX - startX));
      setListWidth(next);
    };
    const finish = (upEvent: PointerEvent) => {
      const next = Math.min(480, Math.max(240, startWidth + upEvent.clientX - startX));
      setListWidth(next);
      window.localStorage.setItem("orin.writing-list-width.v1", String(next));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
  };
  const syncRichEditor = () => {
    if (!editor.current) return;
    setContent(RICH_DOCUMENT_PREFIX + sanitizeRichHtml(editor.current.innerHTML));
    setMessage("Unsaved changes");
  };
  const editorCommand = (command: string, value?: string) => {
    editor.current?.focus();
    document.execCommand(command, false, value);
    syncRichEditor();
  };
  const insertVisualBlock = (html: string) => {
    const surface = editor.current;
    if (!surface) return;
    const selection = window.getSelection();
    let anchor = selection?.rangeCount ? selection.getRangeAt(0).startContainer : null;
    let block = anchor instanceof HTMLElement ? anchor : anchor?.parentElement ?? null;
    while (block?.parentElement && block.parentElement !== surface) block = block.parentElement;
    const template = document.createElement("template");
    template.innerHTML = sanitizeRichHtml(html);
    const inserted = [...template.content.childNodes];
    if (block?.parentElement === surface) block.after(template.content); else surface.append(template.content);
    const last = inserted.at(-1);
    if (last && selection) {
      const range = document.createRange();
      range.selectNodeContents(last);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
    }
    surface.focus();
    syncRichEditor();
  };
  const insertTable = () => {
    const headers = Array.from({length: tableColumns}, (_, index) => `<th>Heading ${index + 1}</th>`).join("");
    const rows = Array.from({length: tableRows}, () => `<tr>${Array.from({length: tableColumns}, () => "<td>Cell</td>").join("")}</tr>`).join("");
    insertVisualBlock(`<table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table><p><br></p>`);
    setTableDialogOpen(false);
  };
  const chooseDesignElement = (target: EventTarget | null) => {
    if (!(target instanceof HTMLElement)) return;
    const element = target.closest<HTMLElement>("table,.magazine-columns,.magazine-callout,.magazine-shape,.magazine-image,blockquote,h1,h2,h3,p");
    selectedDesignElement.current?.classList.remove("is-editor-selected");
    selectedDesignElement.current = element;
    element?.classList.add("is-editor-selected");
    setSelectedDesignKind(element ? (element.classList.contains("magazine-columns") ? "Columns" : element.classList.contains("magazine-callout") ? "Callout" : element.classList.contains("magazine-shape") ? "Shape" : element.classList.contains("magazine-image") ? "Image" : element.tagName === "TABLE" ? "Table" : readable(element.tagName.toLowerCase())) : "");
  };
  const updateSelectedDesign = (property: string, value: string) => {
    const element = selectedDesignElement.current;
    if (!element) { setMessage("Select an element in the page first."); return; }
    element.style.setProperty(property, value);
    syncRichEditor();
  };
  const removeSelectedDesign = () => {
    const element = selectedDesignElement.current;
    if (!element) return;
    const next = element.nextElementSibling;
    element.remove();
    selectedDesignElement.current = null;
    setSelectedDesignKind("");
    syncRichEditor();
    (next as HTMLElement | null)?.focus?.();
  };
  const insertImage = async (file: File) => {
    if (!file.type.startsWith("image/")) { setError("Choose a PNG, JPEG, WebP, or GIF image."); return; }
    if (file.size > 8 * 1024 * 1024) { setError("Images must be smaller than 8 MB."); return; }
    const source = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file); });
    const compressed = await new Promise<string>((resolve, reject) => {
      const image = new Image(); image.onload = () => { const scale = Math.min(1, 1600 / Math.max(image.width, image.height)); const canvas = document.createElement("canvas"); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale)); canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height); resolve(canvas.toDataURL("image/jpeg", .82)); }; image.onerror = reject; image.src = source;
    });
    insertVisualBlock(`<figure class="magazine-image"><img src="${compressed}" alt="${escapeHtml(file.name.replace(/\.[^.]+$/, ""))}"><figcaption>Write a caption…</figcaption></figure><p><br></p>`);
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
  const deleteDocument = async () => {
    if (!selected || !window.confirm(`Delete “${title.trim() || "Untitled"}” permanently? This cannot be undone.`)) return;
    if (!isLocalDraft(selected)) {
      try {
        await request(`/knowledge/documents/${selected.id}`, { method: "DELETE" });
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Note could not be deleted.");
        return;
      }
    }
    try { localStorage.removeItem(draftKey(selected.id)); } catch { /* Storage may be restricted. */ }
    activeDocumentId.current = null;
    setSelected(null);
    setTitle("");
    setContent("");
    setMessage("Note deleted.");
    await refresh();
  };
  const selectNotebook = (notebook: string) => {
    const ordinary = tagsInput.split(",").map(tag => tag.trim()).filter(tag => tag && !tag.startsWith("notebook:"));
    setTagsInput([...ordinary, ...(notebook ? [`notebook:${notebook}`] : [])].join(", "));
    setMessage(isLocalDraft(selected) ? "Not saved yet" : "Unsaved changes");
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
      setSelected(full); setTitle(full.title); replaceDocumentContent(full.content);
      setType(full.document_type); setTagsInput(full.tags.join(", ")); setStatus(full.status);
      setProjectId(full.project_id ?? ""); setExcludeAI(full.exclude_from_ai);
      setReviewAt(full.review_at ? localDateTime(full.review_at) : "");
      failedDraft.current = null; setConflict(false); setError(""); setMessage("Newer version loaded");
    } catch (e) { setError(e instanceof ApiError ? e.message : "The newer note could not be loaded."); }
  };
  const candidates = documents.filter((item) => item.id !== selected?.id);
  const manuscriptText = richTextFromContent(content);
  const wordCount = manuscriptText.trim() ? manuscriptText.trim().split(/\s+/u).length : 0;
  const characterCount = manuscriptText.length;
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 200));
  const exportDocument = async (format: "html" | "docx" | "md" | "pdf") => {
    if (!selected) return;
    setExporting(format);
    setError("");
    const safeTitle = escapeHtml(title.trim() || "Untitled");
    const body = sanitizeRichHtml(richHtmlFromContent(content));
    const filename = (title.trim() || "untitled").replace(/[\\/:*?\"<>|]/g, "-");
    let renderedPage: HTMLElement | null = null;
    let exportBackground = "#fffdf8";
    try {
      const visibleSurface = editor.current ?? document.querySelector<HTMLElement>(".writing-document-preview");
      const stagingSurface = document.createElement("article");
      stagingSurface.className = "writing-rich-editor writing-document-preview writing-export-staging";
      stagingSurface.innerHTML = body;
      if (!visibleSurface) {
        const host = document.querySelector<HTMLElement>(".writing-paper") ?? document.body;
        host.append(stagingSurface);
      }
      const sourceSurface = visibleSurface ?? stagingSurface;
      const sourceWidth = Math.max(620, Math.round(sourceSurface.getBoundingClientRect().width || 820));
      const clonedSurface = sourceSurface.cloneNode(true) as HTMLElement;
      copyRenderedStyles(sourceSurface, clonedSurface);
      clonedSurface.style.width = "100%";
      clonedSurface.style.minHeight = "0";
      clonedSurface.style.height = "auto";
      clonedSurface.style.paddingBottom = "0";
      clonedSurface.style.outline = "0";
      renderedPage = document.createElement("article");
      renderedPage.className = "writing-export-page";
      renderedPage.style.width = `${sourceWidth + 144}px`;
      renderedPage.style.minHeight = "0";
      const paperStyle = window.getComputedStyle(sourceSurface.closest(".writing-paper") ?? sourceSurface);
      exportBackground = paperStyle.backgroundColor === "rgba(0, 0, 0, 0)" ? "#fffdf8" : paperStyle.backgroundColor;
      renderedPage.style.backgroundColor = exportBackground;
      renderedPage.style.color = window.getComputedStyle(sourceSurface).color;
      renderedPage.innerHTML = `<h1 class="writing-export-title">${safeTitle}</h1>`;
      const exportTitle = renderedPage.querySelector<HTMLElement>(".writing-export-title");
      if (exportTitle) exportTitle.style.cssText = "margin:0 0 1.05em;font:700 46px/1.08 Georgia,'Times New Roman',serif;letter-spacing:-.035em;color:inherit";
      renderedPage.append(clonedSurface);
      document.body.append(renderedPage);
      stagingSurface.remove();
      const exactMarkup = renderedPage.outerHTML;
      const completeHtml = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${safeTitle}</title><style>html{background:#e9ece9}body{margin:0;padding:32px}.writing-export-page{position:relative!important;left:auto!important;top:auto!important;z-index:auto!important;margin:0 auto;max-width:calc(100vw - 64px);box-shadow:0 18px 70px #17271e26}.writing-export-page *{box-sizing:border-box}@media(max-width:700px){body{padding:0}.writing-export-page{max-width:100%;padding:36px 24px!important;box-shadow:none}}</style></head><body>${exactMarkup}</body></html>`;
      const styledMarkdown = `<!-- This Markdown file contains styled HTML so the note keeps its original Orin layout. -->\n\n<style>html{background:#e9ece9}body{margin:0;padding:32px}.writing-export-page{position:relative!important;left:auto!important;top:auto!important;z-index:auto!important;margin:0 auto;max-width:calc(100vw - 64px);box-shadow:0 18px 70px #17271e26}.writing-export-page *{box-sizing:border-box}</style>\n\n${exactMarkup}\n`;
      if (format === "html") saveBlob(new Blob([completeHtml], { type: "text/html;charset=utf-8" }), `${filename}.html`);
      if (format === "md") saveBlob(new Blob([styledMarkdown], { type: "text/markdown;charset=utf-8" }), `${filename}.md`);
      let renderedCanvas: HTMLCanvasElement | null = null;
      if (format === "docx" || format === "pdf") {
        const { default: html2canvas } = await import("html2canvas");
        renderedCanvas = await html2canvas(renderedPage, { scale: 2, backgroundColor: exportBackground, useCORS: true, logging: false, imageTimeout: 15000 });
      }
      if (format === "docx") {
        if (!renderedCanvas) throw new Error("The document could not be rendered.");
        const { Document: DocxDocument, Packer, Paragraph, ImageRun } = await import("docx");
        const pages = splitCanvasIntoPages(renderedCanvas, exportBackground);
        const pageWidth = 746;
        const children = pages.map((page, index) => new Paragraph({
          pageBreakBefore: index > 0,
          spacing: { before: 0, after: 0 },
          children: [new ImageRun({ data: page.data, type: "png", transformation: { width: pageWidth, height: Math.round(pageWidth * page.height / page.width) }, altText: { title: title.trim() || "Untitled", description: `Styled page ${index + 1}`, name: `Page ${index + 1}` } })],
        }));
        saveBlob(await Packer.toBlob(new DocxDocument({ sections: [{ properties: { page: { margin: { top: 360, right: 360, bottom: 360, left: 360 } } }, children }] })), `${filename}.docx`);
      }
      if (format === "pdf") {
        if (!renderedCanvas) throw new Error("The document could not be rendered.");
        const { jsPDF } = await import("jspdf");
        const pages = splitCanvasIntoPages(renderedCanvas, exportBackground);
        const pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
        pages.forEach((page, index) => {
          if (index) pdf.addPage();
          const height = 210 * page.height / page.width;
          pdf.addImage(page.data, "PNG", 0, 0, 210, height, undefined, "FAST");
        });
        pdf.save(`${filename}.pdf`);
      }
      setExportDialogOpen(false);
      setMessage(`Exported ${format.toUpperCase()}`);
    } catch (exception) {
      console.error("Document export failed", exception);
      setError(`The ${format.toUpperCase()} export could not be created.`);
    } finally { renderedPage?.remove(); setExporting(null); }
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
      replaceDocumentContent(restored.content);
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
      className={`writing-workspace ${mobileEditor ? "writing-mobile-editor" : ""} ${focusMode ? "writing-focus-mode" : ""} ${listCollapsed ? "writing-list-collapsed" : ""} ${inspectorOpen ? "writing-inspector-open" : ""} ${fullScreen ? "writing-fullscreen" : ""}`}
      style={{ "--writing-list-width": `${listWidth}px` } as CSSProperties}
      aria-label="Creative Studio"
    >
      <aside className="writing-list">
        <header className="writing-list-header">
          <div className="writing-brand">
            <Pencil aria-hidden="true" size={20} />
            <div>
              <h2>Writing</h2>
              <p>{notebookFilter || "All notes"}</p>
            </div>
            <button className="writing-sidebar-toggle" type="button"
              aria-label={listCollapsed ? "Expand notes sidebar" : "Collapse notes sidebar"}
              title={listCollapsed ? "Expand notes sidebar" : "Collapse notes sidebar"}
              onClick={() => setListCollapsed((value) => {
                const next = !value;
                window.localStorage.setItem("orin.writing-list-collapsed.v1", String(next));
                return next;
              })}>
              {listCollapsed ? <PanelLeftOpen size={17}/> : <PanelLeftClose size={17}/>}
            </button>
          </div>
          <div className="writing-collapsed-tools" aria-label="Collapsed writing tools">
            <button type="button" aria-label="Show notes" title="Notes" onClick={() => setLibraryMode("notes")}><FileText size={17}/></button>
            <button type="button" aria-label="Show notebooks" title="Notebooks" onClick={() => setLibraryMode("notebooks")}><BookOpen size={17}/></button>
            <button type="button" aria-label="Create note" title="New note" onClick={() => void create()}><Plus size={17}/></button>
          </div>
          <div className="writing-library-switch" role="tablist" aria-label="Writing library">
            <button type="button" role="tab" aria-selected={libraryMode === "notebooks"} onClick={() => setLibraryMode("notebooks")}>Notebooks</button>
            <button type="button" role="tab" aria-selected={libraryMode === "notes"} onClick={() => setLibraryMode("notes")}>Notes</button>
          </div>
          {libraryMode === "notebooks" && <div className="writing-notebooks" aria-label="Notebooks">
            <div className="writing-notebooks-heading"><strong>Notebooks</strong><button type="button" onClick={createNotebook} aria-label="New notebook"><Plus size={14}/></button></div>
            <button type="button" className={!notebookFilter ? "active" : ""} onClick={() => {setNotebookFilter("");setLibraryMode("notes");}}>All notes <span>{documents.length}</span></button>
            {allNotebooks.map(notebook => <button type="button" key={notebook} className={notebookFilter === notebook ? "active" : ""} onClick={() => {setNotebookFilter(notebook);setLibraryMode("notes");}}>{notebook}<span>{documents.filter(document => document.tags.includes(`notebook:${notebook}`)).length}</span></button>)}
          </div>}
          <button
            className="writing-new"
            disabled={creating}
            onClick={() => void create()}
          >
            <Plus aria-hidden="true" size={16} /> New note <kbd>Ctrl N</kbd>
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
          {libraryMode === "notes" && <div className="writing-search-row">
            <div className="writing-search">
              <Search aria-hidden="true" size={14} />
              <input aria-label="Search documents" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search notes…" />
            </div>
            <button className="writing-filter-button" type="button" aria-label="Filter notes" aria-expanded={filterOpen} onClick={() => setFilterOpen(value => !value)}><SlidersHorizontal size={16}/></button>
            {filterOpen && <div className="writing-library-filter">
              <label>Type<select aria-label="Document type" value={documentTypeFilter} onChange={(event) => setDocumentTypeFilter(event.target.value)}><option value="">All notes</option><option value="idea">Ideas</option><option value="draft">Drafts</option><option value="research">Research</option><option value="quick_note">Quick notes</option></select></label>
              <label><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)}/> Include archived</label>
            </div>}
          </div>}

        </header>
        {libraryMode === "notes" && <nav className="writing-documents" aria-label="Notes">
          {visibleDocuments.map((doc) => (
            <button
              key={doc.id}
              className={`writing-document ${selected?.id === doc.id ? "selected" : ""}`}
              onClick={() => void open(doc)}
            >
              <span className="writing-document-icon" aria-hidden="true">
                <FileText size={16} />
              </span>
              <span className="writing-document-copy">
                <strong>{doc.title || "Untitled"}</strong>
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
          {!visibleDocuments.length && (
            <p className="writing-empty-list">
              {query
                ? "No notes match your search."
                : "Your notes will appear here."}
            </p>
          )}
        </nav>}
        <details id="writing-tools-popover" className="writing-tools writing-tools-popup" open={toolsOpen} onToggle={event => setToolsOpen(event.currentTarget.open)}>
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
      {!listCollapsed && <button type="button" className="writing-list-resizer" aria-label="Resize notes sidebar" title="Drag to resize notes sidebar" onPointerDown={resizeList} />}

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
              <button className="writing-preview-toggle" type="button" aria-label={previewMode ? "Return to editing" : "Preview document"} aria-pressed={previewMode} onClick={() => setPreviewMode(value => !value)}><Eye size={16}/><span>{previewMode ? "Edit" : "Preview"}</span></button>
              <input
                className="writing-toolbar-title"
                aria-label="Document title"
                value={title}
                onChange={(event) => {
                  setTitle(event.target.value);
                  setMessage("Unsaved changes");
                }}
                placeholder="Untitled"
              />
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
              <button className="writing-quiet-action" type="button" aria-pressed={focusMode} onClick={() => setFocusMode((value) => !value)}>{focusMode ? "Exit focus" : "Focus"}</button>
              <button className="writing-inspector-toggle" type="button" aria-label="Writing tools" title="Writing tools" aria-expanded={toolsOpen} aria-controls="writing-tools-popover" onClick={() => setToolsOpen(value => !value)}><BookOpen size={17}/></button>
              <button className="writing-inspector-toggle" type="button" aria-label={inspectorOpen ? "Close inspector" : "Open inspector"} aria-pressed={inspectorOpen} onClick={() => setInspectorOpen(value => !value)}><FileSliders size={17}/></button>
              <details className="writing-more-menu"><summary role="button" aria-label="Manage document"><MoreVertical size={19}/></summary><div className="writing-document-menu">
                <button type="button" onClick={event => { (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); setInspectorTab("details"); setInspectorOpen(true); }}><FileSliders size={15}/>Details</button>
                <label><FolderKanban size={15}/><span>Project</span><select aria-label="Document project" value={projectId} onChange={event => {setProjectId(event.target.value);setMessage(isLocalDraft(selected) ? "Not saved yet" : "Unsaved changes");}}><option value="">No project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
                <label><BookOpen size={15}/><span>Notebook</span><select aria-label="Document notebook" value={tagsInput.split(",").map(tag=>tag.trim()).find(tag=>tag.startsWith("notebook:"))?.slice(9) ?? ""} onChange={event => selectNotebook(event.target.value)}><option value="">No notebook</option>{allNotebooks.map(notebook => <option key={notebook}>{notebook}</option>)}</select></label>
                <button type="button" onClick={event => { (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); setExportDialogOpen(true); }} disabled={isLocalDraft(selected)}><FileDown size={15}/>Export document…</button>
                <button type="button" onClick={() => setFullScreen(value => !value)}><PanelLeftOpen size={15}/>{fullScreen ? "Exit full screen" : "Full screen"}</button>
                <button type="button" onClick={() => void archive()} disabled={isLocalDraft(selected)}><Archive size={15}/>{selected.archived ? "Restore note" : "Archive note"}</button>
                <button className="danger" type="button" onClick={() => void deleteDocument()}><Trash2 size={15}/>Delete note</button>
              </div></details>
            </header>
            {!previewMode && <div
              className="writing-formatbar"
              role="toolbar"
              aria-label="Document design tools"
            >
              <select aria-label="Text style" defaultValue="p" onChange={event => editorCommand("formatBlock", event.target.value)}><option value="p">Body</option><option value="h1">Title</option><option value="h2">Heading</option><option value="h3">Subheading</option><option value="blockquote">Quote</option></select>
              <select aria-label="Font family" defaultValue="Georgia" onChange={event => editorCommand("fontName", event.target.value)}><option value="Georgia">Editorial serif</option><option value="DM Sans">Clean sans</option><option value="Manrope">Display</option><option value="monospace">Mono</option></select>
              <select aria-label="Font size" defaultValue="3" onChange={event => editorCommand("fontSize", event.target.value)}><option value="2">14</option><option value="3">16</option><option value="4">18</option><option value="5">24</option><option value="6">32</option></select>
              <span className="writing-toolbar-group">
                <button type="button" title="Bold" aria-label="Bold" onClick={() => editorCommand("bold")}><Bold size={15}/></button>
                <button type="button" title="Italic" aria-label="Italic" onClick={() => editorCommand("italic")}><Italic size={15}/></button>
                <button type="button" title="Underline" aria-label="Underline" onClick={() => editorCommand("underline")}><Underline size={15}/></button>
              </span>
              <span className="writing-toolbar-group">
                <button type="button" title="Bulleted list" aria-label="Bulleted list" onClick={() => editorCommand("insertUnorderedList")}><List size={15}/></button>
                <button type="button" title="Numbered list" aria-label="Numbered list" onClick={() => editorCommand("insertOrderedList")}><ListChecks size={15}/></button>
                <button type="button" title="Quote" aria-label="Quote" onClick={() => editorCommand("formatBlock", "blockquote")}><Quote size={15}/></button>
                <button type="button" title="Link" aria-label="Link" onClick={() => { const url=window.prompt("Paste a link"); if(url) editorCommand("createLink",url); }}><Link2 size={15}/></button>
              </span>
              <label className="writing-color-control" title="Text color"><span className="writing-color-letter">A</span><input aria-label="Text color" type="color" defaultValue="#223129" onInput={event => editorCommand("foreColor", event.currentTarget.value)}/></label>
              <label className="writing-color-control" title="Highlight"><Highlighter size={15}/><input aria-label="Highlight color" type="color" defaultValue="#f6e59f" onInput={event => editorCommand("hiliteColor", event.currentTarget.value)}/></label>
              <span className="writing-toolbar-group"><button type="button" aria-label="Align left" title="Align left" onClick={() => editorCommand("justifyLeft")}><AlignLeft size={15}/></button><button type="button" aria-label="Align center" title="Align center" onClick={() => editorCommand("justifyCenter")}><AlignCenter size={15}/></button><button type="button" aria-label="Align right" title="Align right" onClick={() => editorCommand("justifyRight")}><AlignRight size={15}/></button></span>
              <span className="writing-toolbar-group writing-insert-group">
                <details className="writing-toolbar-menu"><summary>Insert <ChevronDown size={13}/></summary><div>
                  <button type="button" aria-label="Insert divider" onClick={() => insertVisualBlock('<hr><p><br></p>')}><Minus size={15}/>Divider</button>
                  <button type="button" aria-label="Insert table" onClick={() => setTableDialogOpen(true)}><Table2 size={15}/>Table</button>
                  <button type="button" aria-label="Insert magazine columns" onClick={() => insertVisualBlock('<section class="magazine-columns"><div><h3>First story</h3><p>Write the first column…</p></div><div><h3>Second story</h3><p>Write the second column…</p></div></section><p><br></p>')}><Columns3 size={15}/>Columns</button>
                  <button type="button" aria-label="Insert three columns" onClick={() => insertVisualBlock('<section class="magazine-columns magazine-columns-three"><div><h3>Story one</h3><p>Write here…</p></div><div><h3>Story two</h3><p>Write here…</p></div><div><h3>Story three</h3><p>Write here…</p></div></section><p><br></p>')}><Columns3 size={15}/>Three columns</button>
                  <button type="button" aria-label="Insert styled text area" onClick={() => insertVisualBlock('<aside class="magazine-callout"><h3>Key idea</h3><p>Add supporting text here…</p></aside><p><br></p>')}><Heading2 size={15}/>Callout</button>
                  <button type="button" aria-label="Insert pull quote" onClick={() => insertVisualBlock('<blockquote>Write a memorable pull quote…</blockquote><p><br></p>')}><Quote size={15}/>Pull quote</button>
                  <button type="button" aria-label="Insert feature shape" onClick={() => insertVisualBlock('<div class="magazine-shape">Feature</div><p><br></p>')}><Sparkles size={15}/>Feature badge</button>
                  <button type="button" aria-label="Insert image" onClick={() => imageInput.current?.click()}><ImagePlus size={15}/>Image</button>
                </div></details><input ref={imageInput} className="writing-image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={event => { const file=event.target.files?.[0]; if(file) void insertImage(file); event.currentTarget.value=""; }}/>
              </span>
            </div>}
            <div className={`writing-paper ${previewMode ? "writing-paper-preview" : ""}`}>
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
                      replaceDocumentContent(recovery.draft.content);
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
              {previewMode ? <article className="writing-rich-editor writing-document-preview" aria-label="Document preview" dangerouslySetInnerHTML={{__html:sanitizeRichHtml(richHtmlFromContent(content))}} /> : <RichDocumentSurface documentId={selected.id} initialHtml={richHtmlFromContent(content)} editorRef={editor} onChange={syncRichEditor} onSelect={chooseDesignElement} />}
              {tableDialogOpen && <div className="writing-table-dialog-backdrop" role="presentation"><section className="writing-table-dialog" role="dialog" aria-modal="true" aria-labelledby="table-dialog-title"><header><div><h2 id="table-dialog-title">Insert table</h2><p>Choose the exact structure. You can edit every cell after inserting.</p></div><button type="button" aria-label="Close table dialog" onClick={() => setTableDialogOpen(false)}><X size={17}/></button></header><div><label>Columns<input aria-label="Table columns" type="number" min="1" max="12" value={tableColumns} onChange={event => setTableColumns(Math.min(12,Math.max(1,Number(event.target.value))))}/></label><label>Rows<input aria-label="Table rows" type="number" min="1" max="30" value={tableRows} onChange={event => setTableRows(Math.min(30,Math.max(1,Number(event.target.value))))}/></label></div><div className="writing-table-preview" style={{gridTemplateColumns:`repeat(${tableColumns},1fr)`}}>{Array.from({length:Math.min(tableRows,6)*tableColumns},(_,index)=><i key={index}/>)}</div><footer><button type="button" onClick={() => setTableDialogOpen(false)}>Cancel</button><button type="button" onClick={insertTable}>Insert {tableRows} × {tableColumns} table</button></footer></section></div>}
              {exportDialogOpen && <div className="writing-table-dialog-backdrop" role="presentation"><section className="writing-export-dialog" role="dialog" aria-modal="true" aria-labelledby="export-dialog-title"><header><div><h2 id="export-dialog-title">Export document</h2><p>Choose a format for this note.</p></div><button type="button" aria-label="Close export dialog" onClick={() => setExportDialogOpen(false)} disabled={!!exporting}><X size={17}/></button></header><div className="writing-export-options">
                <button type="button" onClick={() => void exportDocument("html")} disabled={!!exporting}><strong>HTML</strong><span>Styled web page</span></button>
                <button type="button" onClick={() => void exportDocument("docx")} disabled={!!exporting}><strong>DOCX</strong><span>Microsoft Word document</span></button>
                <button type="button" onClick={() => void exportDocument("md")} disabled={!!exporting}><strong>Markdown</strong><span>Portable plain text</span></button>
                <button type="button" onClick={() => void exportDocument("pdf")} disabled={!!exporting}><strong>PDF</strong><span>Print-ready fixed layout</span></button>
              </div>{exporting && <p role="status" className="writing-export-progress">Creating {exporting.toUpperCase()}…</p>}</section></div>}
              <div className="writing-manuscript-stats" aria-live="polite">
                <span>{wordCount.toLocaleString()} words</span>
                <span>{characterCount.toLocaleString()} characters</span>
                <span>{readingMinutes} min read</span>
              </div>
            </div>
            <details ref={writingDetailsRef} className="writing-details">
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
                  Notebook
                  <select aria-label="Notebook" value={tagsInput.split(",").map(tag => tag.trim()).find(tag => tag.startsWith("notebook:"))?.slice(9) ?? ""}
                    onChange={event => {
                      const ordinary = tagsInput.split(",").map(tag => tag.trim()).filter(tag => tag && !tag.startsWith("notebook:"));
                      setTagsInput([...ordinary, ...(event.target.value ? [`notebook:${event.target.value}`] : [])].join(", "));
                      setMessage("Unsaved changes");
                    }}>
                    <option value="">No notebook</option>
                    {allNotebooks.map(notebook => <option key={notebook} value={notebook}>{notebook}</option>)}
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
            <Pencil aria-hidden="true" size={20} />
            <h2>Your space to think.</h2>
            <p>Capture thoughts, take notes, and write your ideas.</p>
            <button
              className="writing-new"
              disabled={creating}
              onClick={() => void create()}
            >
              <Plus aria-hidden="true" size={16} /> New note
            </button>
          </div>
        )}
      </main>
      {selected && inspectorOpen && <aside className="writing-inspector" aria-label="Document inspector">
        <div className="writing-inspector-tabs" role="tablist" aria-label="Inspector views">
          <button role="tab" aria-selected={inspectorTab === "review"} onClick={() => setInspectorTab("review")}>AI Review</button>
          <button role="tab" aria-selected={inspectorTab === "design"} onClick={() => setInspectorTab("design")}>Design</button>
          <button role="tab" aria-selected={inspectorTab === "details"} onClick={() => setInspectorTab("details")}>Note details</button>
          <button type="button" className="writing-inspector-close" aria-label="Close inspector" onClick={() => setInspectorOpen(false)}><X size={17}/></button>
        </div>
        <div className="writing-inspector-body">
          {inspectorTab === "review" && <section className="writing-review-panel">
            <header><Sparkles size={20}/><div><h2>AI Review</h2><p>Live editorial guidance while you write.</p></div></header>
            <label className="writing-live-toggle"><span><strong>Review as I type</strong><small>{excludeAI ? "Disabled for this private note" : reviewState === "reviewing" ? "Reviewing your latest changes…" : writingReview?.mode === "ai" ? `Live · ${writingReview.model}` : writingReview ? "Fast local review" : "Starts after 40 characters"}</small></span><input type="checkbox" checked={liveReview} disabled={excludeAI} onChange={event => setLiveReview(event.target.checked)}/></label>
            {reviewState === "reviewing" && <div className="writing-review-progress" role="status"><i/><span>Reading for clarity, flow, and tone</span></div>}
            {reviewState === "error" && <div className="writing-review-notice" role="alert">Live review paused. Keep writing—we’ll try again after your next change.</div>}
            {writingReview?.limitations.map(item => <div className="writing-review-notice" key={item}>{item}</div>)}
            {writingReview?.suggestions.filter(item => !dismissedSuggestions.includes(suggestionDismissKey(item))).map((item, index) => <article key={item.id} className={`review-${item.severity}`}>
              <span>{index + 1}</span><div><small>{item.category}</small><h3>{item.title}</h3><p>{item.message}</p>
              {item.original && <blockquote>{item.original}</blockquote>}
              <div>{item.replacement && <button type="button" onClick={() => applyWritingSuggestion(item)}>Apply change</button>}<button type="button" onClick={() => dismissWritingSuggestion(item)}>Dismiss</button></div></div>
            </article>)}
            {reviewState !== "reviewing" && manuscriptText.length >= 40 && writingReview && writingReview.suggestions.filter(item => !dismissedSuggestions.includes(suggestionDismissKey(item))).length === 0 && <div className="writing-inspector-empty"><strong>Looking polished.</strong><p>No new suggestions for this draft. Dismissed findings stay dismissed unless you restore them.</p></div>}
            {manuscriptText.length < 40 && <div className="writing-inspector-empty"><strong>Start writing freely.</strong><p>Live review begins once there is enough context to give useful feedback.</p></div>}
          </section>}
          {inspectorTab === "design" && <section className="writing-design-panel"><header><Palette size={20}/><div><h2>Design</h2><p>Click any element in the page, then edit its appearance here.</p></div></header>
            <div className="writing-selected-element"><span>Selected</span><strong>{selectedDesignKind || "Nothing selected"}</strong><small>{selectedDesignKind ? "Changes apply immediately." : "Choose a table, image, callout, columns, shape, heading, or paragraph."}</small></div>
            <h3>Layout</h3><div className="writing-design-controls"><label>Width<select aria-label="Selected element width" defaultValue="100%" disabled={!selectedDesignKind} onChange={event => updateSelectedDesign("width",event.target.value)}><option value="100%">Full width</option><option value="75%">Wide</option><option value="50%">Half</option><option value="33%">Third</option></select></label><label>Alignment<select aria-label="Selected element alignment" defaultValue="left" disabled={!selectedDesignKind} onChange={event => updateSelectedDesign("text-align",event.target.value)}><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label><label>Padding<input aria-label="Selected element padding" type="range" min="0" max="48" defaultValue="20" disabled={!selectedDesignKind} onChange={event => updateSelectedDesign("padding",`${event.target.value}px`)}/></label><label>Corners<input aria-label="Selected element corners" type="range" min="0" max="40" defaultValue="4" disabled={!selectedDesignKind} onChange={event => updateSelectedDesign("border-radius",`${event.target.value}px`)}/></label></div>
            <h3>Color</h3><div className="writing-design-colors"><label>Text<input aria-label="Selected element text color" type="color" defaultValue="#223129" disabled={!selectedDesignKind} onInput={event => updateSelectedDesign("color",event.currentTarget.value)}/></label><label>Background<input aria-label="Selected element background" type="color" defaultValue="#edf1e8" disabled={!selectedDesignKind} onInput={event => updateSelectedDesign("background-color",event.currentTarget.value)}/></label></div>
            {selectedDesignKind === "Image" && <label className="writing-design-fit">Image crop<select aria-label="Selected image fit" defaultValue="cover" onChange={event => { const image=selectedDesignElement.current?.querySelector("img"); if(image){image.style.objectFit=event.target.value;syncRichEditor();}}}><option value="cover">Fill frame</option><option value="contain">Show whole image</option></select></label>}
            <div className="writing-design-actions"><button type="button" disabled={!selectedDesignKind} onClick={() => {const element=selectedDesignElement.current;if(element){element.insertAdjacentHTML("afterend",element.outerHTML);syncRichEditor();}}}>Duplicate</button><button type="button" className="danger" disabled={!selectedDesignKind} onClick={removeSelectedDesign}>Remove</button></div>
            <h3>Add element</h3><div className="writing-inspector-grid"><button onClick={() => setTableDialogOpen(true)}>Table</button><button onClick={() => insertVisualBlock('<section class="magazine-columns"><div><h3>First story</h3><p>Write here…</p></div><div><h3>Second story</h3><p>Write here…</p></div></section><p><br></p>')}>2 columns</button><button onClick={() => insertVisualBlock('<section class="magazine-columns magazine-columns-three"><div><h3>One</h3><p>Write here…</p></div><div><h3>Two</h3><p>Write here…</p></div><div><h3>Three</h3><p>Write here…</p></div></section><p><br></p>')}>3 columns</button><button onClick={() => insertVisualBlock('<aside class="magazine-callout"><h3>Key idea</h3><p>Add supporting text…</p></aside><p><br></p>')}>Callout</button><button onClick={() => insertVisualBlock('<blockquote>Write a pull quote…</blockquote><p><br></p>')}>Pull quote</button><button onClick={() => insertVisualBlock('<div class="magazine-shape">Feature</div><p><br></p>')}>Badge</button><button onClick={() => insertVisualBlock('<hr><p><br></p>')}>Divider</button><button onClick={() => imageInput.current?.click()}>Image</button></div>
          </section>}
          {inspectorTab === "details" && <section className="writing-note-panel"><header><FileSliders size={20}/><div><h2>Note details</h2><p>Organization, status, and document settings.</p></div></header><label>Project<select aria-label="Inspector project" value={projectId} onChange={event => {setProjectId(event.target.value);setMessage(isLocalDraft(selected) ? "Not saved yet" : "Unsaved changes");}}><option value="">No project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label>Notebook<select aria-label="Inspector notebook" value={tagsInput.split(",").map(tag => tag.trim()).find(tag => tag.startsWith("notebook:"))?.slice(9) ?? ""} onChange={event => selectNotebook(event.target.value)}><option value="">No notebook</option>{allNotebooks.map(notebook => <option key={notebook}>{notebook}</option>)}</select></label><label>Status<select value={status} onChange={event => {setStatus(event.target.value);setMessage(isLocalDraft(selected) ? "Not saved yet" : "Unsaved changes");}}><option value="inbox">Inbox</option><option value="developing">Developing</option><option value="waiting">Waiting</option><option value="ready_to_resume">Ready to resume</option><option value="completed">Completed</option><option value="parked">Parked</option><option value="abandoned">Abandoned</option></select></label><p>{content.trim().split(/\s+/).filter(Boolean).length} words · {content.length} characters</p></section>}
        </div>
      </aside>}
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
