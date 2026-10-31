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
  } else sessionStorage.removeItem(windowsLeaseOptInKey);
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
  const sessionId = sessionStorage.getItem(sessionKey);
  const generation = sessionStorage.getItem(generationKey);
  return sessionId && generation ? { sessionId, generation } : null;
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
    const sessions = await request<AuthSession[]>("/auth/sessions");
    const current = sessions.find(s => s.current && s.active);
    if (!current) throw new Error("No active browser session for Windows reminders");
    const generation = crypto.randomUUID();
    await request("/auth/reminder-lease", {
      method: "PUT",
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
      body: JSON.stringify({ workspace_id: workspaceId, generation_id: generation }),
    });
  });
}

export function stopWindowsLease(): Promise<void> {
  return serialize(async () => {
    // A failed revocation must not be misrepresented as a successful shutdown.
    await request<void>("/auth/reminder-lease", { method: "DELETE" });
    publishStatus(null, null);
  });
}

export function clearWindowsLeaseLocalState(): void {
  publishStatus(null, null);
}
