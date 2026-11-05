"""Behaviour diversity on a fixed body (ADR-093): MAP-Elites over a behaviour generator.

The body is the document's and never changes. What evolves is a **behaviour generator**: one vector in
[0, 1]^D that decodes into the parameters of the ``interpreted`` controller (a semi-Markov chain of motion
primitives, switching only where every hoof is down, ADR-085):

* **palette**: one state per entry of ``PALETTE`` that fits the body: stand, a weight shift and a step onto
  either hind leg, walk, trot, turn. Each state's primitive parameters are free over the primitive's own
  vector range (``MotionPrimitive.vector_dims``), so nothing is tied to what interpretation chose for the calf;
* **sequence**: each state has a *weight* w (how often it is chosen), a *place* p in [0, 1] and a typical
  *duration* (log-uniform 0.8-8 s, log-sd 0.4). The chance of going from state i to state j is proportional to
  ``w_j exp(-s |p_i - p_j|)``. ``s`` (0-8, one gene) sets whether a performance wanders between neighbouring
  states (high s) or jumps anywhere (s near 0);
* **blend**: the cross-fade between states (0.2-1.5 s).

Each candidate plays for ``duration_s`` on every seed of the preset, with floor friction and mass varied as
in ``repertoire``, using torque-speed servos at derating 1. It is judged with every limit lowered by the
safety margin (:func:`calflab.behave.interpret.judge`). **A candidate that goes over a limit or falls on any
seed is unsafe.** The archive axes are movement features of what the robot did, averaged over the seeds played
(:mod:`calflab.behave.descriptors`). Within a cell the candidate kept is the one with the highest

    fitness = (+1 if safe else -1) + min(1, worst margin) + unpredictability_weight x unpredictability

so a safe candidate always displaces an unsafe one (with the weight below 2). An unsafe candidate may hold a cell
until a safe one lands there: without that, generation 0 is empty and nothing can be varied (0 of 14 random
generators were safe on the working body, ADR-093). Only safe cells are results; the view marks each cell.
Generation 0 starts around settings found within the limits for each state alone (``safe_centres``).
**Unpredictability** is the entropy rate of the generator's chain (bits per switch, stationary distribution),
divided by its largest possible value log2(n - 1): 0 = the next state is always the same, 1 = every other
state equally likely. Calf-likeness is not scored.

Units: s, deg, mm; margins are headroom over the margin-lowered limits (0 = exactly at margin 0.2).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.evolve.map_elites import Candidate, EvolveProblem, EvolveResult, MapElitesCMA
from calflab.plugins import BehaviorDescriptor, ComputeBackend, Optimizer, Task, register, registry
from calflab.schema import P

#: state name -> (primitive key, fixed base parameters)
PALETTE: dict[str, tuple[str, dict[str, Any]]] = {
    "stand": ("stand", {}),
    "shift_hl": ("weight_shift", {"leg": "hl"}),
    "shift_hr": ("weight_shift", {"leg": "hr"}),
    "step_hl": ("step", {"leg": "hl"}),
    "step_hr": ("step", {"leg": "hr"}),
    "walk": ("walk", {}),
    "trot": ("trot", {}),
    "turn": ("turn", {}),
}
DUR_LO, DUR_HI = math.log(0.8), math.log(8.0)
SHARP_HI = 8.0


def palette_for(spec: Any, names: list[str] | None = None) -> list[tuple[str, str, dict[str, Any]]]:
    """(state, primitive, base) for every palette entry that fits the body, in palette order."""
    out = []
    for name, (key, base) in PALETTE.items():
        if names and name not in names:
            continue
        cls: Any = registry.get("motion_primitive", key)
        if cls.fits(spec):
            out.append((name, key, base))
    return out


def layout(palette: list[tuple[str, str, dict[str, Any]]]) -> list[tuple[str, str, float, float]]:
    """The vector's genes in order: (state or "", gene name, low, high)."""
    genes: list[tuple[str, str, float, float]] = [("", "sharpness", 0.0, SHARP_HI), ("", "blend_s", 0.2, 1.5)]
    for name, key, _base in palette:
        genes += [(name, "weight", 0.0, 1.0), (name, "place", 0.0, 1.0), (name, "duration", DUR_LO, DUR_HI)]
        for d in registry.get("motion_primitive", key).vector_dims():  # type: ignore[attr-defined]
            genes.append((name, d.name, float(d.lo), float(d.hi)))
    return genes


