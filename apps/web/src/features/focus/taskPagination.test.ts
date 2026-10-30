import { describe, expect, it, vi } from "vitest";
import { fetchAllPages, fetchAllPagesWithIdentityCheck } from "./taskPagination";

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

  it("rejects overlapping task identities after an offset page shifts", async () => {
    const first = [{ id: "a" }, { id: "b" }];
    const fetchPage = vi.fn(async (offset: number) => offset === 0 ? first : [{ id: "b" }]);
    await expect(fetchAllPages(fetchPage, "tasks", 2, 5, (row) => row.id))
      .rejects.toThrow("Overlapping tasks pages");
  });


  it("confirms the complete identity set for a stable multi-page inventory", async () => {
    const records = Array.from({ length: 217 }, (_, index) => ({ id: "task-" + index }));
    const fetchPage = vi.fn(async (offset: number, limit: number) => records.slice(offset, offset + limit));
    expect(await fetchAllPagesWithIdentityCheck(fetchPage, "tasks", (row) => row.id))
      .toEqual(records);
    expect(fetchPage).toHaveBeenCalledTimes(6);
  });

  it("rejects a missing identity after a concurrent deletion shifts offsets", async () => {
    const afterDeletion = ["b", "c", "d", "e"].map((id) => ({ id }));
    let firstPage = true;
    const fetchPage = vi.fn(async (offset: number, limit: number) => {
      if (firstPage) {
        firstPage = false;
        return [{ id: "a" }, { id: "b" }];
      }
      return afterDeletion.slice(offset, offset + limit);
    });
    // First pass returns a,b,d,e with no overlap, silently omitting c.
    // Second pass returns b,c,d,e, so the loader must reject the snapshot.
    await expect(fetchAllPagesWithIdentityCheck(fetchPage, "tasks", (row) => row.id, 2, 5))
      .rejects.toThrow("tasks changed during pagination");
  });

  it("avoids a second scan for a single-page collection", async () => {
    const fetchPage = vi.fn(async () => [{ id: "one" }]);
    expect(await fetchAllPagesWithIdentityCheck(fetchPage, "projects", (row) => row.id))
      .toEqual([{ id: "one" }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("rejects invalid project identities and malformed pages", async () => {
    const badId = vi.fn(async () => [{ id: "" }]);
    await expect(fetchAllPages(badId, "projects", 2, 5, (row) => row.id))
      .rejects.toThrow("Invalid projects record");
    const badPage = vi.fn(async () => ({ unexpected: true } as never));
    await expect(fetchAllPages(badPage, "tasks")).rejects.toThrow("Invalid tasks page");
  });
});
