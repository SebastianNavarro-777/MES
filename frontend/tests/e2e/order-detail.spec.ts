import { expect, test } from "@playwright/test";

// UI evidence (DoD) is written here so the happy-path artefacts are regenerated
// on every E2E run. Path is relative to the frontend/ working directory.
const EVIDENCE_DIR = "../.worker-artefacts/NSG-21";

// E2E happy path (AC-1, AC-3, AC-4): navigate to the order detail, confirm a
// state transition, and see the new state reflected. Runs against the Vite dev
// server with MSW enabled (see playwright.config.ts), so no live backend is
// required — the contract is owned by the orders backend Story (Epic NSG-14).

test("operator releases a draft order via the confirmation modal", async ({
  page,
}) => {
  await page.goto("/orders/OF-1001");

  // AC-1: order data is shown.
  await expect(page.getByRole("heading", { name: "OF-1001" })).toBeVisible();
  await expect(page.getByText("Soporte de aluminio A")).toBeVisible();
  await expect(page.getByText("Borrador")).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/01-order-detail-draft.png`, fullPage: true });

  // AC-3: choosing a transition opens a confirmation modal with source/destination.
  await page.getByTestId("transition-released").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Estado actual")).toBeVisible();
  await expect(dialog.getByText("Nuevo estado")).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/02-confirm-modal.png`, fullPage: true });

  // AC-4: confirming reflects the new state and the next available transition.
  await page.getByTestId("confirm-transition").click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Liberada")).toBeVisible();
  await expect(page.getByTestId("transition-in_progress")).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/03-order-detail-released.png`, fullPage: true });
});

test("shows a clear not-found state for a missing order", async ({ page }) => {
  // AC-7: missing/invalid order id shows a clear not-found state.
  await page.goto("/orders/OF-0000");
  await expect(page.getByTestId("order-not-found")).toBeVisible();
  await expect(page.getByText("Orden no encontrada")).toBeVisible();
});
