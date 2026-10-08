import { expect, test } from "@playwright/test";

test("home presents the minimal Orin shell", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("Orin");
  await expect(page.getByRole("heading", { name: "What matters now?" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Tasks" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Activity" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toBeVisible();
});

test("settings reveals granted capabilities in navigation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Show Projects in navigation" }).check();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
});
