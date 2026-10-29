import { expect, test } from "@playwright/test";

test("rollout flag off exposes the professional Tasks workspace and precise scheduling", async ({ page }) => {
  const now = "2026-10-10T08:00:00Z";
  let createdPayload: Record<string, unknown> | null = null;
  let tasks: Array<Record<string, unknown>> = [
    { id: "task-upcoming", title: "Prepare next week's notes", description: null, status: "todo", priority: "normal", due_at: "2099-10-13T14:00:00Z", project_id: null, created_at: now, updated_at: now },
  ];
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-access-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: now } });
    if (pathname === "/api/v1/tasks" && method === "GET") return route.fulfill({ json: tasks });
    if (pathname === "/api/v1/tasks" && method === "POST") {
      createdPayload = await route.request().postDataJSON() as Record<string, unknown>;
      const task = { id: "task-1", status: "todo", created_at: now, updated_at: now, ...createdPayload };
      tasks = [task, ...tasks];
      return route.fulfill({ status: 201, json: task });
    }
    if (pathname === "/api/v1/tasks/task-1" && method === "PATCH") {
      const patch = await route.request().postDataJSON() as Record<string, unknown>;
      tasks = tasks.map(task => task.id === "task-1" ? { ...task, ...patch } : task);
      return route.fulfill({ json: tasks.find(task => task.id === "task-1") });
    }
    if (pathname === "/api/v1/users/me/preferences") return route.fulfill({ json: { density: "comfortable", theme: "light", locale: "en", visible_capabilities: ["home", "tasks", "projects", "activity"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {} } });
    if (pathname === "/api/v1/projects") return route.fulfill({ json: [{ id: "project-1", name: "Research", status: "active" }] });
    if (pathname === "/api/v1/environment/preferences" || pathname.endsWith("/approvals") || pathname.endsWith("/conversations") || pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    return route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("navigation").first().getByRole("button", { name: "Tasks" }).click();

  const workspace = page.locator('[data-orin-control="tasks-workspace"]');
  await expect(workspace.locator("#task-collection-heading")).toBeVisible();
  await expect(workspace).toHaveClass(/focus-shell/);
  await expect(workspace).toHaveClass(/focus-embedded/);
  expect(await workspace.locator(".focus-task-views").evaluate(element => getComputedStyle(element).display)).toBe("flex");
  await expect(workspace.locator("#legacy-tasks-heading")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toHaveCount(0);
  await expect(workspace.getByRole("button", { name: /All tasks/ })).toHaveAttribute("aria-pressed", "true");
  await expect(workspace.getByText("Prepare next week's notes")).toBeVisible();
  expect(await workspace.locator(".focus-task-list li").first().evaluate(element => getComputedStyle(element).display)).toBe("flex");

  await workspace.getByRole("button", { name: "New task" }).click();
  await workspace.getByLabel("Task name").fill("Plan the research review");
  await workspace.getByLabel("Due date and time (local)").fill("2099-11-02T09:45");
  await workspace.getByLabel("Priority").selectOption("high");
  await workspace.getByLabel("Project").selectOption("project-1");
  await workspace.getByRole("button", { name: "Save task" }).click();
  await expect(workspace.getByText("Plan the research review")).toBeVisible();
  await expect.poll(() => createdPayload?.project_id).toBe("project-1");
  expect(createdPayload?.priority).toBe("high");
  expect(new Date(String(createdPayload?.due_at)).getTime()).toBeGreaterThan(0);

  await workspace.getByRole("button", { name: "Edit Plan the research review" }).click();
  await workspace.getByLabel("Task name").fill("Review research findings");
  await workspace.getByRole("button", { name: "Save task" }).click();
  await expect(workspace.getByText("Review research findings")).toBeVisible();
  await workspace.getByRole("button", { name: "Complete Review research findings" }).click();
  await workspace.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Completed/ }).click();
  await expect(workspace.getByRole("button", { name: "Reopen Review research findings" })).toBeVisible();
});
