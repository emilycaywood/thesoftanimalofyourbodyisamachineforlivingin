"""Lying down and rising, evolved per body (ADR-107).

``lie_rise`` (``calflab.builtin.primitives.LieRisePrimitive``) used to be one hand-written movement with two numbers
(``phase_s``, ``hold_s``). Its kneel and reach angles, a time per move, the order of rising, a rock back before the
front rise and pauses with the load on the hooves are now vector dims of the primitive. This module:

* plays one version on one body and seed over the **whole** motion plus ``settle_s`` standing (the screen of
  ``calflab.evolve.hardware`` plays a primitive for at most ``InterpretSettings.max_play_s`` = 10 s, which cuts
  today's 11.5 s lie_rise during the front rise), judged as the R11c suite judges (``hardware.judge_play``);
* splits a play into its moves and says, per move, which joint and limit come closest (``per_move``);
* searches the dims per body with CMA-ES on the **worst-seed margin** (``optimise``), today's motion first.

Units: s, deg; margins are headroom over limits already lowered by the suite's margin (0 = exactly at margin 0.2),
"use" = value / lowered limit (1 = at it; margin = 1 - use).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.schema import P

VERSION = 1  # part of every cache key; bump when a play would no longer give the same record


class LieRiseSearch(BaseModel):
    """CMA-ES per body over the lie_rise primitive's vector dims."""

    popsize: int = P(12, ge=4, le=40, desc="Candidates per generation.")
    generations: int = P(10, ge=1, le=60, desc="Generations (after today's motion, which is played first).")
    sigma: float = P(0.25, ge=0.05, le=1.0, step=0.05, desc="Step size on dims scaled to 0..1.")
    seed: int = P(0, ge=0, ui="number", desc="Seed of the search (plays use the suite's seeds).")
    settle_s: float = P(1.0, unit="s", ge=0.0, le=5.0, step=0.1,
                        desc="Standing still after the motion, judged with it (PROVISIONAL).")
    fall_penalty: float = P(1.0, ge=0.0, le=10.0, desc="Subtracted from a seed's margin when the body falls.")
    excess_weight: float = P(0.1, ge=0.0, le=1.0,
                             desc="Ranking only: a seed's margin less this x its mean excess per move (0 for any "
                                  "version within every limit), so the search has a slope where the margin "
                                  "saturates at -3.")
    early_stop: float = P(-5.0, ge=-20.0, le=0.0,
                          desc="A candidate ranked below this on its first seed is not played on the others.")
    starts: list[dict[str, float]] = Field(default_factory=list,
                                           description="Extra starting versions played before the search (params).")
    extra_dims: list[tuple[str, float, float]] = Field(
        default_factory=list, description="Params searched beyond the primitive's vector dims: (name, lo, hi).")


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def dims(extra: list[tuple[str, float, float]] | None = None) -> list[Any]:
    """The primitive's vector dims, then ``extra`` (name, lo, hi)."""
    from calflab.builtin.primitives import LieRisePrimitive
    from calflab.plugins import VectorDim

    return LieRisePrimitive.vector_dims() + [VectorDim(n, float(lo), float(hi)) for n, lo, hi in (extra or [])]


def classic_effective(ds: list[Any] | None = None) -> dict[str, float]:
    """Today's lie_rise with every move's time written out (the search's start)."""
    from calflab.builtin.primitives import LieRisePrimitive

    p = LieRisePrimitive.Params().model_dump()
    for k in ("kneel_s", "lie_s", "rise_hind_s", "reach_s", "rise_front_s"):
        p[k] = p["phase_s"]
    return {d.name: float(p[d.name]) for d in (ds or dims())}


def params_of(x: np.ndarray, ds: list[Any] | None = None) -> dict[str, float]:
    """Vector in 0..1 -> primitive params (rounded to 0.001: cache keys stay stable)."""
    ds = ds or dims()
    return {d.name: round(d.lo + float(v) * (d.hi - d.lo), 3) for d, v in zip(ds, np.clip(x, 0.0, 1.0), strict=True)}


def x_of(params: dict[str, float], ds: list[Any] | None = None) -> np.ndarray:
    return np.array([(float(params[d.name]) - d.lo) / (d.hi - d.lo) for d in (ds or dims())], dtype=float)


