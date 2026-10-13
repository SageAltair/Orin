import { expect, test, type Page } from "@playwright/test";

test.beforeEach(() => {
  test.skip(
    process.env.ORIN_LIVE_E2E !== "true",
    "Requires an isolated API with ORIN_LIVE_E2E=true",
  );
});

async function account(page: Page) {
  const email = `studio-${Date.now()}-${Math.random()}@example.com`;
  const password = "Isolated-studio-passphrase-123!";
  const register = await page.request.post(
    "http://localhost:8100/api/v1/auth/register",
    {
      data: { email, password, display_name: "Studio writer" },
    },
  );
  expect(register.status()).toBe(201);
  const response = await page.request.post(
    "http://localhost:8100/api/v1/auth/login",
    { data: { email, password } },
  );
  expect(response.ok()).toBe(true);
  const { access_token } = await response.json();
  return { Authorization: `Bearer ${access_token}` };
}

test("Writing connects ideas, notes, outlines and cards across reload and phone layouts", async ({
  page,
}) => {
  const headers = await account(page);
  const project = await (
    await page.request.post("http://localhost:8100/api/v1/projects", {
      headers,
      data: { name: "A story worth telling" },
    })
  ).json();
  await page.request.post("http://localhost:8100/api/v1/knowledge/documents", {
    headers,
    data: {
      title: "Source note",
      content: "The main character chooses courage.",
      project_id: project.id,
    },
  });
  await page.goto("http://localhost:5273");
  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page.getByRole("button", { name: "Idea inbox", exact: true }).click();
  await page
    .locator("#studio-idea-input")
    .fill("The courage scene\nAn ordinary person makes a difficult choice.");
  await page.getByRole("button", { name: "Capture idea", exact: true }).click();
  await expect(page.locator(".studio-inbox")).toContainText(
    "The courage scene",
  );
  await page.getByRole("button", { name: "Connections", exact: true }).click();
  await page
    .locator(".studio-canvas-idea")
    .filter({ hasText: "The courage scene" })
    .click();
  await page
    .locator("#studio-link-document")
    .selectOption({ label: "Source note" });
  await page.locator("#studio-link-type").selectOption("extends");
  await page.getByRole("button", { name: "Link note", exact: true }).click();
  await expect(page.locator(".studio-canvas-links")).toContainText(
    "Source note",
  );
  await page.getByRole("button", { name: "Manuscript", exact: true }).click();
  await page.getByLabel("Outline title").fill("Opening scene");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.locator(".manuscript-outline")).toContainText(
    "Opening scene",
  );
  await page.getByLabel("Card title", { exact: true }).fill("Opening purpose");
  await page
    .getByLabel("Card purpose")
    .fill("Let the audience meet the character.");
  await page.getByRole("button", { name: "Add card", exact: true }).click();
  await page.getByLabel("Status of card Opening purpose").selectOption("ready");
  await expect(page.getByLabel("Status of card Opening purpose")).toHaveValue(
    "ready",
  );
  await page.reload();
  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page.getByRole("button", { name: "Manuscript", exact: true }).click();
  await expect(page.getByLabel("Status of card Opening purpose")).toHaveValue(
    "ready",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("Toggle light or dark theme").click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
});

test("unsaved notes flush on switching and conflicts retain a recoverable local draft", async ({
  page,
}) => {
  const headers = await account(page);
  const initial = await (
    await page.request.post(
      "http://localhost:8100/api/v1/knowledge/documents",
      {
        headers,
        data: { title: "First note", content: "Initial text" },
      },
    )
  ).json();
  await page.request.post("http://localhost:8100/api/v1/knowledge/documents", {
    headers,
    data: { title: "Second note", content: "A second thought" },
  });
  await page.goto("http://localhost:5273");
  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page
    .locator(".writing-documents")
    .getByRole("button", { name: /First note/ })
    .click();
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue("Initial text");
  await page
    .getByLabel("Content", { exact: true })
    .fill("Saved before navigation.");
  await page
    .locator(".writing-documents")
    .getByRole("button", { name: /Second note/ })
    .click();
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue("A second thought");
  const saved = await (
    await page.request.get(
      `http://localhost:8100/api/v1/knowledge/documents/${initial.id}`,
      { headers },
    )
  ).json();
  expect(saved.content).toBe("Saved before navigation.");
  await page
    .locator(".writing-documents")
    .getByRole("button", { name: /First note/ })
    .click();
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue("Saved before navigation.");
  await page.request.patch(
    `http://localhost:8100/api/v1/knowledge/documents/${initial.id}`,
    {
      headers,
      data: { content: "Newer server work", expected_version: saved.version },
    },
  );
  await page
    .getByLabel("Content", { exact: true })
    .fill("My conflicting local draft.");
  await expect(page.getByRole("button", { name: "Retry save" })).toBeVisible();
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue(
    "My conflicting local draft.",
  );
  page.on("dialog", (dialog) => dialog.accept());
  await page.reload();
  await page.getByRole("button", { name: "Writing", exact: true }).click();
  await page
    .locator(".writing-documents")
    .getByRole("button", { name: /First note/ })
    .click();
  await expect(page.getByText(/A local draft is available/)).toBeVisible();
  await page
    .getByRole("button", { name: "Restore draft", exact: true })
    .click();
  await expect(page.locator(".writing-save-status")).toContainText("Saved");
  const restored = await (
    await page.request.get(
      `http://localhost:8100/api/v1/knowledge/documents/${initial.id}`,
      { headers },
    )
  ).json();
  expect(restored.content).toBe("My conflicting local draft.");
});
