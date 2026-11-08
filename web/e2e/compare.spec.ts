import { expect, test, type Page } from "@playwright/test";

// compare.html?set=<key> (ADR-106): one picker switches every cell. The manifest is a fixture served in place of
// /api/compare/e2e (the e2e project has none of R12's runs; the manifest itself is tested in tests/test_compare.py),
// and each cell's embedded lab is a stub that answers like the real one: "ready" after a load, and it records the
// playback messages it gets.

const BODIES = ["working", "g007-002", "g009-000"];
const seedPlays = (play: string, body: string, badges: string[]) =>
  [0, 1, 2].map((seed) => ({
    seed,
    run: `run-${play}-${body}-s${seed}`,
    badge: badges[seed],
    margin: badges[seed] === "over" ? -0.2 : 0.3,
    limit: badges[seed] === "over" ? "fl.carpus sustained belt tension" : null,
    text: badges[seed],
    href: `/?replay=run-${play}-${body}-s${seed}`,
  }));
const item = (key: string, label: string, kind: string, empty: string[] = []) => ({
  key,
  label,
  kind,
  cells: BODIES.map((body) =>
    empty.includes(body)
      ? { body, play: null, playing: null, match: "no matching behaviour", empty: true, message: "no matching behaviour", seeds: [] }
      : {
          body,
          play: key,
          playing: `${label} on ${body}`,
          match: kind === "own" ? "same generator" : null,
          empty: false,
          message: null,
          seeds: seedPlays(key.replace(/[^a-z0-9]/gi, ""), body, ["within", "near", "over"]),
        },
  ),
});
const MANIFEST = {
  set: "e2e",
  title: "e2e bodies",
  seeds: [0, 1, 2],
  near: 0.1,
  stored: 1,
  missing: 0,
  hint: "",
  bodies: BODIES.map((key) => ({ key, label: key, line: "11 held · trot - mm/s · lie_rise -3.00 · cost 0.00", stage_c_run: "x" })),
  groups: [
    { key: "screen", title: "Screen plays (every body)", items: [item("screen:lie_rise", "lie_rise", "screen"), item("screen:walk", "walk", "screen")] },
    { key: "shared", title: "Shared behaviours", items: [item("shared:R7-calm", "R7-calm", "shared")] },
    { key: "own", title: "Own behaviours (Stage C)", items: [item("own:0:1-5", "from R7-calm · cell 1,5", "own", ["g009-000"])] },
  ],
};

const STUB = `<!doctype html><html><body><script>
  const tell = (run) => parent.postMessage({ calflab: "embed", event: "ready", run }, location.origin);
  document.body.dataset.run = new URLSearchParams(location.search).get("replay");
  document.body.dataset.actions = "";
  addEventListener("message", (e) => {
    const d = e.data;
    if (!d || d.calflab !== "playback") return;
    document.body.dataset.actions += d.action + ",";
    if (d.action === "load") { document.body.dataset.run = d.run; setTimeout(() => tell(d.run), 50); }
  });
  setTimeout(() => tell(document.body.dataset.run), 50);
</script></body></html>`;

async function cellRuns(page: Page): Promise<string[]> {
  return page.locator('[data-testid="cell"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.run ?? ""));
}

/** What each embedded cell is showing and the playback messages it got. */
async function frameState(page: Page): Promise<{ run: string; actions: string }[]> {
  const out = [];
  for (const f of page.frames()) {
    if (f === page.mainFrame()) continue;
    out.push(await f.evaluate(() => ({ run: document.body.dataset.run ?? "", actions: document.body.dataset.actions ?? "" })));
  }
  return out;
}

test("one picker switches every cell to a behaviour, restarts them together and shows the badges", async ({ page }) => {
  await page.route("**/api/compare/e2e", (r) => r.fulfill({ json: MANIFEST }));
  await page.route(
    (u) => u.pathname === "/" && u.searchParams.get("embed") === "1",
    (r) => r.fulfill({ contentType: "text/html", body: STUB }),
  );
  await page.goto("/compare.html?set=e2e");

  const cells = page.locator('[data-testid="cell"]');
  await expect(cells).toHaveCount(3);
  await expect(page.getByTestId("picker")).toHaveValue("screen:lie_rise");
  await expect(cells.first().getByTestId("playing")).toHaveText("lie_rise on working");
  await expect(page.getByTestId("status")).toHaveText("");
  const before = await cellRuns(page);
  expect(before).toEqual(BODIES.map((b) => `run-screenlierise-${b}-s0`));
  // seed 0: within (green); every cell got "restart" once all were ready
  await expect(cells.first().getByTestId("badge")).toHaveClass(/within/);
  await expect.poll(async () => (await frameState(page)).every((f) => f.actions.includes("restart"))).toBe(true);

  // ↓ switches every cell to the next behaviour and restarts them together
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("picker")).toHaveValue("screen:walk");
  const after = await cellRuns(page);
  expect(after).toEqual(BODIES.map((b) => `run-screenwalk-${b}-s0`));
  for (let i = 0; i < 3; i++) expect(after[i]).not.toBe(before[i]);
  await expect(cells.nth(2).getByTestId("playing")).toHaveText("walk on g009-000");
  await expect
    .poll(async () => (await frameState(page)).map((f) => [f.run, f.actions.includes("load,restart,")]))
    .toEqual(BODIES.map((b) => [`run-screenwalk-${b}-s0`, true]));
  await expect(page).toHaveURL(/item=screen%3Awalk/);

  // ] steps into the next group; [ back
  await page.keyboard.press("]");
  await expect(page.getByTestId("picker")).toHaveValue("shared:R7-calm");
  await page.keyboard.press("[");
  await expect(page.getByTestId("picker")).toHaveValue("screen:walk");

  // seed 2 for every cell: over (red) with the limit that stopped it
  await page.getByRole("button", { name: "seed 2" }).click();
  expect(await cellRuns(page)).toEqual(BODIES.map((b) => `run-screenwalk-${b}-s2`));
  await expect(cells.first().getByTestId("badge")).toHaveClass(/over/);
  await expect(cells.first()).toContainText("stopped by fl.carpus sustained belt tension");

  // an own behaviour a body has no match for: that cell says so
  await page.getByTestId("picker").selectOption("own:0:1-5");
  await expect(cells.nth(2)).toContainText("no matching behaviour");
  await expect(cells.nth(0).getByTestId("playing")).toHaveText("from R7-calm · cell 1,5 on working");

  // Space pauses every cell; the title opens that body and play in the full lab
  await page.keyboard.press("Space");
  await expect(page.getByTestId("play")).toHaveText("Play all");
  await expect.poll(async () => (await frameState(page)).filter((f) => f.actions.endsWith("pause,")).length).toBeGreaterThanOrEqual(2);
  await expect(cells.first().locator("a.label")).toHaveAttribute("href", "/?replay=run-own015-working-s2");
});
