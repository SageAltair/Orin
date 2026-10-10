import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page, seedCalendarTask = false, seedCalendarProject = false) {
  let preferences = { density: "comfortable", theme: "light", locale: "en", visible_capabilities: ["home", "tasks", "calendar", "projects", "activity"], hidden_capabilities: [], pinned_capabilities: ["home", "tasks"], autonomy_mode: "balanced", custom_autonomy: {} };
  const tasks: Record<string, unknown>[] = seedCalendarTask ? [{ id: "calendar-task-1", owner_id: "user-1", project_id: seedCalendarProject ? "project-1" : null, assignee_id: null, title: "Write project brief", description: null, status: "todo", priority: "normal", due_at: null, estimated_minutes: 45, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" }] : [];
  const projects: Record<string, unknown>[] = seedCalendarProject ? [{ id: "project-1", name: "Orin planning", description: null, objective: null, status: "active", created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" }] : [];
  const memories: Record<string, unknown>[] = [];
  const environment: Record<string, unknown>[] = [];
  const focusSessions: Record<string, unknown>[] = [];
  const devices: Record<string, unknown>[] = [];
  const workerJobs: Record<string, Record<string, unknown>[]> = {};
  const approvals: Record<string, unknown>[] = [];
  const focusTasks: Record<string, unknown>[] = seedCalendarTask ? [{ id: "calendar-task-1", title: "Write project brief", status: "todo", focus_state: "today", first_step: null, why: null, energy_level: null, estimated_minutes: 45, project_id: null }] : [];
  const calendarEvents: Record<string, unknown>[] = [];
  const taskBlocks: Record<string, unknown>[] = [];
  const focusPlan = () => ({ day_key: "2026-10-10", energy_level: "medium", tasks: focusTasks.map((task, index) => ({ ...task, is_anchor: index === 0, today_position: index })) });
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-access-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: "2026-10-08T00:00:00Z" } });
    if (pathname.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    if (pathname.endsWith("/auth/email") && route.request().method() === "POST") return route.fulfill({ json: { id: "user-1", email: "updated@example.com", display_name: "Morgan", created_at: "2026-10-08T00:00:00Z" } });
    if (pathname.endsWith("/auth/password") || pathname.includes("/auth/sessions/")) return route.fulfill({ status: 204 });
    if (pathname === "/api/v1/focus/settings") return route.fulfill({ json: { timezone: "Africa/Dar_es_Salaam", theme: "light", reduced_motion: false, hide_timer_numbers: false, sound_enabled: false, haptics_enabled: false } });
    if (pathname === "/api/v1/focus/now") return route.fulfill({ json: { task: focusTasks[0] ? { ...focusTasks[0], is_anchor: true, today_position: 0 } : null, focus_session: null, day_key: "2026-10-10", energy_level: "medium", empty_state: !focusTasks.length } });
    if (pathname === "/api/v1/focus/today") return route.fulfill({ json: focusPlan() });
    if (pathname === "/api/v1/focus/later") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/focus/close/today") return route.fulfill({ json: { day_key: "2026-10-10", done_list: [], drift_triggers: [], drift_summary: null, tomorrow_task_id: null, reflection: null } });
    if (pathname === "/api/v1/focus/capture" && route.request().method() === "POST") { const input = await route.request().postDataJSON() as { title: string }; const item = { id: `focus-task-${focusTasks.length + 1}`, title: input.title, status: "todo", focus_state: "inbox", first_step: null, why: null, energy_level: null, estimated_minutes: 25, project_id: null }; focusTasks.unshift(item); return route.fulfill({ status: 201, json: item }); }
    if (pathname === "/api/v1/focus/today/tasks" && route.request().method() === "PUT") return route.fulfill({ json: focusPlan() });
    if (pathname === "/api/v1/environment/preferences" && route.request().method() === "GET") return route.fulfill({ json: environment });
    if (pathname === "/api/v1/environment/preferences" && route.request().method() === "DELETE") { environment.splice(0); return route.fulfill({ status: 204 }); }
    if (pathname === "/api/v1/environment/preferences" && route.request().method() === "PUT") { const item = await route.request().postDataJSON() as Record<string, unknown>; const existing = environment.findIndex(value => value.item === item.item && value.surface === item.surface); if (existing >= 0) environment.splice(existing, 1); environment.push(item); return route.fulfill({ json: item }); }
    if (pathname === "/api/v1/memories" && route.request().method() === "GET") return route.fulfill({ json: memories });
    if (pathname === "/api/v1/memories" && route.request().method() === "POST") { const item = await route.request().postDataJSON() as Record<string, unknown>; const memory = { ...item, type: item.memory_type, id: `memory-${memories.length + 1}`, archived: false, updated_at: "2026-10-08T00:00:00Z" }; memories.push(memory); return route.fulfill({ status: 201, json: memory }); }
    if (/\/api\/v1\/memories\/[^/]+$/.test(pathname) && route.request().method() === "PATCH") { const id = pathname.split("/").at(-1); const memory = memories.find(item => item.id === id); if (memory) Object.assign(memory, await route.request().postDataJSON()); return route.fulfill({ json: memory }); }
    if (/\/api\/v1\/memories\/[^/]+$/.test(pathname) && route.request().method() === "DELETE") { const index = memories.findIndex(item => item.id === pathname.split("/").at(-1)); if (index >= 0) memories.splice(index, 1); return route.fulfill({ status: 204 }); }
    if (pathname === "/api/v1/focus-sessions" && route.request().method() === "GET") return route.fulfill({ json: focusSessions });
    if (pathname === "/api/v1/focus-sessions" && route.request().method() === "POST") { const item = await route.request().postDataJSON() as Record<string, unknown>; const focus = { ...item, id: "focus-1", status: "active", ends_at: "2026-10-08T02:00:00Z" }; focusSessions.push(focus); return route.fulfill({ status: 201, json: focus }); }
    if (/\/api\/v1\/focus-sessions\/[^/]+$/.test(pathname) && route.request().method() === "PATCH") { const session = focusSessions[0]; if (session) Object.assign(session, { status: (await route.request().postDataJSON() as { action: string }).action === "cancel" ? "cancelled" : "paused" }); return route.fulfill({ json: session }); }
    if (/\/api\/v1\/projects\/[^/]+\/context$/.test(pathname)) return route.fulfill({ json: { project: {}, progress: { completed_tasks: 0, total_tasks: 0, percentage: null }, tasks: [], blockers: [], activity: [], knowledge: memories, next_actions: [], active_focus: null, agents: [], files: [] } });
    if (pathname === "/api/v1/approvals" && route.request().method() === "GET") return route.fulfill({ json: approvals });
    if (pathname.includes("/approvals/") && route.request().method() === "POST") {
      if (pathname.endsWith("/decision")) {
        const decision = await route.request().postDataJSON() as { approved: boolean };
        approvals.forEach(item => { item.status = decision.approved ? "approved" : "rejected"; });
      }
      return route.fulfill({ json: { command_id: "cmd", status: "approved", message: "Decision saved." } });
    }
    if (pathname === "/api/v1/devices" && route.request().method() === "GET") return route.fulfill({ json: devices });
    if (pathname === "/api/v1/devices" && route.request().method() === "POST") {
      const input = await route.request().postDataJSON() as { name: string; platform: string; version: string };
      const device = { ...input, id: `device-${devices.length + 1}`, credential: "one-time-test-worker-token-that-is-long", status: "pending", last_seen_at: null, created_at: "2026-10-08T00:00:00Z" };
      devices.push({ ...device, credential: undefined }); workerJobs[device.id] = [];
      return route.fulfill({ status: 201, json: device });
    }
    if (/\/api\/v1\/devices\/[^/]+$/.test(pathname) && route.request().method() === "DELETE") {
      const device = devices.find(item => item.id === pathname.split("/").at(-1)); if (device) device.status = "revoked";
      return route.fulfill({ status: 204 });
    }
    if (pathname.endsWith("/jobs") && route.request().method() === "GET") {
      const deviceId = pathname.split("/").at(-2) ?? "";
      return route.fulfill({ json: workerJobs[deviceId] ?? [] });
    }
    if (pathname.endsWith("/jobs") && route.request().method() === "POST") {
      const deviceId = pathname.split("/").at(-2) ?? "";
      const job = { id: "job-1", action: "get_system_info", status: "pending_approval", progress: null, result: null, failure: null, created_at: "2026-10-08T00:00:00Z", finished_at: null };
      workerJobs[deviceId]?.push(job);
      approvals.push({ id: "approval-1", status: "pending", action: "worker_get_system_info", parameters: {}, risk_level: "low", permission: "system.info.read", reversible: true, reason: "Worker actions always require explicit approval.", created_at: "2026-10-08T00:00:00Z", expires_at: null, decided_at: null });
      return route.fulfill({ status: 202, json: { id: job.id, approval_id: "approval-1", status: job.status } });
    }
    if (pathname.endsWith("/users/me/preferences")) {
      if (route.request().method() === "PUT") preferences = await route.request().postDataJSON() as typeof preferences;
      return route.fulfill({ json: preferences });
    }
    if (pathname.endsWith("/commands") && route.request().method() === "GET") return route.fulfill({ json: [] });
    if (pathname.endsWith("/commands") && route.request().method() === "POST") {
      const { text } = await route.request().postDataJSON() as { text: string };
      if (text.toLowerCase() === "hey") return route.fulfill({ json: { command_id: "cmd-1", status: "completed", intent: "RESPOND", result: { response: "Hey! What can I help you with?" }, message: "Hey! What can I help you with?" } });
      if (/create a task/i.test(text)) {
        const taskTitle = text.replace(/create a task(?: called)?/i, "").trim();
        const task = { id: `task-${tasks.length + 1}`, owner_id: "user-1", project_id: null, assignee_id: null, title: taskTitle, description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
        tasks.push(task);
        return route.fulfill({ json: { command_id: "cmd-2", status: "completed", intent: "CREATE_TASK", result: { id: task.id, title: task.title, status: task.status }, message: "Command completed." } });
      }
      return route.fulfill({ json: { command_id: "cmd-3", status: "unsupported", intent: "UNSUPPORTED", result: null, message: "This request is not supported." } });
    }
    if (pathname.endsWith("/tasks") && route.request().method() === "GET") return route.fulfill({ json: tasks });
    if (pathname.endsWith("/tasks") && route.request().method() === "POST") {
      const data = await route.request().postDataJSON() as { title: string };
      const task = { id: `task-${tasks.length + 1}`, owner_id: "user-1", project_id: null, assignee_id: null, title: data.title, description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
      tasks.push(task);
      return route.fulfill({ status: 201, json: task });
    }
    if (/\/api\/v1\/tasks\/[^/]+$/.test(pathname) && route.request().method() === "PATCH") { const task = tasks.find(item => item.id === pathname.split("/").at(-1)); if (!task) return route.fulfill({ status: 404, json: { detail: "Task not found" } }); Object.assign(task, await route.request().postDataJSON()); if (["done", "cancelled"].includes(String(task.status))) { const index = taskBlocks.findIndex(block => block.task_id === task.id); if (index >= 0) taskBlocks.splice(index, 1); } return route.fulfill({ json: task }); }
    if (pathname === "/api/v1/projects" && route.request().method() === "GET") return route.fulfill({ json: projects });
    if (pathname === "/api/v1/projects" && route.request().method() === "POST") { const item = await route.request().postDataJSON() as Record<string, unknown>; const project = { ...item, id: `project-${projects.length + 1}`, status: "active", created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" }; projects.push(project); return route.fulfill({ status: 201, json: project }); }
    if (/\/api\/v1\/projects\/[^/]+$/.test(pathname) && route.request().method() === "PATCH") { const project = projects.find(item => item.id === pathname.split("/").at(-1)); if (project) Object.assign(project, await route.request().postDataJSON()); return route.fulfill({ json: project }); }
    if (pathname === "/api/v1/calendar/events" && route.request().method() === "GET") return route.fulfill({ json: calendarEvents });
    if (pathname === "/api/v1/calendar/events" && route.request().method() === "POST") { const item = await route.request().postDataJSON() as Record<string, unknown>; const saved = { ...item, id: `event-${calendarEvents.length + 1}`, user_id: "user-1", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z" }; calendarEvents.push(saved); return route.fulfill({ status: 201, json: saved }); }
    if (/\/api\/v1\/calendar\/events\/[^/]+$/.test(pathname) && route.request().method() === "PATCH") { const item = calendarEvents.find(event => event.id === pathname.split("/").at(-1)); if (item) Object.assign(item, await route.request().postDataJSON()); return route.fulfill({ json: item }); }
    if (/\/api\/v1\/calendar\/events\/[^/]+$/.test(pathname) && route.request().method() === "DELETE") { const index = calendarEvents.findIndex(event => event.id === pathname.split("/").at(-1)); if (index >= 0) calendarEvents.splice(index, 1); return route.fulfill({ status: 204 }); }
    if (pathname === "/api/v1/calendar/schedule" && route.request().method() === "GET") return route.fulfill({ json: taskBlocks });
    if (/\/api\/v1\/calendar\/tasks\/[^/]+\/schedule$/.test(pathname) && route.request().method() === "PUT") { const taskId = pathname.split("/").at(-2); const task = tasks.find(item => item.id === taskId); if (!task) return route.fulfill({ status: 404, json: { detail: "Task not found" } }); const body = await route.request().postDataJSON() as Record<string, unknown>; let block = taskBlocks.find(item => item.task_id === taskId); if (!block) { block = { id: `block-${taskBlocks.length + 1}`, task_id: taskId, title: task.title, description: task.description, status: task.status, project_id: task.project_id, project_name: null }; taskBlocks.push(block); } Object.assign(block, body, { start_at: body.start_at, end_at: body.end_at, estimated_minutes: body.estimated_minutes, timezone: body.timezone }); return route.fulfill({ json: block }); }
    if (/\/api\/v1\/calendar\/tasks\/[^/]+\/schedule$/.test(pathname) && route.request().method() === "DELETE") { const taskId = pathname.split("/").at(-2); const index = taskBlocks.findIndex(item => item.task_id === taskId); if (index >= 0) taskBlocks.splice(index, 1); return route.fulfill({ status: 204 }); }
    if (pathname.endsWith("/activity")) return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

test("Calendar supports Month and Agenda plus event create, edit, and delete on mobile", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Calendar" }).click();
  await expect(page.getByRole("heading", { name: "Calendar" })).toBeVisible();
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  await expect(page.getByText("No events").first()).toBeVisible();
  await page.getByRole("button", { name: "New event" }).click();
  await page.getByLabel("Title").fill("Planning workshop");
  await page.getByLabel("Description").fill("Review the roadmap and agree next steps.");
  await page.getByLabel("All-day").check();
  await page.getByRole("button", { name: "Save event" }).click();
  const eventRow = page.getByRole("button", { name: /Planning workshop/ }).first();
  await expect(eventRow).toBeVisible();
  await eventRow.click();
  await page.getByLabel("Title").fill("Planning workshop updated");
  await page.getByRole("button", { name: "Save event" }).click();
  await expect(page.getByRole("button", { name: /Planning workshop updated/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Month", exact: true }).click();
  const monthEvent = page.getByRole("button", { name: "Edit Planning workshop updated" });
  await expect(monthEvent).toBeVisible();
  await expect(monthEvent.locator(".calendar-event-chip-label")).toHaveText("Planning workshop updated");
  expect(await monthEvent.evaluate(element => getComputedStyle(element).fontSize)).not.toBe("0px");
  await monthEvent.hover();
  const eventTooltip = page.getByRole("tooltip");
  await expect(eventTooltip).toBeVisible();
  await expect(eventTooltip).toContainText("All day");
  await expect(eventTooltip).toContainText("Review the roadmap and agree next steps.");
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: /Planning workshop updated/ }).first().click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Event deleted.")).toBeVisible();
});

test("Week and Day schedule a task, start focus, and keep task completion separate", async ({ page }) => {
  await mockApi(page, true);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Calendar" }).click();
  await page.getByRole("button", { name: "Week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Week time schedule" })).toBeVisible();
  await page.getByRole("button", { name: "Schedule task" }).first().click();
  await page.getByRole("dialog").getByRole("combobox").selectOption("calendar-task-1");
  await page.getByRole("button", { name: "Save schedule" }).click();
  const scheduledTask = page.locator(".calendar-time-item-main").filter({ hasText: "Write project brief" }).first();
  await scheduledTask.scrollIntoViewIfNeeded();
  await expect(scheduledTask).toBeVisible();
  await page.getByRole("button", { name: "Focus on Write project brief" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Focus session started" })).toBeVisible();
  await page.getByRole("button", { name: "Day", exact: true }).click();
  await page.getByLabel("More actions for Write project brief").scrollIntoViewIfNeeded();
  await page.getByLabel("More actions for Write project brief").click();
  await page.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task completed" })).toBeVisible();
});

test("day and week time slices place items in clock time and create from a selected slot", async ({ page }) => {
  await mockApi(page, true);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Calendar" }).click();
  await page.getByRole("button", { name: "Week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Week time schedule" })).toBeVisible();
  await expect(page.locator(".calendar-time-heading > button:first-child")).toHaveCount(7);
  const hourSpacing = page.getByLabel("Hour spacing");
  await expect(hourSpacing).toHaveValue("fit");
  const timeline = page.locator(".calendar-time-body");
  expect(await timeline.evaluate(element => element.getBoundingClientRect().height)).toBeLessThan(600);
  await hourSpacing.selectOption("roomy");
  expect(await timeline.evaluate(element => element.getBoundingClientRect().height)).toBe(960);
  await hourSpacing.selectOption("fit");
  await page.getByRole("button", { name: "Day", exact: true }).click();
  await expect(page.getByRole("region", { name: /Time schedule for/ })).toBeVisible();
  await page.getByRole("button", { name: /Create event on .* at 14:00/ }).click({ position: { x: 4, y: 4 } });
  await expect(page.getByLabel("Starts")).toHaveValue(/T14:00$/);
  await page.keyboard.press("Escape");
});

test("an existing task can be scheduled directly from the Today task interface", async ({ page }) => {
  await mockApi(page, true);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Tasks" }).click();
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Today" }).click();
  await page.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Schedule a task" })).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("combobox")).toHaveValue("calendar-task-1");
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task scheduled." })).toBeVisible();
});

test("calendar search and filters find project tasks and open the original task", async ({ page }) => {
  await mockApi(page, true, true);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Calendar" }).click();
  await page.getByRole("button", { name: "Week", exact: true }).click();
  await page.getByRole("button", { name: "Schedule task" }).first().click();
  await page.getByRole("dialog").getByRole("combobox").selectOption("calendar-task-1");
  await page.getByRole("button", { name: "Save schedule" }).click();
  await page.getByText("Search and filters").click();
  await page.getByRole("searchbox", { name: "Search calendar" }).fill("project brief");
  await page.getByLabel("Filter calendar items").selectOption("tasks");
  await page.getByLabel("Filter by project").selectOption("project-1");
  const task = page.getByRole("button", { name: "Write project brief" }).first();
  await task.scrollIntoViewIfNeeded();
  await expect(task).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  const taskAfterClear = page.getByRole("button", { name: "Write project brief" }).first();
  await taskAfterClear.scrollIntoViewIfNeeded();
  await expect(taskAfterClear).toBeVisible();
  await taskAfterClear.click({ position: { x: 4, y: 5 } });
  await expect(page.getByRole("navigation").getByRole("button", { name: "Tasks" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Write project brief").first()).toBeVisible();
});

test("calendar dialogs support Escape and focus return at narrow width with dark and reduced-motion settings", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const preferencesLoaded = page.waitForResponse(response => response.url().includes("/users/me/preferences") && response.request().method() === "GET");
  await signIn(page);
  await preferencesLoaded;
  await page.getByRole("button", { name: "Toggle light or dark theme" }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Calendar" }).click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  const workspace = page.locator(".calendar-workspace");
  expect(await workspace.evaluate(element => element.scrollWidth)).toBeLessThanOrEqual(await workspace.evaluate(element => element.clientWidth));
  const newEvent = page.getByRole("button", { name: "New event" });
  await newEvent.click();
  await expect(page.getByRole("dialog", { name: "New event" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(newEvent).toBeFocused();
  expect(await workspace.evaluate(element => Number.parseFloat(getComputedStyle(element.querySelector("button")!).transitionDuration))).toBeLessThanOrEqual(0.00001);
});

async function signIn(page: Page) {
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password").fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
}

test("home shows the personal dashboard and offers Ask Orin", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to Orin" })).toBeVisible();
  await signIn(page);
  await expect(page.getByRole("heading", { name: "What needs your attention, Morgan?" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Tasks" })).toBeVisible();
  await expect(page.getByText("Recent requests")).toHaveCount(0);
  await expect(page.getByRole("banner").getByRole("button", { name: "Ask Orin" })).toBeVisible();
  await page.getByRole("button", { name: "Ask Orin" }).first().click();
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("autocomplete", "off");
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("placeholder", "Ask Orin what you need");
});

test("workspace preferences control visible capabilities", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Show Projects" }).check();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
});

test("settings expose profile security, autonomy, approvals, and worker enrollment", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Email and sessions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose how Orin handles actions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Requests and history" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Connected workers" })).toBeVisible();
  await page.getByLabel("Device name").fill("Sage-Laptop");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByLabel("Worker token")).toHaveValue("one-time-test-worker-token-that-is-long");
  await page.getByRole("button", { name: "Request approval" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Request sent for approval" })).toBeVisible();
  await expect(page.getByText("get system info")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/approved · low risk/)).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("revoked", { exact: true })).toBeVisible();
});

test("GitHub settings show the connected account and accessible repositories", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/integrations/github**", route => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/integrations/github") return route.fulfill({ json: {
      connected: true, provider: "github", account_login: "octo-test", granted_scopes: [],
      capabilities: ["repositories.read", "issues.read", "pull_requests.read"], last_successful_sync_at: null,
    } });
    if (pathname.endsWith("/repositories")) return route.fulfill({ json: [{
      id: "repo-1", full_name: "octo-test/orin-demo", private: true,
      html_url: "https://github.com/octo-test/orin-demo", default_branch: "main", selected_project_ids: [],
    }] });
    return route.continue();
  });
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "GitHub" })).toBeVisible();
  await expect(page.getByText("Connected as").getByText("octo-test")).toBeVisible();
  await expect(page.getByText("octo-test/orin-demo")).toBeVisible();
  await expect(page.getByText("Private")).toBeVisible();
});

test("Ask Orin works alongside the focus task workspace and capture", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Ask Orin" }).first().click();
  const ask = page.getByRole("textbox", { name: "Ask Orin" });
  await ask.fill("hey");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("hey", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Hey! What can I help you with?", { exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "Close Ask Orin" }).last().click();
  await page.getByRole("button", { name: "Ask Orin" }).first().click();
  await expect(page.getByText("Hey! What can I help you with?", { exact: true })).toHaveCount(1);

  await ask.fill("Create a task called Call John");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.getByRole("button", { name: "Close Ask Orin" }).last().click();
  await page.getByRole("navigation").getByRole("button", { name: "Tasks" }).click();
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask Orin" }).first()).toBeVisible();
  await page.getByRole("navigation", { name: "Focus navigation" }).getByRole("button", { name: "Capture" }).click();
  await page.getByRole("textbox", { name: "What would you like to remember?" }).fill("Manual task");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Manual task" })).toBeVisible();
});

test("Ask Orin guides first use with clickable action examples", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Ask Orin" }).first().click();
  const input = page.getByRole("textbox", { name: "Ask Orin" });
  await expect(page.getByRole("group", { name: "Try an Orin action" })).toBeVisible();
  await page.getByRole("button", { name: "Set my energy" }).click();
  await expect(input).toHaveValue("Set my energy to low");
  await page.getByText("More things Orin can do").click();
  await page.getByRole("button", { name: "Release a task" }).click();
  await expect(input).toHaveValue("Release [task name]");
  await expect(page.getByText("Releasing a task will ask you to approve the change.")).toBeVisible();
});

test("project intelligence stores knowledge and starts a persistent focus session", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await page.getByRole("checkbox", { name: "Show Projects" }).check();
  await page.getByRole("navigation").getByRole("button", { name: "Projects" }).click();
  await page.getByRole("textbox", { name: "Project name" }).fill("The Small Voice");
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByRole("heading", { name: "The Small Voice" })).toBeVisible();
  await page.getByLabel("Objective", { exact: true }).fill("Help people begin and grow");
  await page.getByRole("button", { name: "Save project" }).click();
  await page.getByLabel("Focus objective").fill("Review presentation cards");
  await page.getByLabel("Duration").selectOption("120");
  await page.getByRole("button", { name: "Start focus" }).click();
  await expect(page.getByRole("region", { name: "Active focus session" })).toContainText("Review presentation cards");
  await page.getByLabel("Title", { exact: true }).last().fill("Database decision");
  await page.getByLabel("Details").fill("Use PostgreSQL for consistent project data.");
  await page.getByRole("button", { name: "Save memory" }).click();
  await expect(page.getByText("Database decision · decision")).toBeVisible();
});

test("adaptive navigation can minimize, hide, recover, and reset tools", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  const projects = page.getByRole("combobox", { name: "projects", exact: true });
  await projects.selectOption("minimized");
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toHaveClass(/minimized/);
  await projects.selectOption("hidden");
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toHaveCount(0);
  await projects.selectOption("prioritized");
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
  await page.getByRole("button", { name: "Reset layout" }).click();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
});

