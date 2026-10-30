import { describe, expect, it, vi } from "vitest";
import type { Task } from "./api";
import { loadAppTaskInventory } from "./appTaskInventory";

const inventory = (count: number): Task[] => Array.from(
  { length: count },
  (_, index) => ({ id: `task-${index}`, status: index < 15 ? "done" : "todo" } as Task),
);

describe("app dashboard task inventory", () => {
  it("loads all tasks beyond the API's default page and preserves completed records", async () => {
    const tasks = inventory(237);
    const paths: string[] = [];
    const fetchPage = vi.fn(async (path: string) => {
      paths.push(path);
      const params = new URL(path, "https://orin.invalid").searchParams;
      return tasks.slice(Number(params.get("offset")), Number(params.get("offset")) + Number(params.get("limit")));
    });
    const loaded = await loadAppTaskInventory(fetchPage);
    expect(loaded).toHaveLength(237);
    expect(loaded.filter(task => task.status === "done")).toHaveLength(15);
    expect(loaded.at(-1)?.id).toBe("task-236");
    expect(paths).toEqual([
      "/tasks?limit=100&offset=0",
      "/tasks?limit=100&offset=100",
      "/tasks?limit=100&offset=200",
    ]);
  });

  it("confirms the next page is empty when the total is an exact multiple", async () => {
    const tasks = inventory(200);
    const fetchPage = vi.fn(async (path: string) => {
      const params = new URL(path, "https://orin.invalid").searchParams;
      const offset = Number(params.get("offset"));
      return tasks.slice(offset, offset + Number(params.get("limit")));
    });
    expect(await loadAppTaskInventory(fetchPage)).toHaveLength(200);
    expect(fetchPage).toHaveBeenLastCalledWith("/tasks?limit=1&offset=5000");
  });

  it("fails instead of silently presenting partial dashboard totals", async () => {
    const tasks = inventory(100);
    const fetchPage = vi.fn(async (path: string) => {
      if (path.includes("offset=100")) throw new Error("Second page unavailable");
      return tasks;
    });
    await expect(loadAppTaskInventory(fetchPage)).rejects.toThrow("Second page unavailable");
  });
});
