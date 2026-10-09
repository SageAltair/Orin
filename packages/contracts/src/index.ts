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
  created_at: string;
  updated_at: string;
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
  project_id: string;
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
