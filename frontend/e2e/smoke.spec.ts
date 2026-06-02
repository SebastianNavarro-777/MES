import { expect, test } from "@playwright/test";

// AC-1 / AC-6: with a single documented command (`pnpm test:e2e`) Playwright
// boots the app (via the webServer in playwright.config.ts) and verifies the
// initial page renders in a real browser. This is the minimal smoke harness;
// UI Stories (NSG-20, NSG-30) add their happy paths into this ./e2e folder.
test("initial page renders", async ({ page }) => {
  await page.goto("/");

  // The app shell mounts and shows its title.
  await expect(page.getByRole("heading", { name: "NSG MES", level: 1 })).toBeVisible();

  // The example TanStack Query mounted and resolved to one of its states
  // (loading / success / error) — proving the React tree booted, not a blank page.
  const connectivity = page.getByRole("region", { name: "Backend connectivity" });
  await expect(connectivity).toBeVisible();
});
