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
  test.setTimeout(90000);
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
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Opportunities", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Capture opportunity", exact: true })
    .click();
  await page.getByLabel("Opportunity title").fill("Creative collaboration");
  await page.getByLabel("Small next action").fill("Read the brief");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Creative collaboration", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("opportunities-mobile.png"),
  });
  await page
    .getByRole("button", { name: "Consider a risk", exact: true })
    .click();
  await page.getByLabel("Risk title").fill("Capacity clash");
  await page
    .getByLabel("Response plan")
    .fill("Agree a smaller first deliverable");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await page.getByRole("tab", { name: "Risk register" }).click();
  await expect(
    page.getByRole("button", { name: "Capacity clash", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page.getByRole("button", { name: "Calendar", exact: true }).click();
  await page.getByRole("button", { name: "Routines", exact: true }).click();
  await page.getByRole("button", { name: "New routine", exact: true }).click();
  await page.getByLabel("Routine title").fill("Gentle beginning");
  await page.getByLabel("Minimum action").fill("Open my notebook");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Gentle beginning", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Minimum counts", exact: true })
    .click();
  await expect(
    page.getByText("Minimum version counts. You showed up."),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("routines-mobile.png"),
  });
  await page
    .getByRole("button", { name: "Show calendar", exact: true })
    .click();
  await expect(
    page
      .getByRole("button", {
        name: "Open routine ↻ Gentle beginning",
        exact: true,
      })
      .first(),
  ).toBeVisible();
  // A real due task triggers a durable reminder. Persistent mode requires an explicit saved choice.
  await page.request.post("http://localhost:8100/api/v1/tasks", {
    headers,
    data: {
      title: "Review notification delivery",
      due_at: new Date().toISOString(),
    },
  });
  await expect
    .poll(
      async () => {
        const rows = await (
          await page.request.get("http://localhost:8100/api/v1/notifications", {
            headers,
          })
        ).json();
        return rows.some(
          (r: { title: string; attention_ready: boolean }) =>
            r.title === "Review notification delivery" && r.attention_ready,
        );
      },
      { timeout: 25000 },
    )
    .toBe(true);
  await expect(
    page.getByRole("complementary", { name: "Persistent follow-up" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page.getByRole("button", { name: "Preferences", exact: true }).click();
  const notificationSettings = page.getByRole("region", {
    name: "Notification preferences",
  });
  await notificationSettings
    .getByRole("checkbox", { name: /Enable stubborn mode/ })
    .check();
  await notificationSettings
    .getByRole("button", { name: "Save notification preferences", exact: true })
    .click();
  await expect(
    notificationSettings.getByText("Notification preferences saved."),
  ).toBeVisible();
  const savedNotificationPolicy = await (
    await page.request.get(
      "http://localhost:8100/api/v1/notifications/preferences",
      { headers },
    )
  ).json();
  expect(savedNotificationPolicy.persistent).toBe(true);
  const followup = page.getByRole("complementary", {
    name: "Persistent follow-up",
  });
  await expect(followup).toContainText("Review notification delivery");
  await followup
    .getByRole("button", { name: "Snooze 15 min", exact: true })
    .click();
  await expect(followup).toHaveCount(0);
  await page.getByRole("button", { name: /^Reminders/ }).click();
  await page
    .getByRole("button", {
      name: "Mark Review notification delivery read",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Mark Review notification delivery read",
      exact: true,
    }),
  ).toHaveCount(0);
  const inbox = await (
    await page.request.get("http://localhost:8100/api/v1/notifications", {
      headers,
    })
  ).json();
  expect(
    inbox.find(
      (r: { title: string }) => r.title === "Review notification delivery",
    ).read_at,
  ).toBeTruthy();
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
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue(
    "Initial text",
  );
  await page
    .getByLabel("Content", { exact: true })
    .fill("Saved before navigation.");
  await page
    .locator(".writing-documents")
    .getByRole("button", { name: /Second note/ })
    .click();
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue(
    "A second thought",
  );
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
  await expect(page.getByLabel("Content", { exact: true })).toHaveValue(
    "Saved before navigation.",
  );
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
