import { expect, test, type Page } from "@playwright/test";

const timestamp = "2026-10-10T08:00:00Z";

async function setupFocus(page: Page) {
  let task: Record<string, unknown> | null = null;
  let session: Record<string, unknown> | null = null;
  let settings: Record<string, unknown> = { timezone: "Africa/Dar_es_Salaam", theme: "light", reduced_motion: false, hide_timer_numbers: false, sound_enabled: false, haptics_enabled: false, check_in_interval: 15 };
  const plan = () => ({ day_key: "2026-10-10", energy_level: null, tasks: task ? [{ ...task, is_anchor: true, today_position: 0 }] : [] });
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-access-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: timestamp } });
    if (pathname === "/api/v1/focus/settings") {
      if (method === "PUT") settings = { ...settings, ...await route.request().postDataJSON() as Record<string, unknown> };
      return route.fulfill({ json: settings });
    }
    if (pathname === "/api/v1/focus/now") return route.fulfill({ json: { task: task ? { ...task, is_anchor: true, today_position: 0 } : null, focus_session: session, day_key: "2026-10-10", energy_level: "medium", empty_state: !task } });
    if (pathname === "/api/v1/focus/today") return route.fulfill({ json: plan() });
    if (pathname === "/api/v1/focus/later") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/focus/close/today") return route.fulfill({ json: { day_key: "2026-10-10", done_list: [], drift_triggers: [], drift_summary: null, tomorrow_task_id: null, reflection: null } });
    if (pathname === "/api/v1/focus/progress") return route.fulfill({ json: { day_key: "2026-10-10", completed_days: 2, days_in_window: 7, rest_day: false, gentle_nudge: false, reentry: { show: false, absence_key: null }, drift_insights: null } });
    if (pathname === "/api/v1/focus/review") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/focus/weekly-meaning") return route.fulfill({ json: { groups: [] } });
    if (pathname === "/api/v1/focus/prompts") return route.fulfill({ json: { items: [], delivery: "in_app_only", delivery_note: "No notifications are sent." } });
    if (pathname === "/api/v1/focus/reentry/dismiss") return route.fulfill({ status: 204 });
    if (pathname === "/api/v1/focus/privacy/export") return route.fulfill({ json: { drift_events: [], daily_closes: [], daily_plans: [], daily_plan_tasks: [], user_settings: null } });
    if (pathname === "/api/v1/focus/privacy/data" && method === "DELETE") return route.fulfill({ status: 204 });
    if (pathname === "/api/v1/focus/capture" && method === "POST") {
      const input = await route.request().postDataJSON() as { title: string; first_step?: string; energy_level?: string };
      task = { id: "task-1", title: input.title, status: "todo", focus_state: "inbox", first_step: input.first_step ?? null, why: null, energy_level: input.energy_level ?? null, estimated_minutes: 25, project_id: null };
      return route.fulfill({ status: 201, json: task });
    }
    if (pathname === "/api/v1/focus/capture/suggest" && method === "POST") return route.fulfill({ json: { title: "Draft the update", first_step: "Open a blank document", energy_level: "low" } });
    if (pathname === "/api/v1/focus/suggest-smaller" && method === "POST") return route.fulfill({ json: { first_step: "Open the file" } });
    if (pathname === "/api/v1/tasks/task-1" && method === "PATCH") {
      task = { ...task, ...await route.request().postDataJSON() as Record<string, unknown> };
      return route.fulfill({ json: task });
    }
    if (pathname === "/api/v1/focus/today/tasks" && method === "PUT") return route.fulfill({ json: plan() });
    if (pathname === "/api/v1/focus/now/start" && method === "POST") {
      session = { id: "focus-1", task_id: "task-1", duration_minutes: 25, started_at: timestamp, status: "active" };
      return route.fulfill({ json: { task, focus_session: session } });
    }
    if (pathname === "/api/v1/focus/now/drift" && method === "POST") return route.fulfill({ status: 201, json: { id: "drift-1" } });
    if (pathname === "/api/v1/focus/now/complete" && method === "POST") { task = null; session = null; return route.fulfill({ json: { task: null, focus_session: null, day_key: "2026-10-10", energy_level: "medium", empty_state: true } }); }
    if (pathname === "/api/v1/users/me/preferences") return route.fulfill({ json: { density: "comfortable", theme: "light", locale: "en", visible_capabilities: ["home", "tasks", "projects", "activity"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {} } });
    if (pathname.endsWith("/tasks") || pathname.endsWith("/projects") || pathname.endsWith("/commands") || pathname.endsWith("/conversations")) return route.fulfill({ json: [] });
    if (pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    if (pathname === "/api/v1/environment/preferences" || pathname === "/api/v1/memories" || pathname === "/api/v1/approvals" || pathname === "/api/v1/devices") return route.fulfill({ json: [] });
    return route.fulfill({ status: 204 });
  });
}

