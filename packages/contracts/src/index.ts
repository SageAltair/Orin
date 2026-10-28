/** Stable status response shared by API clients. */
export interface HealthStatus {
  status: "ok";
}

export interface CommandRequest {
  text: string;
}

export interface CommandResponse {
  command_id: string;
  status: "completed" | "awaiting_approval" | "denied" | "failed" | "unsupported";
  intent?: "RESPOND" | "CREATE_TASK" | "UPDATE_TASK" | "COMPLETE_TASK" | "CREATE_PROJECT" | "LIST_PROJECTS" | "LIST_TASKS" | "GET_ACTIVITY" | "UNSUPPORTED";
  result?: Record<string, unknown> | Array<Record<string, unknown>> | null;
  message: string;
  execution?: ExecutionResult;
}

export interface ProjectSummary {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  objective: string | null;
  status: "planning" | "active" | "blocked" | "paused" | "completed" | "archived";
  priority: "low" | "normal" | "high" | "urgent";
  target_date: string | null;
  created_at: string;
  updated_at: string;
}

export type KnowledgeDocumentType = "quick_note" | "knowledge" | "research" | "idea" | "draft" | "journal" | "meeting" | "decision" | "reference";
export type KnowledgeDocumentStatus = "inbox" | "developing" | "waiting" | "ready_to_resume" | "completed" | "parked" | "abandoned";

