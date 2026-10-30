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
      activeWorkspaceId="work" mode="balanced" onEditTask={() => undefined}
      onScheduleTask={() => undefined} onStartTask={() => undefined} onCompleteTask={() => undefined}
      now={new Date("2026-10-30T12:00:00Z")}
    />);
    expect(html).toContain("Current workspace commitment");
    expect(html).toContain("Include tasks from all my workspaces");
    expect(html).toContain("No automatic changes or alerts.");
    expect(html).toContain("Edit Current workspace commitment");
    expect(html).toContain("Schedule Current workspace commitment");
    expect(html).toContain("Start Current workspace commitment");
    expect(html).toContain("Mark Current workspace commitment done");
    expect(html).toContain("Mark done");
    expect(html).not.toContain("checked");
  });

  it("disables task actions while another task mutation is in flight", () => {
    const html = renderToStaticMarkup(<PriorityOverview
      tasks={[makeTask("Busy commitment")]} activeWorkspaceId="work" mode="balanced"
      now={new Date("2026-10-30T12:00:00Z")}
      onEditTask={() => undefined} onScheduleTask={() => undefined}
      onStartTask={() => undefined} onCompleteTask={() => undefined} actionsBusy
    />);
    for (const label of ["Edit Busy commitment", "Schedule Busy commitment", "Start Busy commitment", "Mark Busy commitment done"]) {
      const button = html.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>`))?.[0];
      expect(button).toContain('disabled=""');
    }
  });

  it("offers Start only for todo tasks, never blocked or already in-progress work", () => {
    const html = renderToStaticMarkup(<PriorityOverview
      tasks={[
        makeTask("Ready"),
        { ...makeTask("Blocked"), status: "blocked" },
        { ...makeTask("Working"), status: "in_progress" },
      ]}
      activeWorkspaceId="work" mode="balanced"
      onStartTask={() => undefined} onCompleteTask={() => undefined}
      now={new Date("2026-10-30T12:00:00Z")}
    />);
    expect(html).toContain("Start Ready");
    expect(html).not.toContain("Start Blocked");
    expect(html).not.toContain("Start Working");
    expect(html).toContain("Mark Working done");
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
