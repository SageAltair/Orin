import { expect, type APIRequestContext } from "@playwright/test";

// Disposable PostgreSQL stack only. Never target the user's 8100/5273 services.
export const ISOLATED_API_URL = "http://127.0.0.1:18100";
export const ISOLATED_WEB_URL = "http://127.0.0.1:15273";

export function isolatedLiveEnabled(flag: "ORIN_LIVE_E2E" | "ORIN_WORKER_E2E"): boolean {
  return process.env.ORIN_ISOLATED_E2E === "true" && process.env[flag] === "true";
}

export async function requireIsolatedApi(request: APIRequestContext): Promise<void> {
  const ready = await request.get(ISOLATED_API_URL + "/health/ready");
  expect(ready.status(), "disposable API must be ready before creating records").toBe(200);
}
