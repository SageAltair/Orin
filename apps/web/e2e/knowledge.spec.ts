import { expect, test } from "@playwright/test";
test.beforeEach(() => { test.skip(process.env.ORIN_LIVE_E2E !== "true", "Set ORIN_LIVE_E2E=true with an isolated API running to verify live writing workflows"); });

test("personal knowledge capture, editing, links, search, and reload persistence", async ({ page }) => {
  test.setTimeout(120_000);
  const email = `orin-knowledge-${Date.now()}@example.com`;
  await page.goto("http://localhost:5273");
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Knowledge workflow test");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(`Orin-knowledge-${crypto.randomUUID()}!`);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: /What would you like to.*work on today/ })).toBeVisible();

  await page.keyboard.press("Control+k");
  await page.getByRole("button", { name: /Capture an idea/ }).click();
  await page.getByLabel("Your note").fill("Create Christian storytelling videos\nExplore short stories with a clear audience.");
  await page.getByRole("button", { name: "Save note" }).click();
  await page.getByRole("button", { name: "Writing" }).click();
  await page.getByRole("button", { name: /Create Christian storytelling videos/ }).click();
  await expect(page.getByLabel("Content")).toContainText("Explore short stories");
  await page.locator(".writing-details > summary").click();
  await page.locator(".writing-details-grid label").filter({ hasText: "Type" }).locator("select").selectOption("idea");
  await page.getByLabel("Tags, comma separated").fill("story, setting");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });
  await page.locator(".writing-details > summary").click();
  await page.getByLabel("Filter notes").click();
  await page.getByLabel("Document type").selectOption("idea");
  await expect(page.locator(".writing-documents").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await page.getByLabel("Document type").selectOption("");
  let extractionPolls = 0;
  await page.route("**/api/v1/knowledge/documents/*/extract", route => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "queued" }) }));
  await page.route("**/api/v1/knowledge/documents/*/extraction", route => {
    extractionPolls += 1;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(extractionPolls < 2
      ? { status: "queued", extracted_data: null, job: { error: null } }
      : { status: "succeeded", extracted_data: { summary: "A family storytelling project.", topics: ["storytelling"], entities: [], decisions: [], open_questions: [], candidate_actions: [], date_mentions: [] }, job: { error: null } }) });
  });
  await page.locator(".writing-details > summary").click();
  await page.getByRole("button", { name: "Extract knowledge" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Knowledge extracted" })).toBeVisible({ timeout: 8_000 });
  await expect(page.getByText("A family storytelling project.")).toBeVisible();
  await page.unrouteAll();
  await page.locator(".writing-details > summary").click();
  await page.getByLabel("Content").fill("Create Christian storytelling videos for families, with short stories and a clear audience.");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Document title").fill("AI assisted storytelling research");
  await page.locator(".writing-details > summary").click();
  await page.locator(".writing-details-grid label").filter({ hasText: "Type" }).locator("select").selectOption("research");
  await page.locator(".writing-details > summary").click();
  await page.getByLabel("Content").fill("Research AI tools for story outlining and narration.");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });
  await page.getByLabel("Content").click();
  await page.keyboard.press("Control+a");
  await page.getByRole("button", { name: "Bold" }).click();
  expect(await page.getByLabel("Content").evaluate((element) => element.innerHTML)).toMatch(/<(b|strong)(>| )/i);
  await page.getByRole("button", { name: "Preview document" }).click();
  await expect(page.getByLabel("Document preview")).toContainText("Research AI tools");
  await page.getByRole("button", { name: "Return to editing" }).click();
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });
  await page.locator(".writing-details > summary").click();
  await page.getByLabel("Link to").selectOption({ label: "Create Christian storytelling videos" });
  await page.getByRole("button", { name: "Add link" }).click();
  await expect(page.locator(".writing-relations").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();

  await page.getByRole("button", { name: "New note" }).click();
  await page.getByLabel("Document title").fill("Unfinished video script draft");
  await page.locator(".writing-details > summary").click();
  await page.locator(".writing-details-grid label").filter({ hasText: "Type" }).locator("select").selectOption("draft");
  await page.locator(".writing-details-grid label").filter({ hasText: "Status" }).locator("select").selectOption("developing");
  await page.locator(".writing-details-grid label").filter({ hasText: "Review date" }).locator("input").fill("2020-01-01T10:00");
  await page.getByLabel("Content").fill("Opening scene and narration are not finished.");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });

  await page.locator(".writing-tools > summary").click();
  await page.getByRole("button", { name: "Weekly report" }).click();
  await expect(page.locator(".writing-tool-result").filter({ hasText: "Weekly report" })).toBeVisible();

  await page.getByLabel("Ask your notes").fill("Christian storytelling");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".writing-tool-result").first()).toBeVisible();
  await expect(page.locator(".writing-tool-result").first().getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await page.getByRole("button", { name: "Refresh signals" }).click();
  const reviewColumn = page.locator(".writing-signal-list");
  const review = reviewColumn.locator("article").filter({ hasText: "Due" });
  await expect(review).toBeVisible();
  await review.getByRole("button", { name: "Snooze" }).click();
  const snoozedSection = reviewColumn.locator("details").filter({ hasText: "Snoozed" });
  await snoozedSection.locator("summary").click();
  const snoozed = snoozedSection.locator("article").filter({ hasText: "Unfinished video script draft" });
  await expect(snoozed).toBeVisible();
  await snoozed.getByRole("button", { name: "Resume" }).click();
  await expect(review.getByRole("button", { name: "Done" })).toBeVisible();
  await review.getByRole("button", { name: "Done" }).click();

  await page.getByLabel("Search documents").fill("Christian storytelling");
  await expect(page.locator(".writing-documents").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Writing" }).click();
  await expect(page.locator(".writing-documents").getByRole("button", { name: /AI assisted storytelling research/ })).toBeVisible();
  await expect(page.locator(".writing-documents").getByRole("button", { name: /Unfinished video script draft/ })).toBeVisible();
  await page.locator(".writing-documents").getByRole("button", { name: /AI assisted storytelling research/ }).click();
  await expect(page.getByLabel("Document title")).toHaveValue("AI assisted storytelling research", { timeout: 10_000 });
  await page.locator(".writing-details > summary").click();
  await expect(page.locator(".writing-relations").getByRole("button", { name: /Create Christian storytelling videos/ })).toBeVisible();
  await expect(page.locator(".writing-manuscript-stats")).toContainText("words");
  const markdownDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Manage document" }).click();
  await page.getByRole("button", { name: /Export document/ }).click();
  await page.getByRole("dialog", { name: "Export document" }).getByRole("button", { name: /Markdown/ }).click();
  expect((await markdownDownload).suggestedFilename()).toMatch(/\.md$/);
  await page.getByRole("button", { name: "Focus", exact: true }).click();
  await expect(page.locator(".writing-list")).toBeHidden();
  await page.getByRole("button", { name: "Exit focus" }).click();
  await expect(page.locator(".writing-list")).toBeVisible();
  const restore = page.locator(".writing-history").getByRole("button", { name: "Restore" }).first();
  await expect(restore).toBeEnabled();
  await restore.click();
  await expect(page.locator(".writing-save-status")).toContainText("Restored version", { timeout: 10_000 });
  await page.getByLabel("Content").fill("A local draft to recover after an interrupted save.");
  await expect.poll(() => page.evaluate(() => Object.keys(localStorage).find(key => key.startsWith("orin:writing:draft:")) ?? "")).not.toBe("");
  await page.reload();
  await page.getByRole("button", { name: "Writing" }).click();
  await page.locator(".writing-documents").getByRole("button", { name: /AI assisted storytelling research/ }).click();
  await expect(page.getByText(/A local draft is available/)).toBeVisible();
  await page.getByRole("button", { name: "Restore draft" }).click();
  await expect(page.getByLabel("Content")).toHaveText("A local draft to recover after an interrupted save.");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });
});

