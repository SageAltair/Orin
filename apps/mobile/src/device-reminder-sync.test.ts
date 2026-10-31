import { beforeEach, describe, expect, it, vi } from "vitest";
import { request, wasRefreshCredentialRejected } from "./api";
import { getLocalReminderEnabled, revokeLocalReminderOwner, syncLocalReminders } from "./native-reminders";
import { fetchDeviceReminderInbox, fetchDeviceReminderTasks, refreshDeviceReminders } from "./device-reminder-sync";
import type { NotificationPolicy, Reminder, Task } from "./types";

vi.mock("./api", () => ({ request: vi.fn(), wasRefreshCredentialRejected: vi.fn() }));
vi.mock("./native-reminders", () => ({
  getLocalReminderEnabled: vi.fn(),
  revokeLocalReminderOwner: vi.fn(),
  syncLocalReminders: vi.fn(),
}));

const now = Date.parse("2026-10-29T12:00:00Z");
function task(id: string, due: string | null, status: Task["status"] = "todo"): Task {
  return {
    id, title: id, description: null, priority: "normal", status,
    due_at: due, project_id: null,
    created_at: new Date(now).toISOString(),
    updated_at: new Date(now).toISOString(),
  };
}
const due = "2026-11-02T12:00:00Z";
const policy: NotificationPolicy = {
  enabled: true, categories: ["tasks"], persistent: false, repeat_minutes: 15,
  max_repeats: 3, timezone: "UTC", quiet_enabled: false,
  quiet_start: "22:00", quiet_end: "07:00", respect_focus: true,
  browser_alerts: false, sound: false,
};
const inbox: Reminder[] = [];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getLocalReminderEnabled).mockResolvedValue(true);
  vi.mocked(wasRefreshCredentialRejected).mockReturnValue(false);
  vi.mocked(revokeLocalReminderOwner).mockResolvedValue(undefined);
  vi.mocked(syncLocalReminders).mockResolvedValue(undefined);
});

