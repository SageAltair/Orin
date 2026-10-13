import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    launchOptions: process.env.ORIN_BROWSER_EXECUTABLE_PATH
      ? {
          executablePath: process.env.ORIN_BROWSER_EXECUTABLE_PATH,
          args: ["--no-sandbox", "--disable-dev-shm-usage"],
        }
      : {},
  },
  projects: [
    {
      name: "chromium",
      testIgnore: "e2e/legacy-tasks.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:4173" },
    },
    {
      name: "rollout-off",
      testMatch: "e2e/legacy-tasks.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:4174" },
    },
  ],
  webServer: [
    ...(process.env.ORIN_LIVE_E2E === "true"
      ? [
          {
            command: "npm run dev -- --host 127.0.0.1 --port 5273 --strictPort",
            url: "http://127.0.0.1:5273",
            reuseExistingServer: !process.env.CI,
            timeout: 30000,
          },
        ]
      : []),
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      env: { ...process.env, VITE_FOCUS_ENABLED: "true" },
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4174 --strictPort",
      url: "http://127.0.0.1:4174",
      env: { ...process.env, VITE_FOCUS_ENABLED: "false" },
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