/** User-authored document stored in the personal knowledge workspace. */
export interface KnowledgeDocumentRecord {
  id: string;
  project_id: string | null;
  title: string;
  content: string;
  document_type: KnowledgeDocumentType;
  status: KnowledgeDocumentStatus;
  tags: string[];
  archived: boolean;
  exclude_from_ai: boolean;
  review_at: string | null;
  version: number;
  extraction_status?: "not_requested" | "queued" | "processing" | "succeeded" | "failed" | "superseded" | "excluded" | "stale";
  extraction_version?: number;
  extracted_data?: {
    summary: string; topics: string[]; entities: string[]; decisions: string[];
    open_questions: string[]; candidate_actions: string[]; date_mentions: string[];
  } | null;
  extraction_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeInsightRecord {
  id: string;
  type: string;
  title: string;
  explanation: string;
  evidence: Array<{ document_id?: string; task_id?: string; record_type?: "document" | "task"; title: string; updated_at?: string }>;
  frequency: number;
  confidence: number;
  limitations: string;
  suggested_next_step: string;
  status: "active" | "snoozed" | "dismissed" | "resolved";
  snoozed_until: string | null;
  window_start: string | null;
  window_end: string | null;
  evaluated_at: string;
}

export interface KnowledgeReviewRecord {
  id: string;
  document_id: string;
  title: string;
  document_type: KnowledgeDocumentType;
  status: "pending" | "snoozed" | "dismissed" | "resolved";
  due_at: string;
  snoozed_until: string | null;
}

export interface WritingReviewSuggestion {
  id: string;
  category: "clarity" | "flow" | "engagement" | "grammar" | "tone";
  severity: "suggestion" | "important";
  title: string;
  message: string;
  original: string | null;
  replacement: string | null;
}

export interface WritingLiveReview {
  suggestions: WritingReviewSuggestion[];
  reviewed_at: string;
  mode: "ai" | "local";
  model: string | null;
  source_fingerprint: string;
  limitations: string[];
}

export interface KnowledgeAskResult {
  answer: string;
  citations: Array<{ document_id: string; title: string; document_type: KnowledgeDocumentType; updated_at: string }>;
  sources?: Array<{ document_id: string; title: string; document_type: KnowledgeDocumentType; updated_at: string; excerpt: string }>;
  mode: "keyword_only" | "ai_synthesis";
  limitations: string[];
}

export interface KnowledgeWeeklyReport {
  generated_at: string;
  window_start: string;
  window_end: string;
  observations: Array<{ kind: string; title: string; detail: string; evidence: Array<{ document_id: string; title: string }> }>;
  limitations: string[];
}

export interface KnowledgeReport extends KnowledgeWeeklyReport {}

export interface KnowledgeDocumentVersionRecord {
  id: string;
  version: number;
  title: string;
  content: string;
  created_at: string;
}

export interface ProjectMilestone {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  target_date: string | null;
  status: "pending" | "completed";
  completion_criteria: string | null;
  created_at: string;
  updated_at: string;
}

/** A user-owned calendar event; all-day events use local dates rather than UTC instants. */
export interface CalendarEvent {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  description: string | null;
  is_all_day: boolean;
  start_at: string | null;
  end_at: string | null;
  start_date: string | null;
  end_date: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export type FocusState = "inbox" | "later" | "today" | "active" | "released";
export type EnergyLevel = "low" | "medium" | "high";
export type DriftTrigger = "app" | "thought" | "emotion" | "person" | "tired" | "other";

/** Additive focus fields; legacy task status remains unchanged. */
export interface FocusTaskFields {
  focus_state?: FocusState | null;
  first_step?: string | null;
  why?: string | null;
  energy_level?: EnergyLevel | null;
  estimated_minutes?: number | null;
  is_anchor?: boolean;
  trigger?: string | null;
  last_touched_at?: string | null;
  decay_review_at?: string | null;
  skip_count_today?: number;
  skip_day_key?: string | null;
  today_day_key?: string | null;
  today_position?: number | null;
  completed_at?: string | null;
  released_at?: string | null;
}

export interface FocusCaptureRequest {
  title?: string | null;
  first_step?: string | null;
  energy_level?: EnergyLevel | null;
}

export interface FocusCaptureSuggestion {
  title: string;
  first_step: string;
  energy_level: EnergyLevel;
}

export interface FocusSmallerStepSuggestion {
  first_step: string;
}

export interface TaskRecord extends FocusTaskFields {
  id: string;
  owner_id: string;
  project_id: string | null;
  milestone_id?: string | null;
  assignee_id: string | null;
  title: string;
  description: string | null;
  verification_criteria?: string | null;
  status: "todo" | "in_progress" | "blocked" | "done" | "cancelled";
  priority: "low" | "normal" | "high" | "urgent";
  due_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FocusUserSettings {
  timezone: string;
  day_key: string | null;
  energy_today: EnergyLevel | null;
  preferred_anchor_time: string | null;
  quiet_hours: Record<string, string> | null;
  reduced_motion: boolean;
  hide_timer_numbers: boolean;
  sound_enabled: boolean;
  haptics_enabled: boolean;
  theme: "light" | "dark" | "auto";
  body_doubling_enabled: boolean;
  accountability_contact: string | null;
}

export interface DriftEventRecord {
  id: string;
  task_id: string | null;
  focus_session_id: string | null;
  day_key: string;
  trigger_type: DriftTrigger;
  note: string | null;
  created_at: string;
}

export interface DailyCloseRecord {
  id: string;
  day_key: string;
  done_list: Array<Record<string, unknown>>;
  drift_summary: string | null;
  tomorrow_task_id: string | null;
  reflection: string | null;
  created_at: string;
}

export type MemoryType = "preference" | "decision" | "fact" | "commitment" | "workflow" | "project_context";

export interface StructuredMemory {
  id: string;
  project_id: string | null;
  type: MemoryType;
  title: string;
  content: string;
  source: string;
  confidence: number | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface EnvironmentPreference {
  surface: string;
  item: string;
  visibility: "visible" | "hidden" | "minimized" | "prioritized";
  priority: number;
  source: "explicit";
}

export interface FocusSessionSummary {
  id: string;
  project_id: string | null;
  task_id?: string | null;
  objective: string;
  duration_minutes: number;
  started_at: string;
  ends_at: string;
  ended_at: string | null;
  status: "active" | "paused" | "completed" | "cancelled" | "expired";
  context_snapshot: Record<string, unknown>;
}

export interface ProjectContext {
  project: Pick<ProjectSummary, "id" | "name" | "description" | "objective" | "status" | "updated_at">;
  progress: { completed_tasks: number; total_tasks: number; percentage: number | null };
  tasks: Array<{ id: string; title: string; status: string; priority: string }>;
  next_actions: Array<{ id: string; title: string; status: string }>;
  blockers: Array<{ id: string; title: string }>;
  activity: Array<{ id: string; summary: string; created_at: string; result_status: string }>;
  knowledge: StructuredMemory[];
  active_focus: FocusSessionSummary | null;
  agents: never[];
  files: never[];
}

export interface ExecutionResult {
  success: boolean;
  action: string;
  status: "executed" | "pending_approval" | "denied" | "failed" | "invalid" | "unsupported";
  result?: Record<string, unknown> | Array<Record<string, unknown>> | null;
  error?: string | null;
  approval_required: boolean;
  approval_id?: string | null;
  audit_id?: string | null;
}

export type ExecutionTarget = "local" | "cloud" | "auto";

export interface WorkerJobSummary {
  id: string;
  action: string;
  status: "pending_approval" | "queued" | "starting" | "running" | "completed" | "failed" | "cancelled" | "expired";
  requested_target: ExecutionTarget;
  selected_target: Exclude<ExecutionTarget, "auto"> | null;
  progress: string | null;
  result: Record<string, unknown> | null;
  failure: string | null;
  created_at: string;
  finished_at: string | null;
}

/* Creative Studio: ideas, outlines, document cards, and idea links. */

export type CreativeIdeaStatus = "active" | "archived" | "all";

export interface CreativeIdea {
  id: string;
  title: string;
  content: string | null;
  document_id: string | null;
  status: string;
  linked_document_ids: string[];
}

export type IdeaLinkType = "inspires" | "contrasts" | "extends" | "supports";

export interface CreativeIdeaLink {
  idea_id: string;
  document_id: string;
  link_type: IdeaLinkType;
  note: string | null;
}

export type OutlineItemKind = "section" | "chapter" | "scene" | "verse" | "stanza" | "beat" | "act" | "note";
export type OutlineItemStatus = "planned" | "drafted" | "revised" | "done";

export interface CreativeOutlineItem {
  id: string;
  parent_id: string | null;
  document_id: string | null;
  title: string;
  summary: string | null;
  kind: OutlineItemKind;
  status: OutlineItemStatus;
  position: number;
  created_at: string;
  updated_at: string;
}

export type DocumentCardStatus = "todo" | "drafting" | "revised" | "polished" | "ready" | "published";

export interface CreativeDocumentCard {
  id: string;
  project_id: string | null;
  document_id: string | null;
  title: string;
  summary: string | null;
  purpose: string | null;
  central_question: string | null;
  point_of_view: string | null;
  status: DocumentCardStatus;
  position: number;
  created_at: string;
  updated_at: string;
}


export interface OpportunityRecord {
  id: string; title: string; project_id: string | null; task_id: string | null;
  category: "job" | "business" | "learning" | "creative" | "ministry" | "other";
  stage: "inbox" | "exploring" | "pursuing" | "waiting" | "won" | "closed";
  description: string; source_url: string; contact: string; next_action: string; decision_notes: string;
  deadline: string | null; review_on: string | null; value: number; fit: number; effort: number;
}
export interface RiskRecord {
  id: string; title: string; opportunity_id: string | null; project_id: string | null;
  likelihood: number; impact: number; status: "open" | "watching" | "resolved" | "occurred";
  response: "reduce" | "avoid" | "accept" | "transfer"; trigger: string; mitigation: string; review_on: string | null;
}
export interface RoutineRecord {
  id: string; title: string; timezone: string; weekdays: number[]; start_date: string; end_date: string | null;
  time_of_day: string; duration_minutes: number; minimum_minutes: number; cue: string; steps: string;
  minimum_action: string; reward: string; reminder_minutes: number | null; paused: boolean;
}
export interface RoutineOccurrence {
  routine_id: string; day: string; title: string; start_at: string; end_at: string;
  status: "pending" | "done" | "minimum" | "skipped"; cue: string; minimum_action: string;
  duration_minutes: number; minimum_minutes: number;
}
