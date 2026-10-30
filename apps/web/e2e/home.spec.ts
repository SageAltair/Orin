import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

async function settingsSection(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name, exact: true }).click();
}

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
  const knowledgeDocuments: Record<string, unknown>[] = [{ id: "note-1", user_id: "user-1", project_id: null, title: "Meeting notes", content: "A clear first paragraph.", document_type: "quick_note", tags: [], status: "inbox", archived: false, exclude_from_ai: false, review_at: null, version: 1, extraction_status: "not_requested", extracted_data: null, extraction_error: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" }];
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
    if (/\/api\/v1\/projects\/[^/]+\/context$/.test(pathname)) {
      const projectId = pathname.split("/").at(-2);
      const projectTasks = tasks.filter(task => task.project_id === projectId);
      const completed = projectTasks.filter(task => task.status === "done").length;
      const openTasks = projectTasks.filter(task => !["done", "cancelled"].includes(String(task.status)));
      return route.fulfill({ json: { project: projects.find(project => project.id === projectId) ?? {}, progress: { completed_tasks: completed, total_tasks: projectTasks.length, percentage: projectTasks.length ? Math.round(completed * 100 / projectTasks.length) : null }, tasks: projectTasks, blockers: projectTasks.filter(task => task.status === "blocked"), activity: [], knowledge: memories, next_actions: openTasks.slice(0, 3), active_focus: null, agents: [], files: [] } });
    }
    if (/\/api\/v1\/projects\/[^/]+\/milestones$/.test(pathname) && route.request().method() === "GET") return route.fulfill({ json: [] });
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
    if (pathname.endsWith("/tasks") && route.request().method() === "GET") { const projectId = new URL(route.request().url()).searchParams.get("project_id"); return route.fulfill({ json: projectId ? tasks.filter(task => task.project_id === projectId) : tasks }); }
    if (pathname.endsWith("/tasks") && route.request().method() === "POST") {
      const data = await route.request().postDataJSON() as { title: string; project_id?: string | null };
      const task = { id: `task-${tasks.length + 1}`, owner_id: "user-1", project_id: data.project_id ?? null, assignee_id: null, title: data.title, description: null, status: "todo", priority: "normal", due_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" };
      tasks.push(task);
      return route.fulfill({ status: 201, json: task });
    }
    if (/\/api\/v1\/tasks\/[^/]+\/dependencies$/.test(pathname) && route.request().method() === "GET") return route.fulfill({ json: [] });
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
    if (pathname === "/api/v1/knowledge/review-live" && route.request().method() === "POST") {
      const draft = await route.request().postDataJSON() as { content: string };
      return route.fulfill({ json: { suggestions: [{ id: `review-1-${draft.content.length}`, category: "clarity", severity: "suggestion", title: "Tighten the opening", message: "A direct opening is easier to follow.", original: "In order to", replacement: "To" }, { id: `review-2-${draft.content.length}`, category: "tone", severity: "suggestion", title: "Use a warmer audience word", message: "Audience is more specific in this passage.", original: "reader", replacement: "audience" }], reviewed_at: "2026-10-25T10:00:00Z", mode: "ai", model: "test-editor", source_fingerprint: String(draft.content.length), limitations: [] } });
    }
    if (pathname === "/api/v1/knowledge/documents" && route.request().method() === "GET") return route.fulfill({ json: knowledgeDocuments });
    if (pathname === "/api/v1/knowledge/documents" && route.request().method() === "POST") {
      const input = await route.request().postDataJSON() as Record<string, unknown>;
      const document = { id: `note-${knowledgeDocuments.length + 1}`, user_id: "user-1", project_id: input.project_id ?? null, title: input.title ?? "Untitled", content: input.content ?? "", document_type: input.document_type ?? "quick_note", tags: input.tags ?? [], status: input.status ?? "inbox", archived: false, exclude_from_ai: input.exclude_from_ai ?? false, review_at: input.review_at ?? null, version: 1, extraction_status: "not_requested", extracted_data: null, extraction_error: null, created_at: "2026-10-25T10:00:00Z", updated_at: "2026-10-25T10:00:00Z" };
      knowledgeDocuments.push(document);
      return route.fulfill({ status: 201, json: document });
    }
    if (pathname === "/api/v1/knowledge/insights" || pathname === "/api/v1/knowledge/reviews") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/knowledge/documents/note-1" && route.request().method() === "PATCH") { Object.assign(knowledgeDocuments[0], await route.request().postDataJSON(), { version: Number(knowledgeDocuments[0].version) + 1, updated_at: "2026-10-25T10:00:00Z" }); return route.fulfill({ json: knowledgeDocuments[0] }); }
    if (/\/api\/v1\/knowledge\/documents\/[^/]+$/.test(pathname) && route.request().method() === "DELETE") { const index = knowledgeDocuments.findIndex(item => item.id === pathname.split("/").at(-1)); if (index >= 0) knowledgeDocuments.splice(index, 1); return route.fulfill({ status: 204 }); }
    if (pathname === "/api/v1/knowledge/documents/note-1") return route.fulfill({ json: knowledgeDocuments[0] });
    if (pathname === "/api/v1/knowledge/documents/note-1/versions") return route.fulfill({ json: [] });
    if (pathname === "/api/v1/knowledge/documents/note-1/links") return route.fulfill({ json: { links: [], backlinks: [] } });
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
  await expect(page.getByRole("button", { name: "Agenda", exact: true })).toBeVisible();
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
  await page.locator('[data-orin-control="nav-tasks"]').click();
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
  await expect(page.locator('[data-orin-control="nav-tasks"]')).toHaveAttribute("aria-current", "page");
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
  await page.getByLabel("Password", { exact: true }).fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
}

test("home shows the personal dashboard and offers Ask Orin", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to Orin" })).toBeVisible();
  await signIn(page);
  await expect(page.getByRole("heading", { name: /What would you like to.*work on today/ })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Home" })).toBeVisible();
  await expect(page.locator('[data-orin-control="nav-tasks"]')).toBeVisible();
  await expect(page.getByText("Recent requests")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ask Orin", exact: true })).toBeVisible();
  await expect(page.getByRole("banner").getByRole("button", { name: "Ask Orin", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Ask Orin" }).first().click();
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("autocomplete", "off");
  await expect(page.getByRole("textbox", { name: "Ask Orin" })).toHaveAttribute("placeholder", "Ask Orin what you need");
});

test("signing out reloads the workspace before another account can authenticate", async ({ page }) => {
  await mockApi(page, true, true);
  await page.goto("/");
  await signIn(page);
  await expect(page.getByText("Write project brief").first()).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page.getByRole("heading", { name: "Welcome to Orin" })).toBeVisible();
  await expect(page.getByText("Write project brief")).toHaveCount(0);
});

test("workspace preferences control visible capabilities", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await settingsSection(page, "Workspace");
  await page.getByRole("checkbox", { name: "Show Projects" }).check();
  await expect(page.getByRole("navigation").getByRole("button", { name: "Projects" })).toBeVisible();
});

test("settings expose profile security, autonomy, approvals, and worker enrollment", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await settingsSection(page, "Account");
  await expect(page.getByRole("heading", { name: "Email and sessions" })).toBeVisible();
  await settingsSection(page, "Intelligence");
  await expect(page.getByRole("heading", { name: "Choose how Orin handles actions" })).toBeVisible();
  await settingsSection(page, "Approvals");
  await expect(page.getByRole("heading", { name: "Requests and history" })).toBeVisible();
  await settingsSection(page, "Devices");
  await expect(page.getByRole("heading", { name: "Connected workers" })).toBeVisible();
  await page.getByLabel("Device name").fill("Sage-Laptop");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByLabel("Worker token")).toHaveValue("one-time-test-worker-token-that-is-long");
  await page.getByRole("button", { name: "Request approval" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Request sent for approval" })).toBeVisible();
  await settingsSection(page, "Approvals");
  await expect(page.getByText("worker_get_system_info", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/approved · low risk/)).toBeVisible();
  await settingsSection(page, "Devices");
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
  await settingsSection(page, "Integrations");
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
  await page.locator('[data-orin-control="nav-tasks"]').click();
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
  await settingsSection(page, "Workspace");
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
  await expect(page.getByText("Database decision · project")).toBeVisible();
});

test("adaptive navigation can minimize, hide, recover, and reset tools", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences" }).click();
  await settingsSection(page, "Workspace");
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
  await page.route("**/api/v1/projects*", route => route.fulfill({ json: [project] }));
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
  await settingsSection(page, "Workspace");
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
  await page.route("**/api/v1/projects*", route => route.fulfill({ json: [project] }));
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
  await page.route("**/api/v1/tasks**", route => route.fulfill({ json: [
    { id: "task-next", title: "Prepare the launch outline", status: "todo", priority: "high", due_at: null, project_id: "project-active" },
    { id: "task-done", title: "Already finished", status: "done", priority: "urgent", due_at: null, project_id: "project-active" },
  ] }));
  await page.route("**/api/v1/projects*", route => route.fulfill({ json: [
    { id: "project-active", name: "Orin launch", description: "Product work", objective: "Ship a reliable first release", status: "active", created_at: updated, updated_at: updated },
  ] }));
  await page.route("**/api/v1/conversations", route => route.fulfill({ json: [
    { id: "session-1", title: "Release planning", task_id: null, project_id: "project-active", objective: "Plan the release", summary: null, pending_question: null, updated_at: updated },
  ] }));
  await page.route("**/api/v1/commands?**", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await signIn(page);
  await expect(page.getByRole("heading", { name: /What would you like to.*work on today/ })).toBeVisible();
  await expect(page.getByText("Prepare the launch outline")).toBeVisible();
  await expect(page.getByText("Already finished")).toHaveCount(0);
  await expect(page.getByText("Orin launch").first()).toBeVisible();
  await expect(page.getByText("Release planning")).toBeVisible();
});

test("project workspace creates an outcome, updates a task, and reflects completion", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Projects" }).click();

  await page.getByPlaceholder("Create a project").fill("Launch a clear first release");
  await page.getByText("Add the intended outcome").click();
  await page.getByLabel("What would success look like?").fill("A reliable release that early users can complete onboarding with.");
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByText("Project created.", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Objective", exact: true })).toHaveValue("A reliable release that early users can complete onboarding with.");

  await page.getByPlaceholder("Add a task to this project").fill("Write the onboarding checklist");
  await page.getByRole("button", { name: "Add task" }).click();
  const taskButton = page.getByRole("button", { name: "Write the onboarding checklist" });
  await expect(taskButton).toBeVisible();
  await taskButton.click();
  const taskDetails = page.getByRole("dialog", { name: "Task details" });
  await expect(taskDetails).toBeVisible();
  const titleInput = taskDetails.getByLabel("Title");
  await titleInput.fill("Draft the onboarding checklist");
  const savedTask = page.waitForResponse(response => response.url().includes("/api/v1/tasks/task-1") && response.request().method() === "PATCH");
  await taskDetails.getByLabel("Description").click();
  await savedTask;
  await taskDetails.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("button", { name: "Draft the onboarding checklist" })).toBeVisible();

  await page.getByRole("combobox", { name: "Status for Draft the onboarding checklist" }).selectOption("done");
  await expect(page.getByText("1 of 1 tasks complete (100%)")).toBeVisible();
  await page.getByLabel("Show").selectOption("done");
  await expect(page.getByRole("button", { name: "Draft the onboarding checklist" })).toBeVisible();
});

test("quick capture saves an inbox task from the global workspace toolbar", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.keyboard.press("Control+Shift+Space");
  await expect(page.getByRole("dialog", { name: "Quick capture" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator(".topbar-capture").click();
  await page.getByRole("textbox", { name: "What do you want to remember?" }).fill("Ask the ministry team about the venue");
  await page.locator(".quick-capture button[type=submit]").click();
  await expect(page.getByRole("status")).toContainText("Saved to your Inbox");
  await expect(page.getByText("Ask the ministry team about the venue", { exact: true })).toBeVisible();
});


test("settings theme controls persist across pages and section navigation preserves drafts", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences", exact: true }).click();
  const settingsNav = page.getByRole("navigation", { name: "Settings sections" });
  await expect(settingsNav.getByRole("button", { name: "Appearance", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "A familiar kind of calm." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email and sessions" })).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("settings-light.png") });
  await page.getByRole("button", { name: "Dark A softer light for late work", exact: true }).click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await page.getByRole("combobox", { name: "Interface density", exact: true }).selectOption("compact");
  await expect(page.locator(".orin-shell")).toHaveClass(/density-compact/);
  await page.screenshot({ path: testInfo.outputPath("settings-dark.png") });
  await settingsSection(page, "Account");
  await page.getByLabel("Current password", { exact: true }).fill("unfinished-local-test-draft");
  await settingsSection(page, "Appearance");
  await settingsSection(page, "Account");
  await expect(page.getByLabel("Current password", { exact: true })).toHaveValue("unfinished-local-test-draft");
  await page.getByRole("navigation", { name: "Workspace", exact: true }).getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await page.reload();
  await signIn(page);
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await expect(page.locator(".orin-shell")).toHaveClass(/density-compact/);
  await page.getByRole("button", { name: "Preferences", exact: true }).click();
  await settingsSection(page, "Appearance");
  await page.getByRole("button", { name: "System Follow your device", exact: true }).click();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-system/);
  const systemDark = await page.locator(".orin-shell").evaluate(el => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "light" });
  const systemLight = await page.locator(".orin-shell").evaluate(el => getComputedStyle(el).backgroundColor);
  expect(systemDark).not.toBe(systemLight);
});

test("settings stays usable on a phone and section navigation supports keyboard movement", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await page.getByRole("button", { name: "Preferences", exact: true }).click();
  const settingsNav = page.getByRole("navigation", { name: "Settings sections" });
  const appearance = settingsNav.getByRole("button", { name: "Appearance", exact: true });
  await appearance.focus();
  await appearance.press("ArrowRight");
  await expect(settingsNav.getByRole("button", { name: "Workspace", exact: true })).toBeFocused();
  await expect(page.getByRole("heading", { name: "Choose what you see" })).toBeVisible();
  await settingsNav.getByRole("button", { name: "Workspace", exact: true }).press("End");
  await expect(settingsNav.getByRole("button", { name: "Your data", exact: true })).toBeFocused();
  await expect(page.getByRole("button", { name: "Export my account", exact: true })).toBeVisible();
  const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, view: window.innerWidth }));
  expect(size.scroll).toBeLessThanOrEqual(size.view);
  await settingsNav.getByRole("button", { name: "Your data", exact: true }).press("Home");
  await page.getByRole("button", { name: "Dark A softer light for late work", exact: true }).click();
  await expect(page.locator(".orin-shell")).toHaveClass(/theme-dark/);
  await expect(page.getByRole("button", { name: "Dark A softer light for late work", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: testInfo.outputPath("settings-mobile.png") });
});

test("Writing provides collapsible navigation, note pane controls, and full screen editing", async ({ page }, testInfo) => {
  test.setTimeout(120000);
  await mockApi(page, false, true);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Preferences", exact: true }).click();
  await settingsSection(page, "Workspace");
  await page.getByRole("checkbox", { name: "Show Writing" }).check();
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Writing", exact: true }).click();

  const studio = page.locator(".writing-studio");
  await expect(studio).toBeVisible();
  await expect(page.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
  let createdNotes = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === "/api/v1/knowledge/documents" && request.method() === "POST") createdNotes += 1; });
  await page.getByRole("button", { name: /New note/ }).first().click();
  await expect(page.getByLabel("Content", { exact: true })).toBeVisible();
  await page.waitForTimeout(1100);
  expect(createdNotes).toBe(0);
  await expect(page.locator(".writing-save-status")).toContainText("Not saved yet");
  await page.getByLabel("Content", { exact: true }).fill("A note now worth saving.");
  await expect.poll(() => createdNotes).toBe(1);
  await expect(page.locator(".writing-save-status")).toContainText("Saved");
  await page.getByRole("button", { name: "Manage document" }).click();
  await expect(page.getByRole("button", { name: "Details", exact: true })).toBeVisible();
  await expect(page.getByLabel("Document project")).toBeVisible();
  await expect(page.getByLabel("Document notebook")).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Delete note" }).click();
  await expect(page.getByRole("button", { name: /Untitled/ })).toHaveCount(0);
  const noteRow = page.getByRole("navigation", { name: "Notes" }).getByRole("button", { name: /Meeting notes/ });
  await expect(noteRow).toHaveText("Meeting notes");
  await noteRow.click();
  await page.getByRole("button", { name: "Manage document" }).click();
  await page.getByLabel("Document project").selectOption({ label: "Orin planning" });
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10000 });
  await page.getByRole("button", { name: "Export document…" }).click();
  for (const [label, extension] of [["HTML", ".html"], ["DOCX", ".docx"], ["Markdown", ".md"], ["PDF", ".pdf"]] as const) {
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: new RegExp(`^${label}`) }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`Meeting notes${extension}`);
    expect(await download.failure()).toBeNull();
    const downloadPath = await download.path();
    expect(downloadPath).not.toBeNull();
    const exported = await readFile(downloadPath!);
    if (label === "HTML" || label === "Markdown") {
      const markup = exported.toString("utf8");
      expect(markup).toContain("writing-export-page");
      expect(markup).toContain("font:");
      expect(markup).toContain("Meeting notes");
    }
    if (label === "DOCX") expect(exported.toString("latin1")).toContain("word/media/");
    if (label === "PDF") expect(exported.subarray(0, 4).toString("ascii")).toBe("%PDF");
    if (label !== "PDF") {
      await page.getByRole("button", { name: "Manage document" }).click();
      await page.getByRole("button", { name: "Export document…" }).click();
    }
  }
  await page.getByRole("button", { name: "Manage document" }).click();
  await page.getByRole("button", { name: "Details", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("toolbar", { name: "Document design tools" })).toBeVisible();
  await expect(page.locator(".writing-toolbar-top").getByLabel("Document title")).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview document" })).toBeVisible();
  await expect(page.locator(".writing-formatbar")).toHaveCSS("position", "sticky");
  await expect(page.locator(".writing-manuscript-stats")).toHaveCSS("position", "sticky");
  await expect(page.locator(".writing-manuscript-stats")).toHaveCSS("bottom", "0px");
  await expect(page.locator(".writing-cover-image")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Idea inbox" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Connections" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Manuscript" })).toHaveCount(0);
  if (await page.getByRole("button", { name: "Open inspector" }).isVisible()) await page.getByRole("button", { name: "Open inspector" }).click();
  await expect(page.getByRole("tab", { name: "AI Review" })).toBeVisible();
  await page.getByRole("tab", { name: "AI Review" }).click();
  await page.getByLabel("Content", { exact: true }).fill("In order to make this draft useful, the opening should be concise and easy for every reader to understand.");
  await page.getByRole("button", { name: "Preview document" }).click();
  await expect(page.getByLabel("Document preview")).toContainText("In order to make this draft useful");
  await expect(page.getByRole("toolbar", { name: "Document design tools" })).toHaveCount(0);
  await page.getByRole("button", { name: "Return to editing" }).click();
  await expect(page.getByLabel("Content", { exact: true })).toBeVisible();
  await expect(page.getByText("Tighten the opening")).toBeVisible({ timeout: 5000 });
  await page.getByText("Tighten the opening").locator("..").getByRole("button", { name: "Dismiss" }).click();
  await page.getByLabel("Content", { exact: true }).press("End");
  await page.getByLabel("Content", { exact: true }).pressSequentially(" More detail.");
  await expect(page.getByText("Tighten the opening")).toHaveCount(0);
  await expect(page.getByText("Use a warmer audience word")).toBeVisible({ timeout: 5000 });
  await page.getByText("Use a warmer audience word").locator("..").getByRole("button", { name: "Apply change" }).click();
  await expect(page.getByLabel("Content", { exact: true })).toContainText("audience");
  await page.locator(".writing-inspector-close").click();
  const editor = page.getByLabel("Content", { exact: true });
  await page.locator(".writing-toolbar-menu summary").click();
  await page.getByRole("button", { name: "Insert magazine columns" }).click();
  await page.getByRole("button", { name: "Insert table" }).click();
  await page.getByLabel("Table columns").fill("3");
  await page.getByLabel("Table rows").fill("4");
  await page.getByRole("button", { name: "Insert 4 × 3 table" }).click();
  await page.getByRole("button", { name: "Insert styled text area" }).click();
  await page.getByRole("button", { name: "Insert divider" }).click();
  await expect(editor.locator(".magazine-columns")).toBeVisible();
  await expect(editor.locator("table")).toBeVisible();
  await expect(editor.locator("table tr")).toHaveCount(5);
  await expect(editor.locator("table thead th")).toHaveCount(3);
  await expect(editor.locator(".magazine-callout")).toBeVisible();
  await expect(editor.locator("hr")).toHaveCount(1);
  await expect(editor.locator("hr")).toHaveCSS("border-top-style", "solid");
  await expect(editor).not.toContainText('<div class="magazine-columns">');
  await page.locator(".writing-image-input").setInputFiles({ name: "cover.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64") });
  await expect(editor.locator("figure.magazine-image img")).toBeVisible();
  const editRendering = await editor.evaluate(element => {
    const snapshot = (target: Element | null) => {
      if (!target) return null;
      const style = getComputedStyle(target);
      return { display: style.display, width: style.width, fontFamily: style.fontFamily, fontSize: style.fontSize, lineHeight: style.lineHeight, gridTemplateColumns: style.gridTemplateColumns, borderRadius: style.borderRadius, padding: style.padding, backgroundColor: style.backgroundColor };
    };
    return { surface: snapshot(element), columns: snapshot(element.querySelector(".magazine-columns")), table: snapshot(element.querySelector("table")), callout: snapshot(element.querySelector(".magazine-callout")), image: snapshot(element.querySelector(".magazine-image img")) };
  });
  await page.getByRole("button", { name: "Preview document" }).click();
  const preview = page.getByLabel("Document preview");
  const previewRendering = await preview.evaluate(element => {
    const snapshot = (target: Element | null) => {
      if (!target) return null;
      const style = getComputedStyle(target);
      return { display: style.display, width: style.width, fontFamily: style.fontFamily, fontSize: style.fontSize, lineHeight: style.lineHeight, gridTemplateColumns: style.gridTemplateColumns, borderRadius: style.borderRadius, padding: style.padding, backgroundColor: style.backgroundColor };
    };
    return { surface: snapshot(element), columns: snapshot(element.querySelector(".magazine-columns")), table: snapshot(element.querySelector("table")), callout: snapshot(element.querySelector(".magazine-callout")), image: snapshot(element.querySelector(".magazine-image img")) };
  });
  expect(previewRendering).toEqual(editRendering);
  await page.getByRole("button", { name: "Return to editing" }).click();
  await expect(page.locator(".writing-save-status")).toContainText("Saved", { timeout: 10000 });
  await page.getByRole("button", { name: "Manage document" }).click();
  await page.getByRole("button", { name: "Export document…" }).click();
  const designedDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /^HTML/ }).click();
  const designedDownload = await designedDownloadPromise;
  const designedPath = await designedDownload.path();
  const designedHtml = (await readFile(designedPath!)).toString("utf8");
  expect(designedHtml).toContain("magazine-columns");
  expect(designedHtml).toContain("display: grid");
  expect(designedHtml).toContain("<table");
  expect(designedHtml).toContain("magazine-callout");
  expect(designedHtml).toContain("figure class=\"magazine-image\"");
  expect(designedHtml).toMatch(/data:image\/(?:png|jpeg);base64/);
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Home", exact: true }).click();
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Writing", exact: true }).click();
  await page.getByRole("navigation", { name: "Notes" }).getByRole("button", { name: /Meeting notes/ }).click();
  await expect(page.getByLabel("Content", { exact: true }).locator(".magazine-columns")).toBeVisible();
  await expect(page.getByLabel("Content", { exact: true }).locator("figure.magazine-image img")).toBeVisible();
  const editorBox = await page.locator(".writing-editor").boundingBox();
  const statsBox = await page.locator(".writing-manuscript-stats").boundingBox();
  expect(Math.abs(statsBox!.y + statsBox!.height - (editorBox!.y + editorBox!.height))).toBeLessThanOrEqual(2);
  await page.locator(".writing-editor").evaluate(element => { element.scrollTop = 0; element.scrollLeft = 0; });
  await page.screenshot({ path: testInfo.outputPath("writing-magazine-editor.png"), fullPage: true });
  await page.getByRole("button", { name: "Open inspector" }).click();
  await page.getByRole("tab", { name: "Design" }).click();
  await page.getByLabel("Content", { exact: true }).locator("table th").first().click();
  await expect(page.locator(".writing-selected-element")).toContainText("Table");
  await page.getByLabel("Selected element width").selectOption("75%");
  await expect(page.getByLabel("Content", { exact: true }).locator("table")).toHaveAttribute("style", /width:\s*75%/);
  await page.getByRole("button", { name: "Duplicate" }).click();
  await expect(page.getByLabel("Content", { exact: true }).locator("table")).toHaveCount(2);
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByLabel("Content", { exact: true }).locator("table")).toHaveCount(1);
  await page.getByRole("button", { name: "Filter notes", exact: true }).click();
  await expect(page.getByLabel("Document type")).toBeVisible();
  page.once("dialog", dialog => dialog.accept("Work articles"));
  await page.getByRole("tab", { name: "Notebooks" }).click();
  await page.getByRole("button", { name: "New notebook" }).click();
  await expect(page.getByRole("button", { name: /Work articles/ })).toBeVisible();
  await page.getByRole("tab", { name: "Notes" }).click();

  const workspace = page.locator(".writing-workspace");
  await page.getByRole("button", { name: "Collapse notes sidebar" }).click();
  await expect(workspace).toHaveClass(/writing-list-collapsed/);
  await expect(page.locator(".writing-list")).toBeVisible();
  await expect(page.locator(".writing-list")).toHaveCSS("width", "56px");
  await expect(page.getByRole("button", { name: "Expand notes sidebar" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show notes" })).toBeVisible();
  await page.locator(".writing-more-menu summary").click();
  await page.getByRole("button", { name: "Full screen", exact: true }).click();
  await expect(workspace).toHaveClass(/writing-fullscreen/);
  await expect(page.getByLabel("Content", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(workspace).not.toHaveClass(/writing-fullscreen/);

  await page.getByRole("button", { name: "Minimize sidebar" }).click();
  await expect(page.locator(".orin-shell")).toHaveClass(/sidebar-collapsed/);
  await expect(page.locator(".sidebar")).toHaveCSS("width", "68px");
  await expect(page.locator(".sidebar .nav-link-label").first()).toBeHidden();
  await expect(page.locator(".sidebar .workspace-item-label").first()).toBeHidden();
});
test("switching projects ignores stale responses and keeps unsaved objective edits", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.locator('input[type="password"]').fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Projects" }).click();

  await page.getByPlaceholder("Create a project").fill("Project Alpha");
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByRole("heading", { name: "Project Alpha" })).toBeVisible();
  await page.getByPlaceholder("Add a task to this project").fill("Alpha task");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByRole("button", { name: "Alpha task" })).toBeVisible();

  await page.getByPlaceholder("Create a project").fill("Project Beta");
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByRole("heading", { name: "Project Beta" })).toBeVisible();
  await page.getByPlaceholder("Add a task to this project").fill("Beta task");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByRole("button", { name: /^Beta task\b/ })).toBeVisible();

  const objective = page.getByRole("textbox", { name: "Objective", exact: true });
  await objective.fill("A draft that is not yet saved");
  await page.getByPlaceholder("Add a task to this project").fill("Another Beta task");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByRole("button", { name: "Another Beta task" })).toBeVisible();
  await expect(objective).toHaveValue("A draft that is not yet saved");

  let unblockAlpha!: () => void;
  const alphaGate = new Promise<void>(resolve => { unblockAlpha = resolve; });
  let alphaStarted!: () => void;
  const alphaRequest = new Promise<void>(resolve => { alphaStarted = resolve; });
  await page.route("**/api/v1/projects/project-1/context", async route => {
    alphaStarted();
    await alphaGate;
    await route.fallback();
  });

  const projectPicker = page.getByRole("combobox", { name: "Select project" });
  await projectPicker.selectOption("project-1");
  await alphaRequest;
  await projectPicker.selectOption("project-2");
  await expect(page.getByRole("button", { name: /^Beta task\b/ })).toBeVisible();
  const oldResponse = page.waitForResponse(response => response.url().includes("/projects/project-1/context"));
  unblockAlpha();
  await oldResponse;
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole("heading", { name: "Project Beta" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Beta task\b/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Alpha task" })).toHaveCount(0);

  // Switching projects closes task details from the previous project.
  await page.getByRole("button", { name: /^Beta task\b/ }).click();
  await expect(page.getByRole("dialog", { name: "Task details" })).toBeVisible();
  await projectPicker.selectOption("project-1");
  await expect(page.getByRole("dialog", { name: "Task details" })).toHaveCount(0);
  // A delayed task update must not replace the next project's progress or task list.
  await expect(page.getByRole("button", { name: "Alpha task" })).toBeVisible();
  let unblockPatch!: () => void;
  const patchGate = new Promise<void>(resolve => { unblockPatch = resolve; });
  let patchStarted!: () => void;
  const patchRequest = new Promise<void>(resolve => { patchStarted = resolve; });
  await page.route("**/api/v1/tasks/task-1", async route => {
    patchStarted();
    await patchGate;
    await route.fallback();
  });
  await page.getByRole("combobox", { name: "Status for Alpha task" }).selectOption("done");
  await patchRequest;
  await projectPicker.selectOption("project-2");
  await expect(page.getByText("0 of 2 tasks complete (0%)")).toBeVisible();
  const patchCompleted = page.waitForResponse(response => response.url().includes("/tasks/task-1") && response.request().method() === "PATCH");
  unblockPatch();
  await patchCompleted;
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByText("0 of 2 tasks complete (0%)")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Beta task\b/ })).toBeVisible();
});
