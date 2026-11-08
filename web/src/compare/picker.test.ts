import { describe, expect, it } from "vitest";
import {
  actionForKey,
  current,
  elapsed,
  initPicker,
  reduce,
  restartClock,
  setClockPlaying,
  type PickerItem,
} from "./picker";

const items: PickerItem[] = [
  { key: "screen:lie_rise", label: "lie_rise", group: "screen" },
  { key: "screen:walk", label: "walk", group: "screen" },
  { key: "shared:R7-calm", label: "R7-calm", group: "shared" },
  { key: "own:0:1-5", label: "from R7-calm · cell 1,5", group: "own" },
];

describe("compare picker", () => {
  it("starts at the first item and seed, playing, or at the ones in the URL", () => {
    const s = initPicker(items, [0, 1, 2]);
    expect(current(s)?.key).toBe("screen:lie_rise");
    expect(s.seed).toBe(0);
    expect(s.playing).toBe(true);
    const u = initPicker(items, [0, 1, 2], { item: "shared:R7-calm", seed: 2 });
    expect(current(u)?.key).toBe("shared:R7-calm");
    expect(u.seed).toBe(2);
    const bad = initPicker(items, [0, 1, 2], { item: "nope", seed: 7 });
    expect(bad.index).toBe(0);
    expect(bad.seed).toBe(0);
  });

  it("steps across groups, stops at the ends, and restarts every cell on each change", () => {
    let s = initPicker(items, [0, 1, 2]);
    s = reduce(s, { type: "step", delta: -1 });
    expect(s.index).toBe(0);
    expect(s.epoch).toBe(0); // nothing changed, nothing restarts
    s = reduce(s, { type: "step", delta: 1 });
    s = reduce(s, { type: "step", delta: 1 });
    expect(current(s)?.group).toBe("shared");
    expect(s.epoch).toBe(2);
    s = reduce(s, { type: "step", delta: 5 });
    expect(current(s)?.key).toBe("own:0:1-5");
    expect(reduce(s, { type: "step", delta: 1 })).toBe(s);
  });

  it("a new behaviour or seed plays again from the start; play/pause keeps the behaviour", () => {
    let s = initPicker(items, [0, 1, 2]);
    s = reduce(s, { type: "togglePlay" });
    expect(s.playing).toBe(false);
    const e = s.epoch;
    s = reduce(s, { type: "select", key: "screen:walk" });
    expect(s.playing).toBe(true);
    expect(s.epoch).toBe(e + 1);
    s = reduce(s, { type: "seed", seed: 1 });
    expect(s.seed).toBe(1);
    expect(s.epoch).toBe(e + 2);
    expect(reduce(s, { type: "seed", seed: 9 })).toBe(s); // not a seed of the set
    s = reduce(s, { type: "pause" });
    s = reduce(s, { type: "restart" });
    expect(s.playing).toBe(true);
    expect(s.epoch).toBe(e + 3);
    expect(current(s)?.key).toBe("screen:walk");
  });

  it("maps the keys: arrows and brackets step, Space plays or pauses, R restarts", () => {
    expect(actionForKey("ArrowUp")).toEqual({ type: "step", delta: -1 });
    expect(actionForKey("[")).toEqual({ type: "step", delta: -1 });
    expect(actionForKey("ArrowDown")).toEqual({ type: "step", delta: 1 });
    expect(actionForKey("]")).toEqual({ type: "step", delta: 1 });
    expect(actionForKey(" ")).toEqual({ type: "togglePlay" });
    expect(actionForKey("r")).toEqual({ type: "restart" });
    expect(actionForKey("R")).toEqual({ type: "restart" });
    expect(actionForKey("x")).toBeNull();
  });

  it("the shared clock counts seconds since the restart and stops while paused", () => {
    let c = restartClock(1000, true);
    expect(elapsed(c, 3000)).toBeCloseTo(2);
    c = setClockPlaying(c, 3000, false);
    expect(elapsed(c, 9000)).toBeCloseTo(2);
    c = setClockPlaying(c, 9000, true);
    expect(elapsed(c, 10_500)).toBeCloseTo(3.5);
    expect(elapsed(restartClock(5000, false), 8000)).toBe(0);
  });
});