async function signIn(page: Page) {
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password").fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const workspaceNav = page.getByRole("navigation").first();
  await expect(workspaceNav.getByRole("button", { name: "Home" })).toBeVisible();
  await expect(workspaceNav.getByRole("button", { name: "Projects" })).toBeVisible();
  await expect(workspaceNav.getByRole("button", { name: "Activity" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask Orin" }).first()).toBeVisible();
  if ((await page.evaluate(() => window.innerWidth)) < 600) await page.getByRole("button", { name: "Open navigation" }).click();
  await workspaceNav.getByRole("button", { name: "Tasks" }).click();
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toBeVisible();
}

test("capture appears on Now and starts a timer within three taps", async ({ page }) => {
  await setupFocus(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: /Tasks/ }).click();
  await expect(page.getByRole("heading", { name: "What’s one thing on your mind?" })).toBeVisible();
  await page.getByRole("button", { name: "Add one thing" }).click();
  await page.getByRole("textbox", { name: "What would you like to remember?" }).fill("Write the first paragraph");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Write the first paragraph" })).toBeVisible();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByText("FOCUS MODE")).toBeVisible();
  await expect(page.getByText("Next small step")).toBeVisible();
  await expect(page.getByRole("button", { name: "Done", exact: true })).toBeVisible();
});

test("a failed capture save keeps the user's text available for retry", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Capture" }).click();
  await page.route("**/api/v1/focus/capture", route => route.abort("failed"));
  const draft = "Call the clinic about an appointment";
  await page.getByLabel("What would you like to remember?").fill(draft);
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByLabel("What would you like to remember?")).toHaveValue(draft);
  await expect(page.getByText("That capture did not save. Please try again.")).toBeVisible();
});

test("Recovery exposes weekly progress and decay review controls", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByText("What happens next?").click();
  await page.getByRole("button", { name: "Progress and task review" }).click();
  await expect(page.getByRole("heading", { name: "A little room to reset." })).toBeVisible();
  await expect(page.getByText("2 of 7 days included a completed task.")).toBeVisible();
  await expect(page.getByText("No tasks need a review right now.")).toBeVisible();
  await page.getByRole("button", { name: "Back to Now" }).click();
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toBeVisible();
});

test("private focus data can be exported or deleted with confirmation", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByText("What happens next?").click();
  await page.getByRole("button", { name: "Progress and task review" }).click();
  await page.getByText("Your private focus data").click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export my focus data" }).click();
  expect((await download).suggestedFilename()).toBe("orin-focus-data.json");
  page.on("dialog", dialog => dialog.accept());
  const deletion = page.waitForRequest(request => new URL(request.url()).pathname === "/api/v1/focus/privacy/data" && request.method() === "DELETE");
  await page.getByRole("button", { name: "Delete my focus data" }).click();
  await deletion;
  await expect(page.getByRole("status").filter({ hasText: "Your focus settings, plans, drift notes, and reflections were deleted" })).toBeVisible();
});

test("capture suggestions are optional, editable, and saved with the task", async ({ page }) => {
  await setupFocus(page);
  await page.goto("/"); await signIn(page);
  await page.getByRole("button", { name: "Capture", exact: true }).last().click();
  await page.getByRole("textbox", { name: "What would you like to remember?" }).fill("Write my update");
  await page.getByText("Need help with words or the first step?").click();
  await page.getByRole("button", { name: "Suggest a first step" }).click();
  await expect(page.getByRole("group", { name: "Optional task suggestions" })).toBeVisible();
  await page.getByRole("button", { name: "Use suggestions" }).click();
  await expect(page.getByRole("textbox", { name: "What would you like to remember?" })).toHaveValue("Draft the update");
  await expect(page.getByLabel("First step (optional)")).toHaveValue("Open a blank document");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Draft the update" })).toBeVisible();
  await expect(page.getByText("Open a blank document")).toBeVisible();
});

