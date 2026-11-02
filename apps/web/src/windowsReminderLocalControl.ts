/** Optional foreground-only Windows companion stop channel.
 * The generation UUID is an ephemeral HMAC key, never sent over loopback.
 * Failure is not proof of revocation: remote DELETE/logout must still run.
 */
const endpoint = "http://127.0.0.1:18765";
const headers = { "X-Orin-Reminder-Control": "1" };

async function sendLocalWindowsCompanion(
  lease: { sessionId: string; generation: string },
  action: "revoke" | "heartbeat",
): Promise<boolean> {
  try {
    const challenge = await fetch(endpoint + "/challenge", {
      method: "GET", mode: "cors", credentials: "omit", cache: "no-store",
      redirect: "error", headers, signal: AbortSignal.timeout(1500),
    });
    if (!challenge.ok) return false;
    const data = await challenge.json() as { nonce?: unknown };
    if (typeof data.nonce !== "string" || !/^[0-9a-f]{32}$/.test(data.nonce)) return false;
    const key = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(lease.generation),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
    );
    const signature = await crypto.subtle.sign(
      "HMAC", key, new TextEncoder().encode(data.nonce + "|" + lease.sessionId +
        (action === "heartbeat" ? "|heartbeat" : "")),
    );
    const proof = Array.from(new Uint8Array(signature), byte =>
      byte.toString(16).padStart(2, "0")).join("");
    const result = await fetch(endpoint + "/" + action, {
      method: "POST", mode: "cors", credentials: "omit", cache: "no-store",
      redirect: "error",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ nonce: data.nonce, session_id: lease.sessionId, proof }),
      signal: AbortSignal.timeout(1500),
    });
    return result.status === 204;
  } catch {
    // No listener, port collision, browser PNA restriction, crash or timeout.
    // Never report a confirmed local revocation from an uncertain response.
    return false;
  }
}

export function revokeLocalWindowsCompanion(lease: { sessionId: string; generation: string }): Promise<boolean> {
  return sendLocalWindowsCompanion(lease, "revoke");
}

/** Foreground-only presence pulse. Failure leaves native delivery disabled. */
export function heartbeatLocalWindowsCompanion(lease: { sessionId: string; generation: string }): Promise<boolean> {
  return sendLocalWindowsCompanion(lease, "heartbeat");
}
