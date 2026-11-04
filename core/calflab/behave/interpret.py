"""Interpretation: what the calf did, said in the robot's own movements (ADR-085).

For each behaviour of a reading (:mod:`calflab.behave.reading`), every motion
primitive that may stand for it (``MotionPrimitive.behaviours``, and fitting the
body) is searched with a small CMA-ES over its few parameters. Each candidate
is **played in physics** (the torque-speed servos, derating 1, belts and
springs as designed; :mod:`calflab.behave.physics`'s compile settings) and
**read back by the same reader** as the calf
(:func:`calflab.behave.reading.stretch_features` on
:func:`calflab.behave.signals.from_rollout`, contact from the hooves' forces).
Its cost is the distance between the robot's features and the calf's
(log-ratios for sizes and rates, differences over a scale for signed or
bounded ones, weighted), plus a penalty when it falls or goes over any limit
with the margin (``calflab.evolve.safety.safety_report``: stall, rated,
speed, envelope, belts, joint limits). The closest candidate within every
limit is the interpretation.

**The record** says what was read, what the robot does instead, per feature
whether it was kept (within 0.8-1.25x), exaggerated, reduced, reversed or
dropped, and **why**: the limits that stopped a candidate closer to the calf
(the best evaluated point that was closer on that feature but went over a
limit), a limit the chosen one is close to, the primitive's own range, or a
gap of the body (no head, no tail...). It also reports the cost (plays,
seconds) per body.

Evaluations are cached per body (spec, primitive, parameters, settings) on
disk, so a second interpretation of the same body is nearly free.

Units: s, deg, mm.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.schema import P

#: per feature: kind ("log" = ratio, "abs" = difference over scale), the scale or floor, and its label
MATCH: dict[str, tuple[str, float, str]] = {
    "tempo_s": ("log", 0.05, "tempo (period)"),
    "qom_deg_s": ("log", 0.5, "quantity of motion"),
    "amplitude_mean_deg": ("log", 0.3, "amplitude"),
    "step_rate_hz": ("log", 0.05, "step rate"),
    "two_up_fraction": ("abs", 0.25, "share with two or more hooves up"),
    "roll_range_deg": ("log", 0.3, "trunk roll (sway)"),
    "pitch_range_deg": ("log", 0.3, "trunk pitch"),
    "heave_mm": ("log", 2.0, "trunk heave"),
    "turn_rate_deg_s": ("abs", 15.0, "turn rate"),
    "speed_mm_s": ("log", 5.0, "travel speed"),
    "lean_roll_deg": ("abs", 3.0, "lean sideways"),
    "lean_pitch_deg": ("abs", 3.0, "lean fore-aft"),
}
#: what is matched per behaviour (weights)
TARGETS: dict[str, dict[str, float]] = {
    "stand": {"qom_deg_s": 1.0, "amplitude_mean_deg": 0.5, "roll_range_deg": 0.5, "pitch_range_deg": 0.5,
              "heave_mm": 0.3},
    "weight_shift": {"qom_deg_s": 1.0, "amplitude_mean_deg": 1.0, "roll_range_deg": 1.0, "pitch_range_deg": 0.5,
                     "tempo_s": 0.5, "lean_roll_deg": 0.5},
    "step": {"step_rate_hz": 1.0, "amplitude_mean_deg": 1.0, "qom_deg_s": 1.0, "roll_range_deg": 0.5,
             "tempo_s": 0.5},
    "walk": {"tempo_s": 1.0, "step_rate_hz": 1.0, "amplitude_mean_deg": 1.0, "qom_deg_s": 1.0, "speed_mm_s": 0.5,
             "turn_rate_deg_s": 0.5, "roll_range_deg": 0.5, "pitch_range_deg": 0.3, "two_up_fraction": 0.5},
    "turn": {"turn_rate_deg_s": 1.5, "step_rate_hz": 1.0, "tempo_s": 0.5, "amplitude_mean_deg": 0.5,
             "qom_deg_s": 0.5},
    "other": {"tempo_s": 1.0, "step_rate_hz": 1.0, "two_up_fraction": 1.0, "qom_deg_s": 1.0,
              "amplitude_mean_deg": 1.0, "pitch_range_deg": 0.5, "heave_mm": 0.5, "turn_rate_deg_s": 0.5,
              "speed_mm_s": 0.3},
}


class InterpretSettings(BaseModel):
    margin: float = P(0.2, ge=0.0, le=0.9, step=0.05, desc="Safety margin on every limit (0.2 = keep 20 % in hand).")
    popsize: int = P(6, ge=2, le=40, desc="CMA-ES candidates per generation.")
    generations: int = P(3, ge=1, le=50, desc="CMA-ES generations per primitive (plus the primitive's defaults).")
    sigma: float = P(0.3, ge=0.05, le=1.0, step=0.05, desc="CMA-ES step size (on parameters scaled to 0..1).")
    seed: int = P(0, ge=0, ui="number", desc="Seed of the search and of the plays.")
    cycles: float = P(2.0, ge=1.0, le=6.0, step=0.5, desc="Periods of a cycling primitive played per candidate.")
    min_play_s: float = P(4.0, unit="s", ge=1.0, le=20.0,
                          desc="Shortest play judged (after the warm-up): two of the 2 s windows of sustained loads.")
    max_play_s: float = P(10.0, unit="s", ge=2.0, le=60.0, desc="Longest play judged.")
    infeasible_penalty: float = P(10.0, ge=0.0, desc="Added to the cost of a candidate over a limit or falling.")
    buffer: float = P(0.05, ge=0.0, le=0.5, step=0.01,
                      desc="A candidate counts as within the limits only with this much margin left beyond the "
                           "safety margin: plays are a few seconds, a performance a minute (PROVISIONAL).")
    primitives: dict[str, list[str]] = P(default_factory=dict, ui="json",
                                         desc="Optional: behaviour -> primitive keys to try (empty = all that may "
                                              "stand for it and fit the body).")
    behaviours: list[str] = P(default_factory=list, ui="json", desc="Only these behaviours (empty = every one read).")


class Evaluation(BaseModel):
    primitive: str
    params: dict[str, Any]
    cost: float
    distance: float
    per_feature: dict[str, float]
    within_limits: bool
    fell: bool
    margin: float | None
    violations: list[str]
    features: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False
    wall_s: float = 0.0


# ---------------------------------------------------------------------- distance
def _value(f: dict[str, Any], k: str) -> float | None:
    v = f.get(k)
    if isinstance(v, dict):
        v = v.get("mean")
    return None if v is None else float(v)


def feature_distance(robot: dict[str, Any], calf: dict[str, Any], weights: dict[str, float]
                     ) -> tuple[float, dict[str, float]]:
    """Weighted squared distance and its parts per feature (features either side does not have are skipped)."""
    parts = {}
    for k, w in weights.items():
        c, r = _value(calf, k), _value(robot, k)
        if c is None or r is None:
            continue
        kind, scale, _label = MATCH[k]
        if kind == "log":
            d = math.log((abs(r) + scale) / (abs(c) + scale))
        else:
            d = (r - c) / scale
        parts[k] = round(w * d * d, 4)
    return float(sum(parts.values())), parts


def verdict(k: str, calf: float | None, robot: float | None) -> str:
    if calf is None:
        return "not read"
    if robot is None:
        return "not measured"
    kind, scale, _ = MATCH[k]
    if kind == "abs":
        if abs(robot - calf) <= 0.5 * scale:
            return "kept"
        if calf != 0 and robot != 0 and math.copysign(1, robot) != math.copysign(1, calf) and abs(calf) > 0.5 * scale:
            return "reversed"
        return "exaggerated" if abs(robot) > abs(calf) else "reduced"
    if abs(calf) <= scale:
        return "kept" if abs(robot) <= 2 * scale else "exaggerated"
    r = abs(robot) / abs(calf)
    if r < 0.1:
        return "dropped"
    return "kept" if 0.8 <= r <= 1.25 else ("exaggerated" if r > 1.25 else "reduced")


# ---------------------------------------------------------------------- playing a primitive
def _checks(spec: Any) -> dict[str, float]:
    feral = spec.metadata.get("feral") or {}
    return {"rated_fraction": 0.6, "sustained_fraction": 0.25, "breaking_fraction": 0.25, **(feral.get("checks") or {})}


def play_primitive(prim: Any, spec: Any, lib: Any, doc_compile: dict[str, Any], s: InterpretSettings,
                   cancelled: Any = None) -> tuple[Any, float, float, tuple[str, dict[str, Any]]]:
    """Play one primitive in physics. Returns the rollout, the judged window (t0, t1, s) and the controller."""
    from calflab.behave.physics import compile_params
    from calflab.plugins import registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    key, params = prim.controller(spec, lib)
    off = float(prim.warmup_s())
    per = float(prim.period_s())
    length = per if prim.one_shot else s.cycles * per
    length = min(max(length, s.min_play_s), s.max_play_s)
    t1 = off + length
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(compile_params(doc_compile)), s.seed)
    settings = SimSettings(duration_s=round(t1 + 0.3, 3), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=True, seed=s.seed)
    ctrl = registry.get("controller", key)(params)
    ro = run_rollout(cm, ctrl, settings, lib, cancelled=cancelled)  # type: ignore[arg-type]
    return ro, off, t1, (key, params)


def judge(ro: Any, spec: Any, lib: Any, margin: float) -> dict[str, Any]:
    """Falls and every limit with the margin, as the repertoire evolution and the physics review judge them."""
    from calflab.evolve.safety import SafetyPolicy, safety_report
    from calflab.sim import compute_metrics

    c = _checks(spec)
    pol = SafetyPolicy(margin=margin, rated_fraction=c["rated_fraction"], sustained_fraction=c["sustained_fraction"],
                       breaking_fraction=c["breaking_fraction"])
    metrics = compute_metrics(ro)
    rep = safety_report(ro, spec, lib, pol, metrics)
    fell = bool(ro.meta.get("fell"))
    return {"fell": fell, "fall_time_s": ro.meta.get("fall_time"), "violations": list(rep["violations"]),
            "margin": rep["margin"], "within_limits": not rep["violations"] and not fell,
            "constraints": {r["key"]: {"label": r["label"], "value": r["value"], "limit": r["limit"],
                                       "margin": r["margin"], "violated": r["violated"]} for r in rep["constraints"]}}


def robot_features(ro: Any, spec: Any, t0: float, t1: float) -> dict[str, Any]:
    """The reader's features of the robot over [t0, t1) (contact from the hooves' forces)."""
    from calflab.behave.reading import lifted_from_contact, stretch_features
    from calflab.behave.signals import _feet, from_rollout

    sig = from_rollout(ro, spec, t0, t1)
    m = (ro.t >= t0) & (ro.t < t1)
    legs = [leg for leg, *_r in _feet(spec)]
    names = list(ro.foot_geoms)
    ff = ro.foot_force[m].astype(float) if ro.foot_force.size else np.zeros((int(m.sum()), 0))
    order = []
    for g in names:  # foot geoms in the rollout's order -> legs
        leg = next((lg for lg in legs if f".{lg}." in g or g.startswith(f"leg.{lg}") or f"{lg}." in g), g)
        order.append(leg)
    up = lifted_from_contact(ff, order, sig.fps) if ff.shape[1] else {}
    return stretch_features(sig, up, 0, sig.frames, camera_moves=False)


# ---------------------------------------------------------------------- the search
def _cache_key(spec_key: str, prim_key: str, params: dict[str, Any], s: InterpretSettings, compile: dict[str, Any]) -> str:
    blob = json.dumps({"spec": spec_key, "p": prim_key, "params": params, "margin": s.margin, "seed": s.seed,
                       "cycles": s.cycles, "min": s.min_play_s, "max": s.max_play_s, "compile": compile, "v": 2},
                      sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class Interpreter:
    """Evaluates primitives on one body, with a disk cache (``cache_dir``) of every evaluation."""

    def __init__(self, spec: Any, lib: Any, doc_compile: dict[str, Any], s: InterpretSettings,
                 cache_dir: Path | None = None, cancelled: Any = None, report: Any = None):
        from calflab.behave.physics import compile_params

        self.spec, self.lib, self.doc, self.s = spec, lib, doc_compile, s
        self.compile = compile_params(doc_compile)
        self.spec_key = hashlib.sha1(spec.model_dump_json().encode("utf-8")).hexdigest()
        self.cache_dir = cache_dir / self.spec_key[:16] if cache_dir else None
        self.cancelled, self.report = cancelled, report
        self.plays = 0
        self.cache_hits = 0
        self.wall_s = 0.0

    def evaluate(self, prim_key: str, params: dict[str, Any], calf: dict[str, Any], weights: dict[str, float]
                 ) -> Evaluation:
        from calflab.plugins import registry

        cls = registry.get("motion_primitive", prim_key)
        prim = cls(params)
        full = prim.params.model_dump(mode="json")
        key = _cache_key(self.spec_key, prim_key, full, self.s, self.compile)
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        cached = None
        if path is not None and path.is_file():
            cached = json.loads(path.read_text(encoding="utf-8"))
        hit = cached is not None
        if cached is None:
            t = time.perf_counter()
            ro, t0, t1, _ctrl = play_primitive(prim, self.spec, self.lib, self.doc, self.s, self.cancelled)
            j = judge(ro, self.spec, self.lib, self.s.margin)
            end = float(j["fall_time_s"]) if j["fell"] and j["fall_time_s"] is not None else t1
            try:
                feats = robot_features(ro, self.spec, t0, max(t0 + 0.2, min(t1, end)))
            except ValueError:
                feats = {}
            wall = time.perf_counter() - t
            self.plays += 1
            self.wall_s += wall
            cached = {"judge": j, "features": feats, "wall_s": round(wall, 3)}
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(cached, default=float), encoding="utf-8")
        else:
            self.cache_hits += 1
        j, feats = cached["judge"], cached["features"]
        dist, parts = feature_distance(feats, calf, weights)
        cost = dist
        within = bool(j["within_limits"]) and (j["margin"] is None or float(j["margin"]) >= self.s.buffer)
        if not within:
            worst = j["margin"] if j["margin"] is not None else 0.0
            cost += self.s.infeasible_penalty + 10.0 * max(0.0, -float(worst)) + (20.0 if j["fell"] else 0.0)
        return Evaluation(primitive=prim_key, params=full, cost=round(cost, 4), distance=round(dist, 4),
                          per_feature=parts, within_limits=within, fell=j["fell"], margin=j["margin"],
                          violations=j["violations"], features=feats, constraints=j["constraints"],
                          cached=hit, wall_s=float(cached.get("wall_s", 0.0)))

    def search(self, prim_key: str, base: dict[str, Any], calf: dict[str, Any], weights: dict[str, float]
               ) -> list[Evaluation]:
        """The primitive's defaults (with ``base``), then a small CMA-ES over its vector dims."""
        import cma

        from calflab.plugins import registry

        cls = registry.get("motion_primitive", prim_key)
        dims = cls.vector_dims()
        start = cls(base).params.model_dump(mode="json")
        evals = [self.evaluate(prim_key, start, calf, weights)]
        if not dims:
            return evals

        def params_of(x: np.ndarray) -> dict[str, Any]:
            p = dict(start)
            for d, v in zip(dims, np.clip(x, 0.0, 1.0), strict=True):
                p[d.name] = round(d.lo + float(v) * (d.hi - d.lo), 4)
            return p

        if len(dims) == 1:  # CMA-ES needs two dimensions: an even grid of the same budget
            for k, x in enumerate(np.linspace(0.05, 0.95, self.s.popsize * self.s.generations)):
                if self.cancelled is not None and self.cancelled():
                    break
                if self.report is not None:
                    self.report(f"{prim_key}: {k + 1}/{self.s.popsize * self.s.generations}")
                evals.append(self.evaluate(prim_key, params_of(np.array([x])), calf, weights))
            return evals
        x0 = [float(np.clip((float(start[d.name]) - d.lo) / (d.hi - d.lo), 0.02, 0.98)) for d in dims]
        es = cma.CMAEvolutionStrategy(x0, self.s.sigma, {"bounds": [0.0, 1.0], "popsize": self.s.popsize,
                                                         "seed": self.s.seed + 7919, "verbose": -9})
        for g in range(self.s.generations):
            if self.cancelled is not None and self.cancelled():
                break
            xs = es.ask()
            res = []
            for k, x in enumerate(xs):
                if self.report is not None:
                    self.report(f"{prim_key}: generation {g + 1}/{self.s.generations}, candidate {k + 1}/{len(xs)}")
                e = self.evaluate(prim_key, params_of(np.asarray(x)), calf, weights)
                evals.append(e)
                res.append(e.cost)
            es.tell(xs, res)
        return evals


