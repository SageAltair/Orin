import { expect, test } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

test("Docker web, authentication, manual tasks, and live AI command flow", async ({ page }) => {
  test.skip(process.env.ORIN_DOCKER_E2E !== "true", "set ORIN_DOCKER_E2E=true to exercise the running Docker stack and configured AI provider");
  test.setTimeout(180_000);

  const email = `orin-docker-e2e-${Date.now()}@example.com`;
  const password = `Orin-smoke-${crypto.randomUUID()}!`;
  const commandResults: Array<{ intent?: string; status: string; result: unknown }> = [];
  page.on("response", async response => {
    if (response.url().includes("/api/v1/commands") && response.request().method() === "POST") {
      try { commandResults.push(await response.json() as { intent?: string; status: string; result: unknown }); } catch { /* response may be an error */ }
    }
  });
  await page.goto("http://localhost:5273");
  const indexPath = resolve(process.cwd(), "index.html");
  const originalIndex = await readFile(indexPath, "utf8");
  try {
    await writeFile(indexPath, originalIndex.replace("<title>Orin</title>", "<title>Orin HMR probe</title>"));
    await expect(page).toHaveTitle("Orin HMR probe", { timeout: 10_000 });
  } finally {
    await writeFile(indexPath, originalIndex);
  }
  await expect(page).toHaveTitle("Orin");
  await expect(page.getByRole("heading", { name: "Welcome to Orin" })).toBeVisible();
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Orin Docker smoke test");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  const ask = page.getByRole("textbox", { name: "Ask Orin" });
  await expect(ask).toBeVisible();
  await expect(ask).toHaveAttribute("autocomplete", "off");
  await expect(ask).toHaveAttribute("placeholder", "Ask Orin what you need");

  await ask.fill("hey");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-message, .success-message, .api-error").filter({ hasText: /.+/ })).not.toContainText("AI returned an invalid command proposal");
  await expect(page.locator(".command-result")).toContainText("Hey! What can I help you with?", { timeout: 60_000 });

  await ask.fill("How are you today?");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".command-result")).not.toBeEmpty();

  const projectName = `Project ${Date.now()}`;
  await ask.fill(`Create a project called ${projectName}`);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(projectName, { timeout: 60_000 });

  await ask.fill("Show me my projects");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(projectName, { timeout: 60_000 });

  const aiTaskTitle = `AI task ${Date.now()}`;
  await ask.fill(`Create a task called ${aiTaskTitle}`);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(aiTaskTitle, { timeout: 60_000 });
  await expect(page.getByRole("textbox", { name: `Edit ${aiTaskTitle}` })).toBeVisible({ timeout: 60_000 });

  await ask.fill("What tasks do I have?");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(aiTaskTitle, { timeout: 60_000 });

  const updatedTaskTitle = `${aiTaskTitle} revised`;
  await ask.fill(`Update my ${aiTaskTitle} task by changing its title to ${updatedTaskTitle}`);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(updatedTaskTitle, { timeout: 60_000 });

  await ask.fill(`Mark the ${updatedTaskTitle} task as complete`);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText("done", { timeout: 60_000 });

  await ask.fill("Show me my recent activity");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText(`Completed task: ${updatedTaskTitle}`, { timeout: 60_000 });

  const commitmentRequest = "For this test, record the following commitment if you have persistent memory or a supported task system: I will spend my next focused development session fixing Orin's duplicate AI responses. The task is complete only when the root cause is identified, a regression test passes, and the relevant chat flow is verified. Tell me exactly where you stored this information and how I can retrieve it later.";
  await ask.fill(commitmentRequest);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText("Saved and verified", { timeout: 60_000 });
  await expect(page.locator(".command-result")).toContainText("Search previous work");
  const commitmentResult = commandResults.at(-1);
  expect(commitmentResult?.intent).toBe("SAVE_MEMORY");
  const memoryId = (commitmentResult?.result as { id?: string } | null)?.id;
  expect(memoryId).toBeTruthy();
  const memoriesResponse = await page.request.get(`/api/v1/memories?search=${encodeURIComponent("Fix Orin's duplicate AI responses")}`);
  expect(memoriesResponse.ok()).toBeTruthy();
  const memories = await memoriesResponse.json() as Array<{ id: string; type: string; title: string; content: string; metadata: { status: string; acceptance_criteria: string[] } }>;
  const savedMemory = memories.find(memory => memory.id === memoryId);
  expect(savedMemory?.type).toBe("commitment");
  expect(savedMemory?.metadata.status).toBe("not_started");
  expect(savedMemory?.metadata.acceptance_criteria).toHaveLength(3);

  const retrievalResponse = await page.request.post("/api/v1/commands", { data: { text: "Show me my commitment about fixing Orin's duplicate AI responses, including its acceptance criteria and current status." } });
  expect(retrievalResponse.ok()).toBeTruthy();
  const retrieval = await retrievalResponse.json() as { status: string; conversation_id: string; message: string; result: { response?: string } };
  expect(retrieval.status).toBe("completed");
  expect(retrieval.conversation_id).not.toBe(commitmentResult?.conversation_id);
  expect(`${retrieval.message}\n${retrieval.result?.response ?? ""}`).toContain("not_started");
  expect(`${retrieval.message}\n${retrieval.result?.response ?? ""}`).toContain("regression test");

  await ask.fill("Delete my entire database");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".api-error")).toContainText("not supported", { timeout: 60_000 });

  await expect.poll(() => commandResults.map(result => result.intent)).toEqual([
    "RESPOND", "RESPOND", "CREATE_PROJECT", "LIST_PROJECTS", "CREATE_TASK", "LIST_TASKS",
    "UPDATE_TASK", "COMPLETE_TASK", "GET_ACTIVITY", "SAVE_MEMORY", "UNSUPPORTED",
  ]);

  await page.getByRole("navigation").getByRole("button", { name: "Tasks" }).click();
  const manualTitle = `Manual task ${Date.now()}`;
  await page.getByLabel("Task title").fill(manualTitle);
  const addTaskButton = page.getByRole("button", { name: "Add task" });
  await expect(addTaskButton).toHaveText("");
  await addTaskButton.click();
  await expect(page.getByRole("textbox", { name: `Edit ${manualTitle}` })).toBeVisible();
  console.log(`Disposable integration account: ${email}`);
});
