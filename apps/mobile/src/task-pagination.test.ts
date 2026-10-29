import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "./api";
import { fetchAllMobileTasks } from "./task-pagination";

vi.mock("./api", () => ({ request: vi.fn() }));
beforeEach(() => vi.resetAllMocks());

describe("mobile Tasks pagination", () => {
  it("loads every page without hiding tasks beyond the first 100", async () => {
    const first = Array.from({ length: 100 }, (_, i) => ({ id: String(i), title: String(i) }));
    vi.mocked(request).mockImplementation(async (path) =>
      (path.includes("offset=0") ? first : [{ id: "last", title: "last" }]) as never);
    const result = await fetchAllMobileTasks();
    expect(result).toHaveLength(101);
    expect(result.at(-1)?.id).toBe("last");
    expect(vi.mocked(request).mock.calls.map(([path]) => path))
      .toEqual(["/tasks?limit=100&offset=0", "/tasks?limit=100&offset=100"]);
  });
  it("rejects a partial failed fetch instead of silently replacing the full list", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.includes("offset=0")) return Array.from({ length: 100 }, (_, i) => ({ id: String(i) })) as never;
      throw new Error("offline");
    });
    await expect(fetchAllMobileTasks()).rejects.toThrow("offline");
  });
});
