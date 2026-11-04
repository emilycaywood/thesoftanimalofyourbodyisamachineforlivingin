// A clip judged in physics and made feasible (ADR-084): Play in physics on a clip row shows the stored report
// (per-joint table, constraints, hooves, battery, time strip); a Make feasible run (started here through the API
// with a one-round search, so the test stays short) is listed on the row and shows raw and adapted side by side.
// The feasible version is a new clip; the original is not changed. Runs on the fresh feral-calf lab of
// playwright.config.ts.
import { expect, test } from "@playwright/test";
import { feralPort } from "../playwright.config";

test.use({ baseURL: `http://127.0.0.1:${feralPort}` });

test("a clip is played in physics and a feasible version is shown beside it", async ({ page }) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // a slow sway: the hind legs fold and the shoulders swing a little
  const frames = 30;
  const w = Array.from({ length: frames }, (_, i) => 0.5 * (1 - Math.cos((2 * Math.PI * i) / frames)));
  const joints = {
    "joint.hl.stifle": w.map((x) => 30 * x), "joint.hr.stifle": w.map((x) => 30 * x),
    "joint.hl.hock": w.map((x) => 24 * x), "joint.hr.hock": w.map((x) => 24 * x),
    "joint.fl.shoulder": w.map((x) => 15 * x), "joint.fr.shoulder": w.map((x) => -10 * x),
  };
  await page.request.post("/api/motions", { data: { id: "sway-phys", name: "sway-phys", fps: 20, source: "footage", joints } });
  const original = await (await page.request.get("/api/motions/sway-phys")).json();

  // a small search through the command, as the button would start it with full settings
  const started = await (await page.request.post("/api/commands/adapt_clip", {
    data: { clip: "sway-phys", margin: 0.2, settings: { max_rounds: 1, give_back_rounds: 0, max_slowdown: 2 } },
  })).json();
  const jobId: string = started.result.job;
  await expect.poll(async () => (await (await page.request.get(`/api/jobs/${jobId}`)).json()).status, { timeout: 180_000 }).toBe("done");

  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  await page.locator('[data-workspace="behave"]').click();
  const panel = page.getByTestId("behave-panel");
  const row = panel.locator('[data-clip="sway-phys"]');
  await expect(row).toBeVisible();
  await expect(panel.locator('[data-clip="sway-phys-feasible"]')).toBeVisible(); // saved as a new clip

  // Play in physics: a job, then the stored report
  await row.getByTestId("play-in-physics").click();
  const report = row.getByTestId("physics-report");
  await expect(report).toBeVisible({ timeout: 60_000 });
  await expect(report.getByTestId("physics-joints").locator("tbody tr")).toHaveCount(10);
  await expect(report.getByTestId("physics-joints")).toContainText("hl.stifle");
  await expect(report.getByTestId("physics-constraints")).toContainText(/envelope|Torque-speed/i);
  await expect(report.getByTestId("physics-hooves").locator("tbody tr")).toHaveCount(4);
  await expect(report.getByTestId("physics-battery")).toContainText("lower bound"); // no stall current in the library
  await expect(report.getByTestId("physics-basis")).toContainText("UNVERIFIED");
  const strip = report.getByTestId("physics-strip").locator("svg");
  await expect(strip.locator("rect").first()).toBeAttached();
  await strip.click(); // seeks the replay

  // the Make feasible run, listed on the row: raw and adapted side by side
  await row.getByRole("button", { name: "Hide report" }).click();
  await row.getByTestId("show-last-adapt").click();
  const adapt = row.getByTestId("adapt-report");
  await expect(adapt).toBeVisible();
  await expect(adapt.getByTestId("adapt-compare")).toContainText("as retargeted");
  await expect(adapt.getByTestId("adapt-compare")).toContainText("character kept");
  await expect(adapt.getByTestId("adapt-steps")).toBeAttached();
  await expect(adapt.getByTestId("adapted-saved")).toContainText("sway-phys-feasible");
  await adapt.getByTestId("show-raw").click();
  await expect(adapt.getByTestId("physics-joints")).toBeVisible();
  await adapt.getByTestId("show-adapted").click();

  const kept = await (await page.request.get("/api/motions/sway-phys-feasible")).json();
  expect(kept.meta.adapted_from).toBe("sway-phys");
  expect(kept.meta.adapted_operations.plant).toBe(true);
  expect(kept.meta.margin).toBe(0.2);
  expect(await (await page.request.get("/api/motions/sway-phys")).json()).toEqual(original);
  expect(errors).toEqual([]);
});
