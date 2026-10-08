const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8100";
let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export interface User { id: string; email: string; display_name: string; created_at: string }
export interface Task { id: string; title: string; description: string | null; status: "todo" | "in_progress" | "blocked" | "done" | "cancelled"; priority: "low" | "normal" | "high" | "urgent"; due_at: string | null; project_id: string | null; created_at: string; updated_at: string }
export interface Project { id: string; name: string; description: string | null; status: string; created_at: string; updated_at: string }
export interface Activity { id: string; summary: string; activity_type: string; created_at: string; task_id: string | null; project_id: string | null; command_id?: string | null; intent?: string | null; result_status?: string }
export interface Preferences { density: "comfortable" | "compact"; theme: "light" | "dark" | "system"; locale: string; visible_capabilities: string[]; hidden_capabilities: string[]; pinned_capabilities: string[] }
export interface CommandResult { command_id: string; status: "completed" | "awaiting_approval" | "denied" | "failed" | "unsupported" | string; intent: string | null; result: Record<string, unknown> | Record<string, unknown>[] | null; message: string; execution?: { success: boolean; action: string; status: string; result: Record<string, unknown> | Record<string, unknown>[] | null; error: string | null; approval_required: boolean; approval_id: string | null; audit_id: string | null } | null }

async function refresh(): Promise<boolean> {
  if (!refreshPromise) refreshPromise = fetch(`${baseUrl}/api/v1/auth/refresh`, { method: "POST", credentials: "include" }).then(async response => {
    if (!response.ok) { accessToken = null; return false; }
    accessToken = (await response.json() as { access_token: string }).access_token; return true;
  }).catch(() => { accessToken = null; return false; }).finally(() => { refreshPromise = null; });
  return refreshPromise;
}

export async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let response: Response;
  try { response = await fetch(`${baseUrl}/api/v1${path}`, { ...options, headers, credentials: "include" }); }
  catch { throw new ApiError("Could not reach Orin. Check your connection and API configuration.", 0); }
  if (response.status === 401 && retry && path !== "/auth/login" && path !== "/auth/refresh") {
    if (await refresh()) return request<T>(path, options, false);
    accessToken = null;
    window.dispatchEvent(new Event("orin:session-expired"));
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const data = await response.json() as { detail?: string | { msg?: string }[] }; message = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map(e => e.msg ?? "Invalid input").join("; ") : message; } catch { /* non-JSON error */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<User> {
  const result = await request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false);
  accessToken = result.access_token;
  return request<User>("/auth/me");
}
export async function register(email: string, password: string, display_name: string): Promise<User> {
  await request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name }) }, false);
  return login(email, password);
}
export async function restoreSession(): Promise<User | null> { return await refresh() ? request<User>("/auth/me") : null; }
export async function logout(): Promise<void> { try { await request<void>("/auth/logout", { method: "POST" }, false); } finally { accessToken = null; } }
