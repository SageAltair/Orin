import { expect, test } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

test("Docker web, authentication, manual tasks, and live AI command flow", async ({ page }) => {
  test.skip(process.env.ORIN_DOCKER_E2E !== "true", "set ORIN_DOCKER_E2E=true to exercise the running Docker stack and configured AI provider");
  test.setTimeout(180_000);

  const email = `orin-docker-e2e-${Date.now()}@example.com`;
  const password = `Orin-smoke-${crypto.randomUUID()}!`;
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
  await expect(page.locator(".command-result")).toContainText('"response"', { timeout: 60_000 });

  await ask.fill("How are you today?");
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.locator(".command-result")).toContainText('"intent": "RESPOND"', { timeout: 60_000 });

  const aiTaskTitle = `AI task ${Date.now()}`;
  await ask.fill(`Create a task called ${aiTaskTitle}`);
  await page.getByRole("button", { name: "Send to Orin" }).click();
  await expect(page.getByRole("textbox", { name: `Edit ${aiTaskTitle}` })).toBeVisible({ timeout: 60_000 });

  await page.getByRole("navigation").getByRole("button", { name: "Tasks" }).click();
  const manualTitle = `Manual task ${Date.now()}`;
  await page.getByLabel("Task title").fill(manualTitle);
  const addTaskButton = page.getByRole("button", { name: "Add task" });
  await expect(addTaskButton).toHaveText("");
  await addTaskButton.click();
  await expect(page.getByRole("textbox", { name: `Edit ${manualTitle}` })).toBeVisible();
  console.log(`Disposable integration account: ${email}`);
});