def choose_leg(calf: dict[str, Any], behaviour: str) -> str:
    """Which hoof the weight moves off, from the calf's lean (right side down = weight on the right: the left hind
    is freed), for a step the first leg the calf lifted."""
    order = ((calf.get("footfall") or {}).get("order") or "") if isinstance(calf.get("footfall"), dict) else ""
    if behaviour == "step" and order:
        return order.split("-")[0]
    lean = _value(calf, "lean_roll_deg") or 0.0
    return "hl" if lean > 0 else "hr"


def _why(k: str, best: Evaluation, evals: list[Evaluation], v: str) -> str:
    """Why a feature was not kept: the limits that stopped closer candidates, a limit close by, or the range."""
    if v in ("kept", "not read", "not measured"):
        return ""
    mine = best.per_feature.get(k)
    closer = [e for e in evals if not e.within_limits and e.per_feature.get(k) is not None and mine is not None
              and e.per_feature[k] < 0.5 * mine]
    if closer:
        votes: dict[str, int] = {}
        for e in closer:
            for w in (["fall"] if e.fell else []) + e.violations:
                votes[w] = votes.get(w, 0) + 1
        if votes:
            top = sorted(votes.items(), key=lambda kv: -kv[1])
            return ("closer candidates went over: " + ", ".join(f"{w} ({n} of {len(closer)})" for w, n in top[:3]))
    near = [(c["margin"], key) for key, c in best.constraints.items() if c.get("margin") is not None
            and c["margin"] < 0.15]
    if near:
        m, key = min(near)
        return f"the chosen one is near its {best.constraints[key]['label'].lower()} limit (margin {m:.2f})"
    return "beyond what this primitive's parameters reached in the search (not a limit)"


