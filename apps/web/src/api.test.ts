import { afterEach, describe, expect, it, vi } from "vitest";
import { login, request, restoreSession } from "./api";

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
