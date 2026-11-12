"""Behaviour for a body, from its outcome (ADR-110, session R15).

For one body (a worker payload as ``hardware.screen_task``'s) and one of the four behaviours of
``calflab.fitness.outcomes``, CMA-ES searches the ``outcome_motion`` controller's numbers for the version that does
the behaviour best while staying within the R11c suite's limits at its margin (servo torque-speed envelope, sustained
torque, stall, belt tension, joint ranges and speed; ``hardware.judge_play``). Nothing of the old primitives defines
the behaviour; some are used as starting points (``starts``).

* ``play_seed``: one version on one seed: the scene (a block for suckling; contact probes), the rollout, the limits,
  the outcome, a rank.
* ``optimise``: warm starts first, CMA-ES from the best of them, every candidate on the search seeds (worst seed
  ranks), the best few re-judged at the judging length on the judging seeds.

Ranking (search only): the behaviour's score normalised (``NORM``; when a gate fails, half of it capped at 1), less 2 per
failed gate, less 5 if the play stopped early (a fall), plus the limit margin when it is negative (0 = exactly at
margin 0.2). Picking the best is lexicographic: holds, within, then this rank. A version **holds** when, on
every judging seed, it is within every limit and passes every gate.

Units: s, deg, mm, N; margins are headroom over limits lowered by the suite's margin.
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

VERSION = 1  # part of every cache key: bump when a play would no longer give the same record

#: per behaviour, score -> rank units (ranking only; PROVISIONAL): 250 mm/s of trot, stand and suckle effort x2,
#: lie as it is
NORM = {"trot": 1.0 / 250.0, "suckle": 2.0, "stand": 2.0, "lie": 1.0, "free": 2.0}
#: excess over the limits (sum over joints of the most-used limit's use - 1) costs this much rank: margins
#: saturate at -3 for the sustained limits, so without it a search far over a limit has no slope (as ADR-107)
EXCESS_WEIGHT = 0.1


class OutcomeSearch(BaseModel):
    """CMA-ES per body and behaviour."""

    popsize: int = P(10, ge=4, le=40, desc="Candidates per generation.")
    generations: int = P(12, ge=0, le=100, desc="Generations after the warm starts.")
    sigma: float = P(0.2, ge=0.02, le=1.0, step=0.01, desc="Step size on dims scaled to 0..1.")
    seed: int = P(0, ge=0, ui="number", desc="Seed of the search.")
    search_seeds: list[int] = Field(default_factory=lambda: [0, 1, 2], description="Sim seeds every candidate plays.")
    judge_seeds: list[int] = Field(default_factory=lambda: [0, 1, 2], description="Seeds of the final judging.")
    judge_top: int = P(3, ge=1, le=10, desc="How many of the best versions are re-judged at the judging length.")
    early_stop: float = P(-6.0, ge=-50.0, le=0.0, desc="A candidate ranked below this on its first seed plays no more.")


class BehaviourSpace(BaseModel):
    """What is searched for one behaviour: dims (name, lo, hi), fixed params, play lengths, the task's settings."""

    behaviour: str
    dims: list[tuple[str, float, float]]
    fixed: dict[str, Any] = Field(default_factory=dict)
    search_s: float = 12.0
    judge_s: float = 60.0
    #: one-shot behaviours (lying down) play their own length: keyframes + this
    one_shot_extra_s: float | None = None
    task: dict[str, Any] = Field(default_factory=dict)


def _kf(prefix: str, ranges: dict[str, tuple[float, float]]) -> list[tuple[str, float, float]]:
    return [(f"{prefix}_{g}", lo, hi) for g, (lo, hi) in ranges.items()]


#: posture ranges (deg relative to standing), inside the PROVISIONAL joint ranges (hip ab/ad +-25, stifle and hock
#: -30..80, shoulder -60..60, carpus -10..130) less a margin
STAND_RANGES = {"abd": (-10.0, 10.0), "stifle": (-25.0, 45.0), "hock": (-25.0, 45.0), "shoulder": (-35.0, 35.0),
                "carpus": (-8.0, 45.0)}
#: suckling: a light lean around standing (Emily, 2026-11-11: a forward lean is enough)
LEAN_RANGES = {"abd": (-8.0, 8.0), "stifle": (-15.0, 25.0), "hock": (-15.0, 25.0), "shoulder": (-20.0, 20.0),
               "carpus": (-6.0, 25.0)}
