import { describe, expect, it } from "vitest";
import { paginateTaskList } from "./taskListPage";

describe("bounded task list", () => {
  const tasks = Array.from({ length: 26 }, (_, index) => index);
  it("shows only ten tasks per page without losing later tasks", () => {
    expect(paginateTaskList(tasks, 1).pageTasks).toEqual(tasks.slice(0, 10));
    expect(paginateTaskList(tasks, 2).pageTasks).toEqual(tasks.slice(10, 20));
    expect(paginateTaskList(tasks, 3).pageTasks).toEqual(tasks.slice(20));
  });
  it("clamps stale page selection after filtering", () => {
    expect(paginateTaskList(tasks.slice(0, 3), 9)).toMatchObject({ currentPage: 1, pageCount: 1, pageTasks: [0, 1, 2] });
  });
  it("handles empty lists and invalid page size", () => {
    expect(paginateTaskList([], 5)).toMatchObject({ currentPage: 1, pageCount: 1, pageTasks: [] });
    expect(() => paginateTaskList(tasks, 1, 0)).toThrow(RangeError);
  });
});
