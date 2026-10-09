import { afterEach, describe, expect, it, vi } from "vitest";
import { restoreSession } from "./api";

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
