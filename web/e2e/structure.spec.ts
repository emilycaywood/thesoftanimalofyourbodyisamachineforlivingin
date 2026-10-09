// Material and mass of a part: choosing a material in Properties, entering a
// weighed mass, and a solid pushed from Rhino (sent here as the bridge sends
// it) giving the trunk its mass. (Runs after smoke.spec.ts; leaves the
// document as it found it.)
import { expect, test, type Page } from "@playwright/test";

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText(/Connected/);
  await page.getByTestId("tour-skip").click();
}

const tab = (page: Page, title: string) => page.locator(".dv-default-tab", { hasText: new RegExp(`^${title}$`) }).first();
const command = (page: Page, name: string, data: Record<string, unknown> = {}) => page.request.post(`/api/commands/${name}`, { data });
const grams = async (page: Page, id: string) => Number((await page.getByTestId(id).innerText()).replace(/[^\d.]/g, ""));
// the Form panel's readout shares a tab group with Properties, so the total is read from the server
const total = async (page: Page) => (await (await page.request.get("/api/scene")).json()).mass.total_g as number;

/** A 100 mm cube centred on a point, as triangles (optionally without its top face). */
function cube(c: number[], open = false) {
  const h = 50;
  const vertices = [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => [-1, 1].map((z) => [c[0] + x * h, c[1] + y * h, c[2] + z * h])));
  const faces = [
    [0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
    [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3],
  ];
  return { vertices, faces: open ? faces.slice(0, 10) : faces };
}

test("choose a part's material, weigh it, and take the trunk's mass from a pushed solid", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await command(page, "reset_genes");
  await command(page, "clear_overrides");
  await open(page);
  const props = page.getByTestId("properties");
  const total0 = await total(page);
  expect(await grams(page, "mass-total")).toBe(Math.round(total0));

  // --- material of a parametric part: a select in Properties, recorded as an override
  await page.locator('[data-tree-id="leg.fl.shank"]').click();
  await tab(page, "Properties").click();
  const material = props.getByTestId("part-material");
  await expect(material).toHaveValue("petg");
  await expect(props.getByTestId("part-mass-source")).toContainText("Parametric estimate");
  const petg = await grams(page, "part-mass");
  expect(petg).toBeGreaterThan(5);
  await material.selectOption("pla");
  await expect.poll(() => grams(page, "part-mass")).toBeCloseTo((petg * 1.24) / 1.27, 1);
  await expect(material).toHaveValue("pla");
  await tab(page, "Overrides").click();
  await expect(page.locator("[data-override]")).toHaveCount(1);
  await expect(page.locator("[data-override]")).toContainText("leg.fl.shank · material = pla");
  await page.getByTestId("undo").click();
  await expect(page.locator("[data-override]")).toHaveCount(0);
  await tab(page, "Properties").click();
  await expect(material).toHaveValue("petg");
  await expect.poll(() => grams(page, "part-mass")).toBe(petg);

  // --- a weighed part: the measured value is used, the computed one stays visible
  const measured = props.getByTestId("part-measured");
  await measured.fill("31.5");
  await measured.press("Enter");
  await expect(props.getByTestId("part-mass")).toHaveText("31.5 g");
  await expect(props.getByTestId("part-mass-source")).toContainText("Measured");
  await expect.poll(() => grams(page, "part-mass-computed")).toBe(petg);
  await measured.fill("");
  await measured.press("Enter");
  await expect(props.getByTestId("part-mass-source")).toContainText("Parametric estimate");

  // --- a closed 100 mm cube pushed onto the trunk's Structure with PLA: 1000 cm3 x 1.24 g/cm3
  const scene = await (await page.request.get("/api/scene")).json();
  const origin = scene.bodies.find((b: { id: string }) => b.id === "trunk").pos as number[];
  const before = scene.mass.breakdown.bodies.find((r: { body: string }) => r.body === "trunk").structure.mass_g as number;
  const push = (open: boolean) =>
    page.request.post("/api/bridge/rhino/push", {
      data: { target: "trunk", layer: "Structure", name: "cube", material: "pla", ...cube(origin, open) },
    });
  const reply = await (await push(false)).json();
  expect(reply.mass_from_geometry).toBe(true);
  await page.locator('[data-tree-id="trunk"]').click();
  await expect(props.getByTestId("part-mass")).toHaveText("1240 g");
  await expect(props.getByTestId("part-mass-source")).toContainText("Pushed solid");
  await expect(material).toHaveValue("pla");
  await expect(props).toContainText("not counted"); // the envelope estimate it replaced
  expect(await total(page)).toBeCloseTo(total0 + 1240 - before, 0);

  // the same solid in another material, chosen in Properties
  await material.selectOption("petg");
  await expect(props.getByTestId("part-mass")).toHaveText("1270 g");

  // --- the breakdown panel: source per part, and the total
  await tab(page, "Mass").click();
  const panel = page.getByTestId("mass-panel");
  await expect(panel.locator('[data-mass-body="trunk"]')).toContainText("geometry");
  await expect(panel.locator('[data-mass-body="leg.fl.shank"]')).toContainText("estimate");
  await expect(panel.locator('[data-mass-source="geometry"]')).toContainText("1270");
  await panel.locator('[data-mass-body="trunk"]').click(); // opens the part: its motors, boards and skin
  await expect(panel.locator('[data-mass-item="act.fl.hip_abd.motor"]')).toContainText("component");
  await expect(panel.locator('[data-mass-item="trunk.skin"]')).toContainText("estimate");
  const target = panel.getByTestId("mass-target");
  await target.fill("6000");
  await target.press("Enter");
  await tab(page, "Form").click();
  await expect(page.getByTestId("mass-readout")).toContainText("/ 6000 g");
  await tab(page, "Mass").click();

  // --- two solids in one push, each with its own material (as CalflabPush sends several objects)
  await page.request.post("/api/bridge/rhino/push", {
    data: {
      target: "trunk", layer: "Structure", name: "two solids",
      parts: [
        { name: "body", material: "pla", ...cube(origin) },
        { name: "rod", material: "petg", ...cube([origin[0] + 150, origin[1], origin[2]]) },
      ],
    },
  });
  await expect(panel.locator('[data-mass-body="trunk"]')).toContainText("petg + pla");
  await expect(panel.locator('[data-mass-body="trunk"]')).toContainText("geometry");
  await tab(page, "Properties").click();
  await expect(props.getByTestId("part-materials")).toHaveText("petg + pla");
  await expect(props.getByTestId("part-mass")).toHaveText("2510 g"); // 1000 cm3 x 1.24 + 1000 cm3 x 1.27
  await expect(props.locator("[data-part-solid]")).toHaveCount(2);
  await expect(props.getByTestId("part-com")).toContainText("mm");
  await tab(page, "Mass").click();

  // --- an open solid is shown, warned about, and not used for mass
  await push(true);
  await expect(panel.getByTestId("design-warning")).toContainText("not used for mass: it is open (4 naked edges)");
  await expect(panel.locator('[data-mass-body="trunk"]')).toContainText("estimate");
  await tab(page, "Properties").click();
  await expect(props.getByTestId("part-mass-note")).toContainText("The parametric estimate is kept");
  await expect.poll(() => grams(page, "part-mass")).toBeCloseTo(before, 1);

  await command(page, "clear_overrides");
  await command(page, "set_mass_target", { mass_g: 0 });
  await expect.poll(() => total(page)).toBe(total0);
  expect(errors).toEqual([]);
});