def controller_params(params: dict[str, Any]) -> dict[str, Any]:
    """The feral_motion params that play these primitive params (only what differs from today's is sent)."""
    from calflab.builtin.primitives import LieRisePrimitive

    return LieRisePrimitive(params).controller(None, None)[1]


def moves(params: dict[str, Any]) -> list[tuple[str, float, float]]:
    from calflab.control.feral_motion import FeralMotionController, lie_rise_moves

    return lie_rise_moves(FeralMotionController.Params.model_validate(controller_params(params)))


def length_s(params: dict[str, Any]) -> float:
    from calflab.builtin.primitives import LieRisePrimitive

    return float(LieRisePrimitive(params).period_s())


# ====================================================================== per move
def _window_starts(above: np.ndarray, t: np.ndarray, window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Fraction of frames above in each forward window [t_i, t_i + window) (as ``loads.windowed_fraction``) and the
    window's middle time. A run shorter than a window is one window."""
    n = len(above)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    if t[-1] - t[0] <= window_s:
        return np.array([float(np.mean(above))]), np.array([0.5 * (t[0] + t[-1])])
    c = np.concatenate([[0], np.cumsum(above.astype(int))])
    fr, mid = [], []
    j = 0
    for i in range(n):
        while j < n and t[j] - t[i] < window_s:
            j += 1
        fr.append((c[j] - c[i]) / max(1, j - i))
        mid.append(0.5 * (t[i] + t[j - 1]))
        if j >= n:
            break
    return np.asarray(fr, float), np.asarray(mid, float)


def frame_uses(ro: Any, spec: Any, lib: Any, margin: float, window_s: float = 2.0) -> dict[str, Any]:
    """Per joint and limit, the use over time (1 = at the margin-lowered limit): peak limits per frame, sustained
    limits per 2 s window (placed at the window's middle). Returns ``{"t": frames, joint: {limit: (times, uses)}}``."""
    from calflab.behave.interpret import _checks
    from calflab.mech.limits import servo_columns
    from calflab.mech.loads import analyse

    c = _checks(spec)
    keep = 1.0 - margin
    checks = {**c, "rated_fraction": c["rated_fraction"] * keep, "breaking_fraction": c["breaking_fraction"] * keep}
    belts = {d: dict(r) for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items()}
    for r in belts.values():
        if r.get("allowable_working_tension_n") is not None:
            r["allowable_working_tension_n"] = float(r["allowable_working_tension_n"]) * keep
    res = analyse(ro, spec, lib, window_s, checks, belts)
    cols = res["columns"]
    t = np.asarray(cols["t_s"], float)
    sus = float(checks["sustained_fraction"])
    env = {col["joint"].replace("joint.", ""): np.asarray(col["use"], float) for col in servo_columns(ro, spec, lib)}
    lim = np.asarray(ro.meta.get("speed_limit") or [], dtype=float)
    m = ro.t >= 0
    acts = {a.id: a for a in spec.actuators}
    out: dict[str, Any] = {"t": t}
    for k, aid in enumerate(ro.actuator_ids):
        j = acts[aid].joint.replace("joint.", "")
        row: dict[str, Any] = next((r for r in res["summary"] if r["joint"].replace("joint.", "") == j), {})
        u: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        if len(lim) == ro.dq.shape[1] and m.any():
            u["speed"] = (t, np.abs(ro.dq[m][:, k]) / (lim[k] * keep))
        rated = row.get("rated_nm")
        if rated and f"{j}.servo_nm" in cols:
            fr, mid = _window_starts(np.abs(cols[f"{j}.servo_nm"]) > checks["rated_fraction"] * rated, t, window_s)
            u["torque"] = (mid, fr / sus)
        allow = row.get("allowable_n")
        if allow is not None and f"{j}.belt_n" in cols:
            fr, mid = _window_starts(np.asarray(cols[f"{j}.belt_n"]) > float(allow), t, window_s)
            u["belt"] = (mid, fr / sus)
        if f"{j}.pct_stall" in cols:
            u["stall"] = (t, np.asarray(cols[f"{j}.pct_stall"]) / 100.0 / keep)
        if j in env:
            u["envelope"] = (t, env[j] / keep)
        out[j] = u
    return out


def per_move(ro: Any, spec: Any, lib: Any, margin: float, move_list: list[tuple[str, float, float]],
             end_s: float | None = None) -> list[dict[str, Any]]:
    """Per move (and the standing after it, up to ``end_s``): the joint and limit with the largest use, its margin
    (1 - use), and the largest use per front/hind joint group. Sustained limits count for the move their 2 s window
    is centred in."""
    uses = frame_uses(ro, spec, lib, margin)
    spans = list(move_list)
    if end_s is not None and spans and end_s > spans[-1][2]:
        spans.append(("standing after", spans[-1][2], float(end_s)))
    out = []
    for name, t0, t1 in spans:
        best: tuple[float, str, str] | None = None
        per_joint: dict[str, dict[str, float]] = {}
        for j, lims in uses.items():
            if j == "t":
                continue
            for lim, (tt, vv) in lims.items():
                sel = (tt >= t0) & (tt < t1)
                if not sel.any():
                    continue
                v = float(np.max(vv[sel]))
                per_joint.setdefault(j, {})[lim] = round(v, 3)
                if best is None or v > best[0]:
                    best = (v, j, lim)
        out.append({"move": name, "t0": round(t0, 3), "t1": round(t1, 3),
                    "joint": None if best is None else best[1], "limit": None if best is None else best[2],
                    "use": None if best is None else round(best[0], 3),
                    "margin": None if best is None else round(1.0 - best[0], 3), "joints": per_joint})
    return out


# ====================================================================== one play
def play_seed(payload: dict[str, Any], params: dict[str, Any], seed: int, margin: float, settle_s: float,
              rollout_path: str | None = None, detail: bool = True) -> dict[str, Any]:
    """One version on one body (``payload`` as ``hardware.screen_task``'s) and seed, judged over the whole motion and
    ``settle_s`` standing. With ``rollout_path`` the rollout is saved there."""
    from calflab.builtin.primitives import LieRisePrimitive
    from calflab.evolve.hardware import _build, compile_options, judge_play
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    t = time.perf_counter()
    design, lib = _build(payload)
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    prim = LieRisePrimitive(params)
    key, cparams = prim.controller(design.spec, lib)
    t1 = float(prim.period_s()) + float(settle_s)
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(copts), seed)
    # never stopped at the simulator's fall check: lying down can be under its 45 % of standing height
    settings = SimSettings(duration_s=round(t1, 3), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=False, seed=seed)
    ro = run_rollout(cm, registry.get("controller", key)(cparams), settings, lib)  # type: ignore[arg-type]
    fall = lying_fall(ro, design.spec)
    judged = dataclasses.replace(ro, meta={**ro.meta, "fell": False, "fall_time": None})
    rec = judge_play(judged, design.spec, lib, margin, 0.0, t1)
    rec.update(fall)
    if fall["fell"]:
        rec["within"] = False
    if detail:
        rec["moves"] = per_move(ro, design.spec, lib, margin, moves(params), t1)
    rec["excess"] = excess(rec.get("moves") or [])
    rec["controller"] = {"key": key, "params": cparams}
    rec["length_s"] = round(t1, 3)
    rec["wall_s"] = round(time.perf_counter() - t, 2)
    if rollout_path:
        Path(rollout_path).parent.mkdir(parents=True, exist_ok=True)
        ro.save(Path(rollout_path))
        rec["compile"] = copts
    return rec


