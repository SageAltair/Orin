import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const timestamp = "2026-10-10T08:00:00Z";

async function setupFocus(page: Page, priorityMode: "balanced" | "proactive" | "planning-only" = "balanced") {
  let task: Record<string, unknown> | null = null;
  let session: Record<string, unknown> | null = null;
  const collectionTasks: Record<string, unknown>[] = [
    { id: "inbox-task", title: "Ask the team about the venue", description: null, status: "todo", priority: "normal", due_at: null, focus_state: "inbox", project_id: null },
    { id: "today-task", title: "Review the project outline", description: null, status: "todo", priority: "high", due_at: null, focus_state: "today", project_id: null },
    { id: "upcoming-task", title: "Prepare next week's notes", description: null, status: "todo", priority: "normal", due_at: "2099-10-13T14:00:00Z", focus_state: "later", project_id: null },
    { id: "completed-task", title: "Send the approved update", description: null, status: "done", priority: "normal", due_at: null, focus_state: "released", project_id: null },
  ];
  let settings: Record<string, unknown> = { timezone: "Africa/Dar_es_Salaam", theme: "light", reduced_motion: false, hide_timer_numbers: false, sound_enabled: false, haptics_enabled: false, check_in_interval: 15 };
  const plan = () => ({ day_key: "2026-10-10", energy_level: null, tasks: task ? [{ ...task, is_anchor: true, today_position: 0 }] : [] });
  let workspaceTheme = "light";
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
    if (pathname === "/api/v1/tasks" && method === "GET") return route.fulfill({ json: collectionTasks });
    if (pathname === "/api/v1/tasks" && method === "POST") {
      const input = await route.request().postDataJSON() as Record<string, unknown>;
      const created = { id: "new-scheduled-task", status: "todo", focus_state: "inbox", created_at: timestamp, updated_at: timestamp, ...input };
      collectionTasks.unshift(created);
      return route.fulfill({ status: 201, json: created });
    }
    if (/\/api\/v1\/tasks\/[^/]+$/.test(pathname) && method === "PATCH") { const item = collectionTasks.find(candidate => candidate.id === pathname.split("/").at(-1)); if (!item) return route.fulfill({ status: 404, json: { detail: "Task not found" } }); Object.assign(item, await route.request().postDataJSON()); return route.fulfill({ json: item }); }
    if (pathname === "/api/v1/focus/today/tasks" && method === "PUT") return route.fulfill({ json: plan() });
    if (pathname === "/api/v1/focus/now/start" && method === "POST") {
      session = { id: "focus-1", task_id: "task-1", duration_minutes: 25, started_at: timestamp, status: "active" };
      return route.fulfill({ json: { task, focus_session: session } });
    }
    if (pathname === "/api/v1/focus/now/drift" && method === "POST") return route.fulfill({ status: 201, json: { id: "drift-1" } });
    if (pathname === "/api/v1/focus/now/complete" && method === "POST") { task = null; session = null; return route.fulfill({ json: { task: null, focus_session: null, day_key: "2026-10-10", energy_level: "medium", empty_state: true } }); }
    if (pathname === "/api/v1/users/me/preferences") { if (method === "PUT" || method === "PATCH") workspaceTheme = (await route.request().postDataJSON()).theme ?? workspaceTheme; return route.fulfill({ json: { density: "comfortable", theme: workspaceTheme, locale: "en", visible_capabilities: ["home", "tasks", "projects", "activity"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {}, priority_guidance_mode: priorityMode } }); }
    if (pathname.endsWith("/tasks") || pathname.endsWith("/projects") || pathname.endsWith("/commands") || pathname.endsWith("/conversations")) return route.fulfill({ json: [] });
    if (pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    if (pathname === "/api/v1/environment/preferences" || pathname === "/api/v1/memories" || pathname === "/api/v1/approvals" || pathname === "/api/v1/devices") return route.fulfill({ json: [] });
    return route.fulfill({ status: 204 });
  });
}

async function signIn(page: Page) {
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-secure-test-password");
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
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Now" }).click();
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
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Now" }).click();
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
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Now" }).click();
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

test("the focus workspace can find inbox, today, upcoming, and completed tasks", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  const focusNav = page.getByRole("navigation", { name: "Focus navigation" });
  await focusNav.getByRole("button", { name: "Tasks" }).click();
  await expect(page.getByRole("heading", { name: "Tasks", exact: true })).toBeVisible();
  await expect(page.locator(".focus-task-list").getByText("Ask the team about the venue")).toBeVisible();
  await page.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Today/ }).click();
  await expect(page.locator(".focus-task-list").getByText("Review the project outline")).toBeVisible();
  await expect(page.locator(".focus-task-list").getByText("Ask the team about the venue")).toHaveCount(0);
  await page.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Upcoming/ }).click();
  await expect(page.locator(".focus-task-list").getByText("Prepare next week's notes")).toBeVisible();
  await page.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Completed/ }).click();
  await expect(page.locator(".focus-task-list").getByText("Send the approved update")).toBeVisible();
  await expect(page.locator(".task-workspace-heading")).toHaveCount(0);
  await expect(focusNav).toBeVisible();
  expect(await focusNav.evaluate(el => getComputedStyle(el).position)).toBe("static");
  await page.screenshot({path:test.info().outputPath("tasks-desktop.png")});
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByLabel("Toggle light or dark theme").click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({path:test.info().outputPath("tasks-mobile-dark.png")});

});

