"""Many distinct things one body can do safely: a quality-diversity search (R16, ADR-112).

R15 (ADR-110) searched one best version of four behaviours per body. Here the body is fixed and the question is the
other way round: what *different* things can it do within the limits? MAP-Elites over the ``outcome_motion``
controller (version 2: posture keyframes with pauses, a left/right offset, a free-phase rhythm that can start late and
run in bouts, IMU reflexes):

* every candidate is played as the ``free`` outcome (``calflab.fitness.outcomes.measure_free``): no task, only safety
  gates (not tipped, slow descent, soft landing) and descriptors;
* it is judged by the R11c suite's limits at the preset's margin on every search seed (``evolve.outcomes.evaluate``:
  the first seed, then the others only when the first is safe and within; worst seed ranks);
* a candidate that holds on every seed goes into the cell of its **descriptors** (``Grid``): what the body does
  (``CLASSES``: down, kneel, crouch, stand, walk, trot, pace, bound, irregular), its forward speed and its turn rate;
  the majority class and the median speed and turn over the seeds;
* inside a cell the **least servo effort** wins (the ``free`` score, -(mean + worst)/2 of mean |torque| / rated);
* new candidates are mutated elites (``mutate``): a few dims nudged, a line towards another elite, or one whole block
  (a keyframe, the side offset, the rhythm, the reflexes) copied from another elite.

Deterministic for a seed (numpy ``default_rng``; plays are deterministic and cached). Units: mm/s, deg/s, s, deg.
"""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.evolve.outcomes import BehaviourSpace, MapFn, OutcomeSearch, evaluate, summary
from calflab.fitness.outcomes import CLASSES
from calflab.schema import P

#: (name, lo, hi) of the free search, grouped in blocks (``mutate`` copies whole blocks). Postures in deg relative to
#: standing, inside the PROVISIONAL joint ranges less a margin (as ``evolve.outcomes.LIE_RANGES``); times in s.
POSE = {"abd": (-10.0, 10.0), "stifle": (-20.0, 78.0), "hock": (-20.0, 78.0), "shoulder": (-58.0, 30.0),
        "carpus": (-5.0, 128.0)}
BLOCKS: dict[str, list[tuple[str, float, float]]] = {
    "p1": [*((f"p1_{g}", lo, hi) for g, (lo, hi) in POSE.items()), ("p1_s", 0.5, 5.0), ("p1_hold_s", 0.0, 4.0)],
    "p2": [*((f"p2_{g}", lo, hi) for g, (lo, hi) in POSE.items()), ("p2_s", 0.0, 5.0), ("p2_hold_s", 0.0, 4.0)],
    "p3": [*((f"p3_{g}", lo, hi) for g, (lo, hi) in POSE.items()), ("p3_s", 0.0, 10.0),
           ("hold_s", 0.0, 6.0), ("rise_scale", 0.0, 2.5)],
    "side": [("side_abd", -15.0, 15.0), ("side_stifle", -30.0, 30.0), ("side_hock", -30.0, 30.0),
             ("side_shoulder", -30.0, 30.0), ("side_carpus", -30.0, 30.0), ("side_from_s", 0.0, 10.0),
             ("side_s", 0.0, 4.0)],
    "rhythm": [("gait_amp", 0.0, 1.6), ("cycle_s", 0.3, 4.0), ("swing", 0.12, 0.6), ("phase_fl", 0.0, 1.0),
               ("phase_hr", 0.0, 1.0), ("phase_fr", 0.0, 1.0), ("sweep_stifle", -12.0, 6.0),
               ("sweep_hock", -6.0, 20.0), ("sweep_shoulder", -16.0, 6.0), ("lift_stifle", 0.0, 25.0),
               ("lift_hock", 0.0, 35.0), ("lift_carpus", 0.0, 50.0), ("lift_shoulder", -25.0, 5.0),
               ("abd_sway", -6.0, 6.0), ("stride", -1.0, 2.0), ("turn", -1.5, 1.5), ("gait_from_s", 0.0, 8.0),
               ("bout_s", 0.0, 6.0), ("pause_s", 0.5, 4.0)],
    "reflex": [("roll_gain", 0.0, 2.0), ("pitch_gain", -1.0, 2.0), ("pitch_gain_hind", -1.0, 1.0),
               ("yaw_gain", 0.0, 3.0)],
}
#: a dim under this value means "not used" (0): a keyframe, a pause, the side move, the rhythm, bouts, the rise
SNAP = {"p2_s": 0.5, "p3_s": 0.5, "p1_hold_s": 0.3, "p2_hold_s": 0.3, "hold_s": 0.3, "rise_scale": 0.4,
        "side_s": 0.5, "gait_amp": 0.2, "bout_s": 1.0}


