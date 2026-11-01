/** Keep a failed remote sign-out from silently restoring the same browser session. */
export const UNCONFIRMED_SIGN_OUT_KEY = "orin.signOutUnconfirmed.v1";
export const UNCONFIRMED_SIGN_OUT_MESSAGE =
  "Your workspace is hidden, but Orin could not confirm server sign-out. " +
  "A session may still be active. Windows task alerts may continue for up to 45 seconds " +
  "after the last successful reminder-lease renewal. Reconnect and retry server sign-out. " +
  "On a shared device, clear Orin site data to remove local session data; " +
  "this does not revoke the server session or reminder lease.";

type SignOutStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function browserStorage(): SignOutStorage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

export function isSignOutUnconfirmed(storage: SignOutStorage | null = browserStorage()): boolean {
  try {
    return storage?.getItem(UNCONFIRMED_SIGN_OUT_KEY) === "1";
  } catch {
    return false;
  }
}

export function clearSignOutUnconfirmed(storage: SignOutStorage | null = browserStorage()): void {
  try {
    storage?.removeItem(UNCONFIRMED_SIGN_OUT_KEY);
  } catch {
    // Private browsing or restricted storage must not break sign-in.
  }
}

/** A failed request hides the UI but does not prove the server session was revoked. */
export async function attemptSignOut(
  revoke: () => Promise<void>,
  storage: SignOutStorage | null = browserStorage(),
): Promise<boolean> {
  try {
    storage?.setItem(UNCONFIRMED_SIGN_OUT_KEY, "1");
  } catch {
    // Keep the current page signed out even if storage is unavailable.
  }
  try {
    await revoke();
    clearSignOutUnconfirmed(storage);
    return true;
  } catch {
    return false;
  }
}