test("activity links open related workspace records and exposes lifecycle event filters", async ({ page }) => {
  await mockApi(page);
  const project = { id: "project-1", owner_id: "user-1", name: "Roadmap project", description: null, objective: null, status: "active", created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
  const task = { id: "task-1", owner_id: "user-1", project_id: project.id, assignee_id: null, title: "Review roadmap", description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
  const events = [
    { id: "activity-task", user_id: "user-1", project_id: project.id, task_id: task.id, command_id: null, execution_id: null, approval_id: null, worker_job_id: null, activity_type: "task_created", summary: "Created task: Review roadmap", created_at: "2026-10-08T00:00:00Z", result_status: "succeeded", severity: "info", source: "api", correlation_id: null, metadata: {} },
    { id: "activity-plan", user_id: "user-1", project_id: null, task_id: null, command_id: "command-1", execution_id: null, approval_id: null, worker_job_id: null, activity_type: "plan_created", summary: "Validated plan created", created_at: "2026-10-08T00:00:00Z", result_status: "succeeded", severity: "info", source: "planner", correlation_id: "command-1", metadata: {} },
    { id: "activity-progress", user_id: "user-1", project_id: null, task_id: null, command_id: "command-1", execution_id: "execution-1", approval_id: null, worker_job_id: "job-1", activity_type: "worker_job_progress", summary: "Worker progress updated", created_at: "2026-10-08T00:00:00Z", result_status: "running", severity: "info", source: "worker", correlation_id: "command-1", metadata: {} },
  ];
  await page.route("**/api/v1/projects", route => route.fulfill({ json: [project] }));
  await page.route("**/api/v1/tasks", route => route.fulfill({ json: [task] }));
  await page.route("**/api/v1/activity**", route => {
    const query = new URL(route.request().url()).searchParams;
    const filtered = events.filter(item => (!query.has("event_type") || item.activity_type === query.get("event_type"))
      && (!query.has("command_id") || item.command_id === query.get("command_id"))
      && (!query.has("execution_id") || item.execution_id === query.get("execution_id")));
    return route.fulfill({ json: filtered });
  });
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await page.getByRole("checkbox", { name: "Show Projects" }).check();
  await page.getByRole("checkbox", { name: "Show Activity" }).check();
  await page.getByRole("navigation").getByRole("button", { name: "Activity" }).click();
  await expect(page.getByRole("option", { name: "plan created" })).toBeAttached();
  await expect(page.getByRole("option", { name: "worker job progress" })).toBeAttached();
  await page.getByRole("button", { name: "Project project-" }).click();
  await expect(page.getByRole("combobox", { name: "Select project" })).toHaveValue(project.id);
  await page.getByRole("navigation").getByRole("button", { name: "Activity" }).click();
  await page.getByRole("button", { name: "Task task-1" }).click();
  await expect(page.getByRole("navigation", { name: "Focus navigation" })).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: "Activity" }).click();
  await page.getByRole("button", { name: "Execution executio" }).click();
  await expect(page.getByRole("button", { name: "Clear execution filter" })).toBeVisible();
  await expect(page.getByText("Worker progress updated")).toBeVisible();
  await expect(page.getByText("Validated plan created")).toHaveCount(0);
});

