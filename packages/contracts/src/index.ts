/** Stable status response shared by API clients. */
export interface HealthStatus {
  status: "ok";
}

export interface CommandRequest {
  text: string;
}

export interface CommandResponse {
  command_id: string;
  status: "completed" | "unsupported";
  intent?: "CREATE_TASK" | "UPDATE_TASK" | "COMPLETE_TASK" | "CREATE_PROJECT" | "LIST_PROJECTS" | "LIST_TASKS" | "GET_ACTIVITY" | "UNSUPPORTED";
  result?: Record<string, unknown> | Array<Record<string, unknown>>;
  message: string;
}
