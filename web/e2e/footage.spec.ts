// The video inbox (ADR-076): a video dropped into the project's footage/videos
// folder is picked up by the lab's watcher, tracked, cut into candidates, and
// reviewed in the Behave panel: the frame with its tracked points, a preview on
// the robot, and acceptance as a clip with the researcher's affect tags. Uses the
// synthetic stick calf and the colour-marker tracker, on the feral-calf lab of
// playwright.config.ts.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { feralPort } from "../playwright.config";

test.use({ baseURL: `http://127.0.0.1:${feralPort}` });

test("a dropped video is tracked, reviewed and accepted as a tagged clip", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const inbox = await (await page.request.get("/api/footage")).json();
  const settings = await page.request.post("/api/commands/set_footage_settings", {
    data: { tracker: "synthetic", map: "feral_calf_side", auto_side: true },
  });
  expect(settings.ok()).toBeTruthy();
  const project = path.dirname(path.dirname(inbox.dir));
  execFileSync(process.env.CALFLAB_PYTHON ?? "python",
    ["-m", "calflab.cli.main", "tracker", "synthetic", path.join(inbox.dir, "stick.avi"), "--project", project],
    { cwd: process.env.CALFLAB_REPO ?? path.resolve(process.cwd(), "..") });

  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  await page.locator('[data-workspace="behave"]').click();
  const panel = page.getByTestId("behave-panel");
  const row = panel.locator('[data-video="stick.avi"]');
  await expect(row).toContainText("needs review", { timeout: 60_000 }); // the watcher polls every 2 s
  await expect(row).toContainText("3 candidates");

  await panel.getByTestId("review-stick.avi").click();
  await panel.getByTestId("candidate-c2").click();
  await expect(panel.getByTestId("review-frame").locator("img")).toBeVisible();
  await expect(panel.getByTestId("review-frame").locator("circle").first()).toBeVisible(); // tracked points drawn
  await panel.getByTestId("preview-candidate").click();
  await expect(panel.getByTestId("candidate-report")).toContainText(/plays|too fast|clamped/);

  const form = panel.locator('[data-field="name"]').first();
  await form.locator("input").fill("calm walk");
  await panel.locator('[data-unset="arousal"]').click();
  await panel.locator('[data-field="words"] input').first().fill("steady, curious");
  await panel.getByTestId("accept-candidate").click();
  await expect(panel.getByTestId("behave-message")).toContainText("Accepted as clip calm-walk");
  await expect(panel.getByTestId("clip-tags-calm-walk")).toContainText("curious");

  const clip = await (await page.request.get("/api/motions/calm-walk")).json();
  expect(clip.affect.words).toEqual(["steady", "curious"]);
  expect(clip.affect.valence).toBeNull();
  expect(clip.meta.video_sha256).toHaveLength(64);
  expect(clip.meta.tracker.tracker).toBe("synthetic");
  expect(errors).toEqual([]);
});
