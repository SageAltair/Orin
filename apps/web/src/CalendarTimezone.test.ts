import { describe, expect, it } from "vitest";
import { instantFromZoneInput } from "./CalendarWorkspace";

describe("Calendar task scheduling timezone safety", () => {
  it("preserves an unambiguous local time in a non-DST timezone", () => {
    expect(instantFromZoneInput("2026-10-30T09:45", "Africa/Dar_es_Salaam"))
      .toBe("2026-10-30T06:45:00.000Z");
  });

  it("rejects nonexistent spring-forward wall times", () => {
    expect(() => instantFromZoneInput("2026-03-08T02:30", "America/New_York"))
      .toThrow("does not exist");
  });

  it("rejects ambiguous fall-back wall times rather than silently picking an instant", () => {
    expect(() => instantFromZoneInput("2026-11-01T01:30", "America/New_York"))
      .toThrow("occurs twice");
  });

  it("also catches half-hour fall-back transitions", () => {
    expect(() => instantFromZoneInput("2026-04-05T01:45", "Australia/Lord_Howe"))
      .toThrow("occurs twice");
  });

  it("accepts a nearby unambiguous time after the fall-back transition", () => {
    expect(instantFromZoneInput("2026-11-01T02:30", "America/New_York"))
      .toBe("2026-11-01T07:30:00.000Z");
  });
});