def free_space(search_s: float = 16.0, judge_s: float = 30.0, blocks: list[str] | None = None,
               fixed: dict[str, Any] | None = None) -> BehaviourSpace:
    """The free search's space (all blocks, or ``blocks``); every other controller number at ``fixed`` or default."""
    dims = [d for b in (blocks or list(BLOCKS)) for d in BLOCKS[b]]
    return BehaviourSpace(behaviour="free", dims=dims, fixed={"ramp_s": 1.5, **(fixed or {})},
                          search_s=search_s, judge_s=judge_s)


def block_of(name: str) -> str:
    return next((b for b, ds in BLOCKS.items() if any(n == name for n, _lo, _hi in ds)), "other")


# ====================================================================== descriptors -> cells
class Grid(BaseModel):
    """Cells: class x forward speed bin x turn rate bin. Bins are the gaps between ``*_edges`` (plus both ends)."""

    classes: list[str] = Field(default_factory=lambda: list(CLASSES))
    speed_edges: list[float] = Field(default_factory=lambda: [-15.0, 15.0, 100.0, 250.0, 400.0, 550.0],
                                     description="mm/s: backward | in place | creeping | slow | medium | brisk | fast")
    speed_names: list[str] = Field(default_factory=lambda: ["backward", "in place", "creeping", "slow", "medium",
                                                            "brisk", "fast"])
    turn_edges: list[float] = Field(default_factory=lambda: [-10.0, -2.5, 2.5, 10.0],
                                    description="deg/s (+ left): right fast | right | straight | left | left fast")
    turn_names: list[str] = Field(default_factory=lambda: ["turning right fast", "turning right", "straight",
                                                           "turning left", "turning left fast"])

    def size(self) -> int:
        return len(self.classes) * (len(self.speed_edges) + 1) * (len(self.turn_edges) + 1)

    def cell(self, d: dict[str, Any]) -> str | None:
        cls = d.get("class")
        if cls not in self.classes or d.get("speed") is None or d.get("turn") is None:
            return None
        si = int(np.searchsorted(self.speed_edges, float(d["speed"]), side="right"))
        ti = int(np.searchsorted(self.turn_edges, float(d["turn"]), side="right"))
        return f"{cls}|{si}|{ti}"

    def label(self, cell: str) -> str:
        cls, si, ti = cell.split("|")
        names = self.speed_names if len(self.speed_names) == len(self.speed_edges) + 1 else None
        sp = names[int(si)] if names else f"speed bin {si}"
        tn = self.turn_names[int(ti)] if len(self.turn_names) == len(self.turn_edges) + 1 else f"turn bin {ti}"
        return f"{cls}, {sp}, {tn}"


def descriptor(entry: dict[str, Any]) -> dict[str, Any]:
    """Class (majority over the seeds; a tie goes to the first seed), median speed (mm/s) and turn (deg/s)."""
    outs = [r.get("outcome") or {} for r in entry["seeds"]]
    classes = [o.get("d_class") for o in outs if o.get("d_class")]
    if not classes:
        return {"class": None, "speed": None, "turn": None, "agree": 0.0}
    top, n = Counter(classes).most_common(1)[0]
    cls = top if n > 1 or len(classes) == 1 else classes[0]
    sp = [float(o["d_speed_mm_s"]) for o in outs if o.get("d_speed_mm_s") is not None]
    tu = [float(o["d_turn_deg_s"]) for o in outs if o.get("d_turn_deg_s") is not None]
    return {"class": cls, "speed": round(float(np.median(sp)), 1) if sp else None,
            "turn": round(float(np.median(tu)), 2) if tu else None,
            "agree": round(sum(1 for c in classes if c == cls) / len(classes), 2)}


# ====================================================================== parameters
def defaults() -> dict[str, float]:
    from calflab.control.outcome import OutcomeMotionController

    return {k: float(v) for k, v in OutcomeMotionController.Params().model_dump().items()}