test("a small calf: the Form sliders stay in real millimetres", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await command(page, "reset_genes");
  await open(page);
  const field = (name: string) => page.locator(`[data-field="${name}"] input[type="text"]`);
  const genes = async () => (await (await page.request.get("/api/scene")).json()).genome.values as Record<string, number>;
  await expect(field("thigh_length")).toHaveValue("170");

  await field("scale").fill("0.33");
  await field("scale").press("Enter");
  await expect(field("thigh_length")).toHaveValue("56.1"); // 170 x 0.33, as it measures on the body
  await expect(field("trunk_length")).toHaveValue("138.6");
  await expect(field("wall_thickness")).toHaveValue("2"); // a printed wall does not shrink
  await expect(page.getByTestId("mass-readout")).toContainText("height 201 mm");
  expect((await genes()).thigh_length).toBe(170); // stored at full size

  await field("thigh_length").fill("60");
  await field("thigh_length").press("Enter");
  await expect.poll(async () => (await genes()).thigh_length).toBeCloseTo(60 / 0.33, 3);
  await expect(field("thigh_length")).toHaveValue("60");
  await page.locator('[data-tree-id="leg.fl.thigh"]').click();
  await tab(page, "Properties").click();
  await expect(page.getByTestId("properties").locator('[data-param="length"] input')).toHaveValue("60"); // the same number

  await command(page, "reset_genes");
  expect(errors).toEqual([]);
});

test.afterEach(async ({ page }) => {
  // whatever happened above, the tests that follow start from the plain calf
  await command(page, "clear_overrides");
  await command(page, "set_mass_target", { mass_g: 0 });
  await command(page, "reset_genes");
});
