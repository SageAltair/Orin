import { expect, test } from "@playwright/test";

// This test creates accounts and records. It must never run against the
// canonical local stack or a real user's database.
const enabled = process.env.ORIN_ISOLATED_E2E === "true";
const isolatedApi = "http://127.0.0.1:18100";
const isolatedWeb = "http://127.0.0.1:15273";

// Keep local date/time input assertions independent of runner timezone.
test.use({ timezoneId: "UTC" });

test("isolated PostgreSQL browser journey persists Writing and delivers task reminders", async ({
  page,
  request,
}) => {
  test.skip(!enabled, "Run only with the disposable orin-stabilization-acceptance Docker stack");
  test.setTimeout(120_000);

  // Explicit opt-in is necessary but insufficient: verify the dedicated ports.
  // The canonical stack uses 8100/5273 and must remain untouched.
  const ready = await request.get(`${isolatedApi}/health/ready`);
  expect(ready.status(), "isolated API must be ready before creating test records").toBe(200);
  const email = `isolated-browser-${Date.now()}-${crypto.randomUUID()}@example.com`;
  const password = `Isolated-acceptance-${crypto.randomUUID()}!`;

  await page.goto(isolatedWeb);
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Isolated browser acceptance");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: /What would you like to.*work on today/ })).toBeVisible();

  const login = await request.post(`${isolatedApi}/api/v1/auth/login`, {
    data: { email, password },
  });
  expect(login.status()).toBe(200);
  const { access_token: token } = (await login.json()) as { access_token: string };
  const headers = { Authorization: `Bearer ${token}` };

  const projectResponse = await request.post(`${isolatedApi}/api/v1/projects`, {
    headers,
    data: { name: "Disposable browser project" },
  });
  expect(projectResponse.status()).toBe(201);
  const project = (await projectResponse.json()) as { id: string };

  const taskResponse = await request.post(`${isolatedApi}/api/v1/tasks`, {
    headers,
    data: {
      title: "Disposable due-task reminder",
      project_id: project.id,
      due_at: new Date(Date.now() - 60_000).toISOString(),
    },
  });
  expect(taskResponse.status()).toBe(201);
  const task = (await taskResponse.json()) as { id: string };

  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page.getByRole("button", { name: "New note" }).first().click();
  await page.getByLabel("Document title").fill("Disposable browser draft");
  await page.getByLabel("Content", { exact: true }).fill(
    "A real browser autosave against isolated PostgreSQL.",
  );
  await expect(page.locator(".writing-save-status")).toContainText("Saved", {
    timeout: 15_000,
  });

  await page.reload();
  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page.locator(".writing-documents")
    .getByRole("button", { name: /Disposable browser draft/ }).click();
  await expect(page.getByLabel("Content", { exact: true })).toContainText(
    "A real browser autosave against isolated PostgreSQL.",
  );

  const tasks = await request.get(`${isolatedApi}/api/v1/tasks`, { headers });
  expect(tasks.status()).toBe(200);
  expect((await tasks.json() as Array<{ id: string }>).some(row => row.id === task.id)).toBe(true);

  // Real Tasks UI against PostgreSQL, not mocked route fixtures.
  const openTasks = async () => {
    await page.getByRole("navigation", { name: "Workspace" })
      .getByRole("button", { name: "Tasks", exact: true }).click();
    // Personal uses embedded FocusExperience; other workspaces use TaskCollection.
    // Both must expose All Tasks immediately from the main Tasks route.
    await expect(page.locator(".focus-task-collection")).toBeVisible();
  };
  await openTasks();
  let workspace = page.locator(".focus-task-collection");
  await expect(workspace.getByRole("button", { name: /All tasks/ }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable due-task reminder")).toBeVisible();
  await workspace.getByRole("button", { name: "New task" }).click();
  await workspace.getByLabel("Task name").fill("Disposable scheduled browser task");
  await workspace.getByLabel("Due date and time (local)").fill("2099-11-02T09:45");
  await workspace.getByLabel("Priority", { exact: true }).selectOption("high");
  await workspace.getByLabel("Project", { exact: true }).selectOption(project.id);
  await workspace.getByRole("button", { name: "Save task" }).click();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable scheduled browser task")).toBeVisible();

  await page.reload();
  await openTasks();
  workspace = page.locator(".focus-task-collection");
  await workspace.locator(".focus-task-list")
    .getByRole("button", { name: "Edit Disposable scheduled browser task" }).click();
  await expect(workspace.getByLabel("Due date and time (local)"))
    .toHaveValue("2099-11-02T09:45");
  await expect(workspace.getByLabel("Project", { exact: true })).toHaveValue(project.id);
  await workspace.getByLabel("Task name").fill("Disposable scheduled browser task revised");
  await workspace.getByRole("button", { name: "Save task" }).click();
  const updatedRow = workspace.locator(".focus-task-list li")
    .filter({ hasText: "Disposable scheduled browser task revised" });
  await expect(updatedRow).toBeVisible();
  await updatedRow.getByRole("button", {
    name: "Complete Disposable scheduled browser task revised",
  }).click();
  await workspace.getByRole("navigation", { name: "Task views" })
    .getByRole("button", { name: /Completed/ }).click();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable scheduled browser task revised")).toBeVisible();
  const persistedTasks = await request.get(isolatedApi + "/api/v1/tasks?limit=100&offset=0", { headers });
  expect(persistedTasks.status()).toBe(200);
  const persisted = (await persistedTasks.json()) as Array<{
    title: string; status: string; priority: string; project_id: string | null; due_at: string | null;
  }>;
  const savedTask = persisted.find(row => row.title === "Disposable scheduled browser task revised");
  expect(savedTask).toEqual(expect.objectContaining({
    status: "done", priority: "high", project_id: project.id,
  }));
  // Compare UTC instants instead of relying on the API's offset spelling.
  expect(new Date(savedTask?.due_at ?? "").toISOString()).toBe("2099-11-02T09:45:00.000Z");

  await expect.poll(async () => {
    const response = await request.get(`${isolatedApi}/api/v1/notifications`, { headers });
    if (!response.ok()) return false;
    const notifications = (await response.json()) as Array<{
      category: string; source_id: string;
    }>;
    return notifications.some(row => row.category === "tasks" && row.source_id === task.id);
  }, { timeout: 45_000, intervals: [1000, 2000, 3000] }).toBe(true);
});