def to_x(params: dict[str, Any], dims: list[tuple[str, float, float]], base: dict[str, float]) -> np.ndarray:
    """0..1 per dim; a number the params do not set takes the controller's default (not 0)."""
    return np.clip(np.array([(float(params.get(n, base.get(n, 0.0))) - lo) / (hi - lo) for n, lo, hi in dims]), 0, 1)


def from_x(x: np.ndarray, dims: list[tuple[str, float, float]]) -> dict[str, float]:
    out = {}
    for (n, lo, hi), v in zip(dims, np.clip(x, 0.0, 1.0), strict=True):
        val = round(lo + float(v) * (hi - lo), 3)
        if n in SNAP and val < SNAP[n]:
            val = 0.0
        out[n] = val
    return out


class QDSettings(BaseModel):
    """MAP-Elites on one body (ADR-112)."""

    iterations: int = P(30, ge=0, le=2000, desc="Batches after the starting points.")
    batch: int = P(28, ge=1, le=500, desc="Candidates per batch (2 per worker on 14 workers).")
    seed: int = P(0, ge=0, ui="number", desc="Seed of the search (mutations, parent choice).")
    sigma: float = P(0.08, ge=0.0, le=1.0, desc="Gaussian step on dims scaled 0..1.")
    dim_rate: float = P(0.25, ge=0.0, le=1.0, desc="Share of dims a Gaussian step nudges (at least one).")
    line_sigma: float = P(0.2, ge=0.0, le=2.0, desc="Line step towards another elite (iso + line).")
    p_line: float = P(0.3, ge=0.0, le=1.0, desc="Chance of a line step.")
    p_block: float = P(0.2, ge=0.0, le=1.0, desc="Chance of copying a whole block from another elite.")
    early_stop: float = P(-1.9, ge=-50.0, le=0.0,
                          desc="A candidate ranked below this on its first seed plays no more (unsafe or over a limit "
                               "ranks below -2).")
    search_seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])
    judge_seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])


def mutate(rng: np.random.Generator, x: np.ndarray, other: np.ndarray, dims: list[tuple[str, float, float]],
           s: QDSettings) -> tuple[np.ndarray, str]:
    """One child of ``x`` (0..1 per dim) and the operator used."""
    r = float(rng.random())
    if r < s.p_block:
        blocks = sorted({block_of(n) for n, _lo, _hi in dims})
        b = blocks[int(rng.integers(len(blocks)))]
        child = x.copy()
        idx = [i for i, (n, _lo, _hi) in enumerate(dims) if block_of(n) == b]
        child[idx] = other[idx]
        child[idx] += rng.normal(0.0, s.sigma / 2.0, len(idx))
        return np.clip(child, 0, 1), f"block:{b}"
    if r < s.p_block + s.p_line:
        child = x + rng.normal(0.0, s.sigma / 4.0, len(x)) + s.line_sigma * float(rng.normal()) * (other - x)
        return np.clip(child, 0, 1), "line"
    mask = rng.random(len(x)) < s.dim_rate
    if not mask.any():
        mask[int(rng.integers(len(x)))] = True
    return np.clip(x + mask * rng.normal(0.0, s.sigma, len(x)), 0, 1), "gauss"


