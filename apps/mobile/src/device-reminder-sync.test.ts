import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "./api";
import { getLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import { fetchDeviceReminderTasks, refreshDeviceReminders } from "./device-reminder-sync";
import type { NotificationPolicy, Reminder, Task } from "./types";

vi.mock("./api", () => ({ request: vi.fn() }));
vi.mock("./native-reminders", () => ({
  getLocalReminderEnabled: vi.fn(),
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
const policy = { enabled: true, categories: ["tasks"] } as NotificationPolicy;
const inbox: Reminder[] = [];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getLocalReminderEnabled).mockResolvedValue(true);
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
      .toEqual(["/tasks?limit=100&offset=0", "/tasks?limit=100&offset=100"]);
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
      if (path === "/notifications") return inbox as never;
      return policy as never;
    });
    await refreshDeviceReminders("alice", "workspace-a", () => current);
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
      if (path === "/notifications") return inbox as never;
      throw new Error("Task endpoint should not be called");
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(syncLocalReminders).toHaveBeenCalledWith("alice", "workspace-a", inbox, otherPolicy, []);
  });

  it("synchronizes complete tasks and inbox after a successful owner-scoped fetch", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.startsWith("/tasks")) return [task("future", due)] as never;
      if (path === "/notifications") return inbox as never;
      return policy as never;
    });
    await refreshDeviceReminders("alice", "workspace-a");
    expect(syncLocalReminders).toHaveBeenCalledWith(
      "alice", "workspace-a", inbox, policy, [task("future", due)],
    );
  });
});
