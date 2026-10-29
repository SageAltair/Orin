import { afterEach, describe, expect, it, vi } from "vitest";
import { login, logout, request, restoreSession, setActiveWorkspace } from "./api";

describe("session restoration", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("times out and falls back to the login screen when the API does not answer", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      expect(init?.signal?.aborted).toBe(false);
      throw new DOMException("The operation was aborted", "TimeoutError");
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(restoreSession()).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});


describe("authentication refresh reliability", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("keeps the access token after a transient refresh network failure", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "test-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockRejectedValueOnce(new TypeError("Network unavailable"))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("test@example.com", "password123");
    await expect(request<unknown[]>("/tasks")).rejects.toMatchObject({ status: 401 });
    await expect(request<unknown[]>("/tasks")).resolves.toEqual([]);

    const retriedRequest = fetchMock.mock.calls[4]?.[1];
    expect(new Headers(retriedRequest?.headers).get("Authorization")).toBe("Bearer test-token");
    expect(dispatchEvent).not.toHaveBeenCalled();
  });

  it("expires the session when the refresh credential is rejected", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "expired-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("test@example.com", "password123");
    await expect(request<unknown[]>("/tasks")).rejects.toMatchObject({ status: 401 });
    expect(dispatchEvent).toHaveBeenCalledOnce();
    expect(dispatchEvent.mock.calls[0]?.[0]).toMatchObject({ type: "orin:session-expired" });
  });
});


describe("web logout and account isolation", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("refreshes an expired access token before revoking the server session", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "old-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "renewed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("user@example.com", "password");
    setActiveWorkspace("workspace-1");
    await expect(logout()).resolves.toBeUndefined();
    await expect(request<unknown[]>("/tasks")).resolves.toEqual([]);

    expect(fetchMock).toHaveBeenCalledTimes(6);
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain("/auth/refresh");
    const retryHeaders = new Headers(fetchMock.mock.calls[4]?.[1]?.headers);
    expect(retryHeaders.get("Authorization")).toBe("Bearer renewed-token");
    const afterLogoutHeaders = new Headers(fetchMock.mock.calls[5]?.[1]?.headers);
    expect(afterLogoutHeaders.get("Authorization")).toBeNull();
    expect(afterLogoutHeaders.get("X-Orin-Workspace-Id")).toBeNull();
  });

  it("clears local account and workspace state when server logout is unavailable", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "old-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("user@example.com", "password");
    setActiveWorkspace("workspace-1");
    await expect(logout()).rejects.toMatchObject({ status: 0 });
    await expect(request<unknown[]>("/tasks")).resolves.toEqual([]);
    const afterLogoutHeaders = new Headers(fetchMock.mock.calls[3]?.[1]?.headers);
    expect(afterLogoutHeaders.get("Authorization")).toBeNull();
    expect(afterLogoutHeaders.get("X-Orin-Workspace-Id")).toBeNull();
  });

  it("bounds logout requests and clears local scope when the server times out", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "old-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockImplementationOnce(async (_url: RequestInfo | URL, init?: RequestInit) => {
        expect(init?.signal).toBeInstanceOf(AbortSignal);
        throw new DOMException("Timed out", "TimeoutError");
      })
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("user@example.com", "password");
    setActiveWorkspace("workspace-1");
    await expect(logout()).rejects.toMatchObject({ status: 0 });
    await expect(request<unknown[]>("/tasks")).resolves.toEqual([]);
    const headers = new Headers(fetchMock.mock.calls[3]?.[1]?.headers);
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("X-Orin-Workspace-Id")).toBeNull();
  });

  it("can revoke the cookie-backed session on retry after an offline sign-out", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "old-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "renewed-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("user@example.com", "password");
    await expect(logout()).rejects.toMatchObject({ status: 0 });
    // The local token was cleared; retry must refresh using the surviving cookie.
    await expect(logout()).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledTimes(6);
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain("/auth/refresh");
    const retryHeaders = new Headers(fetchMock.mock.calls[5]?.[1]?.headers);
    expect(retryHeaders.get("Authorization")).toBe("Bearer renewed-token");
  });

  it("does not send a previous account's workspace when switching logins", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response());
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "first-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "second-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-2" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await login("first@example.com", "password");
    setActiveWorkspace("first-user-workspace");
    await login("second@example.com", "password");
    const headers = new Headers(fetchMock.mock.calls[3]?.[1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer second-token");
    expect(headers.get("X-Orin-Workspace-Id")).toBeNull();
  });
});