test("Smaller offers a suggestion and keeps the step editable", async ({ page }) => {
  await setupFocus(page);
  await page.goto("/"); await signIn(page);
  await page.getByRole("button", { name: "Capture", exact: true }).last().click();
  await page.getByRole("textbox", { name: "What would you like to remember?" }).fill("Prepare the proposal");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await page.getByRole("button", { name: "Smaller", exact: true }).click();
  await page.getByRole("button", { name: "Suggest a smaller step" }).click();
  await expect(page.getByRole("textbox", { name: "What is a smaller first step?" })).toHaveValue("Open the file");
  await page.getByRole("textbox", { name: "What is a smaller first step?" }).fill("Open the proposal file");
  await page.getByRole("button", { name: "Save step" }).click();
  await expect(page.getByText("Open the proposal file")).toBeVisible();
});

test("focus surfaces respect dark mode, reduced motion, and control sizing and contrast", async ({ page }) => {
  await setupFocus(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await page.getByText("Settings", { exact: true }).click();
  await page.getByText("Appearance and focus options").click();
  await page.locator(".focus-settings-page select").selectOption("dark");
  await page.getByLabel("Reduce motion").check();
  const shell = page.locator(".focus-shell");
  await expect(shell).toHaveClass(/focus-dark/);
  await expect(shell).toHaveClass(/focus-reduced-motion/);
  const audit = await page.evaluate(() => {
    const root = document.querySelector<HTMLElement>(".focus-shell")!;
    const style = getComputedStyle(root);
    const rgb = (value: string) => {
      if (value.startsWith("#")) { const hex = value.slice(1); return hex.length === 3 ? [...hex].map(channel => Number.parseInt(channel + channel, 16)) : [0, 2, 4].map(index => Number.parseInt(hex.slice(index, index + 2), 16)); }
      return value.match(/[\d.]+/g)!.slice(0, 3).map(Number);
    };
    const luminance = (value: string) => {
      const channels = rgb(value).map(channel => { const s = channel / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
      return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
    };
    const ratio = (a: string, b: string) => { const values = [luminance(a), luminance(b)].sort((x, y) => y - x); return (values[0] + 0.05) / (values[1] + 0.05); };
    const text = style.getPropertyValue("--focus-text").trim();
    const secondary = style.getPropertyValue("--focus-secondary").trim();
    const surface = style.getPropertyValue("--focus-surface").trim();
    const controls = [...root.querySelectorAll<HTMLElement>("button, select, input:not([type=checkbox]), textarea, input[type=checkbox]")].filter(el => el.getClientRects().length).map(el => el instanceof HTMLInputElement && el.type === "checkbox" ? el.closest("label") as HTMLElement : el);
    return { contrast: [ratio(text, surface), ratio(secondary, surface)], small: controls.map(el => ({ name: el.getAttribute("aria-label") || el.textContent || el.tagName, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })) };
  });
  expect(audit.contrast.every(value => value >= 4.5), JSON.stringify(audit.contrast)).toBeTruthy();
  expect(audit.small.filter(item => item.width < 48 || item.height < 48), JSON.stringify(audit.small)).toEqual([]);
});

test("Later load errors remain visible and the surface recovers on retry", async ({ page }) => {
  await setupFocus(page);
  let fail = true;
  await page.route("**/api/v1/focus/later", route => fail
    ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
    : route.fulfill({ json: [] }));
  await page.goto("/"); await signIn(page);
  await expect(page.getByRole("alert").filter({ hasText: "Could not load focus" })).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await page.getByRole("button", { name: "Browse Later" }).click();
  await expect(page.getByText("Nothing waiting here.")).toBeVisible();
});

test("Close save failure keeps the answers available for recovery", async ({ page }) => {
  await setupFocus(page);
  await page.route("**/api/v1/focus/daily-closes/today", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/"); await signIn(page);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Tired", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Save and close" }).click();
  await expect(page.getByRole("alert")).toContainText("Could not save the close");
  await expect(page.getByRole("heading", { name: "One thing for tomorrow?" })).toBeVisible();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tired", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("focus remains reachable by keyboard and fits narrow and wide viewports", async ({ page }) => {
  await setupFocus(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/"); await signIn(page);
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  await expect(page.getByRole("main", { name: "" }).last()).toBeVisible();
  const narrow = await page.locator(".focus-shell").evaluate(element => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(narrow.scroll).toBeLessThanOrEqual(narrow.client + 1);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const wide = await page.locator(".focus-shell").evaluate(element => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(wide.scroll).toBeLessThanOrEqual(wide.client + 1);
});

test("focus layout remains readable at 200 percent page zoom", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Capture" }).click();
  await page.evaluate(() => { document.documentElement.style.zoom = "200%"; });
  await expect(page.getByRole("heading", { name: "What would you like to do?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save and continue" })).toBeVisible();
  const shell = await page.locator(".focus-shell").evaluate(element => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(shell.scroll).toBeLessThanOrEqual(shell.client + 1);
});