#: a lie/rise has fallen if the trunk tips this far (its up axis' z below this, as the simulator's check) ...
TIPPED_UP_Z = 0.4
#: ... or does not stand again: at the end, trunk under this share of its standing height or tilted (up z < 0.9)
RISEN_HEIGHT = 0.85


def lying_fall(ro: Any, spec: Any) -> dict[str, Any]:
    """A fall for lying down and rising (ADR-107): tipped over at any time, or not standing at the end. Lying low is
    not a fall (the simulator's check, trunk under 45 % of standing height, fires on a body that lies flat).
    Returns ``fell``, ``tipped``, ``risen``, ``sim_fell`` (the simulator's flag) and ``lying_height_mm``."""
    m = ro.t >= 0
    tr = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
    q = ro.body_quat[m, tr].astype(float)
    up = 1.0 - 2.0 * (q[:, 1] ** 2 + q[:, 2] ** 2)
    h = ro.body_pos[m, tr, 2].astype(float)
    if not len(h):
        return {"fell": True, "tipped": False, "risen": False, "sim_fell": bool(ro.meta.get("fell")),
                "lying_height_mm": None}
    tipped = bool(np.min(up) < TIPPED_UP_Z)
    risen = bool(h[-1] >= RISEN_HEIGHT * h[0] and up[-1] > 0.9)
    return {"fell": tipped or not risen, "tipped": tipped, "risen": risen, "sim_fell": bool(ro.meta.get("fell")),
            "lying_height_mm": round(float(np.min(h)) * 1000.0, 1)}


