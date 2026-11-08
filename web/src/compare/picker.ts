// State of compare.html's group behaviour picker (ADR-106). View state only: which behaviour and seed every cell
// shows, whether they play, and the shared clock that keeps them in step. What the behaviours are, how they match
// across bodies and whether a play held all come from the server's manifest (/api/compare/<set>).

export interface PickerItem {
  key: string;
  label: string;
  group: string;
}

export interface PickerState {
  items: PickerItem[];
  index: number;
  seeds: number[];
  seed: number;
  playing: boolean;
  /** bumped whenever every cell must restart together (new behaviour, new seed, R) */
  epoch: number;
}

export type PickerAction =
  | { type: "step"; delta: number }
  | { type: "select"; key: string }
  | { type: "seed"; seed: number }
  | { type: "togglePlay" }
  | { type: "play" }
  | { type: "pause" }
  | { type: "restart" };

export function initPicker(
  items: PickerItem[],
  seeds: number[],
  want: { item?: string | null; seed?: number | null } = {},
): PickerState {
  const i = want.item ? items.findIndex((it) => it.key === want.item) : -1;
  const seed = want.seed != null && seeds.includes(want.seed) ? want.seed : (seeds[0] ?? 0);
  return { items, index: Math.max(0, i), seeds, seed, playing: true, epoch: 0 };
}

export function current(s: PickerState): PickerItem | null {
  return s.items[s.index] ?? null;
}

/** A change of what is shown restarts every cell together and plays. */
function restartAll(s: PickerState, patch: Partial<PickerState>): PickerState {
  return { ...s, ...patch, playing: true, epoch: s.epoch + 1 };
}

export function reduce(s: PickerState, a: PickerAction): PickerState {
  switch (a.type) {
    case "step": {
      if (!s.items.length) return s;
      const index = Math.max(0, Math.min(s.items.length - 1, s.index + a.delta));
      return index === s.index ? s : restartAll(s, { index });
    }
    case "select": {
      const index = s.items.findIndex((it) => it.key === a.key);
      return index < 0 || index === s.index ? s : restartAll(s, { index });
    }
    case "seed":
      return !s.seeds.includes(a.seed) || a.seed === s.seed ? s : restartAll(s, { seed: a.seed });
    case "togglePlay":
      return { ...s, playing: !s.playing };
    case "play":
      return { ...s, playing: true };
    case "pause":
      return { ...s, playing: false };
    case "restart":
      return restartAll(s, {});
  }
}

/** ↑/↓ or [ / ] step through the picker; Space plays or pauses all; R restarts all. */
export function actionForKey(key: string): PickerAction | null {
  if (key === "ArrowUp" || key === "[") return { type: "step", delta: -1 };
  if (key === "ArrowDown" || key === "]") return { type: "step", delta: 1 };
  if (key === " " || key === "Space" || key === "Spacebar") return { type: "togglePlay" };
  if (key === "r" || key === "R") return { type: "restart" };
  return null;
}

// ---- the shared clock: seconds since every cell restarted, paused with them
export interface Clock {
  /** performance.now() (ms) at the last restart or resume, or null while paused */
  since: number | null;
  /** seconds accumulated before `since` */
  carried: number;
}

export const stoppedClock = (): Clock => ({ since: null, carried: 0 });

export function restartClock(now: number, playing: boolean): Clock {
  return { since: playing ? now : null, carried: 0 };
}

export function elapsed(c: Clock, now: number): number {
  return c.carried + (c.since == null ? 0 : (now - c.since) / 1000);
}

export function setClockPlaying(c: Clock, now: number, playing: boolean): Clock {
  if (playing && c.since == null) return { since: now, carried: c.carried };
  if (!playing && c.since != null) return { since: null, carried: elapsed(c, now) };
  return c;
}
