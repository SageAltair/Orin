import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";

vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(async () => null),
  setItemAsync: vi.fn(async () => undefined),
  deleteItemAsync: vi.fn(async () => undefined),
}));

const user = {
  id: "user-new",
  email: "new@example.test",
  display_name: "New Account",
  created_at: "2026-10-29T00:00:00Z",
  is_admin: false,
  is_disabled: false,
};

async function storedSession() {
  vi.mocked(SecureStore.getItemAsync)
    .mockResolvedValueOnce("old-access-token")
    .mockResolvedValueOnce("old-workspace");
  const api = await import("./api");
  await api.hydrateSession();
  return api;
}

describe("Android account isolation and logout revocation", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.stubEnv("EXPO_PUBLIC_API_BASE_URL", "https://orin.example");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("does not send a previous account's token or workspace when switching accounts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-access-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(user), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await storedSession();

    await expect(api.login(user.email, "example-password")).resolves.toEqual(user);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(call[1]?.headers);
      expect(headers.has("X-Orin-Workspace-Id")).toBe(false);
    }
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has("Authorization")).toBe(false);
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Authorization"))
      .toBe("Bearer new-access-token");
    expect(api.getActiveWorkspaceId()).toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("orin.mobile.workspace-id.v1");
  });

  it("refreshes an expired token before revoking the server session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "fresh-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await storedSession();

    await expect(api.logout()).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/auth/refresh");
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain("/auth/logout");
    const retryHeaders = new Headers(fetchMock.mock.calls[2]?.[1]?.headers);
    expect(retryHeaders.get("Authorization")).toBe("Bearer fresh-token");
    expect(api.getActiveWorkspaceId()).toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("orin.mobile.access-token.v1");
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("orin.mobile.workspace-id.v1");
  });

  it("bounds logout requests to eight seconds instead of the default two minutes", async () => {
    const timerSpy = vi.spyOn(globalThis, "setTimeout");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const api = await storedSession();

    await expect(api.logout()).resolves.toBeUndefined();
    expect(timerSpy.mock.calls.some(([, timeout]) => timeout === 8_000)).toBe(true);
    expect(timerSpy.mock.calls.some(([, timeout]) => timeout === 120_000)).toBe(false);
  });
});
