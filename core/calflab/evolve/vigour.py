"""Vigour within limits: one body judged on a suite of motions (session R step 3, ADR-090).

A fitness preset whose ``evaluation.suite`` is set scores a candidate body by playing a suite of motion
primitives on it, each with its parameters searched for that body (the inner loop), instead of tuning one
controller:

* **gaits** (``kind: gait``; walk, trot): how much of the gait's speed is kept, ``min(1, speed / reference)``.
  The reference is the gait at its default parameters on the starting body, measured once when the run starts
  (``targets[name].ref_speed_mm_s``).
* **read behaviours** (``kind: read``; stand, step, other = the fast play): how much of the calf's behaviour
  the robot keeps, ``sum_k w_k exp(-d_k^2) / sum_k w_k`` over the features the interpretation matches (``d_k``
  as in :func:`calflab.behave.interpret.feature_distance`: a log-ratio over the feature's floor, or a difference
  over its scale). A feature matched exactly counts 1, one off by 1.25x about 0.95, by 2x about 0.62. The
  primitive and its starting parameters are those the interpretation chose on the starting body.

Each motion is searched with a small CMA-ES (``popsize`` x ``generations``, from the optimizer's inner loop)
on seed 0, nothing random, every play cached on disk per body (:class:`calflab.behave.interpret.Interpreter`).
Search cost = ``1 - kept`` plus the interpretation's penalty when a play falls or goes over a limit at the
margin. The best ``verify`` settings within the limits are then played on every seed of the preset with its
friction and mass randomised (as ``repertoire``). The first that stays within every limit at the margin, on
every seed and without falling, is the motion's result. Its kept share and margin come from its worst seed.
A motion with no such setting keeps 0.

Margins are judged as everywhere in session R: every limit is first lowered by the safety margin (0.2: x 0.8),
and a margin is the headroom left over that lowered limit, ``1 - value / (0.8 x limit)``. So 0 = exactly at
margin 0.2, < 0 = over it (the walk's -2.48 of step 1).

Fitness = weighted mean kept share - ``shortfall_weight`` x how far the worst motion's margin is below 0 (at
most 1). The archive axes are ``vigour_kept`` x ``worst_margin`` (descriptors below).

Units: mm, s, mm/s; margins are relative headroom.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab.plugins import BehaviorDescriptor, register
from calflab.schema import P

#: motion -> how the starting parameters, calf features and weights are found
DEFAULT_MOTIONS: list[dict[str, Any]] = [
    {"name": "walk", "kind": "gait", "primitive": "walk"},
    {"name": "trot", "kind": "gait", "primitive": "trot"},
    {"name": "stand", "kind": "read"},
    {"name": "step", "kind": "read"},
    {"name": "other", "kind": "read"},
]


class SuiteMotion(BaseModel):
    name: str = Field(description="Gait primitive, or a behaviour of the reading (stand, step, other ...).")
    kind: Literal["gait", "read"] = "gait"
    primitive: str = Field("", description="Gait: its primitive key. Read: filled from the interpretation.")
    weight: float = 1.0


class SuiteSettings(BaseModel):
    """What ``evaluation.suite`` of a preset holds. ``targets`` and ``cache_dir`` are filled by the lab."""

    motions: list[SuiteMotion] = Field(default_factory=lambda: [SuiteMotion(**m) for m in DEFAULT_MOTIONS])
    interpretation: str = P("", desc="Interpretation run whose behaviours are kept (empty = the latest).")
    margin: float = P(0.2, ge=0.0, le=0.9, desc="Safety margin on every limit.")
    buffer: float = P(0.05, ge=0.0, le=0.5, desc="Headroom a search play needs beyond the margin to count.")
    popsize: int = P(4, ge=2, le=40, desc="CMA-ES candidates per generation per motion (the optimizer's inner "
                                          "popsize overrides it).")
    generations: int = P(2, ge=0, le=50, desc="CMA-ES generations per motion (the optimizer's inner iterations "
                                              "override it).")
    verify: int = P(3, ge=1, le=10, desc="Best settings within the limits checked over every seed, in turn.")
    shortfall_weight: float = P(1.0, ge=0.0, desc="Fitness lost per unit the worst margin is below 0 (over a limit "
                                                  "lowered by the safety margin).")
    #: per motion: {primitive, base, calf, weights, ref_speed_mm_s}; filled when a run starts
    targets: dict[str, dict[str, Any]] | None = None
    #: per-body play cache (the project's .cache/interpret); filled when a run starts
    cache_dir: str = ""


def _interp_settings(suite: SuiteSettings, popsize: int, generations: int) -> Any:
    from calflab.behave.interpret import InterpretSettings

    return InterpretSettings(margin=suite.margin, buffer=suite.buffer, popsize=max(2, popsize),
                             generations=max(1, generations), seed=0)


def kept_share(motion: SuiteMotion, target: dict[str, Any], features: dict[str, Any]) -> float:
    """How much of the motion is kept (0..1), from the robot's reader features."""
    import math

    from calflab.behave.interpret import MATCH, _value

    if motion.kind == "gait":
        ref = float(target.get("ref_speed_mm_s") or 0.0)
        sp = _value(features, "speed_mm_s")
        if ref <= 0 or sp is None:
            return 0.0
        return float(min(1.0, max(0.0, sp / ref)))
    calf, weights = target.get("calf") or {}, target.get("weights") or {}
    num = den = 0.0
    for k, w in weights.items():
        c, r = _value(calf, k), _value(features, k)
        if c is None:
            continue
        den += w
        if r is None:
            continue
        kind, scale, _ = MATCH[k]
        d = math.log((abs(r) + scale) / (abs(c) + scale)) if kind == "log" else (r - c) / scale
        num += w * math.exp(-d * d)
    return float(num / den) if den > 0 else 0.0


