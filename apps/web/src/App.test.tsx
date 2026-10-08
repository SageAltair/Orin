import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "./App";
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
