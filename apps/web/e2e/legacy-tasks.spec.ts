import { expect, test } from "@playwright/test";

test("rollout flag off keeps the legacy Tasks list and task actions available", async ({ page }) => {
  const now = "2026-10-10T08:00:00Z";
  let tasks: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-access-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: now } });
    if (pathname === "/api/v1/tasks" && method === "GET") return route.fulfill({ json: tasks });
    if (pathname === "/api/v1/tasks" && method === "POST") {
      const input = await route.request().postDataJSON() as { title: string };
      const task = { id: "task-1", title: input.title, description: null, status: "todo", priority: "normal", due_at: null, project_id: null, created_at: now, updated_at: now };
      tasks = [task, ...tasks]; return route.fulfill({ status: 201, json: task });
    }
    if (pathname === "/api/v1/tasks/task-1" && method === "PATCH") {
      const patch = await route.request().postDataJSON() as Record<string, unknown>;
      tasks = tasks.map(task => ({ ...task, ...patch }));
      return route.fulfill({ json: tasks[0] });
    }
    if (pathname === "/api/v1/users/me/preferences") return route.fulfill({ json: { density: "comfortable", theme: "light", locale: "en", visible_capabilities: ["home", "tasks", "projects", "activity"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {} } });
    if (pathname === "/api/v1/environment/preferences" || pathname.endsWith("/approvals") || pathname.endsWith("/projects") || pathname.endsWith("/conversations") || pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    return route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password").fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("navigation").first().getByRole("button", { name: "Tasks" }).click();
  await expect(page.locator("#legacy-tasks-heading")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toHaveCount(0);
  await page.getByLabel("New task").fill("Keep the legacy task flow");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByLabel("Edit Keep the legacy task flow")).toBeVisible();
  await page.getByRole("button", { name: "Complete Keep the legacy task flow" }).click();
  await expect(page.getByRole("button", { name: "Reopen Keep the legacy task flow" })).toBeVisible();
});
