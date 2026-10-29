import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";

vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(async () => null),
  setItemAsync: vi.fn(async () => undefined),
  deleteItemAsync: vi.fn(async () => undefined),
}));

const TOKEN_KEY = "orin.mobile.access-token.v1";
const user = {
  id: "new-user",
  email: "new@example.test",
  display_name: "New Account",
  created_at: "2026-10-29T00:00:00Z",
  is_admin: false,
  is_disabled: false,
};

async function oldSession() {
  vi.mocked(SecureStore.getItemAsync)
    .mockResolvedValueOnce("old-token")
    .mockResolvedValueOnce("old-workspace");
  const api = await import("./api");
  await api.hydrateSession();
  return api;
}

describe("Android concurrent refresh and account transitions", () => {
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

  it.each([200, 401] as const)(
    "ignores an old account's delayed refresh response (%i) after explicit login",
    async (refreshStatus) => {
      let completeRefresh!: (response: Response) => void;
      const pendingRefresh = new Promise<Response>((resolve) => {
        completeRefresh = resolve;
      });
      const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
        const path = String(url);
        if (path.endsWith("/projects")) return new Response(null, { status: 401 });
        if (path.endsWith("/auth/refresh")) return pendingRefresh;
        if (path.endsWith("/auth/login"))
          return new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 });
        if (path.endsWith("/auth/me"))
          return new Response(JSON.stringify(user), { status: 200 });
        if (path.endsWith("/tasks"))
          return new Response(JSON.stringify({ ok: true }), { status: 200 });
        throw new Error(`Unexpected URL: ${path}`);
      });
      vi.stubGlobal("fetch", fetchMock);
      const api = await oldSession();

      const oldRequest = api.request("/projects");
      await vi.waitFor(() => {
        expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/refresh"))).toBe(true);
      });

      await expect(api.login(user.email, "new-password")).resolves.toEqual(user);
      completeRefresh(
        refreshStatus === 200
          ? new Response(JSON.stringify({ access_token: "old-refreshed-token" }), { status: 200 })
          : new Response(null, { status: 401 }),
      );
      await expect(oldRequest).rejects.toMatchObject({ status: 401 });
      await expect(api.request("/tasks", {}, false)).resolves.toEqual({ ok: true });

      const taskCall = fetchMock.mock.calls.findLast(([url]) => String(url).endsWith("/tasks"));
      expect(new Headers(taskCall?.[1]?.headers).get("Authorization")).toBe("Bearer new-token");
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, "new-token");
      expect(SecureStore.setItemAsync).not.toHaveBeenCalledWith(TOKEN_KEY, "old-refreshed-token");
    },
  );

  it("does not resurrect an old access token when its refresh completes after logout", async () => {
    let completeRefresh!: (response: Response) => void;
    const pendingRefresh = new Promise<Response>((resolve) => {
      completeRefresh = resolve;
    });
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.endsWith("/projects")) return new Response(null, { status: 401 });
      if (path.endsWith("/auth/refresh")) return pendingRefresh;
      if (path.endsWith("/auth/logout")) return new Response(null, { status: 204 });
      if (path.endsWith("/tasks"))
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      throw new Error(`Unexpected URL: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const api = await oldSession();

    const oldRequest = api.request("/projects");
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/refresh"))).toBe(true);
    });
    await expect(api.logout()).resolves.toBeUndefined();
    completeRefresh(new Response(JSON.stringify({ access_token: "old-refreshed-token" }), { status: 200 }));
    await expect(oldRequest).rejects.toMatchObject({ status: 401 });

    await expect(api.request("/tasks", {}, false)).resolves.toEqual({ ok: true });
    const taskCall = fetchMock.mock.calls.findLast(([url]) => String(url).endsWith("/tasks"));
    expect(new Headers(taskCall?.[1]?.headers).has("Authorization")).toBe(false);
    expect(SecureStore.setItemAsync).not.toHaveBeenCalledWith(TOKEN_KEY, "old-refreshed-token");
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
  });
});