test("compact work toolbar searches, restores, renames, and starts sessions", async ({ page }) => {
  await mockApi(page);
  const updated = new Date().toISOString();
  const project = { id: "project-history", name: "History project", description: null, objective: null, status: "active", created_at: updated, updated_at: updated };
  const conversations = [
    { id: "conversation-history", title: "Release planning", task_id: "task-history", project_id: project.id, objective: "Plan the release", summary: "Decided the rollout order", pending_question: null, updated_at: updated },
  ];
  await page.route("**/api/v1/projects", route => route.fulfill({ json: [project] }));
  await page.route("**/api/v1/conversations**", async route => {
    if (route.request().method() === "PATCH") {
      const title = (await route.request().postDataJSON() as { title: string }).title;
      conversations[0].title = title;
      return route.fulfill({ json: conversations[0] });
    }
    return route.fulfill({ json: conversations });
  });
  await page.route("**/api/v1/search**", route => route.fulfill({ json: [{ result_id: "command-history", kind: "conversation", command_id: "command-history", task_id: null, project_id: project.id, conversation_id: "conversation-history", text: "release timeline", excerpt: "Plan the release rollout", created_at: updated, title: "Release planning" }] }));
  await page.route("**/api/v1/commands?**", route => route.fulfill({ json: [{ command_id: "command-history", conversation_id: "conversation-history", status: "completed", intent: "RESPOND", result: { response: "The rollout starts with a pilot." }, message: "The rollout starts with a pilot.", text: "release timeline", created_at: updated }] }));
  await page.route("**/api/v1/attachments**", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Ask Orin" }).last().click();
  await page.getByRole("button", { name: "Conversation history" }).click();
  await page.locator(".history-entry").filter({ hasText: "Release planning" }).click();
  await expect(page.getByText("The rollout starts with a pilot.")).toBeVisible();
  await page.getByLabel("Work session title").fill("Release plan revised");
  await page.getByLabel("Work session title").press("Enter");
  await expect.poll(() => conversations[0].title).toBe("Release plan revised");
  await page.locator(".chat-more-actions summary").click();
  await page.getByLabel("Associate with project").selectOption(project.id);
  await expect(page.getByLabel("Associate with project")).toHaveValue(project.id);
  await page.getByRole("button", { name: "Search previous work" }).click();
  await page.getByRole("textbox", { name: "Search previous work" }).fill("release");
  await page.getByRole("button", { name: /conversation: Release planning/ }).click();
  await expect(page.getByText("The rollout starts with a pilot.")).toBeVisible();
  await page.getByRole("button", { name: "New work session" }).click();
  await expect(page.getByLabel("Work session title")).toHaveValue("");
});

test("Ask Orin composer grows for multiline text and sends with Enter", async ({ page }) => {
  await mockApi(page);
  let submittedText: string | undefined;
  let uploadedFilename: string | undefined;
  await page.route("**/api/v1/commands", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    submittedText = (await route.request().postDataJSON() as { text: string }).text;
    return route.fulfill({ json: { command_id: "composer-command", conversation_id: "composer-session", status: "completed", intent: "RESPOND", result: { response: "Message received." }, message: "Message received." } });
  });
  await page.route("**/api/v1/attachments**", async route => {
    if (route.request().method() === "POST") {
      uploadedFilename = "brief.txt";
      return route.fulfill({ status: 201, json: [{ id: "attachment-1", conversation_id: null, task_id: null, filename: uploadedFilename, media_type: "text/plain", size_bytes: 12, created_at: new Date().toISOString() }] });
    }
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/conversations", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Ask Orin" }).last().click();
  const composer = page.getByRole("textbox", { name: "Ask Orin" });
  const send = page.getByRole("button", { name: "Send message" });
  await expect(send).toBeDisabled();
  await expect(page.locator(".attach-file-button")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const composerBounds = await page.locator(".chat-composer").evaluate(element => {
    const box = element.getBoundingClientRect();
    return { width: box.width, scrollWidth: element.scrollWidth };
  });
  expect(composerBounds.scrollWidth).toBeLessThanOrEqual(composerBounds.width);

  const paragraphs = Array.from({ length: 18 }, (_, index) => `Paragraph ${index + 1}: ${"meaningful words ".repeat(12)}`).join("\n");
  await composer.fill(paragraphs);
  await expect(composer).toHaveJSProperty("value", paragraphs);
  await expect(composer).toHaveCSS("overflow-y", "auto");
  const dimensions = await composer.evaluate(element => ({ height: element.clientHeight, scrollHeight: element.scrollHeight }));
  expect(dimensions.height).toBeLessThanOrEqual(160);
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.height);

  await composer.press("Control+End");
  await composer.press("Shift+Enter");
  await composer.type("Final manually inserted line");
  const completeMessage = `${paragraphs}\nFinal manually inserted line`;
  await expect(composer).toHaveJSProperty("value", completeMessage);
  expect(submittedText).toBeUndefined();

  await page.locator("#attachment-input").setInputFiles({ name: "brief.txt", mimeType: "text/plain", buffer: Buffer.from("short brief") });
  await expect(page.locator(".pending-attachment span")).toContainText("brief.txt");
  await composer.press("Enter");
  await expect.poll(() => submittedText).toBe(completeMessage);
  expect(uploadedFilename).toBe("brief.txt");
  await expect(composer).toHaveValue("");
  await expect(page.getByText("Message received.")).toBeVisible();
});