def safe_centres(spec: Any, lib: Any, doc_compile: dict[str, Any], palette: list[tuple[str, str, dict[str, Any]]],
                 margin: float, popsize: int = 4, generations: int = 2, cancelled: Any = None,
                 report: Any = None) -> dict[str, dict[str, Any]]:
    """Per palette state: a setting of its primitive within every limit at the margin, played alone on seed 0,
    as close to the primitive's defaults as the search found (a small CMA-ES; cost = distance to the defaults
    in the unit cube, plus 10 + 10 x the shortfall when over a limit). If none is within, the one with the best
    margin. Also its record (margin, within, plays)."""
    import cma

    from calflab.behave.interpret import Interpreter, InterpretSettings

    it = Interpreter(spec, lib, doc_compile, InterpretSettings(margin=margin, popsize=max(2, popsize),
                                                               generations=max(1, generations), seed=0), None,
                     cancelled)
    out: dict[str, dict[str, Any]] = {}
    for n, key, base in palette:
        cls: Any = registry.get("motion_primitive", key)
        dims = list(cls.vector_dims())
        start = cls(dict(base)).params.model_dump(mode="json")
        x0 = np.array([float(np.clip((float(start[d.name]) - d.lo) / (d.hi - d.lo), 0.0, 1.0)) for d in dims])
        tried: list[tuple[float, Any, dict[str, Any]]] = []

        def run(x: np.ndarray, dims: list[Any] = dims, start: dict[str, Any] = start, x0: np.ndarray = x0,
                key: str = key, tried: list[Any] = tried) -> float:
            prm = dict(start)
            for d, v in zip(dims, np.clip(x, 0.0, 1.0), strict=True):
                prm[d.name] = round(d.lo + float(v) * (d.hi - d.lo), 4)
            e = it.evaluate(key, prm, {}, {})
            dist = float(np.linalg.norm(np.clip(x, 0.0, 1.0) - x0)) if len(x0) else 0.0
            c = dist + (0.0 if e.within_limits else 10.0 + 10.0 * max(0.0, -float(e.margin or 0.0)))
            tried.append((c, e, prm))
            return c

        if report is not None:
            report(f"finding a setting within the limits for {n}")
        run(x0)
        if len(dims) >= 2 and not tried[0][1].within_limits:
            es = cma.CMAEvolutionStrategy(list(np.clip(x0, 0.02, 0.98)), 0.3, {"bounds": [0.0, 1.0], "popsize": popsize,
                                                                           "seed": 7919, "verbose": -9})
            for _ in range(generations):
                if cancelled is not None and cancelled():
                    break
                xs = es.ask()
                es.tell(xs, [run(np.asarray(x)) for x in xs])
        within = [t for t in tried if t[1].within_limits]
        best = (min(within, key=lambda t: t[0]) if within
                else max(tried, key=lambda t: float(t[1].margin if t[1].margin is not None else -9.0)))
        out[n] = {"params": best[2], "within": bool(within), "margin": best[1].margin, "plays": len(tried),
                  "violations": best[1].violations}
    return out


def start_vector(palette: list[tuple[str, str, dict[str, Any]]], rng: np.random.Generator, spread: float,
                 centres: dict[str, dict[str, Any]] | None = None) -> np.ndarray:
    """A first-generation vector: the sequence genes anywhere (uniform), each primitive's parameters near a
    centre (normal, ``spread`` of the range): the settings ``safe_centres`` found, else the primitive's defaults.
    Uniform primitive parameters, and the defaults, almost never stay within the limits on the working body
    (0 of 14 each, ADR-093)."""
    out = []
    defaults = {n: registry.get("motion_primitive", k)(dict(b)).params.model_dump(mode="json")  # type: ignore[attr-defined]
                for n, k, b in palette}
    for n in defaults:
        if centres and n in centres:
            defaults[n] = {**defaults[n], **centres[n]["params"]}
    for state, gene, lo, hi in layout(palette):
        if state and gene == "weight" and centres and state in centres and not centres[state]["within"]:
            out.append(float(rng.uniform(0.0, 0.1)))  # no setting within the limits alone: rarely chosen at first
        elif not state or gene in ("weight", "place", "duration"):
            out.append(float(rng.uniform(0.0, 1.0)))
        else:
            d = (float(defaults[state][gene]) - lo) / (hi - lo) if hi > lo else 0.5
            out.append(float(np.clip(d + rng.normal(0.0, spread), 0.0, 1.0)))
    return np.asarray(out)


def decode(x: np.ndarray, palette: list[tuple[str, str, dict[str, Any]]]) -> dict[str, Any]:
    """The generator a vector stands for: per state its weight, place, duration (log s) and primitive params."""
    genes = layout(palette)
    if len(x) != len(genes):
        raise ValueError(f"behaviour vector has {len(x)} values; this palette needs {len(genes)}")
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    out: dict[str, Any] = {"states": {n: {"primitive": k, "params": dict(b)} for n, k, b in palette}}
    for (state, gene, lo, hi), v in zip(genes, x, strict=True):
        val = lo + float(v) * (hi - lo)
        if not state:
            out[gene] = val
        elif gene in ("weight", "place", "duration"):
            out["states"][state][gene] = val
        else:
            out["states"][state]["params"][gene] = round(val, 4)
    return out


