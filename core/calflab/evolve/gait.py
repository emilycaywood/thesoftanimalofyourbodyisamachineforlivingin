"""Tune the gait for one fixed body (ADR-048).

CMA-ES over the controller's optimisable parameters with the body unchanged:
what the inner loop of the MAP-Elites optimizer does, but for the working
design, with two additions. Commanded joint speeds are held under a fraction of
each motor's recorded no-load speed (the simulator limits torque, not speed,
ADR-047), and the winner is checked on a longer rollout so a gait that only
survives the short scoring run is not chosen.

Rollouts are plain tasks, so they run on any compute backend.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.components.library import Library
from calflab.evolve.tasks import slim_metrics
from calflab.model.spec import RobotSpec
from calflab.plugins import ComputeBackend, Task, registry
from calflab.schema import P

SPEED_PENALTY = 6.0  # fitness lost per 100 % over a speed cap
SKIP_ABOVE = 0.5  # more than 50 % over a cap: not worth simulating


class GaitTuneSettings(BaseModel):
    iterations: int = P(30, ge=1, le=200, desc="CMA-ES iterations per footfall pattern.")
    popsize: int = P(12, ge=4, le=64, desc="Gaits tried per iteration.")
    duration_s: float = P(8.0, unit="s", ge=2, le=30, step=0.5, desc="Simulated seconds per trial.")
    speed_fraction: float = P(
        0.67, ge=0.2, le=1.0, step=0.01,
        desc="Commanded joint speed may reach this fraction of each motor's recorded no-load speed.",
    )
    gaits: list[str] = P(
        default_factory=lambda: ["trot", "walk"], ui="json",
        desc="Footfall patterns to try (empty = keep the current one).",
    )
    sigma: float = P(0.25, ge=0.05, le=0.5, step=0.01, desc="Initial CMA-ES step size.")
    seed: int = P(1, ge=1, le=2**31 - 1, ui="number", desc="Random seed.")
    apply: bool = P(True, desc="Write the gait found into the document (undoable).")


def speed_caps(spec: RobotSpec, lib: Library, fraction: float) -> dict[str, float]:
    """Allowed commanded speed (deg/s) per actuated joint: ``fraction`` of the
    actuator's recorded no-load speed at the joint (through its transmission)."""
    ratio = {t.id: t.ratio for t in spec.transmissions}
    out: dict[str, float] = {}
    for a in spec.actuators:
        rpm = lib.actuator(a.component).no_load_speed_rpm
        out[a.joint] = rpm * 6.0 * fraction / (ratio[a.transmission] if a.transmission else 1.0)
    return out


def speed_excess(peaks: dict[str, float], caps: dict[str, float]) -> float:
    """How far the worst joint is over its cap (0 = within; 0.2 = 20 % over)."""
    return max((peaks[j] / caps[j] - 1.0 for j in peaks if j in caps and caps[j] > 0), default=0.0)


