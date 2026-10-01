// Vitest: view-side logic (command matching, shortcuts, selection semantics, form helpers).
import { describe, expect, it } from "vitest";
import type { CommandInfo, FieldSchema } from "@/api/types";
import { chord, DEFAULT_KEYS } from "@/commands/keys";
import { allCommands, findCommand, matchCommands, normalize, parseArgs } from "@/commands/registry";
import { groupFields, numberStep } from "@/components/schemaLogic";
import { normRect, rectSelect, snapValue } from "@/viewport/viewLogic";
import { WORKSPACES } from "@/workspaces";
import { PANEL_IDS } from "@/panels/ids";

const server: CommandInfo[] = [
  {
    type: "command", key: "run_sim", label: "Simulate", description: "Run", version: "1", stub: false, module: "m",
    schema: { title: "", description: "", fields: [] }, mutates: false, category: "Simulate", shortcut: "F5", aliases: ["sim", "simulate"],
  },
  {
    type: "command", key: "set_genes", label: "Set genes", description: "Set", version: "1", stub: false, module: "m",
    schema: { title: "", description: "", fields: [] }, mutates: true, category: "Form", shortcut: null, aliases: [],
  },
];

describe("command line", () => {
  const cmds = allCommands(server);

  it("gives server commands Rhino-style names", () => {
    expect(cmds.find((c) => c.key === "run_sim")?.name).toBe("RunSim");
    expect(findCommand("setgenes", cmds)?.key).toBe("set_genes");
    expect(findCommand("Set_Genes", cmds)?.key).toBe("set_genes");
  });

  it("resolves aliases and is case-insensitive", () => {
    expect(findCommand("simulate", cmds)?.key).toBe("run_sim");
    expect(findCommand("ZE", cmds)?.name).toBe("ZoomExtents");
    expect(findCommand("zoom extents", cmds)?.name).toBe("ZoomExtents");
    expect(findCommand("nonsense", cmds)).toBeUndefined();
  });

  it("ranks prefix matches before substring matches", () => {
    const names = matchCommands("zoom", cmds).map((c) => c.name);
    expect(names.slice(0, 2).sort()).toEqual(["ZoomExtents", "ZoomSelected"]);
    expect(matchCommands("sim", cmds)[0].key).toBe("run_sim");
    expect(matchCommands("", cmds)).toEqual([]);
  });

  it("parses key=value arguments with types", () => {
    expect(parseArgs(["name=calf", "n=3", "x=1.5", "on=true", "junk"])).toEqual({ name: "calf", n: 3, x: 1.5, on: true });
    expect(normalize("Zoom_Extents ")).toBe("zoomextents");
  });

  it("every default shortcut points at an existing command", () => {
    for (const name of Object.values(DEFAULT_KEYS)) {
      const known = findCommand(name, cmds) ?? ["Undo", "Redo", "Bake"].includes(name);
      expect(known, name).toBeTruthy();
    }
  });
});

describe("shortcuts", () => {
  it("builds canonical chords", () => {
    const base = { ctrlKey: false, metaKey: false, altKey: false, shiftKey: false };
    expect(chord({ ...base, key: "b" })).toBe("B");
    expect(chord({ ...base, ctrlKey: true, shiftKey: true, key: "e" })).toBe("Ctrl+Shift+E");
    expect(chord({ ...base, ctrlKey: true, altKey: true, key: "w" })).toBe("Ctrl+Alt+W");
    expect(chord({ ...base, key: " " })).toBe("Space");
    expect(chord({ ...base, ctrlKey: true, key: "Control" })).toBe("");
  });
});

describe("selection rectangle (Rhino semantics)", () => {
  const boxes = [
    { id: "inside", box: { x0: 20, y0: 20, x1: 40, y1: 40 } },
    { id: "straddling", box: { x0: 90, y0: 20, x1: 130, y1: 40 } },
    { id: "outside", box: { x0: 300, y0: 300, x1: 320, y1: 320 } },
  ];
  const rect = normRect(100, 100, 10, 10);

  it("window (left to right) needs objects fully inside", () => {
    expect(rectSelect(rect, boxes, false)).toEqual(["inside"]);
  });
  it("crossing (right to left) takes anything it touches", () => {
    expect(rectSelect(rect, boxes, true)).toEqual(["inside", "straddling"]);
  });
  it("normalises drag direction", () => {
    expect(rect).toEqual({ x0: 10, y0: 10, x1: 100, y1: 100 });
  });
});

describe("snapping and form helpers", () => {
  it("snaps to the grid step", () => {
    expect(snapValue(172.4, 5)).toBe(170);
    expect(snapValue(172.6, 1)).toBe(173);
    expect(snapValue(172.6, 0)).toBe(172.6);
  });

  const f = (over: Partial<FieldSchema>): FieldSchema => ({
    name: "x", label: "X", type: "number", ui: "slider", default: 0, unit: null, min: null, max: null, step: null,
    description: "", group: null, advanced: false, ...over,
  });

  it("derives a sensible slider step", () => {
    expect(numberStep(f({ step: 0.5 }))).toBe(0.5);
    expect(numberStep(f({ type: "integer", min: 0, max: 10 }))).toBe(1);
    expect(numberStep(f({ min: 300, max: 560 }))).toBe(1);
    expect(numberStep(f({ min: 0.2, max: 0.6 }))).toBe(0.002);
  });

  it("groups fields in first-seen order with ungrouped first", () => {
    const groups = groupFields([f({ name: "a", group: "Legs" }), f({ name: "b" }), f({ name: "c", group: "Trunk" }), f({ name: "d", group: "Legs" })]);
    expect(groups.map(([g, fs]) => [g, fs.map((x) => x.name)])).toEqual([[null, ["b"]], ["Legs", ["a", "d"]], ["Trunk", ["c"]]]);
    expect(groupFields([f({ name: "a", group: "Legs" }), f({ name: "b" })], "Legs")).toHaveLength(1);
  });
});

describe("workspaces", () => {
  it("has the nine workspaces from the brief and only known panels", () => {
    expect(WORKSPACES.map((w) => w.label)).toEqual(["Form", "Mechanism", "Simulate", "Evolve", "Behave", "Fabricate", "Wire", "Deploy", "Journal"]);
    for (const w of WORKSPACES) {
      for (const id of [...w.center, ...w.left, ...w.right, ...w.bottom]) expect(PANEL_IDS, `${w.id}: ${id}`).toContain(id);
    }
  });
});