def transition_matrix(gen: dict[str, Any]) -> tuple[list[str], np.ndarray]:
    names = list(gen["states"])
    w = np.array([max(1e-3, gen["states"][n]["weight"]) for n in names])
    p = np.array([gen["states"][n]["place"] for n in names])
    m = w[None, :] * np.exp(-gen["sharpness"] * np.abs(p[:, None] - p[None, :]))
    np.fill_diagonal(m, 0.0)
    m = m / m.sum(axis=1, keepdims=True)
    return names, m


def stationary(m: np.ndarray) -> np.ndarray:
    """Stationary distribution of a transition matrix (share of switches into each state)."""
    vals, vecs = np.linalg.eig(m.T)
    pi = np.real(vecs[:, int(np.argmin(np.abs(vals - 1.0)))])
    return np.abs(pi) / np.abs(pi).sum()


def unpredictability(gen: dict[str, Any]) -> float:
    """Entropy rate of the chain over log2(n - 1): 0 = fixed sequence, 1 = every other state equally likely."""
    names, m = transition_matrix(gen)
    n = len(names)
    if n < 3:
        return 0.0
    pi = stationary(m)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.nansum(pi[:, None] * np.where(m > 0, m * np.log2(m), 0.0))
    return float(min(1.0, max(0.0, h / math.log2(n - 1))))


#: a state's duration is checked, and with ``cap`` held at most, at this quantile of its log-normal (ADR-096/097)
CHECKED_Z = 1.2816  # 90th percentile
LOG_SD = 0.4


def checked_duration(log_mean: float, log_sd: float = LOG_SD) -> float:
    """The length (s) coverage holds a state for: its 90th percentile, within the controller's 0.5-15 s."""
    return float(np.clip(math.exp(log_mean + CHECKED_Z * log_sd), 0.5, 15.0))


def controller_params(gen: dict[str, Any], spec: Any, lib: Any, margin: float = 0.2,
                      cap: bool = False) -> dict[str, Any]:
    """``interpreted`` controller parameters of a generator on this body. Commanded joint speed is capped at
    0.95 x (1 - margin) of each servo's speed, under the margin-lowered joint-speed limit (the controller's own
    default, 0.9, is above it at margin 0.2). With ``cap`` (ADR-097) no episode lasts longer than the length
    coverage checks (:func:`checked_duration`): a longer draw is held at that length."""
    names, m = transition_matrix(gen)
    states = []
    for n in names:
        st = gen["states"][n]
        prim: Any = registry.get("motion_primitive", st["primitive"])(st["params"])
        key, params = prim.controller(spec, lib)
        states.append({"name": n, "primitive": st["primitive"], "controller": {"key": key, "params": params},
                       "period_s": prim.period_s(), "offset_s": prim.phase_offset_s(),
                       "safe": [list(s) for s in prim.safe_phases()], "one_shot": prim.one_shot,
                       "duration": {"log_mean": round(st["duration"], 4), "log_sd": LOG_SD, "min_s": 0.5,
                                    "max_s": round(checked_duration(st["duration"]), 4) if cap else 15.0},
                       "vary": {}})
    w = np.array([max(1e-3, gen["states"][n]["weight"]) for n in names])
    return {"states": states,
            "transitions": {a: {b: round(float(m[i, j]), 4) for j, b in enumerate(names) if m[i, j] > 0}
                            for i, a in enumerate(names)},
            "initial": {n: round(float(v), 4) for n, v in zip(names, w / w.sum(), strict=True)},
            "blend_s": round(float(gen["blend_s"]), 3), "speed_fraction": round(0.95 * (1.0 - margin), 4)}


def reach_probability(gen: dict[str, Any], performance_s: float, log_sd: float = 0.4) -> dict[str, float]:
    """Per state, the chance it is played at least once in a performance of ``performance_s`` (s) (ADR-096).

    Approximation: switches arrive at the chain's mean rate (one per mean episode, episodes log-normal with
    ``log_sd``, clipped to 0.5-15 s as the controller does); visits to a state are Poisson with its stationary
    share of switches; the first episode adds the state's initial probability."""
    names, m = transition_matrix(gen)
    pi = stationary(m)
    mean_d = np.array([float(np.clip(math.exp(gen["states"][n]["duration"] + 0.5 * log_sd**2), 0.5, 15.0))
                       for n in names])
    rate = 1.0 / float((pi * mean_d).sum())
    w = np.array([max(1e-3, gen["states"][n]["weight"]) for n in names])
    init = w / w.sum()
    return {n: float(1.0 - (1.0 - init[i]) * math.exp(-performance_s * rate * pi[i])) for i, n in enumerate(names)}


