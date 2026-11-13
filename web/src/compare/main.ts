// compare.html: recorded runs side by side, each cell an embedded lab (`/?replay=<run>&embed=1`).
//
//   compare.html?set=<key>[&item=<behaviour key>&seed=<n>]   a group of bodies; one picker switches every cell
//     (a manifest with per_cell also gives each cell its own menu; &cells=<key>,<key>,... keeps their picks)
//   compare.html?runs=<id>,<id>,...&labels=<l>|<l>|...      any runs in a grid (no picker)
//   compare.html?a=<id>&b=<id>&la=<label>&lb=<label>         two runs
//   optional &cols=<n>; &full=1 shows the whole lab in each cell.
//
// Layout and playback only (ADR-106): the bodies, the picker's groups, which behaviour each body plays, the badges
// and the limits all come from the server's manifest (/api/compare/<set>).
import {
  actionForKey,
  type Clock,
  current,
  elapsed,
  initPicker,
  type PickerAction,
  type PickerItem,
  type PickerState,
  reduce,
  restartClock,
  setClockPlaying,
  stoppedClock,
} from "./picker";

interface SeedPlay {
  seed: number;
  run: string | null;
  badge: "within" | "near" | "over" | null;
  margin: number | null;
  limit: string | null;
  text: string;
  href?: string;
  /** what this cell's own run plays, measured as its label was (body sets, ADR-125) */
  plays?: { text: string; agrees: boolean } | null;
}
interface Cell {
  body: string;
  play: string | null;
  playing: string | null;
  match: string | null;
  empty: boolean;
  message: string | null;
  seeds: SeedPlay[];
}
interface Item {
  key: string;
  label: string;
  kind: string;
  cells: Cell[];
}
interface Group {
  key: string;
  title: string;
  items: Item[];
}
interface Body {
  key: string;
  label: string;
  line: string;
  stage_c_run: string | null;
}
export interface Manifest {
  set: string;
  title: string;
  seeds: number[];
  bodies: Body[];
  groups: Group[];
  stored: number;
  missing: number;
  hint: string;
  per_cell?: boolean;
  /** with per_cell: the item each cell starts on when the URL gives none (R16) */
  default_cells?: string[];
}

type Msg = { calflab: "playback"; action: string; run?: string; t?: number };
const READY_TIMEOUT_MS = 20_000;
const SYNC_EVERY_MS = 3_000;

const q = new URLSearchParams(location.search);
const root = document.getElementById("root")!;
const embedFlag = q.get("full") ? "" : "&embed=1";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

function post(f: HTMLIFrameElement, msg: Msg) {
  f.contentWindow?.postMessage(msg, location.origin);
}

function gridOf(n: number): HTMLDivElement {
  const cols = Number(q.get("cols")) || (n <= 2 ? 2 : n <= 6 ? 3 : 4);
  const grid = el("div", "grid");
  grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  grid.style.gridTemplateRows = `repeat(${Math.ceil(n / cols)}, 1fr)`;
  return grid;
}

// ------------------------------------------------------------------ plain list of runs (as before)
function runsPage(ids: string[], labels: string[]) {
  const grid = gridOf(ids.length);
  ids.forEach((id, i) => {
    const cell = el("div", "cell");
    const t = el("div", "label");
    t.append(el("b", "", labels[i] || ""), document.createTextNode((labels[i] ? "  " : "") + id));
    t.title = (labels[i] || "") + " " + id;
    const f = el("iframe");
    f.src = "/?replay=" + encodeURIComponent(id) + embedFlag;
    cell.append(t, f);
    grid.appendChild(cell);
  });
  const top = el("div", "top");
  const frames = () => [...grid.querySelectorAll("iframe")];
  for (const [label, action] of [
    ["Restart all", "restart"],
    ["Play all", "play"],
    ["Pause all", "pause"],
  ]) {
    const btn = el("button", "", label);
    btn.onclick = () => frames().forEach((f) => post(f, { calflab: "playback", action }));
    top.appendChild(btn);
  }
  top.appendChild(el("span", "", ids.length + " replays. Each cell: RMB orbit, wheel zoom; its own timeline below it."));
  root.append(top, grid);
}

