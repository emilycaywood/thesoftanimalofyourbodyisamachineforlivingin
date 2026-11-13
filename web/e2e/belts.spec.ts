// Belts and springs on the final feral calf (ADR-063..069): three dropdowns per
// belt drive, everything else read-only; a failing choice is rejected with its
// reason and the document is unchanged; a valid one moves C; undo restores it.
// Since R18 (ADR-115) a new project's belts are McMaster-Carr 3MGT 30T/45T and
// the earlier (not sourceable) systems are greyed.
// Runs against the second lab of playwright.config.ts (a fresh feral project).
import { expect, test } from "@playwright/test";
import { feralPort } from "../playwright.config";

test.use({ baseURL: `http://127.0.0.1:${feralPort}` });

test("choose belts from the catalog: C is derived, a failing belt is rejected, springs are listed", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  // PROVISIONAL genes carry a badge in the Form
  await expect(page.getByTestId("provisional-badge").first()).toBeVisible();

  await page.locator('[data-workspace="mechanism"]').click();
  await page.locator(".dv-default-tab", { hasText: /^Belts and springs$/ }).first().click();
  const panel = page.getByTestId("belts-panel");
  await expect(panel.getByTestId("belt-stifle-derived")).toContainText("180.6 mm");
  await expect(panel.getByTestId("belt-hock-length")).toHaveValue("MM-3MGT-420");
  // no control sets the centre distance: only the three selects per drive
  await expect(panel.getByTestId("belt-hock").locator("input")).toHaveCount(0);
  await expect(panel.getByTestId("belt-hock").locator("select")).toHaveCount(3);
  // a belt system that is not sourceable is greyed (ADR-115)
  await expect(panel.getByTestId("belt-hock-system").locator('option[value="GT2-2mm-10mm-generic"]')).toBeDisabled();

  // the 450 mm belt hits the stifle belt in the stifle's range: rejected, nothing changes
  await panel.getByTestId("belt-hock-length").selectOption("MM-3MGT-450");
  await expect(panel.getByTestId("belt-message")).toContainText("rejected");
  await expect(panel.getByTestId("belt-message")).toContainText("stifle belt");
  await expect(panel.getByTestId("belt-hock-length")).toHaveValue("MM-3MGT-420");

  // a valid one: C follows the catalog entry
  await panel.getByTestId("belt-hock-length").selectOption("MM-3MGT-414");
  await expect(panel.getByTestId("belt-hock-derived")).toContainText("150.6 mm");
  await page.request.post("/api/commands/undo");
  await expect(panel.getByTestId("belt-hock-length")).toHaveValue("MM-3MGT-420");

  // springs in the standing pose, with their side
  await expect(panel.getByTestId("spring-table")).toContainText("hl.stifle");
  await expect(panel.getByTestId("spring-table")).toContainText("resists");

  // belts are catalog genes edited only here: Form does not offer them; Evolve uses this body's own defaults
  await page.locator('[data-workspace="form"]').click();
  await expect(page.getByTestId("genome-panel").locator('[data-field="femur_length"]')).toBeVisible();
  await expect(page.getByTestId("genome-panel").locator('[data-field^="belt_"]')).toHaveCount(0);
  await page.locator('[data-workspace="evolve"]').click();
  await expect(page.getByTestId("evolve-panel").locator('[data-field="descriptor_x"] select')).toHaveValue("standing_height");
  expect(errors).toEqual([]);
});
