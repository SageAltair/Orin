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

  // The browser is pinned to UTC. Exercise the real Today view against a
  // calendar-day due date, rather than relying on a mocked task response.
  const todayAtNoonUtc = new Date();
  todayAtNoonUtc.setUTCHours(12, 0, 0, 0);
  const todayResponse = await request.post(`${isolatedApi}/api/v1/tasks`, {
    headers,
    data: {
      title: "Disposable today browser task",
      due_at: todayAtNoonUtc.toISOString(),
    },
  });
  expect(todayResponse.status()).toBe(201);

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

  // Verify date-based navigation against real persisted tasks, not mocked
  // selectors. Overdue can overlap Today; Upcoming must not.
  const taskViews = workspace.getByRole("navigation", { name: "Task views" });
  await taskViews.getByRole("button", { name: /Today/ }).click();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable today browser task")).toBeVisible();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable scheduled browser task")).toHaveCount(0);
  await taskViews.getByRole("button", { name: /Overdue/ }).click();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable due-task reminder")).toBeVisible();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable scheduled browser task")).toHaveCount(0);
  await taskViews.getByRole("button", { name: /Upcoming/ }).click();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable scheduled browser task")).toBeVisible();
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable due-task reminder")).toHaveCount(0);

  // Real Calendar scheduling must persist a task block without changing the
  // task's deadline. Completion must remove the block from PostgreSQL.
  const scheduleDay = new Date(Date.now() + 24 * 60 * 60_000).toISOString().slice(0, 10);
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Calendar", exact: true }).click();
  await page.getByRole("button", { name: "Schedule task" }).first().click();
  const scheduler = page.getByRole("dialog", { name: "Schedule a task" });
  await scheduler.getByRole("combobox").selectOption({ label: "Disposable scheduled browser task" });
  await scheduler.getByLabel("Starts").fill(`${scheduleDay}T10:00`);
  await scheduler.getByLabel("Duration in minutes").fill("45");
  await scheduler.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task scheduled." })).toBeVisible();
  const scheduleUrl = `${isolatedApi}/api/v1/calendar/schedule?start=${scheduleDay}&end=${scheduleDay}&timezone=UTC`;
  const scheduledResponse = await request.get(scheduleUrl, { headers });
  expect(scheduledResponse.status()).toBe(200);
  const scheduledBlocks = (await scheduledResponse.json()) as Array<{ task_id: string; title: string }>;
  const scheduledBlock = scheduledBlocks.find(row => row.title === "Disposable scheduled browser task");
  expect(scheduledBlock?.task_id).toBeTruthy();

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
  const afterCompletion = await request.get(scheduleUrl, { headers });
  expect(afterCompletion.status()).toBe(200);
  const remainingBlocks = (await afterCompletion.json()) as Array<{ task_id: string }>;
  expect(remainingBlocks.some(row => row.task_id === scheduledBlock?.task_id)).toBe(false);
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