test("Tasks recovers project choices and offers projects beyond the first API page", async ({ page }) => {
  await setupFocus(page);
  const projects = Array.from({ length: 105 }, (_, index) => ({ id: `project-${index}`, name: `Project ${index}`, status: "active" }));
  let fail = true;
  await page.route("**/api/v1/projects?*", route => {
    if (fail) return route.fulfill({ status: 503, json: { detail: "Project list unavailable" } });
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 100);
    return route.fulfill({ json: projects.slice(offset, offset + limit) });
  });
  await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  const workspace = page.locator(".focus-task-collection");
  await workspace.getByRole("button", { name: "New task" }).click();
  await expect(workspace.getByRole("alert").filter({ hasText: "Project choices unavailable" })).toBeVisible();
  await expect(workspace.getByLabel("Project", { exact: true })).toBeDisabled();
  fail = false;
  await workspace.getByRole("button", { name: "Retry projects" }).click();
  await expect(workspace.getByLabel("Project", { exact: true })).toBeEnabled();
  await expect(workspace.getByLabel("Project", { exact: true }).locator("option")).toHaveCount(106);
  await workspace.getByLabel("Task name").fill("Review final project");
  await workspace.getByLabel("Project", { exact: true }).selectOption("project-104");
  const saveRequest = page.waitForRequest(req => new URL(req.url()).pathname === "/api/v1/tasks" && req.method() === "POST");
  await workspace.getByRole("button", { name: "Save task" }).click();
  expect((await saveRequest).postDataJSON().project_id).toBe("project-104");
  await expect(workspace.getByText("Project 104")).toBeVisible();
});