// ------------------------------------------------------------------ a set: one picker for every cell
async function setPage(key: string) {
  root.appendChild(el("div", "empty", "Reading the set..."));
  let m: Manifest;
  try {
    const r = await fetch(`/api/compare/${encodeURIComponent(key)}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail ?? r.statusText);
    m = (await r.json()) as Manifest;
  } catch (e) {
    root.innerHTML = "";
    root.appendChild(el("div", "empty", `Cannot read compare set "${key}": ${(e as Error).message}`));
    return;
  }
  root.innerHTML = "";
  mountSet(m);
}

export function mountSet(m: Manifest) {
  const items: PickerItem[] = m.groups.flatMap((g) => g.items.map((it) => ({ key: it.key, label: it.label, group: g.key })));
  const byKey = new Map(m.groups.flatMap((g) => g.items.map((it) => [it.key, it] as const)));
  let state: PickerState = initPicker(items, m.seeds, { item: q.get("item"), seed: q.get("seed") == null ? null : Number(q.get("seed")) });
  let clock: Clock = stoppedClock();
  // per-cell picks (manifests with per_cell): null = follow the top picker; the top picker clears them
  const fromUrl = q.get("cells") != null ? q.get("cells")!.split(",") : q.get("item") ? [] : (m.default_cells ?? []);
  const picks: (string | null)[] = m.bodies.map((_, i) => (m.per_cell && byKey.has(fromUrl[i]) ? fromUrl[i] : null));

  // ---- top bar: picker, seed, play controls
  const top = el("div", "top");
  const title = el("b", "", m.title);
  const picker = el("select");
  picker.dataset.testid = "picker";
  for (const g of m.groups) {
    const og = el("optgroup");
    og.label = `${g.title} (${g.items.length})`;
    for (const it of g.items) {
      const o = el("option", "", it.label);
      o.value = it.key;
      og.appendChild(o);
    }
    picker.appendChild(og);
  }
  picker.onchange = () => {
    // the top picker sets every cell, including cells whose own menu picked something else
    const had = picks.some(Boolean);
    const before = state.index;
    picks.fill(null);
    dispatch({ type: "select", key: picker.value });
    if (had && state.index === before) show();
  };
  picker.onkeydown = (e) => {
    // the picker's own arrow keys would step twice
    if (actionForKey(e.key)) e.preventDefault();
  };
  const seedBox = el("span", "seeds");
  const seedBtns = m.seeds.map((s) => {
    const b = el("button", "", `seed ${s}`);
    b.dataset.seed = String(s);
    b.onclick = () => dispatch({ type: "seed", seed: s });
    seedBox.appendChild(b);
    return b;
  });
  const playBtn = el("button", "", "Pause all");
  playBtn.dataset.testid = "play";
  playBtn.onclick = () => dispatch({ type: "togglePlay" });
  const restartBtn = el("button", "", "Restart all");
  restartBtn.onclick = () => dispatch({ type: "restart" });
  const status = el("span", "status");
  status.dataset.testid = "status";
  top.append(title, picker, seedBox, playBtn, restartBtn, status);
  const hint = el("div", "hint", "↑/↓ or [ ] behaviour · Space play/pause all · R restart all · click a cell's title to open it in the lab");
  if (m.hint) hint.textContent += ` · ${m.hint}`;

  // ---- cells
  const grid = gridOf(m.bodies.length);
  const cells = m.bodies.map((b, i) => {
    const cell = el("div", "cell");
    cell.dataset.testid = "cell";
    cell.dataset.body = b.key;
    const head = el("a", "label");
    head.target = "_blank";
    head.title = "Open this body and play in the full lab";
    const name = el("b", "", b.label);
    const line = el("span", "line", b.line);
    head.append(name, line);
    const menu = el("select", "cellpick");
    menu.dataset.testid = "cell-picker";
    for (const it of items) {
      const o = el("option", "", it.label);
      o.value = it.key;
      menu.appendChild(o);
    }
    menu.onchange = () => {
      picks[i] = menu.value;
      show();
    };
    menu.onkeydown = (e) => {
      if (actionForKey(e.key)) e.stopPropagation();
    };
    const playing = el("div", "playing");
    playing.dataset.testid = "playing";
    const badge = el("span", "badge");
    badge.dataset.testid = "badge";
    const limit = el("span", "limit");
    const sub = el("div", "sub");
    sub.append(badge, limit);
    const plays = el("div", "plays");
    plays.dataset.testid = "plays";
    const frameBox = el("div", "frame");
    const f = el("iframe");
    const note = el("div", "note");
    frameBox.append(f, note);
    cell.append(head, ...(m.per_cell ? [menu] : []), playing, sub, plays, frameBox);
    grid.appendChild(cell);
    return { body: b, index: i, cell, head, menu, playing, badge, limit, plays, f, note, run: null as string | null, loaded: false, ready: false };
  });
  root.append(top, hint, grid);

  // ---- messages from the cells: ready after a load, keys pressed inside a cell
  let pending = new Set<number>();
  let waitTimer = 0;
  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin) return;
    const d = e.data as { calflab?: string; event?: string; run?: string; key?: string } | null;
    if (d?.calflab !== "embed") return;
    const c = cells.find((x) => x.f.contentWindow === e.source);
    if (!c) return;
    if (d.event === "key" && d.key) {
      const a = actionForKey(d.key);
      if (a) dispatch(a);
    } else if (d.event === "ready" || d.event === "failed") {
      if (d.run !== c.run) return;
      c.ready = d.event === "ready";
      showLoaded(c, c.ready);
      pending.delete(c.index);
      if (!pending.size) startTogether();
    }
  });
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const a = actionForKey(e.key);
    if (!a) return;
    e.preventDefault();
    dispatch(a);
  });

  // a cell that is loading another run is covered, so it never plays the old behaviour under the new title
  function showLoading(c: (typeof cells)[number]) {
    c.f.style.visibility = "hidden";
    c.note.textContent = "loading...";
    c.note.style.display = "flex";
  }
  function showLoaded(c: (typeof cells)[number], ok: boolean) {
    c.f.style.visibility = ok ? "visible" : "hidden";
    c.note.textContent = ok ? "" : "cannot load this run";
    c.note.style.display = ok ? "none" : "flex";
  }

  function startTogether() {
    window.clearTimeout(waitTimer);
    for (const c of cells) if (c.run && !c.ready) c.note.textContent = "still loading (not in step with the others)";
    pending = new Set();
    clock = restartClock(performance.now(), state.playing);
    for (const c of cells) if (c.run) post(c.f, { calflab: "playback", action: "restart" });
    if (!state.playing) for (const c of cells) if (c.run) post(c.f, { calflab: "playback", action: "pause" });
    status.textContent = "";
  }

  // keep them in step: every few seconds, cells that drifted (a throttled frame) are moved to the shared time
  window.setInterval(() => {
    if (!state.playing || pending.size) return;
    const t = elapsed(clock, performance.now());
    for (const c of cells) if (c.run && c.ready) post(c.f, { calflab: "playback", action: "sync", t });
  }, SYNC_EVERY_MS);

  function show() {
    const it = current(state);
    const item = it ? byKey.get(it.key) : undefined;
    picker.value = it?.key ?? "";
    seedBtns.forEach((b) => b.classList.toggle("on", Number(b.dataset.seed) === state.seed));
    const u = new URL(location.href);
    if (it) u.searchParams.set("item", it.key);
    u.searchParams.set("seed", String(state.seed));
    if (picks.some((p) => p)) u.searchParams.set("cells", picks.map((p) => p ?? "").join(","));
    else u.searchParams.delete("cells");
    history.replaceState(null, "", u);
    pending = new Set();
    for (const c of cells) {
      const own = picks[c.index] ? byKey.get(picks[c.index]!) : item;
      c.menu.value = own?.key ?? "";
      const cc = own?.cells.find((x) => x.body === c.body.key);
      const sp = cc?.seeds.find((s) => s.seed === state.seed);
      c.playing.textContent = cc?.empty ? "" : (cc?.playing ?? "");
      c.playing.title = cc?.playing ?? "";
      c.badge.className = "badge" + (sp?.badge ? ` ${sp.badge}` : "");
      c.badge.textContent = sp ? sp.text : "";
      c.limit.textContent = sp?.limit ? `stopped by ${sp.limit}` : "";
      c.plays.textContent = sp?.plays?.text ?? "";
      c.plays.className = "plays" + (sp?.plays && !sp.plays.agrees ? " differs" : "");
      c.plays.title = sp?.plays && !sp.plays.agrees ? "this body's own seed-0 run does not play the gait the behaviour is named after" : "";
      c.head.href = sp?.href ?? "#";
      c.cell.classList.toggle("is-empty", !!cc?.empty);
      const run = sp?.run ?? null;
      c.cell.dataset.run = run ?? "";
      c.cell.dataset.play = cc?.play ?? "";
      if (!run) {
        c.note.textContent = cc?.empty ? (cc.message ?? "no matching behaviour") : "not played yet";
        c.note.style.display = "flex";
        c.f.style.visibility = "hidden";
        if (c.run) post(c.f, { calflab: "playback", action: "pause" });
        c.run = null;
        continue;
      }
      if (run !== c.run) {
        c.run = run;
        c.ready = false;
        pending.add(c.index);
        showLoading(c);
        if (!c.loaded) {
          c.loaded = true;
          c.f.src = "/?replay=" + encodeURIComponent(run) + embedFlag;
        } else post(c.f, { calflab: "playback", action: "load", run });
      }
    }
    if (pending.size) {
      status.textContent = `loading ${pending.size}...`;
      window.clearTimeout(waitTimer);
      waitTimer = window.setTimeout(startTogether, READY_TIMEOUT_MS);
    } else startTogether();
  }

  function dispatch(a: PickerAction) {
    const prev = state;
    state = reduce(state, a);
    playBtn.textContent = state.playing ? "Pause all" : "Play all";
    if (state.epoch !== prev.epoch) {
      if (state.index !== prev.index) picks.fill(null);
      if (state.index !== prev.index || state.seed !== prev.seed) show();
      else startTogether();
      return;
    }
    if (state.playing !== prev.playing) {
      clock = setClockPlaying(clock, performance.now(), state.playing);
      for (const c of cells) if (c.run) post(c.f, { calflab: "playback", action: state.playing ? "play" : "pause" });
    }
  }

  show();
}

// ------------------------------------------------------------------ entry
let ids: string[] = [];
let labels: string[] = [];
if (q.get("runs")) {
  ids = q.get("runs")!.split(",").map((s) => s.trim()).filter(Boolean);
  labels = (q.get("labels") || "").split("|");
} else if (q.get("a") && q.get("b")) {
  ids = [q.get("a")!, q.get("b")!];
  labels = [q.get("la") || "", q.get("lb") || ""];
}
if (q.get("set")) void setPage(q.get("set")!);
else if (ids.length >= 2) runsPage(ids, labels);
else {
  const e = el("div", "empty");
  e.innerHTML =
    "Shows recorded runs side by side, each in its own lab view.<br>" +
    "Open <code>compare.html?set=r12</code> for the R12 / Stage C bodies with one behaviour picker for all, " +
    "<code>compare.html?runs=&lt;id&gt;,&lt;id&gt;,...&amp;labels=a|b|...</code> for a series, or " +
    "<code>compare.html?a=&lt;run id&gt;&amp;b=&lt;run id&gt;</code>. Run ids are in Journal &gt; Runs.";
  root.appendChild(e);
}
