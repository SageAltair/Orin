import { expect, test } from "@playwright/test";

test("personal knowledge capture, editing, links, search, and reload persistence", async ({ page }) => {
  test.setTimeout(60_000);
  const email = `orin-knowledge-${Date.now()}@example.com`;
  await page.goto("http://localhost:5273");
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Knowledge workflow test");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(`Orin-knowledge-${crypto.randomUUID()}!`);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: /What needs your attention/ })).toBeVisible();

  await page.getByRole("button", { name: "Capture a thought" }).click();
  await page.getByLabel("Your note").fill("Create Christian storytelling videos\nExplore short stories with a clear audience.");
  await page.getByRole("button", { name: "Save note" }).click();
  await page.getByRole("button", { name: "Knowledge" }).click();
  await page.getByRole("button", { name: /Create Christian storytelling videos/ }).click();
  await expect(page.getByLabel("Content")).toContainText("Explore short stories");
  await page.getByLabel("Content").fill("Create Christian storytelling videos for families, with short stories and a clear audience.");
  await expect(page.getByRole("status")).toContainText("Saved", { timeout: 10_000 });

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Document title").fill("AI assisted storytelling research");
  await page.locator(".knowledge-properties label").filter({ hasText: "Type" }).locator("select").selectOption("research");
  await page.getByLabel("Content").fill("Research AI tools for story outlining and narration.");
  await expect(page.getByRole("status")).toContainText("Saved", { timeout: 10_000 });
  await page.getByRole("button", { name: "Bold" }).click();
  await expect(page.getByLabel("Content")).toContainText("**text**");
  await page.getByRole("button", { name: "Preview formatting" }).click();
  await expect(page.locator(".knowledge-markdown-preview").getByText("text")).toBeVisible();
  await page.getByRole("button", { name: "Edit markdown" }).click();
  await expect(page.getByRole("status")).toContainText("Saved", { timeout: 10_000 });
  await page.getByLabel("Link to").selectOption({ label: "Create Christian storytelling videos" });
  await page.getByRole("button", { name: "Add link" }).click();
  await expect(page.locator(".knowledge-relations > div").getByText(/Create Christian storytelling videos/)).toBeVisible();

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Document title").fill("Unfinished video script draft");
  await page.locator(".knowledge-properties label").filter({ hasText: "Type" }).locator("select").selectOption("draft");
  await page.getByLabel("Status").selectOption("developing");
  await page.getByLabel("Review date").fill("2020-01-01T10:00");
  await page.getByLabel("Content").fill("Opening scene and narration are not finished.");
  await expect(page.getByRole("status")).toContainText("Saved", { timeout: 10_000 });

  await page.getByRole("button", { name: "Weekly review" }).click();
  await expect(page.locator(".knowledge-weekly-report")).toBeVisible();

  await page.getByLabel("Ask your knowledge").fill("Christian storytelling");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".knowledge-answer")).toBeVisible();
  await expect(page.locator(".knowledge-answer").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await page.getByRole("button", { name: "Refresh signals" }).click();
  const reviewColumn = page.locator(".knowledge-signal-grid > div").nth(1);
  const review = reviewColumn.locator(".knowledge-signal").filter({ hasText: "Unfinished video script draft" });
  await expect(review).toBeVisible();
  await review.getByRole("button", { name: "Snooze" }).click();
  const snoozedSection = reviewColumn.locator("details").filter({ hasText: "Snoozed" });
  await snoozedSection.locator("summary").click();
  const snoozed = snoozedSection.locator(".knowledge-signal").filter({ hasText: "Unfinished video script draft" });
  await expect(snoozed).toBeVisible();
  await snoozed.getByRole("button", { name: "Resume" }).click();
  await expect(review.getByRole("button", { name: "Done" })).toBeVisible();
  await review.getByRole("button", { name: "Done" }).click();

  await page.getByLabel("Search documents").fill("Christian storytelling");
  await expect(page.locator(".knowledge-documents").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Knowledge" }).click();
  await expect(page.locator(".knowledge-documents").getByRole("button", { name: /AI assisted storytelling research/ })).toBeVisible();
  await expect(page.locator(".knowledge-documents").getByRole("button", { name: /Unfinished video script draft/ })).toBeVisible();
  await page.locator(".knowledge-documents").getByRole("button", { name: /AI assisted storytelling research/ }).click();
  await expect(page.locator(".knowledge-relations > div").getByText(/Create Christian storytelling videos/)).toBeVisible();
});
