// Viewport interaction with a real mouse: the gumball arrow and the harness
// overlay. Set CALFLAB_E2E_SHOTS to a folder to keep screenshots of the canvas.
import { expect, test, type Locator, type Page } from "@playwright/test";
import path from "node:path";

const shots = process.env.CALFLAB_E2E_SHOTS;

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  await expect(page.getByTestId("viewport").locator("canvas").first()).toBeVisible();
}

const tab = (page: Page, title: string) => page.locator(".dv-default-tab", { hasText: new RegExp(`^${title}$`) }).first();

async function shot(canvas: Locator, name: string) {
  if (shots) await canvas.screenshot({ path: path.join(shots, `${name}.png`) });
}

/** The active gumball arrow in page coordinates (the viewport publishes it on the canvas). */
async function arrow(canvas: Locator, param: string) {
  await expect(canvas).toHaveAttribute("data-gumball", new RegExp(`^${param} `));
  // the camera frames the robot shortly after load; wait until the arrow stops moving
  let last = "";
  await expect
    .poll(async () => {
      const now = (await canvas.getAttribute("data-gumball")) ?? "";
      const still = now === last;
      last = now;
      return still;
    }, { intervals: [250] })
    .toBe(true);
  const [, bx, by, tx, ty] = last.split(" ").map(Number);
  const box = (await canvas.boundingBox())!;
  const len = Math.hypot(tx - bx, ty - by);
  return { x: box.x + (bx + tx) / 2, y: box.y + (by + ty) / 2, ux: (tx - bx) / len, uy: (ty - by) / len, len };
}

test("dragging the gumball arrow overrides one leg segment", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);
  const canvas = page.getByTestId("viewport").locator("canvas").first();

  await page.locator('[data-tree-id="leg.fr.shank"]').click();
  const hud = page.getByTestId("gumball-hud");
  const value = hud.locator('input[type="text"]');
  await expect(value).toHaveValue("170");
  const a = await arrow(canvas, "length");
  expect(a.len).toBeGreaterThan(60); // a handle you can see and catch, at any zoom
  await shot(canvas, "gumball-leg");

  // drag outward along the arrow: the bar follows while the button is still down
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + a.ux * 40, a.y + a.uy * 40, { steps: 10 });
  await expect.poll(async () => Number(await value.inputValue())).toBeGreaterThan(175);
  await page.mouse.up();
  const dragged = Number(await value.inputValue());
  await shot(canvas, "gumball-leg-dragged");

  // it is an explicit override of that one part, and the selection survived the drag
  await expect(hud).toContainText("leg.fr.shank");
  await tab(page, "Overrides").click();
  await expect(page.locator("[data-override]")).toHaveCount(1);
  await expect(page.locator("[data-override]")).toContainText(`leg.fr.shank.length = ${dragged}`);
  await tab(page, "Properties").click();
  await expect(page.getByTestId("properties").locator('[data-param="length"]')).toContainText("parametric 170");

  // one drag is one undo step
  await page.getByTestId("undo").click();
  await expect(value).toHaveValue("170");
  await tab(page, "Overrides").click();
  await expect(page.locator("[data-override]")).toHaveCount(0);

  // the trunk has a handle per dimension; picking another one in the bar moves the active arrow
  await page.locator('[data-tree-id="trunk"]').click();
  await expect(hud).toContainText("trunk");
  const length = await arrow(canvas, "length");
  await hud.locator("select").first().selectOption("height");
  const height = await arrow(canvas, "height");
  expect(Math.hypot(height.x - length.x, height.y - length.y)).toBeGreaterThan(20);
  await shot(canvas, "gumball-trunk");

  expect(errors).toEqual([]);
});

test("harness routes are drawn over the body", async ({ page }) => {
  await open(page);
  const canvas = page.getByTestId("viewport").locator("canvas").first();
  // count pixels in the Harness layer colour (#c4504e) on the canvas
  const red = () =>
    canvas.evaluate((el) => {
      const src = el as HTMLCanvasElement;
      const c = document.createElement("canvas");
      c.width = src.width;
      c.height = src.height;
      const ctx = c.getContext("2d")!;
      ctx.drawImage(src, 0, 0);
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - 0xc4) < 14 && Math.abs(d[i + 1] - 0x50) < 14 && Math.abs(d[i + 2] - 0x4e) < 14) n++;
      return n;
    });
  await page.waitForTimeout(800); // camera fit
  const before = await red();
  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("OverlayHarness");
  await page.getByTestId("command-input").press("Enter");
  await expect.poll(red).toBeGreaterThan(before + 400); // in Shaded mode, through the shells
  await shot(canvas, "harness-shaded");

  // the Wire workspace shows the harness without the overlay switch, and its table highlights a cable
  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("OverlayHarness");
  await page.getByTestId("command-input").press("Enter");
  await expect.poll(red).toBeLessThan(before + 100);
  await page.locator('[data-workspace="wire"]').click();
  await tab(page, "Viewport").click();
  const wireCanvas = page.getByTestId("viewport").locator("canvas").first();
  await expect(wireCanvas).toBeVisible();
  await expect.poll(red).toBeGreaterThan(before + 400);
});
