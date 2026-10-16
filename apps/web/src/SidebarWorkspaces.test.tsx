import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { readWorkspaces, SidebarWorkspaces, workspaceStorageKey } from "./SidebarWorkspaces";

describe("SidebarWorkspaces", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("starts with a personal workspace and exposes workspace creation", () => {
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem: vi.fn() });
    expect(readWorkspaces("user-1")).toEqual([{ id: "personal", name: "Personal", color: "#6b73ff" }]);
    const markup = renderToStaticMarkup(<SidebarWorkspaces userId="user-1" onActiveChange={() => undefined} />);
    expect(markup).toContain("Personal");
    expect(markup).toContain("New workspace");
  });

  it("restores saved workspace choices for the current user", () => {
    const saved = [{ id: "content", name: "Content &amp; Media", color: "#2da6b5" }];
    const getItem = vi.fn((key: string) => key === workspaceStorageKey("user-2") ? JSON.stringify(saved) : "content");
    vi.stubGlobal("localStorage", { getItem, setItem: vi.fn() });
    expect(readWorkspaces("user-2")).toEqual(saved);
  });
});
