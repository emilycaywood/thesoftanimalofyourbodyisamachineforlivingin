// Behave (ADR-073): a clip in the motion library shows what the body can play
// of it, previews on the body, and joins the stochastic behaviors, which then
// replace the simulation's controller. Runs on the fresh feral-calf lab of
// playwright.config.ts; the footage import itself is tested in tests/test_behave.py.
import { expect, test } from "@playwright/test";
import { feralPort } from "../playwright.config";

test.use({ baseURL: `http://127.0.0.1:${feralPort}` });

test("a clip is checked against the body, previewed, and played among the stochastic behaviors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // a pawing clip of the front left leg, as an import or Blender would store it
  const frames = 60;
  const paw = Array.from({ length: frames }, (_, i) => 40 * Math.max(0, Math.sin((2 * Math.PI * i) / frames)));
  const shoulder = paw.map((v) => -v / 4);
  await page.request.post("/api/motions", {
    data: { id: "paw-test", name: "paw-test", fps: 30, source: "footage", joints: { "joint.fl.carpus": paw, "joint.fl.shoulder": shoulder } },
  });

  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
  await page.locator('[data-workspace="behave"]').click();
  const panel = page.getByTestId("behave-panel");
  const clip = panel.locator('[data-clip="paw-test"]');
  await expect(clip).toBeVisible();
  await expect(clip).toContainText(/plays|too fast|clamped/);

  await clip.getByRole("button", { name: "Preview" }).click();
  await expect(panel.getByTestId("behave-message")).toContainText("Previewing");

  await panel.getByTestId("add-behavior-paw-test").click();
  await expect(panel.getByTestId("behave-message")).toContainText("switched to the behaviors controller");
  const graph = await (await page.request.get("/api/graph")).json();
  const ctrl = graph.graph.nodes.find((n: { id: string }) => n.id === graph.graph.roles.controller);
  expect(ctrl.type).toBe("controller:behaviors");
  expect(ctrl.params.repertoire.map((e: { name: string }) => e.name)).toContain("paw-test");
  await expect(panel.getByRole("button", { name: "Simulate (F5)" })).toBeVisible();

  // the Simulate panel switches controllers; each comes back with its own settings
  await page.locator(".dv-default-tab", { hasText: /^Simulate$/ }).first().click();
  const picker = page.getByTestId("controller-picker");
  await expect(picker).toHaveValue("controller:behaviors");
  await expect(picker.locator('option[value="controller:cpg"]')).toHaveAttribute("disabled", ""); // drives the reference calf only
  await picker.selectOption("controller:feral_motion");
  await expect(page.getByTestId("simulate-panel").locator('[data-field="mode"] select')).toHaveValue("walk");
  await picker.selectOption("controller:behaviors");
  await expect(picker).toHaveValue("controller:behaviors");
  const again = await (await page.request.get("/api/graph")).json();
  const back = again.graph.nodes.find((n: { id: string }) => n.id === again.graph.roles.controller);
  expect(back.params.repertoire.map((e: { name: string }) => e.name)).toContain("paw-test"); // kept while away

  for (let i = 0; i < 3; i++) await page.request.post("/api/commands/undo");
  await page.locator(".dv-default-tab", { hasText: /^Behave$/ }).first().click();
  await expect(page.getByTestId("behave-panel").getByTestId("use-behaviors")).toBeVisible();
  expect(errors).toEqual([]);
});
