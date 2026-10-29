import type {
  CommandResponse,
  FocusSessionSummary,
  KnowledgeDocumentRecord,
  OpportunityRecord,
  ProjectSummary,
  RiskRecord,
  RoutineOccurrence,
  RoutineRecord,
  StructuredMemory,
} from "@orin/contracts";

export type User = {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_disabled: boolean;
  created_at: string;
};

export type Workspace = {
  id: string;
  owner_id: string;
  name: string;
  color: string;
  created_at: string;
  updated_at: string;
};

export type TaskStatus =
  | "todo"
  | "in_progress"
  | "blocked"
  | "done"
  | "cancelled";
export type Task = {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: "low" | "normal" | "high" | "urgent";
  due_at: string | null;
  project_id: string | null;
  first_step?: string | null;
  estimated_minutes?: number | null;
  created_at: string;
  updated_at: string;
};

export type Project = ProjectSummary & { workspace_id?: string | null };
export type Note = KnowledgeDocumentRecord;
export type CommandResult = CommandResponse;
export type TabKey = "home" | "tasks" | "projects" | "notes" | "more";

export type CalendarEvent = {
  id: string;
  title: string;
  description: string | null;
  project_id: string | null;
  is_all_day: boolean;
  start_at: string | null;
  end_at: string | null;
  start_date: string | null;
  end_date: string | null;
  timezone: string;
  reminder_minutes: number | null;
  created_at: string;
  updated_at: string;
};
export type Approval = {
  id: string;
  status: string;
  action: string | null;
  parameters: Record<string, unknown>;
  risk_level: string;
  permission: string | null;
  reversible: boolean | null;
  reason: string | null;
  created_at: string;
  expires_at: string | null;
  decided_at: string | null;
};
export type Activity = {
  id: string;
  summary: string;
  activity_type: string;
  result_status: string;
  severity: string;
  source: string;
  project_id: string | null;
  task_id: string | null;
  created_at: string;
};
export type Reminder = {
  id: string;
  title: string;
  message: string;
  category: string;
  source_id: string | null;
  due_at: string;
  read_at: string | null;
  snoozed_until: string | null;
  revision: number;
  repeats: number;
  attention_ready: boolean;
};
export type NotificationPolicy = {
  enabled: boolean;
  categories: string[];
  persistent: boolean;
  repeat_minutes: 5 | 15 | 30 | 60;
  max_repeats: number;
  timezone: string;
  quiet_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  respect_focus: boolean;
  browser_alerts: boolean;
  sound: boolean;
};
export type FocusSession = FocusSessionSummary;
export type Opportunity = OpportunityRecord;
export type Risk = RiskRecord;
export type Routine = RoutineRecord;
export type RoutineCheckin = RoutineOccurrence;
export type Memory = StructuredMemory & {
  provenance?: string;
  metadata?: Record<string, unknown>;
};
export type SearchResult = {
  result_id: string;
  kind: string;
  command_id: string | null;
  task_id: string | null;
  project_id: string | null;
  conversation_id: string | null;
  document_id: string | null;
  text: string;
  excerpt: string;
  created_at: string;
  title: string | null;
};
export type UserPreferences = {
  density: "comfortable" | "compact";
  theme: "light" | "dark" | "system";
  locale: string;
  visible_capabilities: string[];
  hidden_capabilities: string[];
  pinned_capabilities: string[];
  autonomy_mode: "conservative" | "balanced" | "automatic" | "custom";
  custom_autonomy: Record<string, "automatic" | "approval">;
  proactive_mode: "quiet" | "supportive" | "proactive" | "persistent";
};
export type AuthSession = {
  id: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  revoked_at: string | null;
  active: boolean;
  current: boolean;
};
export type OperationsKey =
  | "calendar"
  | "notifications"
  | "approvals"
  | "activity"
  | "focus"
  | "routines"
  | "opportunities"
  | "search"
  | "memories"
  | "settings"
  | "account";