def coverage_plan(gen: dict[str, Any], ctrl: dict[str, Any], completed: dict[str, int], n_seeds: int,
                  performance_s: float, p_min: float, after_s: float, force_all: bool = False) -> list[dict[str, Any]]:
    """Forced plays for every state likely in a performance (reach probability >= ``p_min``) that was not played to
    its end, and 2 s beyond (the sustained window), on every seed (ADR-096); the likeliest first.

    The path into the state is one the chain really takes: if most of its chance is being the first episode, it
    is played from the start; otherwise it comes after the predecessor with the largest flow pi_i m_ij among
    states that are themselves likely (preferring ones already played to the end). The predecessor plays its
    typical duration (1.5-4 s), the state its 90th-percentile duration (long holds are what load a servo), both
    without draws, then the chain runs ``after_s`` s more. With ``force_all`` (durations capped, ADR-097) every
    likely state is forced, played or not: a seed that played a state at a typical length says nothing about
    holding it for the full capped length. Returns the plays with their controller and length (s)."""
    names, m = transition_matrix(gen)
    pi = stationary(m)
    reach = reach_probability(gen, performance_s)
    w = np.array([max(1e-3, gen["states"][n]["weight"]) for n in names])
    init = w / w.sum()
    plays = []
    for x in sorted(names, key=lambda n: -reach[n]):
        j = names.index(x)
        if reach[x] < p_min or (completed.get(x, 0) >= n_seeds and not force_all):
            continue
        likely = [i for i in range(len(names)) if i != j and reach[names[i]] >= p_min]
        proven = [i for i in likely if completed.get(names[i], 0) > 0]
        pool = proven or likely
        pred = max((pi[i] * m[i, j], names[i]) for i in pool)[1] if pool else None
        if pred is None or init[j] >= 0.5 * reach[x]:
            pred = None
        c = {**ctrl, "states": [dict(st) for st in ctrl["states"]], "transitions": dict(ctrl["transitions"])}
        dur: dict[str, float] = {"": 0.0}
        for st in c["states"]:
            d = dict(st["duration"])
            if st["name"] == pred:
                v = float(np.clip(math.exp(d["log_mean"]), 1.5, 4.0))
            elif st["name"] == x:
                v = float(np.clip(math.exp(d["log_mean"] + CHECKED_Z * d["log_sd"]), d["min_s"], d["max_s"]))
            else:
                continue
            st["duration"] = {**d, "log_mean": round(math.log(v), 4), "log_sd": 0.0}
            dur[st["name"]] = v
            if st.get("one_shot"):  # a one-shot plays whole cycles
                dur[st["name"]] = max(v, st["offset_s"] + st["period_s"]) + st["period_s"]
        if pred is None:
            c["start"] = x
        else:
            c["start"] = pred
            c["transitions"][pred] = {x: 1.0}
        plays.append({"state": x, "from": pred or "start", "reach": round(reach[x], 3), "controller": c,
                      "duration_s": round(dur[pred or ""] + dur[x] + after_s + 2.0, 2)})
    return plays