def _penalty(e: Any) -> float:
    if e.within_limits:
        return 0.0
    worst = e.margin if e.margin is not None else 0.0
    return 10.0 + 10.0 * max(0.0, -float(worst)) + (20.0 if e.fell else 0.0)


def play_seed(prim: Any, spec: Any, lib: Any, doc: dict[str, Any], s: Any, seed: int, ev: Any) -> tuple[Any, float, float]:
    """One play of a primitive on ``seed`` with the preset's friction and mass randomised."""
    from calflab.behave.physics import compile_params
    from calflab.behave.study import randomization
    from calflab.plugins import registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    key, params = prim.controller(spec, lib)
    off, per = float(prim.warmup_s()), float(prim.period_s())
    length = per if prim.one_shot else s.cycles * per
    t1 = off + min(max(length, s.min_play_s), s.max_play_s)
    copts = {**compile_params(doc), "randomization": randomization(ev.randomize, ev.friction, ev.mass_scale)}
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
    settings = SimSettings(duration_s=round(t1 + 0.3, 3), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=True, seed=seed)
    ro = run_rollout(cm, registry.get("controller", key)(params), settings, lib)  # type: ignore[arg-type]
    return ro, off, t1


def search_motion(it: Any, motion: SuiteMotion, target: dict[str, Any], x0: list[float] | None = None
                  ) -> tuple[list[tuple[float, Any, np.ndarray]], list[Any]]:
    """CMA-ES over the primitive's vector, from ``target.base`` (or ``x0``). Returns (cost, evaluation, x) per play
    and the primitive's dims."""
    import cma

    from calflab.plugins import registry

    cls: Any = registry.get("motion_primitive", target["primitive"])
    dims = list(cls.vector_dims())
    start = cls(dict(target.get("base") or {})).params.model_dump(mode="json")
    weights = target.get("weights") or {}
    calf = target.get("calf") or {}
    out: list[tuple[float, Any, np.ndarray]] = []

    def params_of(x: np.ndarray) -> dict[str, Any]:
        p = dict(start)
        for d, v in zip(dims, np.clip(x, 0.0, 1.0), strict=True):
            p[d.name] = round(d.lo + float(v) * (d.hi - d.lo), 4)
        return p

    def run(x: np.ndarray, params: dict[str, Any]) -> float:
        e = it.evaluate(target["primitive"], params, calf, weights)
        cost = 1.0 - kept_share(motion, target, e.features) + _penalty(e)
        out.append((cost, e, x))
        return cost

    x_start = np.array([float(np.clip((float(start[d.name]) - d.lo) / (d.hi - d.lo), 0.02, 0.98)) for d in dims])
    if x0 is not None and len(x0) == len(dims):
        x_start = np.clip(np.asarray(x0, dtype=float), 0.02, 0.98)
        run(x_start, params_of(x_start))
    else:
        run(x_start, start)
    gens = int(getattr(it, "suite_generations", it.s.generations))
    if not dims or gens <= 0:
        return out, dims
    if len(dims) == 1:  # CMA-ES needs two dimensions: an even grid of the same budget
        budget = it.s.popsize * gens
        for x in np.linspace(0.05, 0.95, budget):
            xx = np.array([x])
            run(xx, params_of(xx))
        return out, dims
    es = cma.CMAEvolutionStrategy(list(x_start), it.s.sigma, {"bounds": [0.0, 1.0], "popsize": it.s.popsize,
                                                               "seed": it.s.seed + 7919, "verbose": -9})
    for _ in range(gens):
        if it.cancelled is not None and it.cancelled():
            break
        xs = es.ask()
        es.tell(xs, [run(np.asarray(x), params_of(np.asarray(x))) for x in xs])
    return out, dims


