import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page) {
  let preferences = { density: "comfortable", theme: "light", locale: "en", visible_capabilities: ["home", "tasks"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {} };
  const tasks: Record<string, unknown>[] = [];
  const devices: Record<string, unknown>[] = [];
  const workerJobs: Record<string, Record<string, unknown>[]> = {};
  const approvals: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-access-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: "2026-10-08T00:00:00Z" } });
    if (pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    if (pathname.endsWith("/auth/email") && route.request().method() === "POST") return route.fulfill({ json: { id: "user-1", email: "updated@example.com", display_name: "Morgan", created_at: "2026-10-08T00:00:00Z" } });
    if (pathname.endsWith("/auth/password") || pathname.includes("/auth/sessions/")) return route.fulfill({ status: 204 });
    if (pathname === "/api/v1/approvals" && route.request().method() === "GET") return route.fulfill({ json: approvals });
    if (pathname.includes("/approvals/") && route.request().method() === "POST") {
      if (pathname.endsWith("/decision")) {
        const decision = await route.request().postDataJSON() as { approved: boolean };
        approvals.forEach(item => { item.status = decision.approved ? "approved" : "rejected"; });
      }
      return route.fulfill({ json: { command_id: "cmd", status: "approved", message: "Decision saved." } });
    }
    if (pathname === "/api/v1/devices" && route.request().method() === "GET") return route.fulfill({ json: devices });
    if (pathname === "/api/v1/devices" && route.request().method() === "POST") {
      const input = await route.request().postDataJSON() as { name: string; platform: string; version: string };
      const device = { ...input, id: `device-${devices.length + 1}`, credential: "one-time-test-worker-token-that-is-long", status: "pending", last_seen_at: null, created_at: "2026-10-08T00:00:00Z" };
      devices.push({ ...device, credential: undefined }); workerJobs[device.id] = [];
      return route.fulfill({ status: 201, json: device });
    }
    if (/\/api\/v1\/devices\/[^/]+$/.test(pathname) && route.request().method() === "DELETE") {
      const device = devices.find(item => item.id === pathname.split("/").at(-1)); if (device) device.status = "revoked";
      return route.fulfill({ status: 204 });
    }
    if (pathname.endsWith("/jobs") && route.request().method() === "GET") {
      const deviceId = pathname.split("/").at(-2) ?? "";
      return route.fulfill({ json: workerJobs[deviceId] ?? [] });
    }
    if (pathname.endsWith("/jobs") && route.request().method() === "POST") {
      const deviceId = pathname.split("/").at(-2) ?? "";
      const job = { id: "job-1", action: "get_system_info", status: "pending_approval", progress: null, result: null, failure: null, created_at: "2026-10-08T00:00:00Z", finished_at: null };
      workerJobs[deviceId]?.push(job);
      approvals.push({ id: "approval-1", status: "pending", action: "worker_get_system_info", parameters: {}, risk_level: "low", permission: "system.info.read", reversible: true, reason: "Worker actions always require explicit approval.", created_at: "2026-10-08T00:00:00Z", expires_at: null, decided_at: null });
      return route.fulfill({ status: 202, json: { id: job.id, approval_id: "approval-1", status: job.status } });
    }
    if (pathname.endsWith("/users/me/preferences")) {
      if (route.request().method() === "PUT") preferences = await route.request().postDataJSON() as typeof preferences;
      return route.fulfill({ json: preferences });
    }
    if (pathname.endsWith("/commands") && route.request().method() === "POST") {
      const { text } = await route.request().postDataJSON() as { text: string };
      if (text.toLowerCase() === "hey") return route.fulfill({ json: { command_id: "cmd-1", status: "completed", intent: "RESPOND", result: { response: "Hey! What can I help you with?" }, message: "Hey! What can I help you with?" } });
      if (/create a task/i.test(text)) {
        const taskTitle = text.replace(/create a task(?: called)?/i, "").trim();
        const task = { id: `task-${tasks.length + 1}`, owner_id: "user-1", project_id: null, assignee_id: null, title: taskTitle, description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
        tasks.push(task);
        return route.fulfill({ json: { command_id: "cmd-2", status: "completed", intent: "CREATE_TASK", result: { id: task.id, title: task.title, status: task.status }, message: "Command completed." } });
      }
      return route.fulfill({ json: { command_id: "cmd-3", status: "unsupported", intent: "UNSUPPORTED", result: null, message: "This request is not supported." } });
    }
    if (pathname.endsWith("/tasks") && route.request().method() === "GET") return route.fulfill({ json: tasks });
    if (pathname.endsWith("/tasks") && route.request().method() === "POST") {
      const data = await route.request().postDataJSON() as { title: string };
      const task = { id: `task-${tasks.length + 1}`, owner_id: "user-1", project_id: null, assignee_id: null, title: data.title, description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
      tasks.push(task);
      return route.fulfill({ status: 201, json: task });
    }
    if (["/projects", "/activity"].some(path => pathname.endsWith(path))) return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

async function signIn(page: Page) {
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password").fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("sign in opens the connected Orin workspace", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to Orin" })).toBeVisible();
  await signIn(page);
  await expect(page.getByRole("heading", { name: "What matters now?" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Tasks" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("autocomplete", "off");
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("placeholder", "Ask Orin what you need");
});

test("workspace preferences control visible capabilities", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Show Projects" }).check();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
});

test("settings expose profile security, autonomy, approvals, and worker enrollment", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Email and sessions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose how Orin handles actions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Requests and history" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Connected workers" })).toBeVisible();
  await page.getByLabel("Device name").fill("Sage-Laptop");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByLabel("Worker token")).toHaveValue("one-time-test-worker-token-that-is-long");
  await page.getByRole("button", { name: "Request approval" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Request sent for approval" })).toBeVisible();
  await expect(page.getByText("get system info")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/approved · low risk/)).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("revoked", { exact: true })).toBeVisible();
});

test("Ask Orin answers greetings and creates tasks; manual task creation also works", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  const ask = page.getByRole("textbox", { name: "Ask Orin" });
  await ask.fill("hey");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.getByText("Hey! What can I help you with?").first()).toBeVisible();

  await ask.fill("Create a task called Call John");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.getByRole("textbox", { name: "Edit Call John" })).toBeVisible();

  await page.getByRole("navigation").getByRole("button", { name: "Tasks" }).click();
  await page.getByLabel("Task title").fill("Manual task");
  const addTaskButton = page.getByRole("button", { name: "Add task" });
  await expect(addTaskButton).toHaveText("");
  await addTaskButton.click();
  await expect(page.getByRole("textbox", { name: "Edit Manual task" })).toBeVisible();
});
