import { defineConfig, devices } from "@playwright/test";

// AC-6: Playwright harness. A documented `pnpm test:e2e` boots the app and runs
// the smoke spec. `webServer` lets Playwright start the Vite dev server itself,
// so the happy path is reproducible without manual setup. UI Stories that build
// on this scaffold drop their specs into ./e2e.
const PORT = Number(process.env.VITE_DEV_PORT ?? "5173");
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Use Corepack (bundled with Node) so the dev server starts whether or not
    // a global `pnpm` is on PATH; the pinned version comes from package.json's
    // `packageManager` field. Override with PLAYWRIGHT_WEBSERVER_CMD if needed.
    command: process.env.PLAYWRIGHT_WEBSERVER_CMD ?? "corepack pnpm dev",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