def evaluate_motion(it: Any, motion: SuiteMotion, target: dict[str, Any], ev: Any, suite: SuiteSettings,
                    x0: list[float] | None = None) -> dict[str, Any]:
    """Search, then verify the best settings within the limits over every seed. Returns the motion's record."""
    from calflab.behave.interpret import judge, robot_features
    from calflab.plugins import registry

    tried, dims = search_motion(it, motion, target, x0)
    tried.sort(key=lambda t: t[0])
    within = [t for t in tried if t[1].within_limits]
    best_nominal = tried[0]
    rec: dict[str, Any] = {
        "name": motion.name, "kind": motion.kind, "primitive": target["primitive"], "weight": motion.weight,
        "searched": len(tried), "within_in_search": len(within), "kept": 0.0, "feasible": False,
        "params": best_nominal[1].params, "x": [float(v) for v in best_nominal[2]],
        "margin": best_nominal[1].margin, "violations": list(best_nominal[1].violations), "fell": best_nominal[1].fell,
        "seeds": [], "verified": 0,
    }
    seeds = list(ev.seeds) or [0]
    for _cost, e, x in within[: suite.verify]:
        prim = registry.get("motion_primitive", target["primitive"])(e.params)
        per_seed = []
        for seed in seeds:
            ro, t0, t1 = play_seed(prim, it.spec, it.lib, it.doc, it.s, seed, ev)
            it.plays += 1
            j = judge(ro, it.spec, it.lib, suite.margin)
            end = float(j["fall_time_s"]) if j["fell"] and j["fall_time_s"] is not None else t1
            try:
                feats = robot_features(ro, it.spec, t0, max(t0 + 0.2, min(t1, end)))
            except ValueError:
                feats = {}
            per_seed.append({"seed": seed, "margin": j["margin"], "fell": j["fell"], "violations": j["violations"],
                             "within": bool(j["within_limits"]), "kept": round(kept_share(motion, target, feats), 4),
                             "speed_mm_s": feats.get("speed_mm_s")})
            if not j["within_limits"]:
                break  # this setting fails: no need for its other seeds
        rec["verified"] += 1
        worst_m = min((p["margin"] for p in per_seed if p["margin"] is not None), default=None)
        if all(p["within"] for p in per_seed) and len(per_seed) == len(seeds):
            rec.update({"feasible": True, "params": e.params, "x": [float(v) for v in x], "seeds": per_seed,
                        "kept": min(p["kept"] for p in per_seed), "margin": worst_m,
                        "violations": [], "fell": False})
            return rec
        if not rec["seeds"] or (worst_m is not None and (rec["margin"] is None or worst_m > rec["margin"])):
            rec.update({"seeds": per_seed, "margin": worst_m, "params": e.params, "x": [float(v) for v in x],
                        "violations": sorted({v for p in per_seed for v in p["violations"]}),
                        "fell": any(p["fell"] for p in per_seed)})
    rec["dims"] = [d.name for d in dims]
    return rec


def hoof_half_width(spec: Any) -> dict[str, float]:
    """Distance of the hooves from the centre line, standing (mm), hind and front (the widest of each pair)."""
    from calflab.mech.statics import default_contacts

    ys = [(b, abs(float(p[1]))) for b, p in default_contacts(spec, spec.world_poses())]
    hind = [v for b, v in ys if ".h" in b]
    front = [v for b, v in ys if ".f" in b]
    return {"hind": round(max(hind, default=0.0), 1), "front": round(max(front, default=0.0), 1)}


