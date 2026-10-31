/** Opt-in, tab-scoped Windows companion lease. Never persists access tokens. */
import { request, type AuthSession } from "./api";

export const windowsLeaseOptInKey = "orin:windows-reminder-lease-opt-in";
const generationKey = "orin:windows-reminder-lease-generation";
const sessionKey = "orin:windows-reminder-lease-session";
export const windowsLeaseToggleEvent = "orin:windows-reminder-lease-toggle";
export const windowsLeaseStatusEvent = "orin:windows-reminder-lease-status";

export function isWindowsLeaseOptedIn(ownerId?: string): boolean {
  try { return Boolean(ownerId) && sessionStorage.getItem(windowsLeaseOptInKey) === ownerId; }
  catch { return false; }
}

export function setWindowsLeaseOptIn(enabled: boolean, ownerId?: string): void {
  if (enabled) {
    if (!ownerId) throw new Error("A signed-in owner is required for Windows reminder opt-in");
    sessionStorage.setItem(windowsLeaseOptInKey, ownerId);
  } else {
    try { sessionStorage.removeItem(windowsLeaseOptInKey); }
    catch { /* Storage unavailable: no new lease may be activated. */ }
  }
  window.dispatchEvent(new Event(windowsLeaseToggleEvent));
}

function publishStatus(sessionId: string | null, generation: string | null): void {
  if (sessionId && generation) {
    sessionStorage.setItem(sessionKey, sessionId);
    sessionStorage.setItem(generationKey, generation);
  } else {
    sessionStorage.removeItem(sessionKey);
    sessionStorage.removeItem(generationKey);
  }
  window.dispatchEvent(new Event(windowsLeaseStatusEvent));
}

export function getWindowsLeaseIdentifiers(): { sessionId: string; generation: string } | null {
  try {
    const sessionId = sessionStorage.getItem(sessionKey);
    const generation = sessionStorage.getItem(generationKey);
    return sessionId && generation ? { sessionId, generation } : null;
  } catch { return null; }
}

// Serialize renew/revoke/rotate so an in-flight A heartbeat cannot resurrect
// workspace A after a confirmed revoke during A -> B.
let chain: Promise<unknown> = Promise.resolve();
function serialize<T>(work: () => Promise<T>): Promise<T> {
  const next = chain.then(work, work);
  chain = next.then(() => undefined, () => undefined);
  return next;
}

export function activateWindowsLease(workspaceId: string): Promise<string> {
  return serialize(async () => {
    const sessions = await request<AuthSession[]>("/auth/sessions", { signal: AbortSignal.timeout(8000) });
    const current = sessions.find(s => s.current && s.active);
    if (!current) throw new Error("No active browser session for Windows reminders");
    const generation = crypto.randomUUID();
    await request("/auth/reminder-lease", {
      method: "PUT",
      signal: AbortSignal.timeout(8000),
      body: JSON.stringify({ workspace_id: workspaceId, generation_id: generation, rotate: true }),
    });
    publishStatus(current.id, generation);
    return generation;
  });
}

export function renewWindowsLease(workspaceId: string, generation: string): Promise<void> {
  return serialize(async () => {
    if (getWindowsLeaseIdentifiers()?.generation !== generation) return;
    await request("/auth/reminder-lease", {
      method: "PUT",
      signal: AbortSignal.timeout(8000),
      body: JSON.stringify({ workspace_id: workspaceId, generation_id: generation }),
    });
  });
}

export function stopWindowsLease(): Promise<void> {
  return serialize(async () => {
    // A stale tab cannot revoke another tab's newer workspace generation.
    const generation = getWindowsLeaseIdentifiers()?.generation;
    await request<void>("/auth/reminder-lease", {
      method: "DELETE", signal: AbortSignal.timeout(8000),
      ...(generation ? { body: JSON.stringify({ generation_id: generation }) } : {}),
    });
    publishStatus(null, null);
  });
}

export function clearWindowsLeaseLocalState(): void {
  publishStatus(null, null);
}
