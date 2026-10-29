import { request } from "./api";
import type { Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;

// Load the full owner/workspace-scoped list before replacing visible tasks.
// A partial API failure must never look like a successful empty result.
export async function fetchAllMobileTasks(): Promise<Task[]> {
  const tasks: Task[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const rows = await request<Task[]>(`/tasks?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`);
    if (!Array.isArray(rows)) throw new Error("Task list returned an invalid page.");
    for (const task of rows) {
      if (!seen.has(task.id)) {
        seen.add(task.id);
        tasks.push(task);
      }
    }
    if (rows.length < PAGE_SIZE) return tasks;
  }
  throw new Error("The task list exceeds 10,000 entries. Existing tasks remain visible; try again later.");
}