describe("future task device reminder synchronization", () => {
  it("fetches all owner-scoped API pages and excludes completed, undated and long-expired tasks", async () => {
    const first = Array.from({ length: 100 }, (_, i) => task(String(i), due));
    const second = [task("last", due), task("completed", due, "done"),
      task("undated", null), task("past", "2026-10-26T12:00:00Z")];
    vi.mocked(request).mockImplementation(async (path) =>
      (path.includes("offset=0") ? first : second) as never);
    const result = await fetchDeviceReminderTasks(now);
    expect(result).toHaveLength(101);
    expect(result.at(-1)?.id).toBe("last");
    expect(vi.mocked(request).mock.calls.map(([path]) => path))
      .toEqual([
        "/tasks?limit=100&offset=0", "/tasks?limit=100&offset=100",
        "/tasks?limit=100&offset=0", "/tasks?limit=100&offset=100",
      ]);
  });

  it("detects a deletion that shifts offset pages without overlapping IDs", async () => {
    const original = Array.from({ length: 101 }, (_, i) => task(String(i), due));
    const afterDeletion = original.slice(1);
    let scan = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      const offset = Number(new URLSearchParams(path.split("?")[1]).get("offset"));
      if (offset === 0) scan += 1;
      // First page is read before deletion; the second page has shifted.
      const records = scan === 1 && offset === 0 ? original : afterDeletion;
      return records.slice(offset, offset + 100) as never;
    });
    await expect(fetchDeviceReminderTasks(now)).rejects.toThrow("changed during pagination");
    expect(scan).toBe(2);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects a deadline edit between confirming task scans", async () => {
    const original = Array.from({ length: 101 }, (_, i) => task(String(i), due));
    const edited = original.map((entry) => ({ ...entry }));
    edited[100]!.due_at = "2026-11-02T15:00:00Z";
    let scan = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      const offset = Number(new URLSearchParams(path.split("?")[1]).get("offset"));
      if (offset === 0) scan += 1;
      return (scan === 1 ? original : edited).slice(offset, offset + 100) as never;
    });
    await expect(fetchDeviceReminderTasks(now)).rejects.toThrow("changed during pagination");
    expect(scan).toBe(2);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("retains recently overdue tasks so quiet-hour deferrals survive a foreground sync", async () => {
    const quietDue = "2026-10-29T11:00:00Z";
    vi.mocked(request).mockResolvedValueOnce([
      task("quiet-overdue", quietDue),
      task("expired", "2026-10-26T12:00:00Z"),
    ] as never);
    expect(await fetchDeviceReminderTasks(now)).toEqual([task("quiet-overdue", quietDue)]);
  });

  it("does not apply a partial schedule when a later page fails", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.includes("offset=0")) return Array.from({ length: 100 }, (_, i) => task(String(i), due)) as never;
      throw new Error("offline");
    });
    await expect(fetchDeviceReminderTasks(now)).rejects.toThrow("offline");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects overlapping task pages before replacing any scheduled alerts", async () => {
    const first = Array.from({ length: 100 }, (_, i) => task(String(i), due));
    vi.mocked(request).mockImplementation(async (path) =>
      (path.includes("offset=0") ? first : [task("99", due)]) as never);
    await expect(fetchDeviceReminderTasks(now)).rejects.toThrow("Overlapping");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects malformed task records, naive dates and oversized pages", async () => {
    for (const bad of [
      [{ ...task("bad", due), id: null }],
      [{ ...task("bad", due), status: "unknown" }],
      [task("bad", "2026-11-02T12:00:00")],
      [task("bad", "invalidZ")],
      [task("bad", "2026-02-31T12:00:00Z")],
      [task("bad", "2027-02-29T12:00:00Z")],
      [task("bad", "2026-10-30T12:00:00+15:00")],
      Array.from({ length: 101 }, (_, i) => task(String(i), due)),
    ]) {
      vi.mocked(request).mockReset().mockResolvedValueOnce(bad as never);
      await expect(fetchDeviceReminderTasks(now)).rejects.toThrow(/invalid (record|page)/);
    }
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("accepts valid leap days, server microseconds and legal timezone offsets", async () => {
    const valid = [
      task("leap", "2028-02-29T12:00:00Z"),
      task("offset", "2026-10-30T15:00:00.123456+03:00"),
      task("max-offset", "2026-11-02T12:00:00+14:00"),
    ];
    vi.mocked(request).mockResolvedValueOnce(valid as never);
    expect(await fetchDeviceReminderTasks(now)).toEqual(valid);
  });

  it("accepts exactly 10,000 tasks only after an empty boundary probe", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      const params = new URLSearchParams(path.split("?")[1]);
      const offset = Number(params.get("offset"));
      const limit = Number(params.get("limit"));
      return (offset === 10_000 ? [] :
        Array.from({ length: limit }, (_, i) => task(String(offset + i), due))) as never;
    });
    expect(await fetchDeviceReminderTasks(now)).toHaveLength(10_000);
    expect(vi.mocked(request)).toHaveBeenCalledTimes(202);
    expect(vi.mocked(request).mock.calls.at(-1)?.[0]).toBe("/tasks?limit=1&offset=10000");
  });

  it("rejects more than 10,000 tasks without replacing device schedules", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      const params = new URLSearchParams(path.split("?")[1]);
      const offset = Number(params.get("offset"));
      const limit = Number(params.get("limit"));
      return Array.from({ length: limit }, (_, i) => task(String(offset + i), due)) as never;
    });
    await expect(fetchDeviceReminderTasks(now)).rejects.toThrow("exceeds 10,000");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("requires explicit opt-in and fences a stale account or workspace response", async () => {
    vi.mocked(getLocalReminderEnabled).mockResolvedValueOnce(false);
    await refreshDeviceReminders("alice", "workspace-a");
    expect(request).not.toHaveBeenCalled();

    let current = true;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.startsWith("/tasks")) {
        current = false;
        return [task("future", due)] as never;
      }
      if (path.startsWith("/notifications?")) return inbox as never;
      return policy as never;
    });
    await refreshDeviceReminders("alice", "workspace-a", () => current);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("passes the live session fence into the queued local opt-in check", async () => {
    let current = true;
    vi.mocked(getLocalReminderEnabled).mockImplementationOnce(async (_owner, stillCurrent) => {
      current = false;
      expect(stillCurrent?.()).toBe(false);
      return false;
    });
    await refreshDeviceReminders("alice", "workspace-a", () => current);
    expect(getLocalReminderEnabled).toHaveBeenCalledWith("alice", expect.any(Function));
    expect(request).not.toHaveBeenCalled();
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("cancels local schedules when policy is disabled even if tasks API is unavailable", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") return { ...policy, enabled: false } as never;
      throw new Error("Tasks API is offline");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(request).toHaveBeenCalledTimes(1);
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", [], { ...policy, enabled: false }, [],
    );
  });

  it("does not fetch task pages when the task notification category is disabled", async () => {
    const otherPolicy = { ...policy, categories: ["calendar"] };
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") return otherPolicy as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Task endpoint should not be called");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(syncLocalReminders).toHaveBeenCalledWith("alice", "workspace-a", inbox, otherPolicy, []);
  });

  it("clears device alerts when the server opts out during a slow refresh", async () => {
    const disabled = { ...policy, enabled: false };
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        return (policyReads === 1 ? policy : disabled) as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(policyReads).toBe(2);
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", [], disabled, [],
    );
  });

  it("applies a live category opt-out rather than stale task preferences", async () => {
    const updated = { ...policy, categories: ["calendar"] };
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        return (policyReads === 1 ? policy : updated) as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", inbox, updated, [task("future", due)],
    );
  });

  it("preserves schedules if the final policy read fails", async () => {
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        if (policyReads === 2) throw new Error("policy recheck offline");
        return policy as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a"))
      .rejects.toThrow("policy recheck offline");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("revokes local alerts and reports confirmed session expiry to the foreground", async () => {
    const onRevoked = vi.fn();
    vi.mocked(wasRefreshCredentialRejected).mockReturnValue(true);
    vi.mocked(request).mockRejectedValueOnce(new Error("Session rejected"));
    await expect(refreshDeviceReminders("alice", "workspace-a", () => true, onRevoked))
      .rejects.toThrow("Session rejected");
    expect(revokeLocalReminderOwner).toHaveBeenCalledWith("alice", wasRefreshCredentialRejected);
    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(onRevoked).toHaveBeenCalledWith(true);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("reports failed OS cleanup without pretending the expired session is valid", async () => {
    const onRevoked = vi.fn();
    vi.mocked(wasRefreshCredentialRejected).mockReturnValue(true);
    vi.mocked(request).mockRejectedValueOnce(new Error("Session rejected"));
    vi.mocked(revokeLocalReminderOwner).mockRejectedValueOnce(new Error("OS cancellation failed"));
    await expect(refreshDeviceReminders("alice", "workspace-a", () => true, onRevoked))
      .rejects.toThrow("OS cancellation failed");
    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(onRevoked).toHaveBeenCalledWith(false);
  });

  it("does not sign out a newly authenticated same-owner session", async () => {
    const onRevoked = vi.fn();
    vi.mocked(wasRefreshCredentialRejected).mockReturnValue(true);
    vi.mocked(request).mockRejectedValueOnce(new Error("Old session rejected"));
    vi.mocked(revokeLocalReminderOwner).mockImplementationOnce(async (_owner, stillRejected) => {
      vi.mocked(wasRefreshCredentialRejected).mockReturnValue(false);
      expect(stillRejected?.()).toBe(false);
    });
    await expect(refreshDeviceReminders("alice", "workspace-a", () => true, onRevoked))
      .rejects.toThrow("Old session rejected");
    expect(onRevoked).not.toHaveBeenCalled();
  });

  it("preserves existing local alerts and the visible session on a transient refresh outage", async () => {
    const onRevoked = vi.fn();
    vi.mocked(request).mockRejectedValueOnce(new Error("Refresh server unavailable"));
    await expect(refreshDeviceReminders("alice", "workspace-a", () => true, onRevoked))
      .rejects.toThrow("Refresh server unavailable");
    expect(revokeLocalReminderOwner).not.toHaveBeenCalled();
    expect(onRevoked).not.toHaveBeenCalled();
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("cannot revoke a newer account after an old workspace request becomes stale", async () => {
    let current = true;
    vi.mocked(wasRefreshCredentialRejected).mockReturnValue(true);
    vi.mocked(request).mockImplementationOnce(async () => {
      current = false;
      throw new Error("Old session rejected");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a", () => current))
      .rejects.toThrow("Old session rejected");
    expect(revokeLocalReminderOwner).not.toHaveBeenCalled();
  });

  it("does not schedule a partial task list if the category was enabled mid-refresh", async () => {
    const initial = { ...policy, categories: ["calendar"] };
    const updated = { ...policy, categories: ["calendar", "tasks"] };
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        return (policyReads === 1 ? initial : updated) as never;
      }
      if (path.startsWith("/notifications?")) return inbox as never;
      if (path.startsWith("/tasks?")) throw new Error("Tasks must not be fetched from the old policy");
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a"))
      .rejects.toThrow("Task notification policy changed");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects malformed live notification policy without replacing OS alerts", async () => {
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        return (policyReads === 1 ? policy : { ...policy, enabled: "yes" }) as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a"))
      .rejects.toThrow("Invalid notification policy");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects malformed initial suppression policy without touching OS schedules", async () => {
    for (const bad of [
      { ...policy, quiet_enabled: "false" },
      { ...policy, quiet_start: "25:00" },
      { ...policy, quiet_end: "99:00" },
      { ...policy, timezone: "Invalid/Timezone" },
      { ...policy, respect_focus: "true" },
      { ...policy, categories: ["tasks", 7] },
    ]) {
      vi.mocked(request).mockReset().mockResolvedValueOnce(bad as never);
      await expect(refreshDeviceReminders("alice", "workspace-a"))
        .rejects.toThrow("Invalid notification policy");
      expect(syncLocalReminders).not.toHaveBeenCalled();
    }
  });

  it("preserves schedules when quiet hours become malformed during a slow sync", async () => {
    let policyReads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        policyReads += 1;
        return (policyReads === 1 ? policy : {
          ...policy, quiet_enabled: true, timezone: "Invalid/Timezone",
        }) as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a"))
      .rejects.toThrow("Invalid notification policy");
    expect(policyReads).toBe(2);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("honors empty-category opt-out even if quiet-hours fields are malformed", async () => {
    const noCategories = {
      ...policy, categories: [], quiet_enabled: "invalid", timezone: "Invalid/Timezone",
    };
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") return noCategories as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("No task fetch expected after category opt-out");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(request).toHaveBeenCalledTimes(1);
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", [], noCategories, [],
    );
  });

  it("clears all alerts when categories are removed during an in-flight refresh", async () => {
    const noCategories = {
      ...policy, categories: [], quiet_enabled: "invalid", timezone: "Invalid/Timezone",
    };
    let reads = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") {
        reads += 1;
        return (reads === 1 ? policy : noCategories) as never;
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      throw new Error("Unexpected API request");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(reads).toBe(2);
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", [], noCategories, [],
    );
  });

  it("still clears alerts on explicit server opt-out with malformed unrelated fields", async () => {
    const disabled = { enabled: false, quiet_enabled: "invalid", timezone: "Invalid/Timezone" };
    vi.mocked(request).mockResolvedValueOnce(disabled as never);
    await refreshDeviceReminders("alice", "workspace-a");
    expect(request).toHaveBeenCalledTimes(1);
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", [], disabled, [],
    );
  });

  it("synchronizes complete tasks and inbox after a successful owner-scoped fetch", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.startsWith("/tasks")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) return inbox as never;
      return policy as never;
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", inbox, policy, [task("future", due)],
    );
  });
});


describe("paginated device notification inbox", () => {
  const reminder = (id: string): Reminder => ({
    id, title: "Private", message: "Private", category: "tasks", source_id: null,
    due_at: due, read_at: null, snoozed_until: null, revision: 1,
    repeats: 0, attention_ready: false,
  });

  it("loads older due reminders beyond the API's default first page", async () => {
    const first = Array.from({ length: 200 }, (_, index) => reminder(`newer-${index}`));
    const older = [reminder("older-due")];
    vi.mocked(request).mockImplementation(async (path) =>
      (path.includes("offset=0") ? first : older) as never);
    const result = await fetchDeviceReminderInbox();
    expect(result).toHaveLength(201);
    expect(result.at(-1)?.id).toBe("older-due");
    expect(vi.mocked(request).mock.calls.map(([path]) => path)).toEqual([
      "/notifications?limit=200&offset=0",
      "/notifications?limit=200&offset=200",
      "/notifications?limit=200&offset=0",
      "/notifications?limit=200&offset=200",
    ]);
  });

  it("preserves OS schedules when deletion silently shifts inbox pages", async () => {
    const original = Array.from({ length: 201 }, (_, index) => reminder(`id-${index}`));
    const afterDeletion = original.slice(1);
    let scan = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") return policy as never;
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      if (path.startsWith("/notifications?")) {
        const offset = Number(new URLSearchParams(path.split("?")[1]).get("offset"));
        if (offset === 0) scan += 1;
        const records = scan === 1 && offset === 0 ? original : afterDeletion;
        return records.slice(offset, offset + 200) as never;
      }
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a"))
      .rejects.toThrow("changed during pagination");
    expect(scan).toBe(2);
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("rejects a snooze change between confirming inbox scans", async () => {
    const original = Array.from({ length: 201 }, (_, index) => reminder(`id-${index}`));
    const edited = original.map((entry) => ({ ...entry }));
    edited[200]!.snoozed_until = "2026-11-03T12:00:00Z";
    let scan = 0;
    vi.mocked(request).mockImplementation(async (path) => {
      const offset = Number(new URLSearchParams(path.split("?")[1]).get("offset"));
      if (offset === 0) scan += 1;
      return (scan === 1 ? original : edited).slice(offset, offset + 200) as never;
    });
    await expect(fetchDeviceReminderInbox()).rejects.toThrow("changed during pagination");
    expect(scan).toBe(2);
  });

  it("rejects overlapping pages rather than silently losing older alerts", async () => {
    const first = Array.from({ length: 200 }, (_, index) => reminder(`item-${index}`));
    vi.mocked(request).mockImplementation(async (path) =>
      (path.includes("offset=0") ? first : [reminder("item-199")]) as never);
    await expect(fetchDeviceReminderInbox()).rejects.toThrow("Overlapping");
  });

  it("does not replace device schedules when a later inbox page fails", async () => {
    const first = Array.from({ length: 200 }, (_, index) => reminder(`item-${index}`));
    vi.mocked(request).mockImplementation(async (path) => {
      if (path === "/notifications/preferences") return policy as never;
      if (path.startsWith("/notifications?")) {
        if (path.includes("offset=0")) return first as never;
        throw new Error("second inbox page unavailable");
      }
      if (path.startsWith("/tasks?")) return [task("future", due)] as never;
      throw new Error("Unexpected API request");
    });
    await expect(refreshDeviceReminders("alice", "workspace-a")).rejects.toThrow("second inbox page unavailable");
    expect(syncLocalReminders).not.toHaveBeenCalled();
  });

  it("accepts an exactly full 10,000-record inbox only after confirming the next page is empty", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      const params = new URLSearchParams(path.split("?")[1]);
      const offset = Number(params.get("offset"));
      const limit = Number(params.get("limit"));
      return (offset === 10_000 ? [] : Array.from({ length: limit }, (_, index) => reminder(`id-${offset + index}`))) as never;
    });
    expect(await fetchDeviceReminderInbox()).toHaveLength(10_000);
    expect(vi.mocked(request)).toHaveBeenCalledTimes(102);
    expect(vi.mocked(request).mock.calls.at(-1)?.[0]).toBe("/notifications?limit=1&offset=10000");
  });

  it("rejects malformed notification records before scheduling", async () => {
    vi.mocked(request).mockResolvedValueOnce([{ due_at: due }] as never);
    await expect(fetchDeviceReminderInbox()).rejects.toThrow("invalid record");
  });

  it("rejects invalid inbox dates, revisions and identities instead of cancelling prior alerts", async () => {
    const valid = reminder("existing");
    for (const bad of [
      { ...valid, id: "" },
      { ...valid, category: "" },
      { ...valid, revision: -1 },
      { ...valid, revision: 1.5 },
      { ...valid, due_at: "2026-11-02T12:00:00" },
      { ...valid, due_at: "invalidZ" },
      { ...valid, due_at: "2026-02-31T12:00:00Z" },
      { ...valid, due_at: "2026-10-30T12:00:00+15:00" },
      { ...valid, read_at: "not-a-date" },
      { ...valid, read_at: "2026-04-31T12:00:00Z" },
      { ...valid, snoozed_until: "2026-11-02T12:00:00" },
      { ...valid, snoozed_until: "2027-02-29T12:00:00Z" },
      { ...valid, source_id: 123 },
    ]) {
      vi.mocked(request).mockReset().mockImplementation(async (path) => {
        if (path === "/notifications/preferences") return policy as never;
        if (path.startsWith("/notifications?")) return [bad] as never;
        if (path.startsWith("/tasks?")) return [task("future", due)] as never;
        throw new Error("Unexpected API request");
      });
      await expect(refreshDeviceReminders("alice", "workspace-a")).rejects.toThrow("invalid record");
      expect(syncLocalReminders).not.toHaveBeenCalled();
    }
  });

  it("accepts timezone-aware inbox dates and optional timestamps", async () => {
    const valid = {
      ...reminder("valid"),
      due_at: "2026-11-02T15:00:00.123456+03:00",
      read_at: "2026-10-29T12:00:00Z",
      snoozed_until: "2026-11-03T15:00:00+03:00",
    };
    vi.mocked(request).mockResolvedValueOnce([valid] as never);
    expect(await fetchDeviceReminderInbox()).toEqual([valid]);
  });
});
