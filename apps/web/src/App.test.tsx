import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App, { MarkdownResponse, safeHref } from "./App";
import { capabilities, defaultPreferences, getNavigationCapabilities, type UserPreferences } from "./capabilities";

describe("capability navigation", () => {
  it("shows only capabilities enabled in the user's preferences", () => {
    expect(getNavigationCapabilities(capabilities, defaultPreferences).map(({ id }) => id)).toEqual(["home", "tasks"]);
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
});

describe("Markdown response rendering", () => {
  it("renders GFM structure and escapes raw HTML", () => {
    const markup = renderToStaticMarkup(<MarkdownResponse value={'## Summary\n\n**Useful** text\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>\n\n```js\nconst answer = 42;\n```'} />);
    expect(markup).toContain("<h2>Summary</h2>");
    expect(markup).toContain("<strong>Useful</strong>");
    expect(markup).toContain("table-scroll");
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).toContain('aria-label="Copy code"');
  });

  it("rejects unsafe URL schemes", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,hi")).toBeUndefined();
    expect(safeHref("https://example.com")).toBe("https://example.com");
  });
});
