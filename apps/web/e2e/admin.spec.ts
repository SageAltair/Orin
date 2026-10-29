import { expect, test } from "@playwright/test";

test("administrator console is separate and performs account management", async ({ page }) => {
  let roleChanged = false;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/refresh")) return route.fulfill({ json: { access_token: "admin-token" } });
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "a", email: "owner@example.com", display_name: "Owner", created_at: new Date().toISOString(), is_admin: true, is_disabled: false } });
    if (path.endsWith("/admin/overview")) return route.fulfill({ json: { generated_at: new Date().toISOString(), totals: { users: 2, active_users: 2, workspaces: 1, projects: 1, tasks: 3, attachments: 0, storage_bytes: 0 }, operations: { active_sessions: 1, pending_approvals: 0, commands_30d: 4, active_workers: 0 }, ai: { requests_30d: 4, failures_30d: 0, fallbacks_30d: 0, estimated_cost_microusd_30d: 0, success_rate: 100 } } });
    if (path.endsWith("/admin/users") && route.request().method() === "GET") return route.fulfill({ json: { items: [{ id: "a", email: "owner@example.com", display_name: "Owner", created_at: new Date().toISOString(), is_admin: true, is_disabled: false, workspace_count: 1, project_count: 1, task_count: 3, active_sessions: 1 }, { id: "b", email: "member@example.com", display_name: "Member", created_at: new Date().toISOString(), is_admin: false, is_disabled: false, workspace_count: 0, project_count: 0, task_count: 0, active_sessions: 0 }] } });
    if (path.endsWith("/admin/workspaces")) return route.fulfill({ json: [] });
    if (path.endsWith("/admin/devices")) return route.fulfill({ json: [] });
    if (path.endsWith("/admin/settings")) return route.fulfill({ json: { registration_enabled: true } });
    if (path.endsWith("/admin/audit")) return route.fulfill({ json: [] });
    if (path.endsWith("/admin/users/b") && route.request().method() === "PATCH") { roleChanged = true; return route.fulfill({ json: { id: "b", is_admin: true, is_disabled: false } }); }
    return route.fulfill({ status: 204 });
  });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Control room" })).toBeVisible();
  await expect(page.getByText("Open workspace")).toBeVisible();
  await page.getByRole("button", { name: "Collapse administration sidebar" }).click();
  await expect(page.locator(".admin-portal-shell")).toHaveClass(/admin-sidebar-collapsed/);
  await page.getByRole("button", { name: "People & access" }).click();
  await page.getByText("Member", { exact: true }).click();
  await page.getByRole("button", { name: "Make admin" }).click();
  await expect.poll(() => roleChanged).toBe(true);
});