def evaluate_body(design: Any, lib: Any, payload: dict[str, Any], preset: Any) -> dict[str, Any]:
    """Task body for a preset with ``evaluation.suite``: the evaluate_candidate result for one body."""
    from calflab.behave.interpret import Interpreter

    ev = preset.evaluation
    suite = SuiteSettings.model_validate(ev.suite)
    if not suite.targets:
        raise ValueError("The vigour suite has no targets: start it from the lab (Evolve), which measures the "
                         "gaits' reference speeds and reads the interpretation first")
    inner = payload.get("inner") or {}
    pop = int(inner.get("popsize") or suite.popsize)
    gens = int(inner["iterations"]) if "iterations" in inner else suite.generations
    s = _interp_settings(suite, pop, gens)
    cache = Path(suite.cache_dir) if suite.cache_dir else None
    it = Interpreter(design.spec, lib, payload.get("compile", {}), s, cache)
    it.suite_generations = gens  # type: ignore[attr-defined]
    t = time.perf_counter()
    x0_all = (payload.get("controller") or {}).get("x0")
    motions: list[dict[str, Any]] = []
    xs: list[float] = []
    at = 0
    from calflab.plugins import registry

    for m in suite.motions:
        target = suite.targets.get(m.name)
        if target is None:
            continue
        n = len(registry.get("motion_primitive", target["primitive"]).vector_dims())  # type: ignore[attr-defined]
        x0 = x0_all[at:at + n] if isinstance(x0_all, list) and len(x0_all) >= at + n else None
        at += n
        rec = evaluate_motion(it, m, target, ev, suite, x0)
        motions.append(rec)
        xs += rec["x"] if len(rec["x"]) == n else [0.5] * n
    wsum = sum(r["weight"] for r in motions) or 1.0
    vigour = float(sum(r["weight"] * r["kept"] for r in motions) / wsum)
    margins = [r["margin"] for r in motions if r["margin"] is not None]
    worst = float(min(margins)) if margins else -3.0
    shortfall = float(min(1.0, max(0.0, -worst)))  # 0 = at the margin-lowered limits
    fitness = vigour - suite.shortfall_weight * shortfall
    terms = {"vigour": {"value": round(vigour, 4), "weight": 1.0, "weighted": round(vigour, 4)},
             "margin_shortfall": {"value": round(shortfall, 4), "weight": -suite.shortfall_weight,
                                  "weighted": round(-suite.shortfall_weight * shortfall, 4)}}
    metrics = {
        "vigour": {"kept": round(vigour, 4), "worst_margin": round(worst, 4), "target_margin": suite.margin,
                   "feasible": sum(1 for r in motions if r["feasible"]), "motions": {r["name"]: r for r in motions},
                   "plays": it.plays, "cache_hits": it.cache_hits, "seconds": round(time.perf_counter() - t, 1)},
        "safety_margin": round(worst, 4),
        "hoof_half_width_mm": hoof_half_width(design.spec),
    }
    walk = next((r for r in motions if r["primitive"] == "walk"), None)
    ctrl_params: dict[str, Any] = {}
    if walk is not None:  # what Simulate candidate plays: the walk as tuned for this body
        prim = registry.get("motion_primitive", "walk")(walk["params"])
        ctrl_params = prim.controller(design.spec, lib)[1]  # type: ignore[attr-defined]
    descriptors = {}
    for key in payload.get("descriptors", []):
        d = registry.get("behavior_descriptor", key)()
        descriptors[key] = float(d.describe_candidate(design.spec, metrics, ctrl_params))  # type: ignore[attr-defined]
    return {"fitness": fitness, "fitness_terms": terms, "controller_params": ctrl_params, "controller_x": xs,
            "metrics": metrics, "descriptors": descriptors, "mass_g": design.spec.total_mass_g(), "evals": it.plays}