# ====================================================================== the search
def run(payload: dict[str, Any], space: BehaviourSpace, grid: Grid, s: QDSettings, starts: list[dict[str, Any]],
        margin: float, map_fn: MapFn, cache: str | None, start_labels: list[str] | None = None,
        report: Callable[[str], None] | None = None) -> dict[str, Any]:
    """MAP-Elites from ``starts`` (played first; starting points only). Returns the archive (cell -> elite), the
    coverage per batch, and per class what was tried, held and why the rest failed (the binding limit or gate on the
    first seed)."""
    from calflab.evolve.outcomes import body_key

    t0 = time.perf_counter()
    rng = np.random.default_rng(s.seed)
    bkey = body_key(payload)
    dims = space.dims
    base = defaults()
    os_ = OutcomeSearch(search_seeds=s.search_seeds, judge_seeds=s.judge_seeds, early_stop=s.early_stop)
    archive: dict[str, dict[str, Any]] = {}
    xs: dict[str, np.ndarray] = {}
    tried: dict[str, Counter[str]] = {}
    history: list[dict[str, Any]] = []
    plays = 0

    def consider(cands: list[dict[str, Any]], xs_in: list[np.ndarray], it: int, ops: list[str]) -> int:
        nonlocal plays
        res = evaluate(payload, bkey, space, cands, s.search_seeds, margin, os_, map_fn, cache)
        added = 0
        for e, x, op in zip(res, xs_in, ops, strict=True):
            plays += len(e["seeds"])
            first = e["seeds"][0]
            o = first.get("outcome") or {}
            cls0 = o.get("d_class") or "none"
            c = tried.setdefault(cls0, Counter())
            c["tried"] += 1
            if not first.get("within"):
                b = first.get("binding") or {}
                c[f"limit: {b.get('joint')} {b.get('limit')}"] += 1
            for g, ok in (o.get("gates") or {}).items():
                if not ok:
                    c[f"gate: {g}"] += 1
            if first.get("holds") and not e["holds"]:
                c["fails on another seed"] += 1
            if not e["holds"]:
                continue
            c["held"] += 1
            d = descriptor(e)
            cell = grid.cell(d)
            if cell is None:
                continue
            old = archive.get(cell)
            if old is None or float(e["rank"]) > float(old["rank"]):
                archive[cell] = {"cell": cell, "label": grid.label(cell), "descriptor": d, "rank": e["rank"],
                                 "iteration": it, "op": op, "summary": summary(e),
                                 "replaced": (old or {}).get("replaced", 0) + (1 if old else 0)}
                xs[cell] = x
                added += 1
        return added

    names = start_labels or [f"start {i}" for i in range(len(starts))]
    x0 = [to_x(st, dims, base) for st in starts]
    added = consider([from_x(x, dims) for x in x0], x0, -1, [f"start:{n}" for n in names])
    history.append({"iteration": -1, "cells": len(archive), "added": added, "plays": plays,
                    "wall_s": round(time.perf_counter() - t0, 1)})
    if report:
        report(f"starts: {len(archive)} cells")
    pool = list(x0)
    for it in range(s.iterations):
        keys = sorted(xs)
        parents = [xs[k] for k in keys] or pool
        batch_x, ops = [], []
        for _ in range(s.batch):
            a = parents[int(rng.integers(len(parents)))]
            b = parents[int(rng.integers(len(parents)))]
            child, op = mutate(rng, a, b, dims, s)
            batch_x.append(child)
            ops.append(op)
        added = consider([from_x(x, dims) for x in batch_x], batch_x, it, ops)
        history.append({"iteration": it, "cells": len(archive), "added": added, "plays": plays,
                        "wall_s": round(time.perf_counter() - t0, 1)})
        if report:
            report(f"batch {it + 1}/{s.iterations}: {len(archive)} cells (+{added}), {plays} plays, "
                   f"{time.perf_counter() - t0:.0f} s")
    return {"grid": grid.model_dump(), "settings": s.model_dump(), "space": space.model_dump(mode="json"),
            "archive": archive, "history": history, "tried": {k: dict(v) for k, v in tried.items()},
            "coverage": round(len(archive) / grid.size(), 4), "cells": len(archive), "grid_size": grid.size(),
            "plays": plays, "wall_s": round(time.perf_counter() - t0, 1), "starts": names}


def judge(payload: dict[str, Any], space: BehaviourSpace, grid: Grid, archive: dict[str, dict[str, Any]],
          seeds: list[int], margin: float, map_fn: MapFn, cache: str | None) -> dict[str, dict[str, Any]]:
    """Every elite re-played at the judging length (``space.judge_s``) on ``seeds``: does it still hold, and does it
    stay in its cell? Returns cell -> {holds, within, rank, descriptor, cell, same_cell, summary}."""
    from calflab.evolve.outcomes import body_key

    cells = sorted(archive)
    cands = [archive[c]["summary"]["params"] for c in cells]
    os_ = OutcomeSearch(search_seeds=seeds, judge_seeds=seeds).model_copy(update={"early_stop": -1e9})  # every seed
    res = evaluate(payload, body_key(payload), space, cands, seeds, margin, os_, map_fn, cache, judging=True)
    out = {}
    for c, e in zip(cells, res, strict=True):
        d = descriptor(e)
        jc = grid.cell(d)
        out[c] = {"holds": e["holds"], "within": e["within"], "rank": e["rank"], "descriptor": d, "cell": jc,
                  "same_cell": jc == c, "summary": summary(e)}
    return out