def tune_gait(
    payload: dict[str, Any],
    spec: RobotSpec,
    lib: Library,
    settings: GaitTuneSettings,
    backend: ComputeBackend,
    report: Callable[[float, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Search gait parameters for the body described by ``payload``.

    ``payload`` is a :func:`calflab.evolve.tasks.simulate_once` payload (genome,
    overrides, generator, compile, sim, controller {key, params}, fitness).
    Returns the best gait that stays within the speed caps and does not fall
    (``params`` is None if there is none), with before/after figures.
    """
    import cma

    cls = registry.get("controller", payload["controller"]["key"])
    dims = cls.vector_dims()  # type: ignore[attr-defined]
    if not dims:
        raise ValueError(f"Controller {cls.key!r} has no tunable parameters")
    start = dict(payload["controller"].get("params", {}))
    joint_ids = [a.joint for a in spec.actuators]
    # parameters that do nothing on this body (e.g. elbow settings on a calf
    # with four three-motor legs) are left as they are, not searched
    relevant = set(cls.relevant_dims(joint_ids))  # type: ignore[attr-defined]
    free = [i for i, d in enumerate(dims) if d.name in relevant]
    caps = speed_caps(spec, lib, settings.speed_fraction)
    sim = {**payload.get("sim", {}), "duration_s": settings.duration_s}
    check_s = max(20.0, 2.5 * settings.duration_s)
    evals = [0]

    def peaks(params: dict[str, Any]) -> dict[str, float]:
        return cls.peak_joint_speeds(params, joint_ids)  # type: ignore[attr-defined]

    def rollouts(candidates: list[dict[str, Any]], duration: float | None = None) -> list[Any]:
        tasks = [
            Task(
                fn="calflab.evolve.tasks:simulate_once",
                payload={**payload, "sim": {**sim, **({"duration_s": duration} if duration else {})},
                         "controller": {"key": cls.key, "params": p}},
                id=f"tune-{evals[0] + i}",
            )
            for i, p in enumerate(candidates)
        ]
        evals[0] += len(tasks)
        return backend.map(tasks, cancelled=cancelled) if tasks else []

    def summary(params: dict[str, Any], out: Any) -> dict[str, Any]:
        ok = isinstance(out, dict) and not out.get("error")
        pk = peaks(params)
        return {
            "params": params,
            "fitness": float(out["fitness"]["total"]) if ok else None,
            "metrics": slim_metrics(out["metrics"]) if ok else {},
            "peak_speed_deg_s": {j: round(v, 1) for j, v in pk.items()},
            "speed_excess": round(max(0.0, speed_excess(pk, caps)), 3),
            "error": None if ok else str(out.get("error") if isinstance(out, dict) else out),
        }

    before = summary(start, rollouts([start], check_s)[0])
    has_gait = "gait" in cls.Params.model_fields
    patterns: list[str | None] = list(settings.gaits) if (has_gait and settings.gaits) else [None]
    total = len(patterns) * settings.iterations
    finalists: list[tuple[float, dict[str, Any]]] = []
    step = 0
    for pattern in patterns:
        base = dict(start) if pattern is None else {**start, "gait": pattern}
        x_full = np.array(cls.vector_from_params(base), dtype=np.float64)  # type: ignore[attr-defined]

        def params_of(x: Any, base: dict[str, Any] = base, x_full: np.ndarray = x_full) -> dict[str, Any]:
            full = x_full.copy()
            full[free] = np.asarray(x, dtype=float)
            return cls.params_from_vector(base, full)  # type: ignore[attr-defined]

        es = cma.CMAEvolutionStrategy(
            list(x_full[free]),
            settings.sigma,
            {"bounds": [0.0, 1.0], "popsize": settings.popsize, "seed": settings.seed, "verbose": -9},
        )
        best: tuple[float, dict[str, Any]] | None = None
        for _ in range(settings.iterations):
            if cancelled and cancelled():
                break
            xs = es.ask()
            cands = [params_of(x) for x in xs]
            excess = [max(0.0, speed_excess(peaks(p), caps)) for p in cands]
            run_idx = [i for i, e in enumerate(excess) if e <= SKIP_ABOVE]
            outs: dict[int, Any] = dict(zip(run_idx, rollouts([cands[i] for i in run_idx]), strict=True))
            losses = []
            for i, p in enumerate(cands):
                out: Any = outs.get(i)
                ok = isinstance(out, dict) and not out.get("error")
                fit = float(out["fitness"]["total"]) if ok else 0.0
                losses.append(-(fit - SPEED_PENALTY * excess[i]))
                if ok and excess[i] == 0.0 and not out["metrics"].get("fell") and (best is None or fit > best[0]):
                    best = (fit, p)
            es.tell(xs, losses)
            step += 1
            if report:
                label = f"{pattern or 'gait'}: " + (f"best {best[0]:.3f}" if best else "nothing upright within the speed caps yet")
                report(step / (total + 1), label)
        if best is not None:
            finalists.append(best)

    # keep only finalists that also survive a longer run, then take the best of those
    chosen: dict[str, Any] | None = None
    tried = []
    for (_fit, params), out in zip(finalists, rollouts([p for _, p in finalists], check_s), strict=True):
        s = summary(params, out)
        tried.append(s)
        if s["fitness"] is not None and not s["metrics"].get("fell") and (chosen is None or s["fitness"] > chosen["fitness"]):
            chosen = s
    return {
        "controller": cls.key,
        "params": chosen["params"] if chosen else None,
        "after": chosen,
        "before": before,
        "tried": tried,
        "speed_caps_deg_s": {j: round(v, 1) for j, v in caps.items()},
        "check_duration_s": check_s,
        "evals": evals[0],
        "cancelled": bool(cancelled and cancelled()),
    }
