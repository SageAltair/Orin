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

function isClientScopeError(error: unknown): boolean {
  return error instanceof Error &&
    (error.message === "Workspace changed while the request was in flight." ||
     error.message === "Session changed while the request was in flight.");
}

export function activateWindowsLease(workspaceId: string): Promise<string> {
  return serialize(async () => {
    const sessions = await request<AuthSession[]>("/auth/sessions", { signal: AbortSignal.timeout(8000) });
    const current = sessions.find(s => s.current && s.active);
    if (!current) throw new Error("No active browser session for Windows reminders");
    const previous = getWindowsLeaseIdentifiers();
    if (previous) {
      // A rotation PUT can fail before committing. Overwriting the old handle
      // first would make a still-live previous generation impossible to revoke.
      // Confirm old revocation before creating a replacement generation.
      if (previous.sessionId !== current.id)
        throw new Error("A different browser session still owns the reminder lease");
      try {
        await request<void>("/auth/reminder-lease", {
          method: "DELETE",
          signal: AbortSignal.timeout(8000),
          body: JSON.stringify({ generation_id: previous.generation }),
        });
      } catch (error) {
        // 409 confirms another tab already replaced this generation.
        if (!(error instanceof Error && "status" in error && error.status === 409))
          throw error;
      }
      clearWindowsLeaseLocalState();
    }
    const generation = crypto.randomUUID();
    // Persist the revocation handle before asking the server to create a
    // lease. Storage failure must not leave a live lease with no local handle.
    publishStatus(current.id, generation);
    try {
      await request("/auth/reminder-lease", {
        method: "PUT",
        signal: AbortSignal.timeout(8000),
        body: JSON.stringify({ workspace_id: workspaceId, generation_id: generation, rotate: true }),
      });
    } catch (error) {
      const status = error instanceof Error && "status" in error ? error.status : undefined;
      // A definite 4xx rejection did not activate this generation. An
      // ambiguous network/5xx failure may have committed before the response
      // failed, so keep its handle available for a scoped DELETE.
      if (!isClientScopeError(error) &&
          typeof status === "number" && status >= 400 && status < 500) {
        clearWindowsLeaseLocalState();
      }
      throw error;
    }
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
    // No local generation means this tab does not own the server lease.
    // An unscoped DELETE could revoke a different tab's active workspace.
    if (!generation) {
      publishStatus(null, null);
      return;
    }
    try {
      await request<void>("/auth/reminder-lease", {
        method: "DELETE", signal: AbortSignal.timeout(8000),
        body: JSON.stringify({ generation_id: generation }),
      });
    } catch (error) {
      // 409 means another tab already replaced this generation. The old
      // workspace is no longer authorized, so clearing our local ownership
      // is safe. Other errors leave navigation blocked until confirmed.
      if (!(error instanceof Error && "status" in error && error.status === 409)) throw error;
    }
    publishStatus(null, null);
  });
}


/**
 * Preserve the tab's generation when a heartbeat fails without proving
 * revocation. Otherwise a later explicit opt-out cannot send the scoped
 * DELETE, and the old server lease can authorize alerts until expiry.
 *
 * A confirmed missing/stale lease can be discarded. A late failure from an
 * older generation must never clear a newer tab/workspace activation.
 */
export function handleWindowsLeaseRenewalFailure(generation: string, error: unknown): void {
  if (getWindowsLeaseIdentifiers()?.generation !== generation) return;
  const status = error instanceof Error && "status" in error ? error.status : undefined;
  // The shared API can synthesize a 409 after a successful server PUT if
  // the user switched workspaces while the response was in flight.
  if (!isClientScopeError(error) && (status === 404 || status === 409))
    clearWindowsLeaseLocalState();
}

export function clearWindowsLeaseLocalState(): void {
  publishStatus(null, null);
}
