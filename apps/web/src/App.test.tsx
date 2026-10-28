import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App, { CommandAnswer, MarkdownResponse, mergeCommandHistory, safeHref } from "./App";
import { KnowledgeWorkspace, QuickKnowledgeCapture } from "./KnowledgeWorkspace";
import { capabilities, defaultPreferences, getNavigationCapabilities, type UserPreferences } from "./capabilities";
import { OrinWorkspace } from "./OrinWorkspace";
import { QuickOrin } from "./QuickOrin";
import { GuidedMode, GUIDES } from "./GuidedMode";
import { IntelligenceExplorer } from "./IntelligenceExplorer";
import { SpecialistAutomation } from "./SpecialistAutomation";
import { IntelligenceReview } from "./IntelligenceReview";

describe("capability navigation", () => {
  it("shows only capabilities enabled in the user's preferences", () => {
    expect(getNavigationCapabilities(capabilities, defaultPreferences).map(({ id }) => id)).toEqual(["home", "tasks", "orin", "calendar", "opportunities", "projects", "activity", "memories", "focus"]);
  });

  it("orders pinned capabilities first and never exposes ungranted capabilities", () => {
    const preferences: UserPreferences = { ...defaultPreferences, visibleCapabilities: ["projects", "tasks", "home"], pinnedCapabilities: ["projects"] };
    const granted = capabilities.filter(({ id }) => id !== "activity");
    expect(getNavigationCapabilities(granted, preferences).map(({ id }) => id)).toEqual(["projects", "home", "tasks"]);
  });

  it("checks for a refreshable session before showing private workspace data", () => {
    const markup = renderToStaticMarkup(<App />);
    expect(markup).toContain("Checking your session");
    expect(markup).not.toContain("Morgan");
  });

  it("renders the full Orin workspace with session and context controls", () => {
    const markup = renderToStaticMarkup(<OrinWorkspace command="" setCommand={() => undefined} submitCommand={() => undefined} busy={false} message="" turns={[]} conversations={[]} conversationId={null} openConversation={async () => undefined} newConversation={() => undefined} projects={[]} tasks={[]} projectId="" setProjectId={() => undefined} taskId="" setTaskId={() => undefined} models={[]} modelId="" setModelId={() => undefined} starters={[{ label: "Plan today", prompt: "Plan today" }]} templatesOpen={false} setTemplatesOpen={() => undefined} renderAnswer={() => null} />);
    expect(markup).toContain('aria-label="Orin Workspace"');
    expect(markup).toContain("Recent work");
    expect(markup).toContain("Workspace context");
    expect(markup).toContain("Plan today");
  });

  it("renders Quick Orin with contextual actions and navigation", () => {
    const markup = renderToStaticMarkup(<QuickOrin open onClose={() => undefined} command="" setCommand={() => undefined} submitCommand={async () => undefined} onSent={() => undefined} onCaptureIdea={() => undefined} navigate={() => undefined} capabilities={capabilities} page="projects" projectName="Documentary" taskName="Draft outline" busy={false} />);
    expect(markup).toContain('aria-label="Quick Orin command"');
    expect(markup).toContain("Capture an idea");
    expect(markup).toContain("Current context: projects · Documentary · Draft outline");
    expect(markup).toContain("Ctrl");
  });

  it("renders Guided Mode with reusable walkthroughs and server-safe progress", () => {
    const markup = renderToStaticMarkup(<GuidedMode open onClose={() => undefined} navigate={() => undefined} />);
    expect(markup).toContain('aria-labelledby="guided-title"');
    expect(markup).toContain("Configure an AI provider");
    expect(markup).toContain("Plan time on your calendar");
    expect(GUIDES.flatMap(guide => guide.steps).every(step => step.control.length > 0)).toBe(true);
  });

  it("renders the advanced intelligence entry points", () => {
    const markup = renderToStaticMarkup(<IntelligenceExplorer projects={[]} />);
    expect(markup).toContain("Personal Radar");
    expect(markup).toContain("Life Graph");
    expect(markup).toContain("Decision Simulator");
  });

  it("renders unified specialist coordination and automation", () => {
    const markup = renderToStaticMarkup(<SpecialistAutomation projects={[]} />);
    expect(markup).toContain("Specialists and automation");
    expect(markup).toContain("Open coordinator");
  });

  it("renders missing-work, reflection, and brain-dump tools", () => {
    const markup = renderToStaticMarkup(<IntelligenceReview />);
    expect(markup).toContain("What am I missing?");
    expect(markup).toContain("Weekly reflection");
    expect(markup).toContain("Brain dump");
  });
});

describe("Markdown response rendering", () => {
  it("renders the writing workspace and quick capture privacy notice", () => {
    const workspace = renderToStaticMarkup(<KnowledgeWorkspace projects={[]} />);
    const capture = renderToStaticMarkup(<QuickKnowledgeCapture onClose={() => undefined} onSaved={() => undefined} />);
    expect(workspace).toContain('aria-label="Creative Studio"');
    expect(workspace).toContain("Notes");
    expect(workspace).toContain("Notebooks");
    expect(workspace).toContain("New note");
    expect(capture).toContain("Saved to Writing");
    expect(capture).toContain('aria-modal="true"');
  });

  it("restores command history in order without duplicating an already rendered command", () => {
    const old = { command_id: "old", text: "first", created_at: "2026-10-08T00:00:00Z", status: "completed", intent: "RESPOND", result: { response: "first answer" }, message: "first answer" };
    const latest = { ...old, command_id: "latest", text: "second", result: { response: "second answer" }, message: "second answer" };
    const restored = mergeCommandHistory([latest, old], [{ prompt: "second", result: latest }]);
    expect(restored.map(turn => turn.result.command_id)).toEqual(["old", "latest"]);
  });

  it("renders a command response once when the API repeats it in message and result fields", () => {
    const answer = "A single answer from Orin.";
    const markup = renderToStaticMarkup(<CommandAnswer result={{ command_id: "cmd-1", status: "completed", intent: "RESPOND", message: answer, result: { response: answer } }} />);
    expect(markup.split(answer)).toHaveLength(2);
    expect(markup).toContain("markdown-body");
  });

  it("renders GFM structure and escapes raw HTML", () => {
    const markup = renderToStaticMarkup(<MarkdownResponse value={'## Summary\n\n**Useful** text\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>\n\n```js\nconst answer = 42;\n```'} />);
    expect(markup).toContain("<h2>Summary</h2>");
    expect(markup).toContain("<strong>Useful</strong>");
    expect(markup).toContain("table-scroll");
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).toContain('aria-label="Copy code"');
    expect(markup).toContain("Copy response");
    expect(markup).not.toContain("svgCopy response");
    expect(markup).not.toContain("svgAdd attachmentAsk Orin");
  });

  it("rejects unsafe URL schemes", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,hi")).toBeUndefined();
    expect(safeHref("https://example.com")).toBe("https://example.com");
  });
});
