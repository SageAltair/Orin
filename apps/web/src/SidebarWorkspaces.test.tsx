import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SidebarWorkspaces, workspaceStorageKey } from "./SidebarWorkspaces";

describe("SidebarWorkspaces", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("exposes server-backed workspace creation", () => {
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem: vi.fn() });
    const markup = renderToStaticMarkup(<SidebarWorkspaces userId="user-1" onActiveChange={() => undefined} />);
    expect(markup).toContain("New workspace");
  });

  it("keeps each user's active workspace choice separate", () => {
    expect(workspaceStorageKey("user-2")).toBe("orin.sidebar-workspaces.user-2.v1");
  });
});
