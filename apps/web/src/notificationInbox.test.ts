import { describe, expect, it, vi } from "vitest";
import { eligibleAttentionItems, fetchCompleteNotificationInbox } from "./notificationInbox";

describe("web notification inbox completeness", () => {
  it("loads older unread reminders beyond the API's default first 100", async () => {
    const records = Array.from({ length: 225 }, (_, i) => ({
      id: "notification-" + i,
      read_at: i === 224 ? null : "2026-10-30T10:00:00Z",
    }));
    const fetchPage = vi.fn(async (offset: number, limit: number) =>
      records.slice(offset, offset + limit));
    const loaded = await fetchCompleteNotificationInbox(fetchPage);
    expect(loaded).toHaveLength(225);
    expect(loaded.at(-1)).toEqual({ id: "notification-224", read_at: null });
    expect(fetchPage).toHaveBeenCalledTimes(4); // Two confirmed 200+25 passes.
    expect(fetchPage).toHaveBeenCalledWith(200, 200);
  });

  it("avoids redundant scans for a short inbox", async () => {
    const fetchPage = vi.fn(async () => [{ id: "one" }]);
    expect(await fetchCompleteNotificationInbox(fetchPage)).toEqual([{ id: "one" }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("rejects a concurrent deletion that silently shifts offset pages", async () => {
    let first = true;
    const fetchPage = vi.fn(async (offset: number, limit: number) => {
      if (first) {
        first = false;
        return [{ id: "a" }, { id: "b" }];
      }
      return ["b", "c", "d", "e"].map((id) => ({ id })).slice(offset, offset + limit);
    });
    await expect(fetchCompleteNotificationInbox(fetchPage, 2, 5))
      .rejects.toThrow("notifications changed during pagination");
  });

  it("rejects an oversized inbox rather than claiming the count is complete", async () => {
    const rows = Array.from({ length: 6 }, (_, i) => ({ id: String(i) }));
    const fetchPage = vi.fn(async (offset: number, limit: number) =>
      rows.slice(offset, offset + limit));
    await expect(fetchCompleteNotificationInbox(fetchPage, 2, 2))
      .rejects.toThrow("More than 4 notifications exist");
  });
});

describe("browser interruption policy", () => {
  const rows = [
    { id: "older", category: "tasks", attention_ready: true, read_at: null },
    { id: "disabled-category", category: "calendar", attention_ready: true, read_at: null },
    { id: "acknowledged", category: "tasks", attention_ready: true, read_at: "2026-10-30T12:00:00Z" },
    { id: "not-ready", category: "tasks", attention_ready: false, read_at: null },
  ];
  it("suppresses all stale alerts immediately after global opt-out", () => {
    expect(eligibleAttentionItems(rows, { enabled: false, categories: ["tasks", "calendar"] }))
      .toEqual([]);
  });
  it("excludes disabled categories, acknowledged and not-ready records", () => {
    expect(eligibleAttentionItems(rows, { enabled: true, categories: ["tasks"] }))
      .toEqual([rows[0]]);
  });
});