def excess(move_rows: list[dict[str, Any]]) -> float:
    """Mean over moves of the summed excess (use - 1, where over) of each joint's most-used limit: 0 for a play
    within every limit."""
    if not move_rows:
        return 0.0
    tot = 0.0
    for m in move_rows:
        tot += sum(max(0.0, max(lims.values()) - 1.0) for lims in (m.get("joints") or {}).values() if lims)
    return round(tot / len(move_rows), 4)


def margin_of(rec: dict[str, Any]) -> float:
    """A seed's margin as reported (None = -1)."""
    m = rec.get("margin")
    return float(-1.0 if m is None else m)


def score(rec: dict[str, Any], fall_penalty: float, excess_weight: float = 0.0) -> float:
    """A seed's rank in the search: its margin, less ``excess_weight`` x its excess, less ``fall_penalty`` if it
    fell. Equal to the margin for a play within every limit that stood up again."""
    return (margin_of(rec) - excess_weight * float(rec.get("excess") or 0.0)
            - (fall_penalty if rec.get("fell") else 0.0))


def task(job: dict[str, Any]) -> dict[str, Any]:
    """Worker: one (body, params, seed) play, cached on disk under ``job["cache"]``."""
    cache = Path(job["cache"]) if job.get("cache") else None
    f = cache / f"{job['key']}.json" if cache else None
    if f is not None and f.is_file():
        try:
            return {**json.loads(f.read_text(encoding="utf-8")), "cached": True}
        except (OSError, json.JSONDecodeError):
            pass
    rec = play_seed(job["payload"], job["params"], int(job["seed"]), float(job["margin"]), float(job["settle_s"]))
    if f is not None:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{time.perf_counter_ns()}.tmp")
        tmp.write_text(json.dumps(rec, default=float), encoding="utf-8")
        tmp.replace(f)
    return {**rec, "cached": False}


def job_key(spec_key: str, params: dict[str, Any], seed: int, copts_key: str, margin: float, settle_s: float) -> str:
    return _digest({"v": VERSION, "spec": spec_key, "ctrl": controller_params(params), "seed": int(seed),
                    "copts": copts_key, "margin": margin, "settle": settle_s})


def body_keys(payload: dict[str, Any]) -> tuple[str, str]:
    """(spec digest, compile digest) of a body payload: what makes two plays the same."""
    from calflab.evolve.hardware import _build

    design, _lib = _build(payload)
    return _digest(design.spec.model_dump(mode="json")), _digest({"c": payload.get("compile"),
                                                                    "e": payload.get("evaluation")})