def interpret_behaviour(it: Interpreter, behaviour: str, calf: dict[str, Any], candidates: list[str],
                        calf_detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search every candidate primitive for one read behaviour; the record of the closest within limits."""
    weights = TARGETS.get(behaviour, TARGETS["other"])
    t = time.perf_counter()
    p0, h0 = it.plays, it.cache_hits
    alternatives = []
    all_evals: dict[str, list[Evaluation]] = {}
    leg = choose_leg(calf_detail or calf, behaviour)
    for key in candidates:
        base: dict[str, Any] = {}
        if key in ("weight_shift", "step"):
            base["leg"] = leg
        if key in ("turn", "trot") and (_value(calf, "turn_rate_deg_s") or 0.0) < 0 and key == "turn":
            base["turn"] = -0.8
        evals = it.search(key, base, calf, weights)
        all_evals[key] = evals
        ok = [e for e in evals if e.within_limits]
        best = min(ok or evals, key=lambda e: e.cost)
        alternatives.append({"primitive": key, "best_cost": best.cost, "best_distance": best.distance,
                             "feasible": bool(ok), "evaluated": len(evals),
                             "feasible_share": round(len(ok) / max(1, len(evals)), 3),
                             "defaults": {"within_limits": evals[0].within_limits, "violations": evals[0].violations,
                                          "margin": evals[0].margin, "fell": evals[0].fell,
                                          "distance": evals[0].distance}})
    feasible = [(e, k) for k, ev in all_evals.items() for e in ev if e.within_limits]
    chosen, ckey = (min(feasible, key=lambda ek: ek[0].cost) if feasible
                    else min(((e, k) for k, ev in all_evals.items() for e in ev), key=lambda ek: ek[0].cost))
    rows = []
    for k in weights:
        c, r = _value(calf, k), _value(chosen.features, k)
        v = verdict(k, c, r)
        rows.append({"feature": k, "label": MATCH[k][2], "calf": c, "robot": r,
                     "ratio": None if c in (None, 0) or r is None else round(r / c, 3), "verdict": v,
                     "why": _why(k, chosen, all_evals[ckey], v)})
    return {
        "behaviour": behaviour, "primitive": ckey, "params": chosen.params, "within_limits": chosen.within_limits,
        "fell": chosen.fell, "margin": chosen.margin, "violations": chosen.violations,
        "distance": chosen.distance, "robot_features": chosen.features, "comparison": rows,
        "constraints": chosen.constraints, "alternatives": alternatives, "leg": leg,
        "note": "" if feasible else "no candidate stayed within every limit: the closest one is shown, not used",
        "cost": {"plays": it.plays - p0, "cache_hits": it.cache_hits - h0,
                 "seconds": round(time.perf_counter() - t, 1)},
    }


def candidates_for(behaviour: str, spec: Any, s: InterpretSettings) -> list[str]:
    from calflab.plugins import registry

    if s.primitives.get(behaviour):
        return list(s.primitives[behaviour])
    out = []
    for c in registry.all("motion_primitive").values():
        if behaviour in c.behaviours and c.fits(spec):  # type: ignore[attr-defined]
            out.append(c.key)
    return sorted(out, key=lambda k: (0 if k == behaviour else 1, k))