test("Writing adapts its navigation and editor across desktop, tablet, and narrow phone viewports", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("http://localhost:5273");
  await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
  await page.getByLabel("Your name").fill("Writing responsive check");
  await page.getByLabel("Email").fill(`orin-writing-layout-${Date.now()}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill(`Orin-layout-${crypto.randomUUID()}!`);
  await page.getByRole("button", { name: "Create account" }).click();
  // The Writing studio intentionally hides the global topbar, so verify theme
  // switching while the accessible control is present before entering it.
  await page.getByLabel("Toggle light or dark theme").click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await page.getByLabel("Toggle light or dark theme").click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-light/);
  await page.getByRole("button", { name: "Writing" }).click();
  await page.getByRole("button", { name: "New note" }).first().click();
  await page.getByLabel("Document title").fill("Responsive writing note");
  await page.getByLabel("Content").fill("A saved note that remains comfortable to edit at every viewport.");
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10_000 });

  const viewports = [
    [1920, 1080], [1440, 900], [1280, 800], [1024, 768], [768, 1024],
    [932, 430], [844, 390], [430, 932], [390, 844], [375, 667], [320, 568],
  ] as const;
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await expect(page.locator(".writing-workspace")).toBeVisible();
    await expect(page.locator(".writing-editor")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `no horizontal page overflow at ${width}x${height}`).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 2), `no unnecessary page-level vertical scrolling at ${width}x${height}`).toBe(true);
    if (width <= 820) {
      await expect(page.locator(".writing-list")).toBeHidden();
      await expect(page.getByLabel("Back to notes")).toBeVisible();
      if (width === 390) {
        await page.screenshot({ path: "test-results/writing-mobile-390.png", fullPage: true });
      }
      if (width === 320) await page.screenshot({ path: "test-results/writing-narrow-320.png", fullPage: true });
      await page.getByLabel("Back to notes").click();
      await expect(page.locator(".writing-list")).toBeVisible();
      await expect(page.locator(".writing-documents").getByRole("button", { name: /Responsive writing note/ })).toBeVisible();
      await page.locator(".writing-documents").getByRole("button", { name: /Responsive writing note/ }).click();
    } else {
      await expect(page.locator(".writing-list")).toBeVisible();
      if (width === 1440) await page.screenshot({ path: "test-results/writing-desktop-1440.png", fullPage: true });
    }
  }
});
