// UI smoke test: the Phase 1 vertical slice, end to end, in a real browser
// against a real server and a fresh project.
import { expect, test, type Page } from "@playwright/test";

const massOf = async (page: Page) => Number((await page.getByTestId("mass-total").innerText()).replace(/[^\d.]/g, ""));

async function command(page: Page, text: string) {
  await page.keyboard.press("Control+K");
  const input = page.getByTestId("command-input");
  await input.fill(text);
  await input.press("Enter");
}

const tab = (page: Page, title: string) => page.locator(".dv-default-tab", { hasText: new RegExp(`^${title}$`) }).first();

test("design, override, undo, simulate, bake", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);

  // first-run tour appears once and can be skipped
  await expect(page.getByTestId("tour")).toBeVisible();
  await page.getByTestId("tour-skip").click();
  await expect(page.getByTestId("tour")).toBeHidden();

  // the reference calf is in the viewport and the scene tree lists stable IDs
  await expect(page.getByTestId("viewport").locator("canvas").first()).toBeVisible();
  await expect(page.locator('[data-tree-id="leg.fl.shank"]')).toBeVisible();
  await expect(page.locator('[data-workspace="form"]')).toHaveAttribute("aria-selected", "true");

  // schema-driven genome form: change a gene, mass follows, undo restores it
  const mass0 = await massOf(page);
  expect(mass0).toBeGreaterThan(3000);
  const trunk = page.locator('[data-field="trunk_length"] input[type="text"]');
  await trunk.fill("520");
  await trunk.press("Enter");
  await expect.poll(() => massOf(page)).toBeGreaterThan(mass0);
  await page.getByTestId("undo").click();
  await expect.poll(() => massOf(page)).toBe(mass0);

  // direct edit of one segment -> explicit override, visible in Properties, removable
  await page.locator('[data-tree-id="leg.fl.shank"]').click();
  const hud = page.getByTestId("gumball-hud");
  await expect(hud).toContainText("leg.fl.shank");
  const hudValue = hud.locator('input[type="text"]');
  await hudValue.fill("195");
  await hudValue.press("Enter");
  await tab(page, "Properties").click();
  const lengthRow = page.getByTestId("properties").locator('[data-param="length"]');
  await expect(lengthRow).toContainText("override");
  await expect(lengthRow).toContainText("parametric 170");
  await tab(page, "Overrides").click();
  await expect(page.locator("[data-override]")).toHaveCount(1);
  await page.locator("[data-override]").getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("[data-override]")).toHaveCount(0);

  // display modes are commands
  await command(page, "DisplayGhosted");
  await command(page, "DisplayShaded");

  // simulate from the command line; poses stream into the timeline
  await page.locator('[data-workspace="simulate"]').click();
  await command(page, "Simulate");
  await expect(page.getByTestId("frame-readout")).toContainText("/", { timeout: 60_000 });
  await expect(page.locator('[data-job-status="done"]').or(page.getByTestId("timeline"))).toBeVisible();
  await tab(page, "Runs").click();
  await expect(page.locator("[data-run]")).toHaveCount(1, { timeout: 30_000 });

  // the node editor shows the pipeline with every node computed
  await tab(page, "Graph").click();
  await expect(page.locator('[data-node="fitness"]')).toHaveAttribute("data-status", "ok", { timeout: 30_000 });

  // bake a versioned design
  await command(page, "Bake name=smoke");
  await expect(page.getByTestId("last-log")).toContainText("smoke-v001");

  expect(errors).toEqual([]);
});
