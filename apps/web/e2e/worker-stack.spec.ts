import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { ISOLATED_API_URL, ISOLATED_WEB_URL, isolatedLiveEnabled, requireIsolatedApi } from "./isolated-runtime";

test.use({ trace: "off" });

test("real API approval releases a signed job to a live worker and reports its result", async ({ page }) => {
  test.skip(!isolatedLiveEnabled("ORIN_WORKER_E2E"), "Requires ORIN_ISOLATED_E2E=true and ORIN_WORKER_E2E=true with disposable stack");
  await requireIsolatedApi(page.request);
  test.setTimeout(120_000);
  const root = await mkdtemp(join(tmpdir(), "orin-worker-e2e-"));
  let worker: ChildProcess | undefined;
  let workerDiagnostics = "";
  const email = `orin-worker-e2e-${Date.now()}@example.com`;
  const password = "Public-Docker-Worker-Test-Password-2026!";
  try {
    await page.goto(ISOLATED_WEB_URL);
    await page.getByRole("button", { name: "New to Orin? Create an account" }).click();
    await page.getByLabel("Your name").fill("Worker integration test");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("button", { name: "Ask Orin", exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "Preferences" }).click();
    await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Devices", exact: true }).click();
    await page.getByLabel("Device name").fill("E2E-Windows-Worker");
    await page.getByRole("button", { name: "Register", exact: true }).click();
    const token = await page.getByLabel("Worker token").inputValue();
    const setup = await page.locator(".device-enrollment pre").innerText();
    const deviceId = setup.match(/ORIN_DEVICE_ID="([^"]+)"/)?.[1];
    expect(deviceId).toBeTruthy();

    worker = spawn(process.env.ORIN_WORKER_PYTHON ?? "python", ["-m", "orin_worker.main"], {
      cwd: process.cwd(),
      stdio: ["ignore", "ignore", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: join(process.cwd(), "..", "..", "apps", "worker", "src"),
        ORIN_API_URL: ISOLATED_API_URL,
        ORIN_DEVICE_ID: deviceId!,
        ORIN_WORKER_TOKEN: token,
        ORIN_ALLOWED_ROOTS: root,
        ORIN_WORKER_STATE_PATH: join(root, "worker-state.sqlite3"),
      },
    });
    worker.stderr?.on("data", chunk => { workerDiagnostics = (workerDiagnostics + String(chunk)).slice(-2000); });
    await expect(page.getByText("active", { exact: true }), workerDiagnostics).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Request approval" }).click();
    await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Approvals", exact: true }).click();
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText(/executed · low risk/)).toBeVisible({ timeout: 45_000 });
    await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Devices", exact: true }).click();
    await expect(page.getByText(/completed · Running an allowed capability/)).toBeVisible({ timeout: 45_000 });
    await expect(page.locator(".data-main pre").filter({ hasText: /platform/ })).toBeVisible();
    const workers = page.getByRole("region", { name: "Connected workers" });
    page.once("dialog", dialog => dialog.accept());
    await workers.getByRole("button", { name: "Revoke" }).click();
    await expect(workers.getByText(/revoked/)).toBeVisible();
  } finally {
    if (worker && worker.exitCode === null) {
      const exited = new Promise<void>(resolve => worker?.once("close", () => resolve()));
      worker.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 5000))]);
    }
    await rm(root, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
  }
});
