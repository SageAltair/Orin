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