# ---------------------------------------------------------------------- the task
def evaluate_behaviour(payload: dict[str, Any]) -> dict[str, Any]:
    """Play one behaviour generator on the fixed body over the preset's seeds. JSON in, JSON out.

    Payload: genome, overrides, generator, generator_params, compile, fitness (preset dump), x, palette (names),
    duration_s, margin, unpredictability_weight, descriptors; optionally coverage (bool), performance_s,
    coverage_p, coverage_after_s (ADR-096), cap_durations (ADR-097): a candidate safe on every seed then plays, forced, every state likely
    in a performance of ``performance_s`` that its seeds did not play to the end, on every seed."""
    from calflab.behave.descriptors import movement_features
    from calflab.behave.interpret import judge
    from calflab.behave.physics import compile_params
    from calflab.behave.study import randomization
    from calflab.components import library
    from calflab.design import build_design
    from calflab.evolve.constraints import infeasible
    from calflab.fitness.preset import EvaluationSettings, FitnessPreset
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    lib = library()
    design = build_design(Genome.model_validate(payload["genome"]),
                          [Override.model_validate(o) for o in payload.get("overrides", [])],
                          payload.get("generator", "feral_calf"), payload.get("generator_params"))
    reasons = infeasible(design.spec)
    if reasons:
        return {"infeasible": reasons, "mass_g": design.spec.total_mass_g(), "evals": 0}
    spec = design.spec
    palette = palette_for(spec, payload.get("palette") or None)
    gen = decode(np.asarray(payload["x"], dtype=float), palette)
    margin = float(payload.get("margin", 0.2))
    cap = bool(payload.get("cap_durations"))
    ctrl = controller_params(gen, spec, lib, margin, cap=cap)
    preset = FitnessPreset.model_validate(payload["fitness"])
    ev = preset.evaluation or EvaluationSettings()
    copts = {**compile_params(payload.get("compile", {})),
             "randomization": randomization(ev.randomize, ev.friction, ev.mass_scale)}
    dur = float(payload.get("duration_s", 24.0))
    seeds, feats, fell_any, unsafe = [], [], False, []
    completed: dict[str, int] = {}

    def play(c: dict[str, Any], seed: int, seconds: float) -> Any:
        cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
        settings = SimSettings(duration_s=seconds, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                               stop_on_fall=True, seed=seed)
        return run_rollout(cm, registry.get("controller", "interpreted")(c), settings, lib)  # type: ignore[arg-type]

    for seed in ev.seeds:
        ro = play(ctrl, seed, dur)
        j = judge(ro, spec, lib, margin)
        mv = movement_features(ro, spec)
        eps = [e for e in ((ro.meta.get("controller_log") or {}).get("episodes") or []) if isinstance(e, dict)]
        log = [e.get("name") for e in eps]
        for name in {str(e.get("name")) for e in eps if e.get("t1") is not None and float(e["t1"]) + 2.0 <= dur}:
            completed[name] = completed.get(name, 0) + 1
        seeds.append({"seed": seed, "margin": j["margin"], "fell": j["fell"], "violations": j["violations"],
                      "within": bool(j["within_limits"]), "episodes": log,
                      "constraints": {k: v["margin"] for k, v in j["constraints"].items()}})
        feats.append(mv)
        fell_any = fell_any or j["fell"]
        if not j["within_limits"]:
            unsafe += [f"seed {seed}: " + ("fell" if j["fell"] else ", ".join(j["violations"]))]
            break  # one seed over a limit is enough to keep it out of the archive
    coverage: dict[str, Any] | None = None
    if payload.get("coverage") and not unsafe:
        perf_s = float(payload.get("performance_s", 60.0))
        plan = coverage_plan(gen, ctrl, completed, len(ev.seeds), perf_s, float(payload.get("coverage_p", 0.05)),
                             float(payload.get("coverage_after_s", 6.0)), force_all=cap)
        coverage = {"performance_s": perf_s,
                    "reach": {k: round(v, 3) for k, v in reach_probability(gen, perf_s).items()},
                    "completed_on_seeds": completed, "plays": []}
        for pl in plan:
            rec: dict[str, Any] = {"state": pl["state"], "from": pl["from"], "reach": pl["reach"],
                                   "duration_s": pl["duration_s"], "seeds": []}
            coverage["plays"].append(rec)
            for seed in ev.seeds:
                ro = play(pl["controller"], seed, pl["duration_s"])
                j = judge(ro, spec, lib, margin)
                played = [str(e.get("name")) for e in ((ro.meta.get("controller_log") or {}).get("episodes") or [])
                          if isinstance(e, dict)]
                rec["seeds"].append({"seed": seed, "margin": j["margin"], "fell": j["fell"], "episodes": played,
                                     "violations": j["violations"], "within": bool(j["within_limits"])})
                fell_any = fell_any or j["fell"]
                if not j["within_limits"]:
                    unsafe += [f"seed {seed}, {pl['state']} forced after {pl['from']} ({' > '.join(played)}): "
                               + ("fell" if j["fell"] else ", ".join(j["violations"]))]
                    break
            if unsafe:
                break
    keys = [k for k in feats[0] if isinstance(feats[0].get(k), int | float)] if feats else []
    movement = {k: float(np.mean([f[k] for f in feats if isinstance(f.get(k), int | float)])) for k in keys}
    margins = [s["margin"] for s in seeds if s["margin"] is not None]
    margins += [s["margin"] for pl in (coverage or {}).get("plays", []) for s in pl["seeds"]
                if s["margin"] is not None]
    worst = float(min(margins)) if margins else -3.0
    unp = unpredictability(gen)
    weight = float(payload.get("unpredictability_weight", 0.5))
    safe = not unsafe
    fitness = (1.0 if safe else -1.0) + min(1.0, worst) + weight * unp
    used = sorted({e for s in seeds for e in s["episodes"] if e})
    metrics = {"movement": movement, "safety_margin": round(worst, 4), "within_limits": safe, "unpredictability": round(unp, 4),
               "seeds": seeds, "states_played": used, "fell": fell_any,
               "generator": {"sharpness": round(gen["sharpness"], 3), "blend_s": round(gen["blend_s"], 3),
                             "states": {n: {"primitive": s["primitive"], "weight": round(s["weight"], 3),
                                            "place": round(s["place"], 3),
                                            "duration_s": round(math.exp(s["duration"]), 2), "params": s["params"]}
                                        for n, s in gen["states"].items()}}}
    if coverage is not None:
        metrics["coverage"] = coverage
    rollouts = len(seeds) + sum(len(pl["seeds"]) for pl in (coverage or {}).get("plays", []))
    terms = {"safe": {"value": 1.0 if safe else 0.0, "weight": 2.0, "weighted": 1.0 if safe else -1.0},
             "worst_margin": {"value": round(worst, 4), "weight": 1.0, "weighted": round(min(1.0, worst), 4)},
             "unpredictability": {"value": round(unp, 4), "weight": weight, "weighted": round(weight * unp, 4)}}
    out: dict[str, Any] = {"fitness": fitness, "fitness_terms": terms, "controller_params": ctrl,
                           "controller_x": [float(v) for v in np.clip(payload["x"], 0, 1)], "metrics": metrics,
                           "mass_g": spec.total_mass_g(), "evals": rollouts}
    if unsafe:
        out["unsafe_reasons"] = unsafe
    out["descriptors"] = {k: float(registry.get("behavior_descriptor", k)().describe_candidate(  # type: ignore[attr-defined]
        spec, metrics, ctrl)) for k in payload.get("descriptors", [])}
    return out