LIE_RANGES = {"abd": (-10.0, 10.0), "stifle": (-20.0, 78.0), "hock": (-20.0, 78.0), "shoulder": (-58.0, 20.0),
              "carpus": (-5.0, 128.0)}


def default_spaces() -> dict[str, BehaviourSpace]:
    """The pilot's spaces (ADR-110). Lengths: searched short, judged long."""
    return {
        "stand": BehaviourSpace(
            behaviour="stand", dims=[*_kf("p1", STAND_RANGES), ("roll_gain", -1.0, 1.0), ("pitch_gain", -1.0, 1.0)],
            fixed={"p1_s": 2.0}, search_s=12.0, judge_s=120.0),
        "suckle": BehaviourSpace(
            behaviour="suckle",
            dims=[*_kf("p1", LEAN_RANGES), ("p1_s", 0.5, 3.0), *_kf("p2", LEAN_RANGES), ("p2_s", 0.5, 3.0),
                  *_kf("p3", LEAN_RANGES), ("p3_s", 5.0, 16.0),
                  ("pitch_gain", -1.0, 1.0), ("pitch_gain_hind", -1.0, 1.0), ("roll_gain", -1.0, 1.0)],
            # variant A, chosen by Emily (ADR-110): a 6 s approach then a 10 s press, searched at its judging
            # length; keyframe 3, reached slowly, lets the lean keep going as the hooves creep
            fixed={}, search_s=16.0, judge_s=16.0, task={"press_from_s": 6.0, "max_slip_mm": 30.0}),
        "trot": BehaviourSpace(
            behaviour="trot",
            dims=[("cycle_s", 0.35, 1.0), ("swing", 0.3, 0.55), ("phase_fl", 0.0, 1.0), ("phase_hr", 0.0, 1.0),
                  ("phase_fr", 0.0, 1.0), ("sweep_stifle", -12.0, 4.0), ("sweep_hock", -4.0, 20.0),
                  ("sweep_shoulder", -16.0, 4.0), ("lift_stifle", 0.0, 25.0), ("lift_hock", 0.0, 35.0),
                  ("lift_carpus", 0.0, 50.0), ("lift_shoulder", -25.0, 5.0), ("abd_sway", -6.0, 6.0),
                  ("roll_gain", 0.0, 2.0), ("pitch_gain", 0.0, 2.0), ("yaw_gain", 0.0, 3.0),
                  ("p1_stifle", -15.0, 15.0), ("p1_hock", -15.0, 15.0), ("p1_shoulder", -15.0, 15.0),
                  ("p1_carpus", -5.0, 15.0)],
            fixed={"gait_amp": 1.0, "p1_s": 1.0, "ramp_s": 1.5}, search_s=12.0, judge_s=60.0),
        "lie": BehaviourSpace(
            behaviour="lie",
            dims=[*_kf("p1", LIE_RANGES), ("p1_s", 0.8, 6.0), *_kf("p2", LIE_RANGES), ("p2_s", 0.8, 6.0),
                  ("pitch_gain", -1.0, 1.0)],
            fixed={}, one_shot_extra_s=3.5),
    }


class OutcomeSettings(BaseModel):
    """A preset's ``outcomes:`` block (``config/fitness/outcomes_r15.yaml``): which behaviours, at which mass model
    and margin, their task settings (``calflab.fitness.outcomes.TASKS``) and search spaces (``default_spaces`` when
    not given), and the per-behaviour search."""

    behaviours: list[str] = Field(default_factory=lambda: ["stand", "suckle", "trot", "lie"])
    mass_model: str = "explicit_v2"
    margin: float = 0.2
    search: OutcomeSearch = Field(default_factory=OutcomeSearch)
    tasks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    spaces: dict[str, BehaviourSpace] = Field(default_factory=dict)

    def space(self, behaviour: str) -> BehaviourSpace:
        """The behaviour's space with the preset's task settings over the space's own."""
        sp = self.spaces.get(behaviour) or default_spaces()[behaviour]
        return sp.model_copy(update={"task": {**sp.task, **self.tasks.get(behaviour, {})}})


