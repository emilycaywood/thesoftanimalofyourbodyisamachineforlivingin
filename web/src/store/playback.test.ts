// Vitest: a slow earlier load never overwrites a later one (compare.html switches cells quickly, ADR-125).
import { beforeEach, describe, expect, it, vi } from "vitest";

const pending = new Map<string, (v: unknown) => void>();
vi.mock("@/api/client", () => ({
  api: {
    get: (url: string) => new Promise((resolve) => pending.set(url, resolve)),
  },
}));
vi.mock("./lab", () => ({ onLabEvent: () => () => {}, useLab: { getState: () => ({ log: () => {} }) } }));

import { usePlayback } from "./playback";

function payload(n: number) {
  return {
    body_ids: ["trunk"], t: Array.from({ length: n }, (_, i) => i * 0.02), pos: [], quat: [], scene: null, com: [],
    support: [], foot_pos: [], foot_force: [], series: { channels: {} }, metrics: null,
  };
}

describe("loadRun", () => {
  beforeEach(() => {
    pending.clear();
    usePlayback.getState().clear();
  });

  it("drops a response that arrives after a later load", async () => {
    const a = usePlayback.getState().loadRun("trot", false);
    const b = usePlayback.getState().loadRun("lie", false);
    pending.get("/api/runs/lie/rollout")!(payload(388)); // the later (smaller) load answers first
    expect(await b).toBe(true);
    pending.get("/api/runs/trot/rollout")!(payload(1521));
    expect(await a).toBe(false);
    expect(usePlayback.getState().runId).toBe("lie");
    expect(usePlayback.getState().t.length).toBe(388);
  });

  it("applies a load that is still the latest", async () => {
    const a = usePlayback.getState().loadRun("walk", true);
    pending.get("/api/runs/walk/rollout")!(payload(10));
    expect(await a).toBe(true);
    expect(usePlayback.getState().runId).toBe("walk");
  });
});
