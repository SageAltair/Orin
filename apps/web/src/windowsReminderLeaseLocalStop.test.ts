import { beforeEach, describe, expect, it, vi } from "vitest";

const requestMock = vi.hoisted(() => vi.fn());
const localStop = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ request: requestMock }));
vi.mock("./windowsReminderLocalControl", () => ({ revokeLocalWindowsCompanion: localStop }));

import { activateWindowsLease, getWindowsLeaseIdentifiers, stopWindowsLease } from "./windowsReminderLease";

describe("independent local stop on remote revocation uncertainty", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => { storage.set(key, value); },
      removeItem: (key: string) => { storage.delete(key); },
    });
    vi.stubGlobal("window", { dispatchEvent: vi.fn() });
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-4111-8111-111111111111" });
    localStop.mockReset().mockResolvedValue(true);
    requestMock.mockReset().mockImplementation(async (path: string) =>
      path === "/auth/sessions" ? [{ id: "browser-session", current: true, active: true }] : undefined);
  });

  it("sends a local stop before a failed server DELETE and preserves retry handle", async () => {
    const generation = await activateWindowsLease("workspace-a");
    const order: string[] = [];
    localStop.mockImplementation(async () => { order.push("local"); return true; });
    requestMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/reminder-lease" && options?.method === "DELETE") {
        order.push("remote");
        throw Object.assign(new Error("API unavailable"), { status: 503 });
      }
      return undefined;
    });
    await expect(stopWindowsLease()).rejects.toMatchObject({ status: 503 });
    expect(order).toEqual(["local", "remote"]);
    expect(localStop).toHaveBeenCalledWith({ sessionId: "browser-session", generation });
    expect(getWindowsLeaseIdentifiers()?.generation).toBe(generation);
  });

  it("still revokes remotely when no local listener is available", async () => {
    await activateWindowsLease("workspace-a");
    localStop.mockResolvedValue(false);
    await expect(stopWindowsLease()).resolves.toBeUndefined();
    expect(requestMock.mock.calls.some(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "DELETE")).toBe(true);
    expect(getWindowsLeaseIdentifiers()).toBeNull();
  });
});