# ====================================================================== the search
MapFn = Callable[[Callable[[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]]


def _serial(fn: Callable[[dict[str, Any]], dict[str, Any]], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [fn(j) for j in jobs]


def evaluate(payload: dict[str, Any], keys: tuple[str, str], cands: list[dict[str, float]], seeds: list[int],
             margin: float, s: LieRiseSearch, map_fn: MapFn, cache: str | None) -> list[dict[str, Any]]:
    """Each candidate on the first seed, then (if not below ``early_stop``) on the others; worst-seed score."""
    def jobs_for(seed: int, idx: list[int]) -> list[dict[str, Any]]:
        return [{"payload": payload, "params": cands[i], "seed": seed, "margin": margin, "settle_s": s.settle_s,
                 "cache": cache, "key": job_key(keys[0], cands[i], seed, keys[1], margin, s.settle_s)} for i in idx]

    per: list[list[dict[str, Any]]] = [[] for _ in cands]
    first = map_fn(task, jobs_for(seeds[0], list(range(len(cands)))))
    for i, r in enumerate(first):
        per[i].append({"seed": seeds[0], **r})
    more = [i for i, r in enumerate(first) if score(r, s.fall_penalty, s.excess_weight) >= s.early_stop]
    rest = [(seed, i) for seed in seeds[1:] for i in more]
    if rest:
        res = map_fn(task, [j for seed, i in rest for j in jobs_for(seed, [i])])
        for (seed, i), r in zip(rest, res, strict=True):
            per[i].append({"seed": seed, **r})
    out = []
    for i, c in enumerate(cands):
        complete = len(per[i]) == len(seeds)
        out.append({"params": c, "seeds": per[i], "complete": complete,
                    "worst": round(min(margin_of(r) for r in per[i]), 4),
                    "rank": round(min(score(r, s.fall_penalty, s.excess_weight) for r in per[i]), 4),
                    "held": complete and all(r["within"] for r in per[i]),
                    "fell_any": any(bool(r.get("fell")) for r in per[i]),
                    "evals": sum(0 if r.get("cached") else 1 for r in per[i])})
    return out


def _key(e: dict[str, Any]) -> tuple[bool, bool, float]:
    """Best first: played on every seed, holds on every seed, then the rank (= worst-seed margin when within)."""
    return bool(e["complete"]), bool(e["held"]), float(e["rank"])


def optimise(payload: dict[str, Any], seeds: list[int], margin: float, s: LieRiseSearch,
             map_fn: MapFn | None = None, cache: str | None = None,
             report: Callable[[str], None] | None = None) -> dict[str, Any]:
    """CMA-ES (maximising the worst-seed margin) over the lie_rise dims for one body. Today's motion and
    ``s.starts`` are played first; the search starts from the best of them. Deterministic for a given seed (results
    do not depend on the worker count)."""
    import cma

    map_fn = map_fn or _serial
    keys = body_keys(payload)
    t0 = time.perf_counter()
    ds = dims(s.extra_dims)
    start = classic_effective(ds)
    history: list[dict[str, Any]] = []
    first = [start, *[{**start, **x} for x in s.starts]]
    evals = evaluate(payload, keys, first, seeds, margin, s, map_fn, cache)
    for e in evals:
        e["generation"] = -1
    history += evals
    best = max(evals, key=_key)
    # the search starts from the best of what was played first (today's motion unless a start beats it)
    x0 = x_of({**start, **{k: v for k, v in best["params"].items() if k in start}}, ds)
    es = cma.CMAEvolutionStrategy(list(np.clip(x0, 0.02, 0.98)), s.sigma,
                                  {"bounds": [0.0, 1.0], "popsize": s.popsize, "seed": s.seed + 7919, "verbose": -9})
    for g in range(s.generations):
        xs = es.ask()
        cands = [params_of(np.asarray(x), ds) for x in xs]
        res = evaluate(payload, keys, cands, seeds, margin, s, map_fn, cache)
        for e in res:
            e["generation"] = g
        history += res
        es.tell(xs, [-e["rank"] for e in res])
        gbest = max(res, key=_key)
        if _key(gbest) > _key(best):
            best = gbest
        if report:
            report(f"generation {g + 1}/{s.generations}: best margin {best['worst']:+.3f} rank {best['rank']:+.3f} "
                   f"held {best['held']} (this generation {gbest['worst']:+.3f}); "
                   f"{sum(e['evals'] for e in res)} new plays")
    return {"start": next(e for e in history if e["generation"] == -1), "best": best,
            "history": [{"generation": e["generation"], "worst": e["worst"], "rank": e["rank"], "held": e["held"],
                         "complete": e["complete"], "params": e["params"]} for e in history],
            "plays": sum(len(e["seeds"]) for e in history), "new_plays": sum(e["evals"] for e in history),
            "wall_s": round(time.perf_counter() - t0, 1), "search": s.model_dump()}
