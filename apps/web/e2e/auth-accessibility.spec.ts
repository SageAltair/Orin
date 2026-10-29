import { expect, test } from "@playwright/test";

test("password visibility control has a separate accessible name from its input", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", route =>
    route.fulfill({ status: 401, json: { detail: "Not authenticated" } }),
  );
  await page.goto("/");

  const password = page.getByLabel("Password", { exact: true });
  await expect(password).toHaveCount(1);
  await expect(password).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "Show password" })).toBeVisible();

  await password.fill("a-secure-test-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();

  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
});
