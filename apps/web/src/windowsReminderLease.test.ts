import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequest = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ request: apiRequest }));
import {
  activateWindowsLease, getWindowsLeaseIdentifiers, renewWindowsLease,
  stopWindowsLease, setWindowsLeaseOptIn, isWindowsLeaseOptedIn,
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

  it("requires explicit opt-in and serializes A revoke before B activation", async () => {
    expect(isWindowsLeaseOptedIn()).toBe(false);
    setWindowsLeaseOptIn(true);
    expect(isWindowsLeaseOptedIn()).toBe(true);
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
    expect(operations[0].body).toMatchObject({
      workspace_id: "workspace-a", generation_id: first, rotate: true,
    });
    expect(operations[3].body).toMatchObject({
      workspace_id: "workspace-b", generation_id: second, rotate: true,
    });
  });
});
