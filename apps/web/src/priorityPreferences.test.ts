import { describe, expect, it } from "vitest";
import { defaultPreferences, normalizePreferences } from "./capabilities";

describe("priority guidance preferences", () => {
  it("defaults to balanced for missing or legacy settings", () => {
    expect(defaultPreferences.priorityGuidanceMode).toBe("balanced");
    expect(normalizePreferences(null).priorityGuidanceMode).toBe("balanced");
    expect(normalizePreferences({ proactiveMode: "persistent" }).priorityGuidanceMode).toBe("balanced");
  });

  it("accepts all supported modes independently from proactive assistance", () => {
    expect(normalizePreferences({ priorityGuidanceMode: "proactive" }).priorityGuidanceMode).toBe("proactive");
    const planning = normalizePreferences({ priorityGuidanceMode: "planning-only", proactiveMode: "persistent" });
    expect(planning.priorityGuidanceMode).toBe("planning-only");
    expect(planning.proactiveMode).toBe("persistent");
    expect(normalizePreferences({ priorityGuidanceMode: "persistent" }).priorityGuidanceMode).toBe("balanced");
  });
});
