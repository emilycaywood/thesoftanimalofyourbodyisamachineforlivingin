// Interpretation (ADR-085): a reading (here a known synthetic sequence, as the fresh lab has no footage) is
// interpreted on the body with a tiny search, played for a few seconds, and the stored report is shown in the Behave
// panel: shares side by side, the interpretation record per behaviour with its verdicts and reasons, the gaps, the
// time strip (calf and robot), and the gaits at margin 0.2. Runs on the fresh feral-calf lab of playwright.config.ts.
import { expect, test } from "@playwright/test";
import { feralPort } from "../playwright.config";

test.use({ baseURL: `http://127.0.0.1:${feralPort}` });

test("a reading is interpreted and the report is shown side by side with the calf", async ({ page }) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const read = await (await page.request.post("/api/commands/read_footage", {
    data: { synthetic: [["stand", 2.0], ["weight_shift", 2.0], ["walk", 3.6], ["stand", 1.5]] },
  })).json();
  expect(read.result.stretches).toBe(4);
  const started = await (await page.request.post("/api/commands/interpret_footage", {
    data: { seconds: 6, seeds: [0], settings: { popsize: 2, generations: 1, min_play_s: 2, max_play_s: 4,
      primitives: { stand: ["stand"], weight_shift: ["weight_shift"], walk: ["walk"] } } },
  })).json();
  const jobId: string = started.result.job;
  await expect.poll(async () => (await (await page.request.get(`/api/jobs/${jobId}`)).json()).status, { timeout: 200_000 }).toBe("done");

  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  await page.locator('[data-workspace="behave"]').click();
  const report = page.getByTestId("interpret-report");
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("interpret-support")).toContainText("stretches");
  await expect(page.getByTestId("interpret-shares").locator("tbody tr")).toHaveCount(6);
  for (const b of ["stand", "weight_shift", "walk"]) {
    await expect(page.getByTestId(`interpretation-${b}`)).toBeVisible();
  }
  // a record opens to its feature table with verdicts and reasons
  await page.getByTestId("interpretation-walk").locator("button").first().click();
  await expect(page.getByTestId("interpretation-walk")).toContainText(/kept|reduced|exaggerated|dropped/);
  await expect(page.getByTestId("interpret-defaults")).toContainText("walk");
  await expect(page.getByTestId("interpret-gaps")).toContainText("head and neck");
  // the time strip: the calf's stretches and the robot's episodes, both clickable
  await expect(page.getByTestId("calf-strip").locator("rect")).toHaveCount(4);
  await expect(page.getByTestId("robot-strip").locator("rect").first()).toBeAttached();
  await page.getByTestId("robot-strip").locator("svg").click(); // seeks the replay
  await expect(page.getByTestId("interpret-play")).toContainText("seed 0");
  expect(errors).toEqual([]);
});
