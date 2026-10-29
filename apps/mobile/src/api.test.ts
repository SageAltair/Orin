import { beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";

vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(async () => null),
  setItemAsync: vi.fn(async () => undefined),
  deleteItemAsync: vi.fn(async () => undefined),
}));

describe("mobile API boundary", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it("normalizes a configured API origin without changing its path", async () => {
    const { normalizeBaseUrl } = await import("./api");
    expect(normalizeBaseUrl(" https://orin.example/api/// ")).toBe(
      "https://orin.example/api",
    );
  });

  it("extracts stable API validation messages", async () => {
    const { errorDetail } = await import("./api");
    expect(errorDetail({ detail: "Wrong password" }, "fallback")).toBe(
      "Wrong password",
    );
    expect(
      errorDetail(
        {
          detail: [
            { msg: "Email is invalid" },
            { msg: "Password is too short" },
          ],
        },
        "fallback",
      ),
    ).toBe("Email is invalid; Password is too short");
    expect(errorDetail(null, "fallback")).toBe("fallback");
  });

  it("sends the secure token and active workspace on API requests", async () => {
    vi.stubEnv("EXPO_PUBLIC_API_BASE_URL", "https://orin.example");
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("access-token")
      .mockResolvedValueOnce("workspace-1");
    const fetchMock = vi.fn(
      async (_url: string | URL | Request, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe("Bearer access-token");
        expect(headers.get("X-Orin-Workspace-Id")).toBe("workspace-1");
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    await api.hydrateSession();
    await expect(api.request<unknown[]>("/tasks")).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("sends consent preferences and reminder actions to the owner-scoped API", async () => {
    vi.stubEnv("EXPO_PUBLIC_API_BASE_URL", "https://orin.example");
    vi.mocked(SecureStore.getItemAsync)
      .mockResolvedValueOnce("notification-token")
      .mockResolvedValueOnce("workspace-1");
    const calls: Array<{ path: string; method: string; body: unknown }> = [];
    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("Authorization")).toBe("Bearer notification-token");
      expect(headers.get("X-Orin-Workspace-Id")).toBe("workspace-1");
      expect(init?.credentials).toBe("include");
      calls.push({
        path: String(url),
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      return new Response(JSON.stringify({ status: "acknowledge" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { hydrateSession, request } = await import("./api");
    await hydrateSession();

    const preferences = {
      enabled: false,
      categories: ["tasks"],
      persistent: false,
      repeat_minutes: 15,
      max_repeats: 3,
      timezone: "UTC",
      quiet_enabled: true,
      quiet_start: "22:00",
      quiet_end: "07:00",
      respect_focus: true,
      browser_alerts: false,
      sound: false,
    };
    await request("/notifications/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    });
    await request("/notifications/reminder-1/action", {
      method: "POST",
      body: JSON.stringify({ action: "acknowledge", minutes: 15 }),
    });

    expect(calls).toEqual([
      {
        path: "https://orin.example/api/v1/notifications/preferences",
        method: "PUT",
        body: preferences,
      },
      {
        path: "https://orin.example/api/v1/notifications/reminder-1/action",
        method: "POST",
        body: { action: "acknowledge", minutes: 15 },
      },
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
