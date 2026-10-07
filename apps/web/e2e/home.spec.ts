import { expect, test } from "@playwright/test";

test("home page presents Orin's purpose", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("Orin");
  await expect(page.getByRole("heading", { name: "Make room for what comes next." })).toBeVisible();
  await expect(page.getByText("Your personal execution environment")).toBeVisible();
});
