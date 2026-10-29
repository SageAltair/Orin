import { describe, expect, it } from "vitest";
import { mobileProjectLabel, PROJECT_CHOICE_LIMIT, searchMobileProjects } from "./task-projects";
import type { Project } from "./types";

const project = (id: string, name: string) => ({ id, name } as Project);

describe("mobile task project association", () => {
  it("finds projects beyond the first page with case-insensitive search", () => {
    const projects = Array.from({ length: 120 }, (_, index) => project(String(index), `Project ${index}`));
    projects.push(project("last", "Rare Research Initiative"));
    const result = searchMobileProjects(projects, "  RESEARCH  ");
    expect(result.total).toBe(1);
    expect(result.choices.map((item) => item.id)).toEqual(["last"]);
  });

  it("limits rendering without silently claiming the full list is visible", () => {
    const projects = Array.from({ length: 140 }, (_, index) => project(String(index), `Project ${index}`));
    const result = searchMobileProjects(projects, "");
    expect(result.total).toBe(140);
    expect(result.choices).toHaveLength(PROJECT_CHOICE_LIMIT);
    expect(result.choices[0].name).toBe("Project 0");
  });

  it("sorts duplicate names consistently and handles an empty search", () => {
    const result = searchMobileProjects([project("b", "Alpha"), project("a", "Alpha"), project("c", "Beta")], "alpha");
    expect(result.choices.map((item) => item.id)).toEqual(["a", "b"]);
    expect(searchMobileProjects([], "anything")).toEqual({ choices: [], total: 0 });
  });

  it("preserves the identity of a linked project when its choices cannot be loaded", () => {
    const projects = [project("one", "First project")];
    expect(mobileProjectLabel(projects, "one")).toBe("First project");
    expect(mobileProjectLabel(projects, null)).toBe("No project");
    expect(mobileProjectLabel(projects, "missing")).toBe("Linked project unavailable");
  });
});