# ---------------------------------------------------------------------- the optimizer
@register
class MapElitesBehaviour(Optimizer):
    """MAP-Elites over a behaviour generator; the body stays as it is."""

    key = "map_elites_behaviour"
    label = "MAP-Elites over behaviour"
    description = ("Keeps the body as it is and illuminates the movements it can perform within every limit: a "
                   "behaviour generator (which primitives, how they follow each other, their parameters) evolves, "
                   "archived by movement features of what the robot did.")
    version = "1"
    #: the body's own evolve defaults (archive axes, rollout length; ADR-070) describe bodies, not behaviours
    body_defaults = False

    class Params(BaseModel):
        generations: int = P(6, ge=1, le=500, desc="Generations.", group="Budget")
        batch_size: int = P(16, ge=2, le=256, desc="Generators per generation.", group="Budget")
        duration_s: float = P(24.0, unit="s", ge=5.0, le=120.0, desc="Performance length per seed.", group="Budget")
        descriptor_x: str = P("quantity_of_motion", desc="Archive X axis.", group="Archive")
        descriptor_y: str = P("tempo_regularity", desc="Archive Y axis.", group="Archive")
        grid_x: int = P(10, ge=2, le=50, desc="Cells along X.", group="Archive")
        grid_y: int = P(10, ge=2, le=50, desc="Cells along Y.", group="Archive")
        range_x: list[float] = P(default_factory=lambda: [0.0, 15.0], ui="json", group="Archive",
                                 desc="X axis range (empty = the descriptor's own). Quantity of motion on the working "
                                      "body runs about 1-10 deg/s (ADR-093), not the descriptor's 0-40.")
        range_y: list[float] = P(default_factory=list, ui="json", group="Archive",
                                 desc="Y axis range (empty = the descriptor's own).")
        margin: float = P(0.2, ge=0.0, le=0.9, desc="Safety margin on every limit.", group="Fitness")
        unpredictability_weight: float = P(0.5, ge=0.0, le=5.0, desc="Weight of unpredictability in a cell.",
                                           group="Fitness")
        palette: list[str] = P(default_factory=list, ui="json",
                               desc="States to use (empty = every palette entry that fits the body).", group="Variation")
        start_spread: float = P(0.1, ge=0.0, le=0.5, desc="First generation: spread of the primitives' parameters "
                                "around their defaults (fraction of each range); the sequence genes are uniform.",
                                group="Variation")
        sigma_iso: float = P(0.08, ge=0.0, le=0.5, desc="Isotropic mutation (fraction of each range).",
                             group="Variation")
        sigma_line: float = P(0.2, ge=0.0, le=1.0, desc="Mutation along the line between two elites.",
                              group="Variation")
        coverage: bool = P(False, group="Fitness",
                           desc="Before a candidate counts as safe, force every state likely in a performance (and "
                                "not played to its end on every seed) into an extra play on every seed (ADR-096).")
        performance_s: float = P(60.0, unit="s", ge=5.0, le=600.0, group="Fitness",
                                 desc="Coverage: the performance length the states must be safe for.")
        coverage_p: float = P(0.05, ge=0.0, le=1.0, group="Fitness",
                              desc="Coverage: a state at least this likely to be played in the performance is checked.")
        coverage_after_s: float = P(6.0, unit="s", ge=0.0, le=30.0, group="Fitness",
                                    desc="Coverage: how long the chain runs on after the forced state.")
        cap_durations: bool = P(False, group="Fitness",
                                desc="No movement is held longer than the length coverage checks (its 90th "
                                     "percentile); with coverage, every likely movement is then checked at that "
                                     "length (ADR-097).")
        seed: int = P(0, ge=0, le=2**31 - 1, ui="number", desc="Random seed.", group="Budget")
        #: read by Estimate cost: no inner loop
        inner_iterations: int = P(0, ge=0, le=0, advanced=True, desc="No inner loop (one play per seed).")
        inner_popsize: int = P(2, ge=2, le=2, advanced=True, desc="Unused.")

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        schema = super().params_schema()
        choices = sorted(registry.all("behavior_descriptor"))
        for f in schema["fields"]:
            if f["name"] in ("descriptor_x", "descriptor_y"):
                f.update({"type": "enum", "ui": "enum", "choices": choices})
        return schema

    def run(self, problem: EvolveProblem, backend: ComputeBackend, report: Callable[..., None]) -> EvolveResult:
        from ribs.archives import GridArchive

        from calflab.components import library
        from calflab.design import build_design
        from calflab.model.genome import Genome
        from calflab.model.overrides import Override

        p: Any = self.params
        rng = np.random.default_rng(p.seed)
        spec = build_design(Genome.model_validate(problem.genome), [Override.model_validate(o) for o in problem.overrides],
                            problem.generator, problem.generator_params).spec
        palette = palette_for(spec, list(p.palette) or None)
        if len(palette) < 2:
            raise ValueError("Fewer than two palette states fit this body: nothing to sequence")
        dim = len(layout(palette))
        report(kind="progress", generation=0, fraction=0.0)
        centres = safe_centres(spec, library(), problem.compile, palette, p.margin, cancelled=problem.cancelled)
        dkeys = [p.descriptor_x, p.descriptor_y]
        ranges = [tuple(r) if len(r) == 2 else registry.get("behavior_descriptor", k).range  # type: ignore[attr-defined]
                  for k, r in zip(dkeys, (list(p.range_x), list(p.range_y)), strict=True)]
        archive = GridArchive(solution_dim=dim, dims=[p.grid_x, p.grid_y], ranges=ranges, qd_score_offset=-2.0)
        result = EvolveResult()
        by_id: dict[str, Candidate] = {}
        vec: dict[str, np.ndarray] = {}
        base = {"genome": problem.genome, "overrides": problem.overrides, "generator": problem.generator,
                "generator_params": problem.generator_params, "compile": problem.compile, "fitness": problem.fitness,
                "palette": [n for n, _k, _b in palette], "duration_s": p.duration_s, "margin": p.margin,
                "unpredictability_weight": p.unpredictability_weight, "descriptors": dkeys,
                "coverage": p.coverage, "performance_s": p.performance_s, "coverage_p": p.coverage_p,
                "coverage_after_s": p.coverage_after_s, "cap_durations": p.cap_durations}

        def cancelled() -> bool:
            return bool(problem.cancelled and problem.cancelled())

        for gen in range(p.generations):
            if cancelled():
                break
            elites = list(result.cells.values())
            xs: list[np.ndarray] = []
            parents: list[list[str]] = []
            for _ in range(p.batch_size):
                if not elites:  # any sequence, the primitives near their defaults
                    xs.append(start_vector(palette, rng, p.start_spread, centres))
                    parents.append([])
                    continue
                a = by_id[elites[int(rng.integers(len(elites)))]]
                b = by_id[elites[int(rng.integers(len(elites)))]]
                x = vec[a.id] + rng.normal(0, p.sigma_iso, dim) + rng.normal(0, p.sigma_line) * (vec[b.id] - vec[a.id])
                xs.append(np.clip(x, 0.0, 1.0))
                parents.append([a.id] if a.id == b.id else [a.id, b.id])
            tasks = [Task(fn="calflab.evolve.diversity:evaluate_behaviour",
                          payload={**base, "x": [float(v) for v in x]}, id=f"{problem.run_id}-g{gen:03d}-{i:03d}")
                     for i, x in enumerate(xs)]
            done = [0]

            def on_result(_i: int, _r: Any, gen: int = gen, done: list[int] = done, n: int = len(tasks)) -> None:
                done[0] += 1
                report(kind="progress", generation=gen, fraction=(gen + done[0] / n) / p.generations)

            outs = backend.map(tasks, on_result=on_result, cancelled=cancelled)
            new: list[Candidate] = []
            ctrl0 = {"key": "interpreted", "params": {}}
            for i, (task, out) in enumerate(zip(tasks, outs, strict=True)):
                common = {"id": task.id, "run_id": problem.run_id, "generation": gen, "parents": parents[i],
                          "genome": problem.genome}
                if not isinstance(out, dict) or out.get("error"):
                    new.append(Candidate(**common, controller=ctrl0, fitness=-1e9, status="failed",
                                         error=str(out.get("error") if isinstance(out, dict) else out)))
                    continue
                if out.get("infeasible"):
                    new.append(Candidate(**common, controller=ctrl0, fitness=-1e9, status="infeasible",
                                         error="; ".join(out["infeasible"])))
                    continue
                result.evals += int(out.get("evals", 0))
                ctrl = {"key": "interpreted", "params": out["controller_params"]}
                measures = np.array([[out["descriptors"][k] for k in dkeys]])
                info = archive.add(xs[i][None, :], np.array([out["fitness"]]), measures)
                status = int(info["status"][0])
                gi = archive.int_to_grid_index(archive.index_of(measures))[0]
                cand = Candidate(**common, controller=ctrl, controller_x=out["controller_x"],
                                 fitness=float(out["fitness"]), fitness_terms=out["fitness_terms"],
                                 descriptors=out["descriptors"], metrics=out["metrics"], cell=(int(gi[0]), int(gi[1])),
                                 status={0: "rejected", 1: "improved", 2: "new"}[status],
                                 mass_g=float(out.get("mass_g", 0.0)),
                                 error="; ".join(out.get("unsafe_reasons") or []) or None)
                by_id[cand.id] = cand
                vec[cand.id] = xs[i]
                if status > 0:
                    result.cells[f"{gi[0]},{gi[1]}"] = cand.id
                new.append(cand)
            result.candidates += new
            ok = [c for c in new if c.status in ("new", "improved", "rejected")]
            stats = archive.stats
            entry = {"generation": gen,
                     "best": float(stats.obj_max) if stats.num_elites else None,  # type: ignore[arg-type]
                     "mean": float(stats.obj_mean) if stats.num_elites else None,  # type: ignore[arg-type]
                     "gen_best": max((c.fitness for c in ok), default=None),
                     "gen_mean": float(np.mean([c.fitness for c in ok])) if ok else None,
                     "coverage": float(stats.coverage), "qd_score": float(stats.qd_score),
                     "elites": int(stats.num_elites), "evals": result.evals,
                     "failed": sum(1 for c in new if c.status == "failed"),
                     "infeasible": sum(1 for c in new if c.status == "infeasible"),
                     "unsafe": sum(1 for c in new if not c.metrics.get("within_limits", True)),
                     "safe_elites": sum(1 for cid in result.cells.values() if by_id[cid].metrics.get("within_limits"))}
            result.history.append(entry)
            result.archive = {**self.archive_view(result, by_id, dkeys, ranges), "start": centres}
            report(kind="generation", generation=gen, entry=entry, candidates=new, result=result)
        if not result.archive:
            result.archive = {**self.archive_view(result, by_id, dkeys, ranges), "start": centres}
        return result

    def archive_view(self, result: EvolveResult, by_id: dict[str, Candidate], dkeys: list[str],
                     ranges: list[tuple[float, float]]) -> dict[str, Any]:
        """The same heatmap view as MAP-Elites + CMA-ES; each cell says whether its behaviour is within the limits."""
        view = MapElitesCMA.archive_view(self, result, by_id, dkeys, ranges)  # type: ignore[arg-type]
        for c in view["cells"]:
            m = by_id[c["candidate"]].metrics
            c.update({"within_limits": bool(m.get("within_limits")), "safety_margin": m.get("safety_margin"),
                      "unpredictability": m.get("unpredictability"), "states_played": m.get("states_played")})
        return view


