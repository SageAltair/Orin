import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Task } from "../../api";
import { PriorityOverview } from "./PriorityOverview";

const makeTask = (id: string): Task => ({
  id, title: id, description: null, status: "todo", priority: "high",
  due_at: "2026-10-30T12:25:00Z", project_id: null,
  created_at: "2026-10-30T09:00:00Z", updated_at: "2026-10-30T09:00:00Z",
});

describe("priority outlook", () => {
  it("defaults to current workspace only with an explicit cross-workspace opt-in", () => {
    const html = renderToStaticMarkup(<PriorityOverview
      tasks={[makeTask("Current workspace commitment")]}
      activeWorkspaceId="work" mode="balanced"
      now={new Date("2026-10-30T12:00:00Z")}
    />);
    expect(html).toContain("Current workspace commitment");
    expect(html).toContain("Include tasks from all my workspaces");
    expect(html).toContain("Read-only, no alerts sent");
    expect(html).not.toContain("checked");
  });

  it("labels planning-only without promising device alerts", () => {
    const html = renderToStaticMarkup(<PriorityOverview
      tasks={[]} activeWorkspaceId="work" mode="planning-only"
      now={new Date("2026-10-30T12:00:00Z")}
    />);
    expect(html).toContain("Planning-only");
    expect(html).toContain("No active tasks to prioritize");
  });
});
