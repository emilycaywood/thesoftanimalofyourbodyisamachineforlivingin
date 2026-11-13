// Simulation playback: body poses streamed from the server or loaded from a
// recorded run. The viewport reads `frame` every animation frame without
// re-rendering React.
import { create } from "zustand";
import { api } from "@/api/client";
import type { Channel, RolloutPayload, Scene, Vec3 } from "@/api/types";
import { onLabEvent, useLab } from "./lab";

interface PlaybackStore {
  source: "none" | "live" | "run";
  runId: string | null;
  jobId: string | null;
  bodyIds: string[];
  t: number[];
  pos: number[][];
  quat: number[][];
  scene: Scene | null; // the scene the poses belong to (may differ from the document)
  com: Vec3[];
  support: [number, number][][];
  footPos: Vec3[][];
  footForce: number[][];
  series: Record<string, Channel>;
  metrics: Record<string, any> | null;
  /** what the controller did in the run, e.g. the behaviors it chose */
  controllerLog: { episodes?: { name: string; kind: string; t0: number; t1: number; composition?: { label?: string }; [k: string]: unknown }[] } | null;
  frame: number; // fractional frame index
  playing: boolean;
  speed: number;
  loop: boolean;
  setFrame: (f: number) => void;
  toggle: () => void;
  set: (patch: Partial<PlaybackStore>) => void;
  /** Load a recorded run; resolves false (and changes nothing) if another load or a live run started meanwhile. */
  loadRun: (runId: string, autoplay?: boolean) => Promise<boolean>;
  clear: () => void;
}

const EMPTY = {
  source: "none" as const,
  runId: null,
  jobId: null,
  bodyIds: [] as string[],
  t: [] as number[],
  pos: [] as number[][],
  quat: [] as number[][],
  scene: null,
  com: [] as Vec3[],
  support: [] as [number, number][][],
  footPos: [] as Vec3[][],
  footForce: [] as number[][],
  series: {} as Record<string, Channel>,
  metrics: null,
  controllerLog: null,
  frame: 0,
  playing: false,
};

// Each load (and each live run) takes a ticket; a response whose ticket is no longer the latest is dropped, so a slow
// earlier load can never overwrite a later one (compare.html switches cells quickly).
let loadTicket = 0;

export const usePlayback = create<PlaybackStore>((set, get) => ({
  ...EMPTY,
  speed: 1,
  loop: true,
  setFrame: (f) => set({ frame: Math.max(0, Math.min(f, Math.max(0, get().t.length - 1))) }),
  toggle: () => {
    const s = get();
    if (!s.t.length) return;
    if (!s.playing && s.frame >= s.t.length - 1) set({ frame: 0 });
    set({ playing: !get().playing });
  },
  set: (patch) => set(patch),
  clear: () => {
    loadTicket += 1;
    set({ ...EMPTY });
  },
  loadRun: async (runId, autoplay = true) => {
    const ticket = ++loadTicket;
    const r = await api.get<RolloutPayload>(`/api/runs/${runId}/rollout`);
    if (ticket !== loadTicket) return false;
    set({
      source: "run",
      runId,
      jobId: null,
      bodyIds: r.body_ids,
      t: r.t,
      pos: r.pos,
      quat: r.quat,
      scene: r.scene,
      com: r.com,
      support: r.support,
      footPos: r.foot_pos,
      footForce: r.foot_force,
      series: r.series.channels,
      metrics: r.metrics,
      controllerLog: r.controller_log ?? null,
      frame: autoplay ? 0 : Math.min(get().frame, r.t.length - 1),
      playing: autoplay,
    });
    return true;
  },
}));

/** Wire the event stream into the playback store (call once). */
export function connectPlayback(): () => void {
  return onLabEvent((e) => {
    const s = usePlayback.getState();
    if (e.type === "sim.started") {
      loadTicket += 1; // a live run replaces whatever was loading
      usePlayback.setState({
        ...EMPTY,
        source: "live",
        jobId: e.job,
        bodyIds: e.body_ids,
        scene: e.scene,
        playing: true,
      });
    } else if (e.type === "sim.frames" && s.source === "live" && s.jobId === e.job) {
      usePlayback.setState({ t: s.t.concat(e.t), pos: s.pos.concat(e.pos), quat: s.quat.concat(e.quat) });
    } else if (e.type === "sim.done" && (s.jobId === e.job || s.source === "none")) {
      // switch from the live stream to the recorded run (adds metrics, series, overlays)
      const keep = s.source === "live" && !e.cached ? s.frame : 0;
      void usePlayback
        .getState()
        .loadRun(e.run_id, true)
        .then((applied) => {
          if (applied) usePlayback.setState({ frame: keep });
        })
        .catch((err) => useLab.getState().log("error", String(err.message ?? err), "playback"));
    }
  });
}

/** Pose of every body at the current (fractional) frame, or null when idle. */
export function currentFrameIndex(): number {
  const s = usePlayback.getState();
  if (s.source === "none" || !s.t.length) return -1;
  return Math.max(0, Math.min(Math.round(s.frame), s.t.length - 1));
}
