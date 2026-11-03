"""The composition study (ADR-078): one body, several compositions of its behaviors.

Each composition is a set of the behaviors controller's parameters (tempo,
amplitude, stillness, smoothness, phrasing, affect curve, repertoire...)
applied over the document's controller. Every composition plays with every
seed (and, optionally, mildly randomised friction and mass), and each
rollout gives:

* the movement features of :mod:`calflab.behave.descriptors` (kinematics, not
  emotions);
* how closely the joints followed the clips (RMS tracking error, overall and
  per clip);
* the safety constraints of :mod:`calflab.evolve.safety` and whether the body
  fell.

The table gives, per composition, the mean and spread over seeds, so the
researcher can compare how compositions read and what they cost the hardware.
Evaluations are tasks (``evaluate_composition``) so they run on any compute
backend.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.behave.descriptors import FEATURES, NOTE, clip_tracking, movement_features


class Composition(BaseModel):
    name: str
    #: behaviors-controller parameters over the document's (partial)
    params: dict[str, Any] = Field(default_factory=dict)


def _default_compositions() -> list[Composition]:
    return [
        Composition(name="as set", params={}),
        Composition(name="slow, still, smooth", params={"tempo": 0.7, "idle_share": 0.6, "lowpass_hz": 2.0, "blend_s": 1.2}),
        Composition(name="fast, busy, sharp", params={"tempo": 1.4, "idle_share": 0.1, "lowpass_hz": 0.0, "blend_s": 0.3}),
    ]


class CompositionStudySettings(BaseModel):
    compositions: list[Composition] = Field(default_factory=_default_compositions)
    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])
    duration_s: float = Field(20.0, ge=2.0, le=300.0)
    #: mild domain randomisation per seed: floor friction and mass scale
    randomize: bool = False
    friction: tuple[float, float] = (0.7, 1.1)
    mass_scale: tuple[float, float] = (0.95, 1.05)


def randomization(on: bool, friction: tuple[float, float], mass: tuple[float, float]) -> dict[str, Any]:
    """CompileOptions.randomization that varies only friction and mass (others held at 1)."""
    return {"enabled": on, "friction": list(friction), "mass_scale": list(mass), "torque_scale": [1.0, 1.0],
            "kp_scale": [1.0, 1.0], "damping_scale": [1.0, 1.0], "skin_scale": [1.0, 1.0]}


def evaluate_composition(payload: dict[str, Any]) -> dict[str, Any]:
    """Task: build, compile, play the behaviors once; features, tracking and safety.

    Payload: genome, overrides, generator, generator_params, compile, sim, controller {key, params}, safety
    (policy dict)."""
    from calflab.components import library
    from calflab.design import build_design
    from calflab.evolve.constraints import infeasible
    from calflab.evolve.safety import SafetyPolicy, safety_report
    from calflab.evolve.tasks import slim_metrics
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout

    load_plugins()
    lib = library()
    design = build_design(Genome.model_validate(payload["genome"]),
                          [Override.model_validate(o) for o in payload.get("overrides", [])],
                          payload.get("generator", "calf"), payload.get("generator_params"))
    reasons = infeasible(design.spec)
    if reasons:
        return {"infeasible": reasons}
    settings = SimSettings.model_validate(payload.get("sim", {}))
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(payload.get("compile", {})), settings.seed)
    ctrl = registry.get("controller", payload["controller"]["key"])(payload["controller"].get("params", {}))
    rollout = run_rollout(cm, ctrl, settings, lib)  # type: ignore[arg-type]
    metrics = compute_metrics(rollout)
    safety = safety_report(rollout, design.spec, lib, SafetyPolicy.model_validate(payload.get("safety") or {}), metrics)
    return {
        "metrics": slim_metrics(metrics),
        "features": movement_features(rollout, design.spec),
        "clips": clip_tracking(rollout),
        "safety": safety,
        "episodes": len((rollout.meta.get("controller_log") or {}).get("episodes") or []),
    }


def _stat(vals: list[float]) -> dict[str, float | None]:
    v = [x for x in vals if x is not None]
    if not v:
        return {"mean": None, "sd": None, "min": None, "max": None}
    a = np.asarray(v, dtype=float)
    return {"mean": round(float(a.mean()), 4), "sd": round(float(a.std()), 4), "min": round(float(a.min()), 4),
            "max": round(float(a.max()), 4)}


def summarize(compositions: list[Composition], seeds: list[int], results: list[list[Any]]) -> list[dict[str, Any]]:
    """One row per composition: each feature, tracking and safety number as mean / spread over the seeds."""
    rows = []
    for comp, per_seed in zip(compositions, results, strict=True):
        ok = [r for r in per_seed if isinstance(r, dict) and "features" in r]
        row: dict[str, Any] = {"name": comp.name, "params": comp.params, "runs": len(per_seed), "ok": len(ok),
                               "errors": [str(r.get("error") if isinstance(r, dict) else r) for r in per_seed
                                          if not (isinstance(r, dict) and "features" in r)]}
        row["features"] = {k: _stat([r["features"].get(k) for r in ok]) for k in FEATURES}
        row["tracking_rms_deg"] = _stat([r["metrics"].get("tracking_rms_deg") for r in ok])
        row["falls"] = sum(1 for r in ok if r["metrics"].get("fell"))
        row["safety_margin"] = _stat([r["safety"]["margin"] for r in ok])
        row["rejected_runs"] = sum(1 for r in ok if r["safety"]["rejected"])
        viol: dict[str, int] = {}
        for r in ok:
            for k in r["safety"]["violations"]:
                viol[k] = viol.get(k, 0) + 1
        row["violations"] = viol
        clips: dict[str, list[float]] = {}
        for r in ok:
            for cid, c in r["clips"].items():
                clips.setdefault(cid, []).append(c["tracking_rms_deg"])
        row["clip_tracking_deg"] = {cid: _stat(v) for cid, v in clips.items()}
        row["seeds"] = seeds
        rows.append(row)
    return rows


def table_csv(rows: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    head = ["composition", "runs", "falls", "tracking_rms_deg_mean", "tracking_rms_deg_sd", "safety_margin_mean",
            "safety_margin_min", "rejected_runs", "violations"]
    for k in FEATURES:
        head += [f"{k}_mean", f"{k}_sd"]
    w.writerow(head)
    for r in rows:
        line = [r["name"], r["ok"], r["falls"], r["tracking_rms_deg"]["mean"], r["tracking_rms_deg"]["sd"],
                r["safety_margin"]["mean"], r["safety_margin"]["min"], r["rejected_runs"],
                " ".join(f"{k}:{v}" for k, v in r["violations"].items())]
        for k in FEATURES:
            line += [r["features"][k]["mean"], r["features"][k]["sd"]]
        w.writerow(["" if v is None else v for v in line])
    return out.getvalue()


def feature_columns() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "unit": unit} for k, (label, unit) in FEATURES.items()]


__all__ = ["NOTE", "Composition", "CompositionStudySettings", "evaluate_composition", "summarize", "table_csv"]