test("home dashboard shows persisted tasks, projects, and work sessions", async ({ page }) => {
  await mockApi(page);
  const updated = new Date().toISOString();
  await page.route("**/api/v1/tasks", route => route.fulfill({ json: [
    { id: "task-next", title: "Prepare the launch outline", status: "todo", priority: "high", due_at: null, project_id: "project-active" },
    { id: "task-done", title: "Already finished", status: "done", priority: "urgent", due_at: null, project_id: "project-active" },
  ] }));
  await page.route("**/api/v1/projects", route => route.fulfill({ json: [
    { id: "project-active", name: "Orin launch", description: "Product work", objective: "Ship a reliable first release", status: "active", created_at: updated, updated_at: updated },
  ] }));
  await page.route("**/api/v1/conversations", route => route.fulfill({ json: [
    { id: "session-1", title: "Release planning", task_id: null, project_id: "project-active", objective: "Plan the release", summary: null, pending_question: null, updated_at: updated },
  ] }));
  await page.route("**/api/v1/commands?**", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await signIn(page);
  await expect(page.getByRole("heading", { name: "What needs your attention, Morgan?" })).toBeVisible();
  await expect(page.getByText("Prepare the launch outline")).toBeVisible();
  await expect(page.getByText("Already finished")).toHaveCount(0);
  await expect(page.getByText("Orin launch")).toBeVisible();
  await expect(page.getByText("Release planning")).toBeVisible();
});