test("isolated PostgreSQL All Tasks includes records beyond the first API page", async ({
  page,
  request,
}) => {
  test.skip(!enabled, "Run only with the disposable orin-stabilization-acceptance Docker stack");
  test.setTimeout(180_000);

  const ready = await request.get(`${isolatedApi}/health/ready`);
  expect(ready.status()).toBe(200);

  const email = `isolated-pagination-${crypto.randomUUID()}@example.com`;
  const password = `Isolated-pagination-${crypto.randomUUID()}!`;
  await page.goto(isolatedWeb);
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Disposable pagination acceptance");
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
  const createTask = async (title: string) => {
    const response = await request.post(`${isolatedApi}/api/v1/tasks`, {
      headers, data: { title },
    });
    expect(response.status(), `creating ${title}`).toBe(201);
    return (await response.json()) as { id: string };
  };

  // Create the marker first. The API returns newest records first, so after
  // 100 later tasks this record must appear only on the second API page.
  const marker = await createTask("Disposable page two marker");
  for (let start = 0; start < 100; start += 10) {
    await Promise.all(Array.from({ length: 10 }, (_, index) =>
      createTask(`Disposable pagination task ${start + index + 1}`)));
  }

  const firstResponse = await request.get(`${isolatedApi}/api/v1/tasks?limit=100&offset=0`, { headers });
  const secondResponse = await request.get(`${isolatedApi}/api/v1/tasks?limit=100&offset=100`, { headers });
  expect(firstResponse.status()).toBe(200);
  expect(secondResponse.status()).toBe(200);
  const first = (await firstResponse.json()) as Array<{ id: string }>;
  const second = (await secondResponse.json()) as Array<{ id: string }>;
  expect(first).toHaveLength(100);
  expect(first.some(row => row.id === marker.id)).toBe(false);
  expect(second.some(row => row.id === marker.id)).toBe(true);

  await page.reload();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Tasks", exact: true }).click();
  const workspace = page.locator(".focus-task-collection");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("button", { name: /All tasks/ }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(workspace.locator(".focus-task-list li")).toHaveCount(101, { timeout: 20_000 });
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable page two marker")).toBeVisible();

  await workspace.getByLabel("Search tasks").fill("page two marker");
  await expect(workspace.locator(".focus-task-list li")).toHaveCount(1);
  await expect(workspace.locator(".focus-task-list")
    .getByText("Disposable page two marker")).toBeVisible();
});


test("isolated PostgreSQL keeps task and project inventories within owner and workspace", async ({
  page,
  request,
  browser,
}) => {
  test.skip(!enabled, "Run only with the disposable orin-stabilization-acceptance Docker stack");
  test.setTimeout(120_000);

  const signUp = async (target: typeof page, label: string) => {
    const email = `isolated-scope-${crypto.randomUUID()}@example.com`;
    const password = `Isolated-scope-${crypto.randomUUID()}!`;
    await target.goto(isolatedWeb);
    await target.getByRole("button", { name: "New to Orin? Create an account" }).click();
    await target.getByLabel("Your name").fill(label);
    await target.getByLabel("Email").fill(email);
    await target.getByLabel("Password", { exact: true }).fill(password);
    await target.getByRole("button", { name: "Create account" }).click();
    await expect(target.getByRole("heading", { name: /What would you like to.*work on today/ })).toBeVisible();
    const response = await request.post(`${isolatedApi}/api/v1/auth/login`, {
      data: { email, password },
    });
    expect(response.status()).toBe(200);
    const { access_token: token } = (await response.json()) as { access_token: string };
    return { Authorization: `Bearer ${token}` };
  };

  const ownerA = await signUp(page, "Disposable workspace owner A");
  const workspaces = await request.get(`${isolatedApi}/api/v1/workspaces`, { headers: ownerA });
  expect(workspaces.status()).toBe(200);
  const personal = (await workspaces.json()) as Array<{ id: string; name: string }>;
  expect(personal.length).toBeGreaterThan(0);
  const personalId = personal[0].id;

  const newWorkspace = await request.post(`${isolatedApi}/api/v1/workspaces`, {
    headers: ownerA, data: { name: "Disposable isolated office" },
  });
  expect(newWorkspace.status()).toBe(201);
  const { id: officeId } = (await newWorkspace.json()) as { id: string };
  const personalHeaders = { ...ownerA, "X-Orin-Workspace-Id": personalId };
  const officeHeaders = { ...ownerA, "X-Orin-Workspace-Id": officeId };

  const projectResponse = await request.post(`${isolatedApi}/api/v1/projects`, {
    headers: officeHeaders, data: { name: "Disposable private project" },
  });
  expect(projectResponse.status()).toBe(201);
  const { id: projectId } = (await projectResponse.json()) as { id: string };
  const officeTask = await request.post(`${isolatedApi}/api/v1/tasks`, {
    headers: officeHeaders, data: { title: "Office-only task", project_id: projectId },
  });
  expect(officeTask.status()).toBe(201);
  const personalTask = await request.post(`${isolatedApi}/api/v1/tasks`, {
    headers: personalHeaders, data: { title: "Personal-only task" },
  });
  expect(personalTask.status()).toBe(201);

  const titlesFor = async (headers: Record<string, string>) => {
    const response = await request.get(`${isolatedApi}/api/v1/tasks`, { headers });
    expect(response.status()).toBe(200);
    return ((await response.json()) as Array<{ title: string }>).map(task => task.title);
  };
  expect(await titlesFor(officeHeaders)).toContain("Office-only task");
  expect(await titlesFor(officeHeaders)).not.toContain("Personal-only task");
  expect(await titlesFor(personalHeaders)).toContain("Personal-only task");
  expect(await titlesFor(personalHeaders)).not.toContain("Office-only task");

  const wrongWorkspaceProject = await request.post(`${isolatedApi}/api/v1/tasks`, {
    headers: personalHeaders, data: { title: "Should be rejected", project_id: projectId },
  });
  expect(wrongWorkspaceProject.status()).toBe(422);

  const secondPage = await browser.newPage();
  try {
    const ownerB = await signUp(secondPage, "Disposable workspace owner B");
    expect(await titlesFor(ownerB)).toEqual([]);
    const foreignWorkspace = await request.get(`${isolatedApi}/api/v1/tasks`, {
      headers: { ...ownerB, "X-Orin-Workspace-Id": officeId },
    });
    expect(foreignWorkspace.status()).toBe(404);
    const foreignProject = await request.post(`${isolatedApi}/api/v1/tasks`, {
      headers: ownerB, data: { title: "Should also be rejected", project_id: projectId },
    });
    expect(foreignProject.status()).toBe(422);
  } finally {
    await secondPage.close();
  }
});

// Exercise the actual browser timezone rather than only UTC or mocked unit cases.
test.describe("Dar es Salaam local task scheduling", () => {
  test.use({ timezoneId: "Africa/Dar_es_Salaam" });

  test("isolated PostgreSQL preserves Dar es Salaam local task time through edit", async ({
    page,
    request,
  }) => {
    test.skip(!enabled, "Run only with the disposable orin-stabilization-acceptance Docker stack");
    test.setTimeout(120_000);

    const ready = await request.get(`${isolatedApi}/health/ready`);
    expect(ready.status()).toBe(200);
    expect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone))
      .toBe("Africa/Dar_es_Salaam");

    const email = `isolated-dar-time-${crypto.randomUUID()}@example.com`;
    const password = `Isolated-Dar-time-${crypto.randomUUID()}!`;
    await page.goto(isolatedWeb);
    await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
    await page.getByLabel("Your name").fill("Disposable Dar time acceptance");
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

    const openTasks = async () => {
      await page.getByRole("navigation", { name: "Workspace" })
        .getByRole("button", { name: "Tasks", exact: true }).click();
      await expect(page.locator(".focus-task-collection")).toBeVisible();
    };
    await openTasks();
    let tasks = page.locator(".focus-task-collection");
    await tasks.getByRole("button", { name: "New task" }).click();
    await tasks.getByLabel("Task name").fill("Disposable Dar timezone task");
    await tasks.getByLabel("Due date and time (local)").fill("2099-11-02T09:45");
    await tasks.getByRole("button", { name: "Save task" }).click();
    await expect(tasks.locator(".focus-task-list")
      .getByText("Disposable Dar timezone task")).toBeVisible();

    const persisted = await request.get(`${isolatedApi}/api/v1/tasks`, { headers });
    expect(persisted.status()).toBe(200);
    const records = (await persisted.json()) as Array<{ title: string; due_at: string | null }>;
    const saved = records.find(task => task.title === "Disposable Dar timezone task");
    expect(saved).toBeDefined();
    // 09:45 in Tanzania (UTC+03:00) is 06:45 UTC.
    expect(new Date(saved?.due_at ?? "").toISOString()).toBe("2099-11-02T06:45:00.000Z");

    await page.reload();
    await openTasks();
    tasks = page.locator(".focus-task-collection");
    await tasks.locator(".focus-task-list")
      .getByRole("button", { name: "Edit Disposable Dar timezone task" }).click();
    await expect(tasks.getByLabel("Due date and time (local)")).toHaveValue("2099-11-02T09:45");
    await tasks.getByLabel("Task name").fill("Disposable Dar timezone task revised");
    await tasks.getByRole("button", { name: "Save task" }).click();
    // Wait for the awaited PATCH to commit before reading PostgreSQL via the API.
    await expect(tasks.getByText("Task updated.")).toBeVisible();
    await expect(tasks.locator(".focus-task-list")
      .getByText("Disposable Dar timezone task revised")).toBeVisible();

    const afterEdit = await request.get(`${isolatedApi}/api/v1/tasks`, { headers });
    expect(afterEdit.status()).toBe(200);
    const updated = (await afterEdit.json()) as Array<{ title: string; due_at: string | null }>;
    const revised = updated.find(task => task.title === "Disposable Dar timezone task revised");
    expect(revised).toBeDefined();
    // Editing unrelated fields must not shift the original instant.
    expect(new Date(revised?.due_at ?? "").toISOString()).toBe("2099-11-02T06:45:00.000Z");
  });
});