def settings_from_preset(name: str) -> OutcomeSettings:
    from calflab.fitness.preset import preset

    p = preset(name)
    if p.outcomes is None:
        raise ValueError(f"preset {name} has no outcomes block")
    return OutcomeSettings.model_validate(p.outcomes)


def warm_starts(behaviour: str, lie_versions: list[dict[str, Any]] | None = None) -> list[dict[str, float]]:
    """Starting versions per behaviour (ADR-110): standing still; a lean forward on the brace; ``feral_motion``'s
    trot at R11c's grid corners (lift 0.6); R13's lie_rise kneel and lie poses (``lie_versions``: their
    ``feral_motion`` params, the classic one first)."""
    from calflab.control.outcome import from_feral_trot

    if behaviour == "stand":
        return [{}]
    if behaviour == "suckle":  # standing, then small leans (shoulders back = trunk forward over the front hooves)
        return [{"p1_s": 2.0, "p2_s": 2.0},
                {"p1_s": 2.0, "p2_s": 2.0, "p2_shoulder": 3.0},
                {"p1_s": 2.0, "p2_s": 2.0, "p2_shoulder": 6.0},
                {"p1_s": 2.0, "p2_s": 2.0, "p2_shoulder": 4.0, "p2_stifle": 4.0, "p2_hock": 4.0},
                {"p1_s": 2.0, "p2_s": 2.0, "p2_shoulder": 4.0, "p2_stifle": 4.0, "p2_hock": 4.0,
                 "p3_s": 12.0, "p3_shoulder": 7.0, "p3_stifle": 6.0, "p3_hock": 6.0}]
    if behaviour == "trot":
        out = []
        for c, st in ((0.5, 1.5), (0.6, 1.0), (0.8, 0.5), (0.4, 2.0)):
            p = from_feral_trot(cycle_s=c, stride=st, lift=0.6)
            out.append({k: v for k, v in p.items() if k not in ("gait_amp", "ramp_s")})
        return out
    if behaviour == "lie":
        from calflab.control.feral_motion import FeralMotionController

        out = []
        versions: list[dict[str, Any]] = [{}, *(lie_versions or [])]
        for v in versions:
            d = FeralMotionController.Params.model_validate({"mode": "lie_rise", **v})
            kneel_s = float(d.kneel_s) or float(d.phase_s)
            lie_s = float(d.lie_s) or float(d.phase_s)
            out.append({"p1_shoulder": d.kneel_shoulder, "p1_carpus": d.kneel_carpus, "p1_s": kneel_s,
                        "p2_shoulder": d.lie_shoulder, "p2_carpus": d.lie_carpus, "p2_stifle": d.lie_stifle,
                        "p2_hock": d.lie_hock, "p2_s": lie_s})
        return out
    raise KeyError(behaviour)


# ====================================================================== one play
def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def scene(behaviour: str, cm: Any, spec: Any, task: Any) -> Any:
    """The compiled model with what the behaviour needs: a block ahead of the head and the head made solid for
    suckling; contact probes (head on block, the rest of the body on the block, the body but hooves on the floor)."""
    from calflab.sim.scene import Block, collision_geoms, with_scene

    feet = set(cm.foot_geoms)
    if behaviour == "suckle":
        head = next(g for g in spec.root.geoms if g.id == "head.mass")
        hx = float(spec.root.pos[0] + head.pos[0])
        hz = float(cm.root_height * 1000.0 + head.pos[2])
        r = float(head.size[0])
        hx_half = float(task.half_mm[0])
        block = Block(id="suckle.block", center_mm=(hx + r + float(task.gap_mm) + hx_half, float(spec.root.pos[1]),
                                                    hz + float(task.height_mm)), half_mm=tuple(task.half_mm))
        solid = [*collision_geoms(cm), "head.mass"]
        body = [g for g in solid if g not in feet]
        probes = [{"id": "head_block", "geoms": ["head.mass"], "other": [block.id]},
                  {"id": "body_block", "geoms": [g for g in solid if g != "head.mass"], "other": [block.id]},
                  {"id": "body_floor", "geoms": body, "other": ["floor"]}]
        return with_scene(cm, [block], ["head.mass"], probes)
    body = [g for g in collision_geoms(cm) if g not in feet]
    return with_scene(cm, [], [], [{"id": "body_floor", "geoms": body, "other": ["floor"]}])


def controller_params(space: BehaviourSpace, params: dict[str, Any]) -> dict[str, Any]:
    return {**space.fixed, **params}


