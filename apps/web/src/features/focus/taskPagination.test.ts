import { describe, expect, it, vi } from "vitest";
import { fetchAllPages } from "./taskPagination";

describe("task workspace pagination", () => {
  it("loads every page, including project choices beyond the first hundred", async () => {
    const records = Array.from({ length: 217 }, (_, index) => `project-${index}`);
    const fetchPage = vi.fn(async (offset: number, limit: number) => records.slice(offset, offset + limit));
    expect(await fetchAllPages(fetchPage, "projects")).toEqual(records);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    expect(fetchPage).toHaveBeenLastCalledWith(200, 100);
  });

  it("accepts an exact page multiple only after confirming the next page is empty", async () => {
    const fetchPage = vi.fn(async (offset: number, limit: number) => Array.from({ length: 200 }, (_, index) => index).slice(offset, offset + limit));
    expect(await fetchAllPages(fetchPage, "tasks", 100, 2)).toHaveLength(200);
    expect(fetchPage).toHaveBeenLastCalledWith(200, 1);
  });

  it("fails visibly rather than silently truncating a collection", async () => {
    const fetchPage = vi.fn(async (offset: number, limit: number) => Array.from({ length: 201 }, (_, index) => index).slice(offset, offset + limit));
    await expect(fetchAllPages(fetchPage, "tasks", 100, 2)).rejects.toThrow("More than 200 tasks exist");
  });

  it("propagates API failures instead of presenting an incomplete list", async () => {
    const fetchPage = vi.fn(async (offset: number) => {
      if (offset === 100) throw new Error("Network unavailable");
      return Array.from({ length: 100 }, (_, index) => index);
    });
    await expect(fetchAllPages(fetchPage, "projects")).rejects.toThrow("Network unavailable");
  });
});
