import { expect, test } from "@playwright/test";

// UI evidence (DoD) for NSG-41. Artefacts land under .worker-artefacts/NSG-41/.
// Path is relative to the frontend/ working directory.
const EVIDENCE_DIR = "../.worker-artefacts/NSG-41";

// E2E happy path: open an in-progress order's detail screen and see the WIP
// balances panel populated from the wip read projection. Runs against the Vite
// dev server with MSW enabled (see playwright.config.ts) — the real contract is
// owned by the wip backend Story (NSG-37) and fixed by ADR 0004.

test("operator sees WIP balances per route step on the order detail", async ({
  page,
}) => {
  await page.goto("/orders/OF-2002");

  // The order detail renders, then the WIP panel mounts below it.
  await expect(page.getByRole("heading", { name: "OF-2002" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Balances de WIP" }),
  ).toBeVisible();

  // Balances per route step are listed (three seeded steps for OF-2002).
  await expect(page.getByTestId("wip-table")).toBeVisible();
  await expect(page.getByTestId("wip-row-1")).toBeVisible();
  await expect(page.getByTestId("wip-row-2")).toContainText("45");
  await expect(page.getByTestId("wip-row-3")).toContainText("200");

  await page.screenshot({
    path: `${EVIDENCE_DIR}/01-order-wip-balances.png`,
    fullPage: true,
  });
});

test("shows a clear empty state when the order has no WIP positions", async ({
  page,
}) => {
  await page.goto("/orders/OF-1001");

  await expect(page.getByRole("heading", { name: "OF-1001" })).toBeVisible();
  await expect(page.getByTestId("wip-empty")).toBeVisible();
  await page.screenshot({
    path: `${EVIDENCE_DIR}/02-order-wip-empty.png`,
    fullPage: true,
  });
});