def play_length(space: BehaviourSpace, params: dict[str, Any], judging: bool) -> float:
    if space.one_shot_extra_s is not None:
        from calflab.control.outcome import OutcomeMotionController

        c = OutcomeMotionController(controller_params(space, params))
        return round(c.length_s() + float(space.one_shot_extra_s), 3)
    return float(space.judge_s if judging else space.search_s)


def play_seed(payload: dict[str, Any], space: BehaviourSpace, params: dict[str, Any], seed: int, margin: float,
              judging: bool = False, rollout_path: str | None = None) -> dict[str, Any]:
    """One version of a behaviour on one body and seed: limits (as the R11c suite) and outcome."""
    from calflab.evolve.hardware import _build, compile_options, judge_play
    from calflab.fitness.outcomes import TASKS, measure
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    t0 = time.perf_counter()
    design, lib = _build(payload)
    spec = design.spec
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    task = TASKS[space.behaviour].model_validate(space.task)
    length = play_length(space, params, judging)
    cm = scene(space.behaviour, compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed), spec, task)
    lie = space.behaviour in ("lie", "free")  # may go down: judged by tilt and impact, not the fall check
    settings = SimSettings(duration_s=min(length, 60.0), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=not lie, seed=seed)
    # SimSettings' 60 s bound is the lab's slider range; standing is judged for minutes (the runner has no limit)
    settings.duration_s = length
    ctrl = registry.get("controller", "outcome_motion")(controller_params(space, params))  # type: ignore[call-arg]
    ro = run_rollout(cm, ctrl, settings, lib)  # type: ignore[arg-type]
    complete = bool(len(ro.t) and float(ro.t[-1]) >= length - 0.05)
    judged = dataclasses.replace(ro, meta={**ro.meta, "fell": False, "fall_time": None}) if lie else ro
    lim = judge_play(judged, spec, lib, margin, 0.0, length)
    out = measure(space.behaviour, ro, spec, task)
    rec = {"within": bool(lim["within"]) and complete, "margin": lim["margin"], "closest": lim["closest"],
           "violations": lim["violations"], "joints": lim["joints"], "complete": complete,
           "sim_fell": bool(ro.meta.get("fell")), "outcome": out, "length_s": length,
           "binding": binding(lim["joints"]), "wall_s": round(time.perf_counter() - t0, 2)}
    rec["holds"] = bool(rec["within"] and out.get("holds"))
    rec["rank"] = rank(space.behaviour, rec)
    if rollout_path:
        Path(rollout_path).parent.mkdir(parents=True, exist_ok=True)
        ro.save(Path(rollout_path))
    return rec


def binding(joints: dict[str, Any]) -> dict[str, Any] | None:
    """The joint and limit with the largest use in a play (``hardware.per_joint``'s rows)."""
    best: tuple[float, str, str] | None = None
    for j, row in (joints or {}).items():
        for lim in ("speed", "torque", "belt", "envelope", "stall"):
            use = row.get(lim)
            if use is not None and (best is None or float(use) > best[0]):
                best = (float(use), j, lim)
    return None if best is None else {"joint": best[1], "limit": best[2], "use": round(best[0], 3)}


def excess(joints: dict[str, Any]) -> float:
    """Sum over joints of how far the most-used limit is past 1 (0 within every limit)."""
    tot = 0.0
    for row in joints.values():
        uses = [float(row[k]) for k in ("speed", "torque", "belt", "envelope", "stall") if row.get(k) is not None]
        if uses:
            tot += max(0.0, max(uses) - 1.0)
    return round(tot, 4)


def rank(behaviour: str, rec: dict[str, Any]) -> float:
    o = rec.get("outcome") or {}
    failed = sum(1 for v in (o.get("gates") or {}).values() if not v)
    m = rec.get("margin")
    m = -1.0 if m is None else float(m)
    sc = float(o.get("score", 0.0)) * NORM[behaviour]
    if not rec.get("within", True):  # over a limit counts as a failed gate (a fast trot over a belt limit must not lead)
        failed += 1
    if failed:  # a version that fails a gate or a limit never outranks one that passes them all on its score
        sc = 0.5 * min(sc, 1.0)
    r = sc - 2.0 * float(failed) + min(0.0, m) - EXCESS_WEIGHT * excess(rec.get("joints") or {})
    if not rec.get("complete", True):
        r -= 5.0
    return round(r, 4)


