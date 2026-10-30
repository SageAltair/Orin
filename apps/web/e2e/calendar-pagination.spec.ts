import { expect, test } from "@playwright/test";

test("calendar schedules tasks beyond the first hundred and refreshes every page", async ({ page }) => {
  const now = "2026-10-30T08:00:00Z";
  const tasks = Array.from({ length: 125 }, (_, index) => ({
    id: `task-${index}`, owner_id: "user-1", project_id: null,
    title: `Calendar task ${index}`, description: null, status: "todo",
    priority: "normal", due_at: null, estimated_minutes: 60,
    created_at: now, updated_at: now,
  }));
  const offsets: number[] = [];
  let scheduled: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: now } });
    if (pathname === "/api/v1/users/me/preferences") return route.fulfill({ json: {
      density: "comfortable", theme: "light", locale: "en",
      visible_capabilities: ["home", "tasks", "calendar", "projects"],
      hidden_capabilities: [], pinned_capabilities: ["home", "tasks"],
      autonomy_mode: "balanced", custom_autonomy: {},
    } });
    if (pathname === "/api/v1/focus/settings") return route.fulfill({ json: {
      timezone: "UTC", theme: "light", reduced_motion: false,
      hide_timer_numbers: false, sound_enabled: false, haptics_enabled: false,
    } });
    if (pathname === "/api/v1/tasks" && method === "GET") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      offsets.push(offset);
      return route.fulfill({ json: tasks.slice(offset, offset + limit) });
    }
    if (pathname === "/api/v1/projects") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/calendar/events" && method === "GET") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/calendar/schedule" && method === "GET") return route.fulfill({ json: scheduled });
    if (/^\/api\/v1\/calendar\/tasks\/[^/]+\/schedule$/.test(pathname) && method === "PUT") {
      const taskId = pathname.split("/").at(-2)!;
      const input = await route.request().postDataJSON() as Record<string, unknown>;
      const task = tasks.find(item => item.id === taskId)!;
      const block = {
        id: "block-1", task_id: taskId, title: task.title, description: null,
        project_id: null, project_name: null, status: "todo", ...input,
      };
      scheduled = [block];
      return route.fulfill({ json: block });
    }
    if (pathname === "/api/v1/environment/preferences" ||
        pathname === "/api/v1/approvals" ||
        pathname === "/api/v1/conversations" ||
        pathname === "/api/v1/auth/sessions") return route.fulfill({ json: [] });
    return route.fulfill({ status: 204 });
  });

  await page.goto("/");
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("navigation").first().getByRole("button", { name: "Calendar" }).click();
  await page.getByRole("button", { name: "Schedule task" }).first().click();

  const scheduler = page.getByRole("dialog", { name: "Schedule a task" });
  await expect(scheduler.getByRole("option", { name: "Calendar task 124" })).toHaveCount(1);
  await scheduler.getByRole("combobox").selectOption("task-124");
  const secondPageReads = offsets.filter(offset => offset === 100).length;
  await scheduler.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task scheduled." })).toBeVisible();
  await expect.poll(() => offsets.filter(offset => offset === 100).length)
    .toBeGreaterThan(secondPageReads);
  expect(scheduled[0]?.task_id).toBe("task-124");
});
