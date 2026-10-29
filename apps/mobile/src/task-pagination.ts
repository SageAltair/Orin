import { request } from "./api";
import type { Project, Task } from "./types";

const PAGE_SIZE = 100;
const MAX_PAGES = 100;

// The API scopes requests to the owner and active workspace.
// Never silently replace complete data with a partial result.
async function fetchAllPages<T extends { id: string }>(
  endpoint: string,
  resource: string,
): Promise<T[]> {
  const records: T[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const separator = endpoint.includes("?") ? "&" : "?";
    const rows = await request<T[]>(
      endpoint + separator + "limit=" + PAGE_SIZE + "&offset=" + (page * PAGE_SIZE),
    );
    if (!Array.isArray(rows)) throw new Error(resource + " list returned an invalid page.");
    for (const row of rows) {
      if (!row || typeof row.id !== "string")
        throw new Error(resource + " list returned an invalid record.");
      if (!seen.has(row.id)) {
        seen.add(row.id);
        records.push(row);
      }
    }
    if (rows.length < PAGE_SIZE) return records;
  }
  throw new Error(
    "The " + resource + " list exceeds 10,000 entries. Existing records remain visible; try again later.",
  );
}

export const fetchAllMobileTasks = () => fetchAllPages<Task>("/tasks", "task");
export const fetchAllMobileProjects = () => fetchAllPages<Project>("/projects", "project");
export const fetchAllMobileProjectTasks = (projectId: string) =>
  fetchAllPages<Task>("/tasks?project_id=" + encodeURIComponent(projectId), "project task");
