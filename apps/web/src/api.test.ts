import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestBlob, restoreSession } from "./api";

describe("session restoration", () => {
  afterEach(() => vi.unstubAllGlobals());

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
});