# ---------------------------------------------------------------------- archive axes
def _mv(metrics: dict[str, Any], key: str) -> float:
    v = (metrics.get("movement") or {}).get(key)
    return float(v) if isinstance(v, int | float) and math.isfinite(v) else 0.0


@register
class TempoRegularity(BehaviorDescriptor):
    key = "tempo_regularity"
    label = "Tempo regularity"
    description = ("Height of the joint activity's strongest repetition in 0.3-3 s (0 = no rhythm, 1 = perfectly "
                   "periodic). A movement feature, not an emotion.")
    range = (0.0, 1.0)
    unit = ""

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return _mv(metrics, "tempo_regularity")


@register
class StillnessRatio(BehaviorDescriptor):
    key = "stillness_ratio"
    label = "Stillness ratio"
    description = "Share of the time the joints move slower than 5 deg/s. A movement feature, not an emotion."
    range = (0.0, 1.0)
    unit = ""

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return _mv(metrics, "stillness_ratio")


@register
class Unpredictability(BehaviorDescriptor):
    key = "unpredictability"
    label = "Unpredictability"
    description = ("Entropy rate of the behaviour generator's chain over its largest possible value (0 = the next "
                   "behaviour is always the same, 1 = every other one equally likely).")
    range = (0.0, 1.0)
    unit = ""

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        v = metrics.get("unpredictability")
        return float(v) if isinstance(v, int | float) and math.isfinite(v) else 0.0
