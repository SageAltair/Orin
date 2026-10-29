import { describe, expect, it, vi } from "vitest";
import {
  attemptSignOut,
  clearSignOutUnconfirmed,
  isSignOutUnconfirmed,
  UNCONFIRMED_SIGN_OUT_KEY,
} from "./signOut";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  };
}

describe("remote sign-out confirmation", () => {
  it("marks sign-out pending before requesting revocation and clears only on success", async () => {
    const storage = memoryStorage();
    const revoke = vi.fn(async () => {
      expect(isSignOutUnconfirmed(storage)).toBe(true);
    });
    await expect(attemptSignOut(revoke, storage)).resolves.toBe(true);
    expect(revoke).toHaveBeenCalledOnce();
    expect(isSignOutUnconfirmed(storage)).toBe(false);
  });

  it("retains the marker when offline and clears it after a successful retry", async () => {
    const storage = memoryStorage();
    await expect(attemptSignOut(async () => { throw new TypeError("offline"); }, storage)).resolves.toBe(false);
    expect(storage.getItem(UNCONFIRMED_SIGN_OUT_KEY)).toBe("1");
    await expect(attemptSignOut(async () => undefined, storage)).resolves.toBe(true);
    expect(isSignOutUnconfirmed(storage)).toBe(false);
  });

  it("can clear a stale marker after explicit authentication", () => {
    const storage = memoryStorage();
    storage.setItem(UNCONFIRMED_SIGN_OUT_KEY, "1");
    clearSignOutUnconfirmed(storage);
    expect(isSignOutUnconfirmed(storage)).toBe(false);
  });

  it("does not throw when browser storage is restricted", async () => {
    const storage = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    };
    expect(isSignOutUnconfirmed(storage)).toBe(false);
    await expect(attemptSignOut(async () => undefined, storage)).resolves.toBe(true);
    clearSignOutUnconfirmed(storage);
  });
});
