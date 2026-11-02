import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequest = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ request: apiRequest }));
import {
  activateWindowsLease, getWindowsLeaseIdentifiers, renewWindowsLease,
  stopWindowsLease, setWindowsLeaseOptIn, isWindowsLeaseOptedIn,
  handleWindowsLeaseRenewalFailure,
} from "./windowsReminderLease";

describe("Windows reminder browser lease", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    vi.stubGlobal("window", { dispatchEvent: vi.fn() });
    vi.stubGlobal("crypto", { randomUUID: vi.fn()
      .mockReturnValueOnce("11111111-1111-4111-8111-111111111111")
      .mockReturnValueOnce("22222222-2222-4222-8222-222222222222") });
    apiRequest.mockReset();
    apiRequest.mockImplementation(async (path: string) =>
      path === "/auth/sessions"
        ? [{ id: "browser-session", current: true, active: true }]
        : undefined);
  });

  it("never revokes another tab's lease when this tab has no generation", async () => {
    // An opted-in tab can be closing before its own activation completed.
    // A DELETE without a generation would revoke the active lease of another tab.
    setWindowsLeaseOptIn(true, "owner-a");
    expect(getWindowsLeaseIdentifiers()).toBeNull();
    await stopWindowsLease();
    expect(apiRequest).not.toHaveBeenCalled();
    expect(getWindowsLeaseIdentifiers()).toBeNull();
  });

  it("requires explicit opt-in and serializes A revoke before B activation", async () => {
    expect(isWindowsLeaseOptedIn("owner-a")).toBe(false);
    setWindowsLeaseOptIn(true, "owner-a");
    expect(isWindowsLeaseOptedIn("owner-a")).toBe(true);
    expect(isWindowsLeaseOptedIn("owner-b")).toBe(false);
    const first = await activateWindowsLease("workspace-a");
    expect(getWindowsLeaseIdentifiers()).toEqual({
      sessionId: "browser-session", generation: first,
    });
    await renewWindowsLease("workspace-a", first);
    await stopWindowsLease();
    expect(getWindowsLeaseIdentifiers()).toBeNull();
    const second = await activateWindowsLease("workspace-b");
    expect(second).not.toBe(first);
    const operations = apiRequest.mock.calls
      .filter(([path]) => path === "/auth/reminder-lease")
      .map(([, options]) => ({
        method: options.method,
        body: options.body ? JSON.parse(options.body) : null,
      }));
    expect(operations.map(operation => operation.method))
      .toEqual(["PUT", "PUT", "DELETE", "PUT"]);
    expect(operations[2].body).toEqual({ generation_id: first });
    expect(operations[0].body).toMatchObject({
      workspace_id: "workspace-a", generation_id: first, rotate: true,
    });
    expect(operations[3].body).toMatchObject({
      workspace_id: "workspace-b", generation_id: second, rotate: true,
    });
  });
  it("treats a stale-generation 409 as confirmed revocation of this tab's lease", async () => {
    const first = await activateWindowsLease("workspace-a");
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/sessions") {
        return [{ id: "browser-session", current: true, active: true }];
      }
      if (path === "/auth/reminder-lease" && options?.method === "DELETE") {
        throw Object.assign(new Error("Reminder lease generation changed"), { status: 409 });
      }
      return undefined;
    });
    // Another tab already replaced A's generation. A must not be trapped
    // in workspace A merely because its conditional DELETE returned 409.
    await expect(stopWindowsLease()).resolves.toBeUndefined();
    expect(getWindowsLeaseIdentifiers()).toBeNull();
    const second = await activateWindowsLease("workspace-b");
    expect(second).not.toBe(first);
  });

  it("still blocks a workspace switch when revocation returns a server error", async () => {
    const first = await activateWindowsLease("workspace-a");
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/reminder-lease" && options?.method === "DELETE") {
        throw Object.assign(new Error("API unavailable"), { status: 503 });
      }
      return undefined;
    });
    await expect(stopWindowsLease()).rejects.toMatchObject({ status: 503 });
    expect(getWindowsLeaseIdentifiers()?.generation).toBe(first);
  });

  it("retains a revocable generation after transient heartbeat failure", async () => {
    const generation = await activateWindowsLease("workspace-a");
    // A 503 does not prove that the server-side lease was revoked. The
    // user must still be able to send a generation-scoped DELETE.
    const outage = Object.assign(new Error("API unavailable"), { status: 503 });
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/reminder-lease" && options?.method === "PUT") throw outage;
      return undefined;
    });
    await expect(renewWindowsLease("workspace-a", generation)).rejects.toBe(outage);
    handleWindowsLeaseRenewalFailure(generation, outage);
    expect(getWindowsLeaseIdentifiers()?.generation).toBe(generation);
    await stopWindowsLease();
    const deletes = apiRequest.mock.calls.filter(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "DELETE");
    expect(deletes).toHaveLength(1);
    expect(JSON.parse(deletes[0][1].body)).toEqual({ generation_id: generation });
  });

  it("keeps an uncertain activation generation available for scoped revocation", async () => {
    const outage = Object.assign(new Error("API unavailable after PUT"), { status: 503 });
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/sessions") return [{ id: "browser-session", current: true, active: true }];
      if (path === "/auth/reminder-lease" && options?.method === "PUT") throw outage;
      return undefined;
    });
    await expect(activateWindowsLease("workspace-a")).rejects.toBe(outage);
    const uncertain = getWindowsLeaseIdentifiers();
    expect(uncertain?.generation).toBe("11111111-1111-4111-8111-111111111111");
    await stopWindowsLease();
    expect(getWindowsLeaseIdentifiers()).toBeNull();
    const deletes = apiRequest.mock.calls.filter(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "DELETE");
    expect(deletes).toHaveLength(1);
    expect(JSON.parse(deletes[0][1].body)).toEqual({ generation_id: uncertain?.generation });
  });

  it("does not create a server lease when tab storage cannot retain its revocation handle", async () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => null,
      setItem: () => { throw new Error("Storage disabled"); },
      removeItem: () => undefined,
    });
    await expect(activateWindowsLease("workspace-a")).rejects.toThrow("Storage disabled");
    const puts = apiRequest.mock.calls.filter(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "PUT");
    expect(puts).toHaveLength(0);
  });

  it("retains a generation when the client reports a late workspace-scope 409", async () => {
    const stale = Object.assign(new Error("Workspace changed while the request was in flight."), { status: 409 });
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/sessions") return [{ id: "browser-session", current: true, active: true }];
      if (path === "/auth/reminder-lease" && options?.method === "PUT") throw stale;
      return undefined;
    });
    await expect(activateWindowsLease("workspace-a")).rejects.toBe(stale);
    const generation = getWindowsLeaseIdentifiers()?.generation;
    expect(generation).toBe("11111111-1111-4111-8111-111111111111");
    await stopWindowsLease();
    const deletes = apiRequest.mock.calls.filter(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "DELETE");
    expect(JSON.parse(deletes[0][1].body)).toEqual({ generation_id: generation });
  });

  it("restores the previous revocation handle after a definite rotation rejection", async () => {
    const first = await activateWindowsLease("workspace-a");
    apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/auth/sessions") return [{ id: "browser-session", current: true, active: true }];
      if (path === "/auth/reminder-lease" && options?.method === "PUT") {
        throw Object.assign(new Error("Rotation rejected"), { status: 409 });
      }
      return undefined;
    });
    await expect(activateWindowsLease("workspace-b")).rejects.toMatchObject({ status: 409 });
    expect(getWindowsLeaseIdentifiers()?.generation).toBe(first);
    await stopWindowsLease();
    const deletes = apiRequest.mock.calls.filter(([path, options]) =>
      path === "/auth/reminder-lease" && options?.method === "DELETE");
    expect(JSON.parse(deletes[0][1].body)).toEqual({ generation_id: first });
  });

  it("clears a generation confirmed stale, but not a newer generation", async () => {
    const first = await activateWindowsLease("workspace-a");
    const second = await activateWindowsLease("workspace-b");
    handleWindowsLeaseRenewalFailure(first, Object.assign(new Error("stale"), { status: 409 }));
    expect(getWindowsLeaseIdentifiers()?.generation).toBe(second);
    handleWindowsLeaseRenewalFailure(second, Object.assign(new Error("stale"), { status: 409 }));
    expect(getWindowsLeaseIdentifiers()).toBeNull();
  });

});