# ---------------------------------------------------------------------- preparing a run
def prepare_targets(suite: SuiteSettings, spec: Any, lib: Any, doc_compile: dict[str, Any],
                    interpretation: dict[str, Any] | None, cache_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Per motion: the primitive, its starting parameters, the calf's features and weights, and for a gait its
    reference speed (its defaults played on the starting body, seed 0)."""
    from calflab.behave.interpret import TARGETS, Interpreter

    it = Interpreter(spec, lib, doc_compile, _interp_settings(suite, suite.popsize, max(1, suite.generations)),
                     cache_dir)
    records = {r["behaviour"]: r for r in (interpretation or {}).get("records", [])}
    out: dict[str, dict[str, Any]] = {}
    for m in suite.motions:
        if m.kind == "gait":
            key = m.primitive or m.name
            e = it.evaluate(key, {}, {}, {})
            out[m.name] = {"primitive": key, "base": {}, "calf": {}, "weights": {},
                           "ref_speed_mm_s": float(e.features.get("speed_mm_s") or 0.0)}
            continue
        r = records.get(m.name)
        if r is None:
            raise ValueError(f"The interpretation has no behaviour {m.name!r} (it has {sorted(records)})")
        calf = {k: (v.get("mean") if isinstance(v, dict) else v) for k, v in r["read"]["features"].items()}
        out[m.name] = {"primitive": m.primitive or r["primitive"], "base": dict(r["params"]), "calf": calf,
                       "weights": dict(TARGETS.get(m.name, TARGETS["other"]))}
    return out


def suite_plays(suite: SuiteSettings, popsize: int, generations: int, seeds: int) -> dict[str, Any]:
    """Plays per body at most: per motion 1 + popsize x generations searched (none when cached) and up to
    ``verify`` x seeds verified (fewer when a setting fails early). Also the simulated seconds per play."""
    from calflab.plugins import registry

    search = verify = 0
    seconds = 0.0
    s = _interp_settings(suite, popsize, max(1, generations))
    for m in suite.motions:
        key = m.primitive or {"stand": "weight_shift", "step": "step", "other": "trot"}.get(m.name, m.name)
        try:
            prim = registry.get("motion_primitive", key)({})
        except KeyError:
            continue
        n = len(prim.vector_dims())  # type: ignore[attr-defined]
        searched = 1 + (popsize * generations if n else 0)
        search += searched
        verify += suite.verify * seeds
        per = float(prim.period_s())  # type: ignore[attr-defined]
        length = per if prim.one_shot else s.cycles * per  # type: ignore[attr-defined]
        play = float(prim.warmup_s()) + min(max(length, s.min_play_s), s.max_play_s) + 0.7  # type: ignore[attr-defined]
        seconds += play * (searched + suite.verify * seeds)
    total = search + verify
    return {"search_plays": search, "verify_plays_max": verify, "plays_max": total,
            "simulated_s_max": round(seconds, 1), "mean_play_s": round(seconds / max(1, total), 2)}


# ---------------------------------------------------------------------- archive axes
@register
class VigourKept(BehaviorDescriptor):
    key = "vigour_kept"
    label = "Vigour kept"
    description = ("How much of the suite's motions a body keeps within every limit at the margin (vigour preset): "
                   "gait speed for the gaits, the calf's features for the read behaviours; 0..1.")
    range = (0.0, 1.0)
    unit = ""

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return float(((metrics.get("vigour") or {}).get("kept")) or 0.0)


@register
class WorstMargin(BehaviorDescriptor):
    key = "worst_margin"
    label = "Worst safety margin"
    description = ("The smallest headroom across the suite's motions and seeds over every limit lowered by the safety "
                   "margin (0 = exactly at margin 0.2, < 0 = over it).")
    range = (-1.0, 0.6)
    unit = ""

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        v = (metrics.get("vigour") or {}).get("worst_margin", metrics.get("safety_margin"))
        return float(min(0.6, max(-1.0, float(v)))) if v is not None else -1.0


@register
class HoofWidth(BehaviorDescriptor):
    key = "hoof_width"
    label = "Hoof width"
    description = "Distance of the hind hooves from the centre line, standing (the base's half-width)."
    range = (50.0, 300.0)
    unit = "mm"

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        w = metrics.get("hoof_half_width_mm")
        if isinstance(w, dict) and w.get("hind") is not None:
            return float(w["hind"])
        try:
            return float(hoof_half_width(spec)["hind"])
        except Exception:
            return 0.0
