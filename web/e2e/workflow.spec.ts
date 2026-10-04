// Runs and Journal: replaying a run by clicking it, and linking chosen runs
// into a journal entry. (Runs after smoke.spec.ts, which counts its own runs.)
import { expect, test, type Page } from "@playwright/test";

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
}

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
