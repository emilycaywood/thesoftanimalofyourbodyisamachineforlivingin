// Runs, Journal, Designs and Evolve: replaying a run by clicking it, linking
// chosen runs into a journal entry, evolving from a baked design and reading a
// candidate's genes. (Runs after smoke.spec.ts, which counts its own runs.)
import { expect, test, type Page } from "@playwright/test";

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
}

const tab = (page: Page, title: string) => page.locator(".dv-default-tab", { hasText: new RegExp(`^${title}$`) }).first();
const command = (page: Page, name: string, data: Record<string, unknown> = {}) => page.request.post(`/api/commands/${name}`, { data });

async function simulate(page: Page, genes: Record<string, unknown>): Promise<string> {
  const before = (await (await page.request.get("/api/runs?kind=sim")).json()) as { id: string }[];
  await page.request.post("/api/commands/set_genes", { data: { values: genes } });
  await page.request.post("/api/commands/run_sim", { data: {} });
  let id = "";
  await expect
    .poll(async () => {
      const runs = (await (await page.request.get("/api/runs?kind=sim")).json()) as { id: string }[];
      id = runs.find((r) => !before.some((b) => b.id === r.id))?.id ?? "";
      return id;
    }, { timeout: 90_000 })
    .not.toBe("");
  return id;
}

test("clicking a run replays it; the journal links chosen runs", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);
  const first = await simulate(page, { trunk_length: 400 });
  const second = await simulate(page, { trunk_length: 440 });

  // Journal workspace: the viewport is beside the journal, the runs are on the right
  await page.locator('[data-workspace="journal"]').click();
  await expect(page.getByTestId("journal-panel")).toBeVisible();
  await expect(page.getByTestId("viewport")).toBeVisible();
  const stop = page.getByRole("button", { name: /Playback/ });
  if (await stop.isVisible()) await stop.click(); // the second sim is still on the timeline
  await expect(stop).toBeHidden();

  await page.locator(`[data-run="${first}"]`).click();
  await expect(page.locator(`[data-run="${first}"]`)).toHaveAttribute("data-current", "true");
  await expect(stop).toBeVisible(); // the viewport is replaying
  await expect(page.getByTestId("last-log")).toContainText(`Replaying run ${first}`);

  // link the run selected in Runs, then a different one from the list, without typing an id
  await page.getByRole("button", { name: "New entry" }).click();
  await page.getByPlaceholder("Title").fill("Two trunks");
  const editor = page.getByPlaceholder("Write in Markdown...");
  await editor.fill("Short trunk:");
  const link = page.getByTestId("link-run");
  await expect(link.locator("option").nth(1)).toHaveText(`Selected in Runs: ${first}`);
  await link.selectOption({ index: 1 });
  await editor.press("End");
  await editor.pressSequentially("and long trunk:");
  await link.selectOption(second);
  await expect(editor).toHaveValue(`Short trunk: calflab://run/${first} and long trunk: calflab://run/${second} `);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: `run:${first}` })).toBeVisible();

  // a link in the saved entry replays that run
  await page.getByRole("button", { name: `run:${second}` }).click();
  await expect(page.locator(`[data-run="${second}"]`)).toHaveAttribute("data-current", "true");

  expect(errors).toEqual([]);
});

test("evolve from a baked design and compare candidates by their genes", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);

  // a design with one long leg, baked; then the document goes back to the plain calf
  await command(page, "reset_genes");
  await command(page, "clear_overrides");
  await command(page, "add_override", { target: "leg.fl.shank", param: "length", value: 200 });
  const baked = (await (await command(page, "bake", { name: "long fl shank e2e" })).json()).result.design as string;
  await command(page, "clear_overrides");

  // browse the baked designs in the Evolve workspace and start from one
  await page.locator('[data-workspace="evolve"]').click();
  await tab(page, "Designs").click();
  await page.locator(`[data-design="${baked}"]`).getByTestId("design-evolve").click();
  await expect(page.getByTestId("evolve-start-from")).toHaveValue(baked);
  await expect(page.getByTestId("evolve-start-note")).toContainText("the working document is not changed");
  for (const [field, value] of [["generations", "1"], ["batch_size", "6"], ["inner_iterations", "0"]]) {
    const input = page.locator(`[data-field="${field}"] input[type="text"]`);
    await input.fill(value);
    await input.press("Enter");
  }
  await page.getByTestId("evolve-start").click();

  // the run record names the design it started from
  let run: { id: string; status: string; parent: string | null } | undefined;
  await expect
    .poll(async () => {
      const runs = (await (await page.request.get("/api/runs?kind=evolve")).json()) as NonNullable<typeof run>[];
      run = runs.find((r) => r.parent === baked);
      return run?.status;
    }, { timeout: 110_000 })
    .toBe("done");
  const record = await (await page.request.get(`/api/runs/${run!.id}`)).json();
  expect(record.inputs.start).toEqual({ source: "design", design: baked });
  expect(record.overrides.map((o: { target: string }) => o.target)).toEqual(["leg.fl.shank"]);
  expect((await (await page.request.get("/api/state")).json()).overrides).toEqual([]); // the document was left alone

  await tab(page, "Archive").click();
  await expect(page.getByTestId("evolve-started-from")).toContainText(`Started from baked design ${baked}`);
  await expect(page.locator(`[data-evolve-run="${run!.id}"]`)).toContainText(`from ${baked}`);

  // click a cell: its genes, as differences, without adopting it
  const cells = page.locator("[data-cell]");
  await expect.poll(() => cells.count()).toBeGreaterThan(1);
  await cells.nth(0).click();
  const genes = page.getByTestId("candidate-genes");
  await expect(genes).toContainText("vs current design");
  await expect(page.getByTestId("candidate-overrides")).toContainText("leg.fl.shank.length = 200");
  await genes.getByLabel("show unchanged").check();
  await expect.poll(() => genes.locator("[data-gene]").count()).toBeGreaterThan(25); // every gene, not only the changed ones
  await expect(genes.locator('[data-gene="thigh_length"]')).toBeVisible();

  // pin it and click another cell: a third column compares the two bodies
  await page.getByTestId("pin").click();
  await cells.nth(1).click();
  await expect(genes).toContainText("vs pinned");
  expect((await (await page.request.get("/api/state")).json()).overrides).toEqual([]);

  // load the baked design into the working document, and undo
  await tab(page, "Designs").click();
  await page.locator(`[data-design="${baked}"]`).getByTestId("design-load").click();
  await expect.poll(async () => (await (await page.request.get("/api/state")).json()).overrides.length).toBe(1);
  await expect(page.getByTestId("last-log")).toContainText(baked);
  await page.getByTestId("undo").click();
  await expect.poll(async () => (await (await page.request.get("/api/state")).json()).overrides.length).toBe(0);

  expect(errors).toEqual([]);
});
