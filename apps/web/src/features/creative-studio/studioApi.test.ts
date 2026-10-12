import { describe, expect, it } from "vitest";
import { suggestIdeas } from "./studioApi";

describe("studio suggestions", () => {
  it("offers one prompt for each thinking move", () => {
    const suggestions = suggestIdeas("A lighthouse that keeps no light");

    expect(suggestions.map(item => item.kind)).toEqual(["explore", "expand", "connect", "challenge"]);
    expect(new Set(suggestions.map(item => item.kind)).size).toBe(suggestions.length);
  });

  it("seeds every prompt with the first line of the idea", () => {
    const suggestions = suggestIdeas("The keeper waits\nand asks nothing.");

    expect(suggestions.every(item => item.prompt.includes("The keeper waits"))).toBe(true);
  });

  it("trims and bounds a long seed so prompts stay readable", () => {
    const suggestions = suggestIdeas(`  ${"x".repeat(200)}  `);

    expect(suggestions[0].prompt).not.toContain("  ");
    expect(suggestions[0].prompt.length).toBeLessThan(200);
  });

  it("falls back to a readable topic when the idea is blank", () => {
    const suggestions = suggestIdeas("   ");

    expect(suggestions.every(item => item.prompt.includes("this idea"))).toBe(true);
  });

  it("keeps prompts non-empty and labelled", () => {
    for (const suggestion of suggestIdeas("A quiet harbour")) {
      expect(suggestion.label.length).toBeGreaterThan(0);
      expect(suggestion.prompt.trim().length).toBeGreaterThan(0);
    }
  });
});
