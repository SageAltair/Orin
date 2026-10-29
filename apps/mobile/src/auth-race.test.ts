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
      const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
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

      const taskCall = [...fetchMock.mock.calls].reverse().find(([url]) => String(url).endsWith("/tasks"));
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
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
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
    const taskCall = [...fetchMock.mock.calls].reverse().find(([url]) => String(url).endsWith("/tasks"));
    expect(new Headers(taskCall?.[1]?.headers).has("Authorization")).toBe(false);
    expect(SecureStore.setItemAsync).not.toHaveBeenCalledWith(TOKEN_KEY, "old-refreshed-token");
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
  });
  it("does not return a restored user after logout overtakes the startup request", async () => {
    let completeMe!: (response: Response) => void;
    const pendingMe = new Promise<Response>((resolve) => {
      completeMe = resolve;
    });
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/auth/me")) return pendingMe;
      if (path.endsWith("/auth/logout")) return new Response(null, { status: 204 });
      if (path.endsWith("/tasks"))
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      throw new Error(`Unexpected URL: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("old-token")
      .mockResolvedValueOnce("old-workspace");
    const api = await import("./api");

    const restoring = api.restoreSession();
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/me"))).toBe(true);
    });
    await api.logout();
    completeMe(new Response(JSON.stringify(user), { status: 200 }));
    await expect(restoring).resolves.toBeNull();
    await api.request("/tasks", {}, false);
    const taskCall = [...fetchMock.mock.calls].reverse().find(([url]) => String(url).endsWith("/tasks"));
    expect(new Headers(taskCall?.[1]?.headers).has("Authorization")).toBe(false);
  });

  it("clears an old workspace write before the next account's login completes", async () => {
    let finishWorkspaceWrite!: () => void;
    const pendingWorkspaceWrite = new Promise<void>((resolve) => {
      finishWorkspaceWrite = resolve;
    });
    vi.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
      if (key === "orin.mobile.workspace-id.v1" && value === "old-workspace")
        await pendingWorkspaceWrite;
    });
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/auth/login"))
        return new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 });
      if (path.endsWith("/auth/me"))
        return new Response(JSON.stringify(user), { status: 200 });
      throw new Error(`Unexpected URL: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");

    const oldWrite = api.setActiveWorkspace("old-workspace");
    await vi.waitFor(() => {
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith("orin.mobile.workspace-id.v1", "old-workspace");
    });
    const switching = api.login(user.email, "new-password");
    finishWorkspaceWrite();
    await oldWrite;
    await expect(switching).resolves.toEqual(user);
    expect(api.getActiveWorkspaceId()).toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("orin.mobile.workspace-id.v1");
  });

  it("ignores a late SecureStore hydration from the previous account", async () => {
    let finishTokenRead!: (token: string | null) => void;
    const pendingTokenRead = new Promise<string | null>((resolve) => {
      finishTokenRead = resolve;
    });
    vi.mocked(SecureStore.getItemAsync).mockImplementation(async (key) =>
      key === TOKEN_KEY ? pendingTokenRead : "old-workspace",
    );
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/auth/login"))
        return new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 });
      if (path.endsWith("/auth/me"))
        return new Response(JSON.stringify(user), { status: 200 });
      if (path.endsWith("/tasks"))
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      throw new Error(`Unexpected URL: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");

    const restoring = api.restoreSession();
    await vi.waitFor(() => {
      expect(SecureStore.getItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
    });
    const switching = api.login(user.email, "new-password");
    finishTokenRead("old-token");
    await expect(switching).resolves.toEqual(user);
    await expect(restoring).resolves.toBeNull();
    await api.request("/tasks", {}, false);
    const taskCall = [...fetchMock.mock.calls].reverse().find(([url]) => String(url).endsWith("/tasks"));
    expect(new Headers(taskCall?.[1]?.headers).get("Authorization")).toBe("Bearer new-token");
  });

});
