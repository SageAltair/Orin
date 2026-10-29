import type { Project } from "./types";

export const PROJECT_CHOICE_LIMIT = 30;

// Search the complete, owner/workspace-scoped project result, not just its first page.
// Keep rendering bounded on phones while allowing every project to be found by name.
export function searchMobileProjects(projects: Project[], search: string) {
  const query = search.trim().toLocaleLowerCase();
  const matches = projects
    .filter((project) => project.name.toLocaleLowerCase().includes(query))
    .sort((left, right) => left.name.localeCompare(right.name) || left.id.localeCompare(right.id));
  return { choices: matches.slice(0, PROJECT_CHOICE_LIMIT), total: matches.length };
}

export function mobileProjectLabel(projects: Project[], projectId: string | null) {
  if (!projectId) return "No project";
  return projects.find((project) => project.id === projectId)?.name ?? "Linked project unavailable";
}
