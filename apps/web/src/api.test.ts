import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, login, logout, request, requestBlob, restoreSession, setActiveWorkspace } from "./api";

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

describe("authenticated file downloads", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("bounds file requests with a timeout and gives a connectivity error", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      throw new DOMException("Request timed out", "TimeoutError");
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(requestBlob("/attachments/test/download")).rejects.toMatchObject({
      message: "Could not reach Orin. Check your connection and API configuration.",
      status: 0,
    } satisfies Partial<ApiError>);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("refreshes once and retries the download after an expired access token", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response("file contents", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(requestBlob("/attachments/test/download").then(blob => blob.text())).resolves.toBe("file contents");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain("/auth/refresh");
    const headers = fetchMock.mock.calls[2][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer new-token");
  });

  it("preserves the token and avoids session-expired on transient download refresh failure", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "download-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockRejectedValueOnce(new TypeError("Network unavailable"))
      .mockResolvedValueOnce(new Response("file contents", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await login("user@example.com", "password");
    await expect(requestBlob("/attachments/test/download")).rejects.toMatchObject({ status: 401 });
    await expect(requestBlob("/attachments/test/download").then(blob => blob.text())).resolves.toBe("file contents");
    const headers = new Headers(fetchMock.mock.calls[4]?.[1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer download-token");
    expect(dispatchEvent).not.toHaveBeenCalled();
  });

  it("expires the session only when download refresh credentials are rejected", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "expired-download-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await login("user@example.com", "password");
    await expect(requestBlob("/attachments/test/download")).rejects.toMatchObject({ status: 401 });
    expect(dispatchEvent).toHaveBeenCalledOnce();
    expect(dispatchEvent.mock.calls[0]?.[0]).toMatchObject({ type: "orin:session-expired" });
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


describe("successful response metadata", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("exposes the recovery header without changing the parsed API result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ enabled: false }), {
        status: 200,
        headers: { "X-Orin-Preferences-Recovery": "required" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const observe = vi.fn();
    const result = await request<{ enabled: boolean }>(
      "/notifications/preferences", {}, true, observe,
    );
    expect(result).toEqual({ enabled: false });
    expect(observe).toHaveBeenCalledOnce();
    expect(observe.mock.calls[0][0].headers.get("X-Orin-Preferences-Recovery")).toBe("required");
  });

  it("never treats a failed response as successful recovery metadata", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 }),
    ));
    const observe = vi.fn();
    await expect(request("/notifications/preferences", {}, true, observe)).rejects.toMatchObject({ status: 503 });
    expect(observe).not.toHaveBeenCalled();
  });
});
