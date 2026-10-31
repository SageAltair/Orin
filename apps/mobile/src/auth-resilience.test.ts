import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";

vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(async () => null),
  setItemAsync: vi.fn(async () => undefined),
  deleteItemAsync: vi.fn(async () => undefined),
}));

const user = {
  id: "user-1",
  email: "test@example.com",
  display_name: "Test",
  created_at: "2026-10-29T00:00:00Z",
  is_admin: false,
  is_disabled: false,
};

async function withStoredToken(token = "old-token") {
  vi.mocked(SecureStore.getItemAsync)
    .mockResolvedValueOnce(token)
    .mockResolvedValueOnce("workspace-1");
  const api = await import("./api");
  await api.hydrateSession();
  return api;
}

describe("mobile authentication resilience", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.stubEnv("EXPO_PUBLIC_API_BASE_URL", "https://orin.example");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it.each(["offline", "server error"])(
    "keeps a saved access token after a %s during refresh",
    async (failure) => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(new Response(null, { status: 401 }))
        .mockImplementationOnce(() =>
          failure === "offline"
            ? Promise.reject(new Error("Network unavailable"))
            : Promise.resolve(new Response(null, { status: 503 })),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ ok: true }), { status: 200 }),
        );
      vi.stubGlobal("fetch", fetchMock);
      const api = await withStoredToken();

      await expect(api.request("/tasks")).rejects.toMatchObject({ status: 401 });
      expect(api.wasRefreshCredentialRejected()).toBe(false);
      await expect(api.request<{ ok: boolean }>("/tasks")).resolves.toEqual({ ok: true });
      const lastHeaders = new Headers(fetchMock.mock.calls[2]?.[1]?.headers);
      expect(lastHeaders.get("Authorization")).toBe("Bearer old-token");
      expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
    },
  );

  it.each([401, 403])(
    "removes the stored access token when refresh credentials are rejected (%i)",
    async (status) => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(new Response(null, { status: 401 }))
        .mockResolvedValueOnce(new Response(null, { status }))
        .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
      vi.stubGlobal("fetch", fetchMock);
      const api = await withStoredToken();

      await expect(api.request("/tasks")).rejects.toMatchObject({ status: 401 });
      expect(api.wasRefreshCredentialRejected()).toBe(true);
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
        "orin.mobile.access-token.v1",
      );
      await api.request("/tasks");
      const lastHeaders = new Headers(fetchMock.mock.calls[2]?.[1]?.headers);
      expect(lastHeaders.has("Authorization")).toBe(false);
    },
  );

  it("does not refresh or erase a saved session when startup is offline", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("old-token")
      .mockResolvedValueOnce("workspace-1");
    const api = await import("./api");

    await expect(api.restoreSession()).resolves.toBeNull();
    expect(api.wasRefreshCredentialRejected()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
    await api.request("/tasks");
    const lastHeaders = new Headers(fetchMock.mock.calls[1]?.[1]?.headers);
    expect(lastHeaders.get("Authorization")).toBe("Bearer old-token");
  });

  it("marks a definitively rejected startup refresh for OS reminder cleanup", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("expired-token")
      .mockResolvedValueOnce("workspace-1");
    const api = await import("./api");

    await expect(api.restoreSession()).resolves.toBeNull();
    expect(api.wasRefreshCredentialRejected()).toBe(true);
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
      "orin.mobile.access-token.v1",
    );
  });

  it("refreshes an expired token and restores the authenticated user", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(user), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("expired-token")
      .mockResolvedValueOnce("workspace-1");
    const api = await import("./api");

    await expect(api.restoreSession()).resolves.toMatchObject(user);
    expect(api.wasRefreshCredentialRejected()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
      "orin.mobile.access-token.v1",
      "new-token",
    );
    const lastHeaders = new Headers(fetchMock.mock.calls[2]?.[1]?.headers);
    expect(lastHeaders.get("Authorization")).toBe("Bearer new-token");
  });

  it("resets a rejected-refresh signal on explicit login to a new session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(user), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await withStoredToken();

    await expect(api.request("/tasks")).rejects.toMatchObject({ status: 401 });
    expect(api.wasRefreshCredentialRejected()).toBe(true);
    await expect(api.login(user.email, "new-password")).resolves.toEqual(user);
    expect(api.wasRefreshCredentialRejected()).toBe(false);
  });

  it("provides actionable physical-device diagnostics on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Network unavailable")));
    const api = await import("./api");

    await expect(api.request("/tasks")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("/health/ready"),
    });
  });

  it("clears local credentials even when remote logout cannot be confirmed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
    const api = await withStoredToken();

    await expect(api.logout()).rejects.toMatchObject({ status: 0 });
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
      "orin.mobile.access-token.v1",
    );
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
      "orin.mobile.workspace-id.v1",
    );
  });
});
