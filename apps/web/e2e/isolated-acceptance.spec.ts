import { expect, test } from "@playwright/test";

// This test creates accounts and records. It must never run against the
// canonical local stack or a real user's database.
const enabled = process.env.ORIN_ISOLATED_E2E === "true";
const isolatedApi = "http://127.0.0.1:18100";
const isolatedWeb = "http://127.0.0.1:15273";

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

  await expect.poll(async () => {
    const response = await request.get(`${isolatedApi}/api/v1/notifications`, { headers });
    if (!response.ok()) return false;
    const notifications = (await response.json()) as Array<{
      category: string; source_id: string;
    }>;
    return notifications.some(row => row.category === "tasks" && row.source_id === task.id);
  }, { timeout: 45_000, intervals: [1000, 2000, 3000] }).toBe(true);
});
