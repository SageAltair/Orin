import { expect, test } from "@playwright/test";

test("web reminders include older unread records and show the oldest eligible follow-up", async ({ page }) => {
  // Permission denial must not consume the only interruption attempt.
  // Use a fake Notification API to avoid real browser/OS notifications.
  await page.addInitScript(() => {
    class FakeNotification {
      static get permission() {
        return sessionStorage.getItem("test:notification-permission") ?? "denied";
      }
      onclick: (() => void) | null = null;
      constructor() {
        const previous = Number(sessionStorage.getItem("test:notifications-shown") ?? "0");
        sessionStorage.setItem("test:notifications-shown", String(previous + 1));
      }
      close() {}
    }
    Object.defineProperty(window, "Notification", { configurable: true, value: FakeNotification });
    // Simulate autoplay blocking the sound fallback without touching real audio.
    class BlockedAudioContext {
      constructor() {
        sessionStorage.setItem("test:audio-blocked", "yes");
        throw new Error("Audio playback requires a user gesture");
      }
    }
    Object.defineProperty(window, "AudioContext", { configurable: true, value: BlockedAudioContext });
  });
  const now = "2026-10-30T12:00:00Z";
  const reminders = Array.from({ length: 225 }, (_, index) => ({
    id: `reminder-${index}`,
    title: `Reminder ${index}`,
    message: "Disposable browser reminder",
    category: "tasks",
    source_id: null,
    due_at: index === 224 ? "2026-10-29T12:00:00Z" :
      new Date(Date.parse("2027-01-01T00:00:00Z") + (225 - index) * 60_000).toISOString(),
    read_at: index === 224 ? null : now,
    snoozed_until: null,
    revision: 1,
    repeats: 0,
    attention_ready: index === 224,
  }));
  const offsets: number[] = [];
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    if (pathname.endsWith("/auth/refresh")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "test-token", token_type: "bearer", expires_in: 900 } });
    if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "morgan@example.com", display_name: "Morgan", created_at: now } });
    if (pathname === "/api/v1/users/me/preferences") return route.fulfill({ json: {
      density: "comfortable", theme: "light", locale: "en",
      visible_capabilities: ["home", "tasks", "calendar", "projects"],
      hidden_capabilities: [], pinned_capabilities: ["home", "tasks"],
      autonomy_mode: "balanced", custom_autonomy: {},
    } });
    if (pathname === "/api/v1/focus/settings") return route.fulfill({ json: {
      timezone: "UTC", theme: "light", reduced_motion: false,
      hide_timer_numbers: false, sound_enabled: false, haptics_enabled: false,
    } });
    if (pathname === "/api/v1/notifications/preferences") return route.fulfill({ json: {
      enabled: true, categories: ["tasks"], persistent: true, repeat_minutes: 15,
      max_repeats: 3, timezone: "UTC", quiet_enabled: false,
      quiet_start: "22:00", quiet_end: "07:00", respect_focus: true,
      browser_alerts: true, sound: true,
    } });
    if (pathname === "/api/v1/notifications") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 100);
      offsets.push(offset);
      return route.fulfill({ json: reminders.slice(offset, offset + limit) });
    }
    if (["/api/v1/tasks", "/api/v1/projects", "/api/v1/environment/preferences",
      "/api/v1/approvals", "/api/v1/conversations", "/api/v1/auth/sessions"].includes(pathname)) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ status: 204 });
  });

  await page.goto("/");
  await page.getByLabel("Email").fill("morgan@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-secure-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  const bell = page.getByRole("button", { name: "Reminders, 1 unread" });
  await expect(bell).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Persistent follow-up" })
    .getByText("Reminder 224", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("test:audio-blocked"))).toBe("yes");
  expect(await page.evaluate(() => sessionStorage.getItem("orin:alert:reminder-224:1"))).toBeNull();
  expect(await page.evaluate(() => sessionStorage.getItem("test:notifications-shown"))).toBeNull();
  await page.evaluate(() => {
    sessionStorage.setItem("test:notification-permission", "granted");
    window.dispatchEvent(new Event("orin-notification-preferences"));
  });
  await expect.poll(() => page.evaluate(() =>
    sessionStorage.getItem("orin:alert:reminder-224:1"))).toBe("seen");
  expect(await page.evaluate(() => sessionStorage.getItem("test:notifications-shown"))).toBe("1");
  await bell.click();
  const panel = page.getByRole("region", { name: "Your reminders" });
  await expect(panel.getByText("Reminder 224", { exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: /Show 100 older reminders/ }).click();
  await expect(panel.getByText("Reminder 224", { exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: /Show 100 older reminders/ }).click();
  await expect(panel.getByText("Reminder 224", { exact: true })).toBeVisible();
  expect(offsets.filter(offset => offset === 200).length).toBeGreaterThanOrEqual(2);
});
