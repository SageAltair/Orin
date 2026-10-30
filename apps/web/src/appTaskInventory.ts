import { request, type Task } from "./api";
import { fetchAllPages } from "./features/focus/taskPagination";

/**
 * App-level task inventory powers Home progress and task shortcuts.
 * Keep it complete, just like the dedicated Tasks workspace, so that
 * accounts with more than one API page never show misleading totals.
 */
export function loadAppTaskInventory(
  fetchPage: (path: string) => Promise<Task[]> = path => request<Task[]>(path),
): Promise<Task[]> {
  return fetchAllPages<Task>(
    (offset, limit) => fetchPage(`/tasks?limit=${limit}&offset=${offset}`),
    "dashboard tasks",
    100,
    50,
    task => task.id,
  );
}
