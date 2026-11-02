import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const sessionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const generation = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const root = resolve(fileURLToPath(new URL("../../../", import.meta.url)));

test("real Chromium revokes a disposable foreground companion over loopback", async ({ page }) => {
  // This Python listener uses no API credentials, account, database or OS toast.
  // Port collision is a test failure, never a reason to skip the security gate.
  const code = [
    "import threading",
    "from orin_worker.windows_reminder_control import LocalRevocationControl",
    "stop=threading.Event()",
    "with LocalRevocationControl(session_id='" + sessionId + "', generation='" + generation + "',",
    "  allowed_origin='http://127.0.0.1:4173', stopping=stop,",
    "  delivery_lock=threading.Lock(), port=18765):",
    "  print('READY', flush=True)",
    "  print('STOPPED' if stop.wait(20) else 'TIMED_OUT', flush=True)",
  ].join("\n");
  const child = spawn(process.platform === "win32" ? "python" : "python3", ["-u", "-c", code], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: resolve(root, "apps/worker/src") },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  let errors = "";
  child.stdout.on("data", chunk => { output += String(chunk); });
  child.stderr.on("data", chunk => { errors += String(chunk); });

  try {
    await new Promise<void>((done, fail) => {
      const timeout = setTimeout(() => fail(new Error("Local listener did not start: " + errors)), 10_000);
      const onData = () => {
        if (!output.includes("READY")) return;
        clearTimeout(timeout);
        child.stdout.off("data", onData);
        done();
      };
      child.stdout.on("data", onData);
      child.on("error", fail);
      child.on("exit", code => {
        if (!output.includes("READY")) fail(new Error("Local listener exited " + code + ": " + errors));
      });
      onData();
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    // A cold Vite dev server may still be transforming this module after / loads.
    await expect.poll(async () =>
      (await page.request.get("/src/windowsReminderLocalControl.ts")).status(),
      { timeout: 10_000 },
    ).toBe(200);
    const revoked = await page.evaluate(async ({ sessionId, generation }) => {
      const { revokeLocalWindowsCompanion } = await import("/src/windowsReminderLocalControl.ts");
      return revokeLocalWindowsCompanion({ sessionId, generation });
    }, { sessionId, generation });
    expect(revoked).toBe(true);
    await expect.poll(() => output.includes("STOPPED"), { timeout: 5_000 }).toBe(true);
  } finally {
    if (child.exitCode === null) child.kill();
  }
});
