"""Evaluation tasks. These are plain functions of a JSON payload so they can
run in a local worker process, on a remote machine, or in a notebook (ADR-013).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.components import library
from calflab.design import build_design
from calflab.fitness.preset import FitnessPreset
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.plugins import load_plugins, registry
from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout


def slim_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Metrics without the per-actuator table (kept small for archives)."""
    return {k: v for k, v in metrics.items() if k != "by_actuator"}


def simulate_once(payload: dict[str, Any]) -> dict[str, Any]:
    """Build, compile and roll out one design with one controller; return metrics + fitness.

    Payload keys: genome, overrides, generator, generator_params, compile,
    sim, controller {key, params}, fitness (preset dict, optional).
    """
    load_plugins()
    lib = library()
    design = build_design(
        Genome.model_validate(payload["genome"]),
        [Override.model_validate(o) for o in payload.get("overrides", [])],
        payload.get("generator", "calf"),
        payload.get("generator_params"),
    )
    settings = SimSettings.model_validate(payload.get("sim", {}))
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(payload.get("compile", {})), settings.seed)
    ckey = payload["controller"]["key"]
    controller = registry.get("controller", ckey)(payload["controller"].get("params", {}))
    rollout = run_rollout(cm, controller, settings, lib)  # type: ignore[arg-type]
    metrics = compute_metrics(rollout)
    out: dict[str, Any] = {"metrics": metrics}
    if payload.get("fitness"):
        out["fitness"] = FitnessPreset.model_validate(payload["fitness"]).evaluate(metrics)
    return out


def evaluate_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Score one morphology: an inner CMA-ES loop tunes the controller for it (ADR-012).

    Extra payload keys: inner {iterations, popsize, sigma}, descriptors [keys],
    controller.x0 (optional warm-start vector in [0, 1]).
    Returns the best controller found with its fitness, metrics and descriptors.
    """
    import cma

    load_plugins()
    lib = library()
    design = build_design(
        Genome.model_validate(payload["genome"]),
        [Override.model_validate(o) for o in payload.get("overrides", [])],
        payload.get("generator", "calf"),
        payload.get("generator_params"),
    )
    settings = SimSettings.model_validate(payload.get("sim", {}))
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(payload.get("compile", {})), settings.seed)
    preset = FitnessPreset.model_validate(payload["fitness"])
    ctrl_cls = registry.get("controller", payload["controller"]["key"])
    base_params: dict[str, Any] = dict(payload["controller"].get("params", {}))
    dims = ctrl_cls.vector_dims()  # type: ignore[attr-defined]
    seed = int(payload.get("seed", 0))

    def score(params: dict[str, Any]) -> tuple[float, dict[str, Any], dict[str, Any]]:
        rollout = run_rollout(cm, ctrl_cls(params), settings, lib)  # type: ignore[arg-type]
        metrics = compute_metrics(rollout)
        fit = preset.evaluate(metrics)
        return float(fit["total"]), fit, metrics

    x0 = payload["controller"].get("x0")
    x_start = (
        np.clip(np.asarray(x0, dtype=float), 0.0, 1.0)
        if x0 is not None and len(x0) == len(dims)
        else ctrl_cls.vector_from_params(base_params)  # type: ignore[attr-defined]
    )
    best_params = ctrl_cls.params_from_vector(base_params, x_start) if dims else base_params  # type: ignore[attr-defined]
    best_f, best_fit, best_metrics = score(best_params)
    best_x = x_start
    evals = 1

    inner = payload.get("inner", {})
    iterations = int(inner.get("iterations", 0))
    if dims and iterations > 0:
        es = cma.CMAEvolutionStrategy(
            list(x_start),
            float(inner.get("sigma", 0.15)),
            {
                "bounds": [0.0, 1.0],
                "popsize": int(inner.get("popsize", 6)),
                "seed": seed + 1,  # cma treats 0 as "random"
                "verbose": -9,
            },
        )
        for _ in range(iterations):
            xs = es.ask()
            losses = []
            for x in xs:
                params = ctrl_cls.params_from_vector(base_params, np.asarray(x))  # type: ignore[attr-defined]
                f, fit, metrics = score(params)
                evals += 1
                losses.append(-f)
                if f > best_f:
                    best_f, best_fit, best_metrics, best_params, best_x = f, fit, metrics, params, np.asarray(x)
            es.tell(xs, losses)

    descriptors = {}
    for key in payload.get("descriptors", []):
        d = registry.get("behavior_descriptor", key)()
        descriptors[key] = float(d.describe_candidate(design.spec, best_metrics, best_params))  # type: ignore[attr-defined]
    return {
        "fitness": best_f,
        "fitness_terms": best_fit["terms"],
        "controller_params": best_params,
        "controller_x": [float(v) for v in best_x],
        "metrics": slim_metrics(best_metrics),
        "descriptors": descriptors,
        "mass_g": design.spec.total_mass_g(),
        "evals": evals,
    }