def task_fn(job: dict[str, Any]) -> dict[str, Any]:
    """Worker: one play, cached on disk under ``job["cache"]``."""
    cache = Path(job["cache"]) if job.get("cache") else None
    f = cache / f"{job['key']}.json" if cache else None
    if f is not None and f.is_file():
        try:
            return {**json.loads(f.read_text(encoding="utf-8")), "cached": True}
        except (OSError, json.JSONDecodeError):
            pass
    space = BehaviourSpace.model_validate(job["space"])
    rec = play_seed(job["payload"], space, job["params"], int(job["seed"]), float(job["margin"]),
                    bool(job.get("judging")))
    if f is not None:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{time.perf_counter_ns()}.tmp")
        tmp.write_text(json.dumps(rec, default=float), encoding="utf-8")
        tmp.replace(f)
    return {**rec, "cached": False}


def body_key(payload: dict[str, Any]) -> str:
    from calflab.evolve.hardware import _build

    design, _lib = _build(payload)
    return _digest({"spec": design.spec.model_dump(mode="json"), "c": payload.get("compile"),
                    "e": payload.get("evaluation")})


# ====================================================================== the search
MapFn = Callable[[Callable[[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]]


def _serial(fn: Callable[[dict[str, Any]], dict[str, Any]], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [fn(j) for j in jobs]


def _x(params: dict[str, Any], dims: list[tuple[str, float, float]]) -> np.ndarray:
    return np.array([(float(params.get(n, 0.0)) - lo) / (hi - lo) for n, lo, hi in dims], float)


def _params(x: np.ndarray, dims: list[tuple[str, float, float]]) -> dict[str, float]:
    return {n: round(lo + float(v) * (hi - lo), 3) for (n, lo, hi), v in zip(dims, np.clip(x, 0.0, 1.0), strict=True)}


def evaluate(payload: dict[str, Any], bkey: str, space: BehaviourSpace, cands: list[dict[str, Any]],
             seeds: list[int], margin: float, s: OutcomeSearch, map_fn: MapFn, cache: str | None,
             judging: bool = False) -> list[dict[str, Any]]:
    """Each candidate on the first seed, then (unless below ``early_stop``) on the others; worst-seed rank."""
    sp = space.model_dump(mode="json")

    def jobs(seed: int, idx: list[int]) -> list[dict[str, Any]]:
        return [{"payload": payload, "space": sp, "params": cands[i], "seed": seed, "margin": margin,
                 "judging": judging, "cache": cache,
                 "key": _digest({"v": VERSION, "body": bkey, "space": sp if judging else {**sp, "judge_s": None},
                                 "ctrl": controller_params(space, cands[i]), "seed": seed, "margin": margin,
                                 "judging": judging})} for i in idx]

    def ranked(r: dict[str, Any]) -> dict[str, Any]:  # the rank is never taken from the cache
        return {**r, "rank": rank(space.behaviour, r)}

    per: list[list[dict[str, Any]]] = [[] for _ in cands]
    first = [ranked(r) for r in map_fn(task_fn, jobs(seeds[0], list(range(len(cands)))))]
    for i, r in enumerate(first):
        per[i].append({"seed": seeds[0], **r})
    more = [i for i, r in enumerate(first) if r["rank"] >= s.early_stop]
    rest = [(seed, i) for seed in seeds[1:] for i in more]
    if rest:
        res = [ranked(r) for r in map_fn(task_fn, [j for seed, i in rest for j in jobs(seed, [i])])]
        for (seed, i), r in zip(rest, res, strict=True):
            per[i].append({"seed": seed, **r})
    out = []
    for i, c in enumerate(cands):
        complete = len(per[i]) == len(seeds)
        out.append({"params": c, "seeds": per[i], "complete": complete,
                    "rank": round(min(r["rank"] for r in per[i]) - (0 if complete else 10.0), 4),
                    "holds": complete and all(r["holds"] for r in per[i]),
                    "within": complete and all(r["within"] for r in per[i]),
                    "evals": sum(0 if r.get("cached") else 1 for r in per[i])})
    return out


def _key(e: dict[str, Any]) -> tuple[bool, bool, float]:
    return (bool(e["holds"]), bool(e["within"]), float(e["rank"]))


def summary(e: dict[str, Any]) -> dict[str, Any]:
    """A short record of an evaluated version: rank, holds, per seed the outcome numbers and what binds."""
    keep_out = ("score", "gates", "holds")
    rows = []
    for r in e["seeds"]:
        o = r.get("outcome") or {}
        rows.append({"seed": r["seed"], "rank": r["rank"], "holds": r["holds"], "within": r["within"],
                     "margin": r.get("margin"), "closest": r.get("closest"), "binding": r.get("binding"),
                     "complete": r.get("complete"), "violations": r.get("violations"),
                     "outcome": {k: v for k, v in o.items() if k in keep_out or not isinstance(v, dict)
                                 or k in ("effort", "footfall")}})
    return {"params": e["params"], "rank": e["rank"], "holds": e["holds"], "within": e["within"], "seeds": rows}


def optimise(payload: dict[str, Any], space: BehaviourSpace, margin: float, s: OutcomeSearch,
             starts: list[dict[str, Any]] | None = None, map_fn: MapFn | None = None, cache: str | None = None,
             report: Callable[[str], None] | None = None) -> dict[str, Any]:
    """CMA-ES over ``space.dims`` for one body; warm starts played first (the search starts from the best); the best
    ``judge_top`` distinct versions re-judged at the judging length on ``judge_seeds``. Deterministic for a seed."""
    import cma

    map_fn = map_fn or _serial
    t0 = time.perf_counter()
    bkey = body_key(payload)
    dims = space.dims
    names = [n for n, _lo, _hi in dims]
    first = [_params(np.clip(_x(st, dims), 0, 1), dims) for st in (starts or [{}])]
    # starts may set params outside the dims (e.g. fixed ones): keep them only via dims
    history = evaluate(payload, bkey, space, first, s.search_seeds, margin, s, map_fn, cache)
    for e in history:
        e["generation"] = -1
    best = max(history, key=_key)
    x0 = np.clip(_x(best["params"], dims), 0.02, 0.98)
    plays = sum(len(e["seeds"]) for e in history)
    if s.generations > 0:
        es = cma.CMAEvolutionStrategy(list(x0), s.sigma, {"bounds": [0.0, 1.0], "popsize": s.popsize,
                                                          "seed": s.seed + 7919, "verbose": -9})
        for g in range(s.generations):
            xs = es.ask()
            cands = [_params(np.asarray(x), dims) for x in xs]
            res = evaluate(payload, bkey, space, cands, s.search_seeds, margin, s, map_fn, cache)
            for e in res:
                e["generation"] = g
            history += res
            plays += sum(len(e["seeds"]) for e in res)
            es.tell(xs, [-e["rank"] for e in res])
            gb = max(res, key=_key)
            if _key(gb) > _key(best):
                best = gb
            if report:
                report(f"{space.behaviour} gen {g + 1}/{s.generations}: best rank {best['rank']:+.3f} holds "
                       f"{best['holds']} within {best['within']} (gen {gb['rank']:+.3f})")
    t_search = time.perf_counter() - t0
    # judging: the best distinct versions at the judging length
    ranked = sorted(history, key=_key, reverse=True)
    top: list[dict[str, Any]] = []
    for e in ranked:
        if all(e["params"] != t["params"] for t in top):
            top.append(e)
        if len(top) >= s.judge_top:
            break
    judged = evaluate(payload, bkey, space, [t["params"] for t in top], s.judge_seeds, margin,
                      s.model_copy(update={"early_stop": -1e9}), map_fn, cache, judging=True)
    jbest = max(judged, key=_key)
    return {"behaviour": space.behaviour, "dims": names, "space": space.model_dump(mode="json"),
            "start": summary(next(e for e in history if e["generation"] == -1 and e["params"] == first[0])),
            "starts": [summary(e) for e in history if e["generation"] == -1],
            "search_best": summary(best), "judged": [summary(e) for e in judged], "best": summary(jbest),
            "progress": [{"generation": e["generation"], "rank": e["rank"], "holds": e["holds"]} for e in history],
            "plays": plays + sum(len(e["seeds"]) for e in judged),
            "search_wall_s": round(t_search, 1), "wall_s": round(time.perf_counter() - t0, 1),
            "search": s.model_dump()}