test("Tasks creates and edits a precisely scheduled task in the unified list", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  const workspace = page.locator(".focus-task-collection");
  await expect(workspace.getByRole("button", { name: /All tasks/ })).toHaveAttribute("aria-pressed", "true");
  await workspace.getByRole("button", { name: "New task" }).click();
  await workspace.getByLabel("Task name").fill("Scheduled notification test");
  // Keep the due date in Upcoming regardless of when CI runs or the browser timezone.
  // A fixed 2026-11-01 date became Today on Nov 1 and invalidated this assertion.
  const futureLocal = await page.evaluate(() => {
    const date = new Date();
    date.setDate(date.getDate() + 2);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T15:45`;
  });
  await workspace.getByLabel("Due date and time (local)").fill(futureLocal);
  await workspace.getByLabel("Priority", { exact: true }).selectOption("high");
  await workspace.getByRole("button", { name: "Save task" }).click();
  await expect(workspace.locator(".focus-task-list").getByText("Scheduled notification test")).toBeVisible();
  await workspace.locator(".focus-task-list").getByRole("button", { name: "Edit Scheduled notification test" }).click();
  await expect(workspace.getByLabel("Due date and time (local)")).toHaveValue(futureLocal);
  await workspace.getByLabel("Task name").fill("Scheduled task updated");
  await workspace.getByRole("button", { name: "Save task" }).click();
  await expect(workspace.locator(".focus-task-list").getByText("Scheduled task updated")).toBeVisible();
  await workspace.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Upcoming/ }).click();
  await expect(workspace.locator(".focus-task-list").getByText("Scheduled task updated")).toBeVisible();
});

test("personal Tasks respects the account's persisted priority guidance mode", async ({ page }) => {
  await setupFocus(page, "planning-only");
  await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  await page.locator(".focus-priority-disclosure > summary").click();
  const outlook = page.getByRole("region", { name: "Priority outlook" });
  await expect(outlook.getByText("Planning-only")).toBeVisible();
});

test("priority Start explicitly marks a task in progress without starting a focus timer", async ({ page }) => {
  await setupFocus(page); await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  await page.locator(".focus-priority-disclosure > summary").click();
  const outlook = page.getByRole("region", { name: "Priority outlook" });
  const taskName = "Ask the team about the venue";
  const start = outlook.getByRole("button", { name: `Start ${taskName}` });
  await expect(start).toBeVisible();
  const startPatch = page.waitForRequest(req =>
    new URL(req.url()).pathname === "/api/v1/tasks/inbox-task" && req.method() === "PATCH");
  await start.click();
  expect((await startPatch).postDataJSON()).toEqual({ status: "in_progress" });
  await expect(start).toHaveCount(0);
  const taskRow = page.locator(".focus-task-list li").filter({ hasText: taskName });
  await expect(taskRow).toContainText("in progress");
  await expect(page.getByText("FOCUS MODE")).toHaveCount(0);
  const donePatch = page.waitForRequest(req =>
    new URL(req.url()).pathname === "/api/v1/tasks/inbox-task" && req.method() === "PATCH");
  await outlook.getByRole("button", { name: `Mark ${taskName} done` }).click();
  expect((await donePatch).postDataJSON()).toEqual({ status: "done" });
  await expect(outlook.getByText(taskName)).toHaveCount(0);
});

test("all-workspace priorities revalidate after an explicit current-workspace completion", async ({ page }) => {
  await setupFocus(page);
  let completed = false;
  let inventoryReads = 0;
  await page.route("**/api/v1/priority/tasks?*", route => {
    inventoryReads += 1;
    return route.fulfill({ json: completed ? [] : [{
      id: "inbox-task", title: "Ask the team about the venue", description: null,
      status: "todo", priority: "normal", due_at: null, project_id: null,
      workspace_id: "personal", created_at: timestamp, updated_at: timestamp,
    }] });
  });
  await page.route("**/api/v1/workspaces", route => route.fulfill({
    json: [{ id: "personal", name: "Personal" }],
  }));
  await page.route("**/api/v1/tasks/inbox-task", route => {
    if (route.request().method() !== "PATCH") return route.fallback();
    completed = true;
    return route.fulfill({ json: {
      id: "inbox-task", title: "Ask the team about the venue", description: null,
      status: "done", priority: "normal", due_at: null, project_id: null,
      created_at: timestamp, updated_at: timestamp,
    } });
  });
  await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  await page.locator(".focus-priority-disclosure > summary").click();
  const outlook = page.getByRole("region", { name: "Priority outlook" });
  await outlook.getByRole("checkbox", { name: "Include tasks from all my workspaces" }).check();
  await expect(outlook.getByText("Ask the team about the venue")).toBeVisible();
  await outlook.getByRole("button", { name: "Mark Ask the team about the venue done" }).click();
  await expect(outlook.getByText("Ask the team about the venue")).toHaveCount(0);
  expect(inventoryReads).toBeGreaterThanOrEqual(2);
});

test("priority outlook requires explicit cross-workspace opt-in and can return to private scope", async ({ page }) => {
  await setupFocus(page);
  await page.route("**/api/v1/priority/tasks?*", route => route.fulfill({ json: [{
    id: "work-deadline", title: "Work-only deadline", description: null, status: "todo",
    priority: "urgent", due_at: "2099-10-13T14:00:00Z", project_id: null,
    workspace_id: "work", created_at: timestamp, updated_at: timestamp,
  }, {
    id: "unscoped-deadline", title: "Legacy unscoped deadline", description: null,
    status: "todo", priority: "high", due_at: "2099-10-13T14:00:00Z",
    project_id: null, workspace_id: null, created_at: timestamp, updated_at: timestamp,
  }] }));
  await page.route("**/api/v1/workspaces", route => route.fulfill({ json: [
    { id: "personal", name: "Personal" }, { id: "work", name: "Work" },
  ] }));
  await page.goto("/"); await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  await page.locator(".focus-priority-disclosure > summary").click();
  const outlook = page.getByRole("region", { name: "Priority outlook" });
  const optIn = outlook.getByRole("checkbox", { name: "Include tasks from all my workspaces" });
  await expect(optIn).not.toBeChecked();
  await expect(outlook.getByText("Work-only deadline")).toHaveCount(0);
  await optIn.check();
  await expect(outlook.getByText("Work-only deadline")).toBeVisible();
  await expect(outlook.locator(".focus-priority-list")).toContainText("Work");
  const otherWorkspace = outlook.locator(".focus-priority-list li").filter({ hasText: "Work-only deadline" });
  await expect(otherWorkspace.getByRole("button")).toHaveCount(0);
  const unscoped = outlook.locator(".focus-priority-list li").filter({ hasText: "Legacy unscoped deadline" });
  await expect(unscoped).toContainText("Unscoped task");
  await expect(unscoped.getByRole("button")).toHaveCount(0);
  await optIn.uncheck();
  await expect(outlook.getByText("Work-only deadline")).toHaveCount(0);
  await expect(outlook.getByText("Ask the team about the venue")).toBeVisible();
  await expect(outlook.getByRole("button", { name: "Schedule Ask the team about the venue" })).toBeVisible();
  await outlook.getByRole("button", { name: "Mark Ask the team about the venue done" }).click();
  await expect(outlook.getByText("Ask the team about the venue")).toHaveCount(0);
});

test("completed Tasks retain WCAG AA contrast at desktop and phone widths", async ({ page }) => {
  await setupFocus(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Tasks" }).click();
  await page.getByRole("navigation", { name: "Task views" }).getByRole("button", { name: /Completed/ }).click();
  await expect(page.locator(".focus-task-done")).toBeVisible();

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const theme of ["light", "dark"]) {
      if (theme === "dark") await page.getByLabel("Toggle light or dark theme").click();
      const report = await new AxeBuilder({ page })
        .include(".focus-task-collection")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const serious = report.violations.filter(violation =>
        violation.impact === "serious" || violation.impact === "critical");
      expect(serious.map(violation => ({
        id: violation.id,
        targets: violation.nodes.map(node => node.target),
      })), `WCAG A/AA accessibility at ${width}px in ${theme} theme`).toEqual([]);
      if (theme === "dark") await page.getByLabel("Toggle light or dark theme").click();
    }
  }
});
