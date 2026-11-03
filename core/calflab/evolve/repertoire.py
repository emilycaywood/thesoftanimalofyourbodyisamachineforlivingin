"""Evaluating a candidate consistently and safely (ADR-079).

When the fitness preset has an ``evaluation`` block (the ``repertoire``
preset), one controller setting is scored over several seeds, each with
mildly randomised floor friction and mass (compiled per seed), and:

* every rollout's metrics get the movement features (archive axes), the
  per-clip tracking from the episode log, and the required clips' tracking
  (for ``imitation_required``);
* every rollout gets the safety report of :mod:`calflab.evolve.safety`
  (judged up to a fall); a penalised violation lowers that seed's fitness;
* the seeds are aggregated pessimistically: mean minus ``spread_k`` x spread,
  or the worst seed;
* a constraint set to ``reject`` that is violated in *any* seed rejects the
  setting (status ``unsafe`` when no setting of the inner loop is safe).

Every seed is recorded with its friction and mass scale, fitness, fall,
margin and violations.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.behave.descriptors import clip_tracking, movement_features
from calflab.behave.study import randomization
from calflab.evolve.safety import SafetyPolicy, safety_report
from calflab.fitness.preset import EvaluationSettings, FitnessPreset

#: subtracted from a rejected setting's fitness inside the inner loop, so CMA-ES moves away from it
UNSAFE_LOSS = 10.0


def required_clips(params: dict[str, Any], tracking: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per required behavior: its weight and the tracking error over the clips it played (None if none played)."""
    out = {}
    for raw in params.get("repertoire") or []:
        e = raw if isinstance(raw, dict) else raw.model_dump()
        if not e.get("required") or e.get("kind") != "clip":
            continue
        ids = [e["clip"]] if e.get("clip") else list((params.get("pools") or {}).get(e["name"], []))
        played = [tracking[c] for c in ids if c in tracking]
        if played:
            secs = sum(p["played_s"] for p in played) or 1.0
            rms = float(np.sqrt(sum(p["tracking_rms_deg"] ** 2 * p["played_s"] for p in played) / secs))
        else:
            rms = None
        out[e["name"]] = {"weight": float(e.get("imitation_weight", 1.0)), "tracking_rms_deg": rms, "clips": ids}
    return out


def enrich(metrics: dict[str, Any], rollout: Any, spec: Any, params: dict[str, Any]) -> dict[str, Any]:
    tracking = clip_tracking(rollout)
    return {**metrics, "movement": movement_features(rollout, spec), "clip_tracking": tracking,
            "required_clips": required_clips(params, tracking)}


def aggregate(values: list[float], ev: EvaluationSettings) -> float:
    a = np.asarray(values, dtype=float)
    if ev.aggregate == "worst":
        return float(a.min())
    return float(a.mean() - ev.spread_k * a.std())


def evaluate(design: Any, lib: Any, payload: dict[str, Any], ctrl_cls: Any, params: dict[str, Any],
             preset: FitnessPreset) -> dict[str, Any]:
    """Score one controller setting over the preset's seeds. Returns fitness (aggregated, with penalties), the
    worst seed's terms and enriched metrics, every seed's record, and whether it is rejected."""
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout

    ev = preset.evaluation or EvaluationSettings()
    policy = SafetyPolicy.model_validate(ev.safety) if ev.safety is not None else None
    if ctrl_cls.key == "behaviors" and ev.play_required_first:
        params = {**params, "play_required_first": True}
    copts = dict(payload.get("compile", {}))
    if ev.torque_derating is not None:
        copts["torque_derating"] = ev.torque_derating
    if ev.servo_model is not None:
        copts["servo_model"] = ev.servo_model
    copts["randomization"] = randomization(ev.randomize, ev.friction, ev.mass_scale)
    seeds = []
    for seed in ev.seeds:
        cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(copts), seed)
        settings = SimSettings.model_validate({**payload.get("sim", {}), "seed": seed})
        rollout = run_rollout(cm, ctrl_cls(params), settings, lib)
        metrics = enrich(compute_metrics(rollout), rollout, design.spec, params)
        fit = preset.evaluate(metrics)
        safety = safety_report(rollout, design.spec, lib, policy, metrics) if policy is not None else None
        penalty = safety["penalty"] if safety else 0.0
        seeds.append({"seed": seed, "fitness": float(fit["total"]) - penalty, "raw_fitness": float(fit["total"]),
                      "penalty": penalty, "fell": bool(metrics.get("fell")), "terms": fit["terms"], "metrics": metrics,
                      "safety": safety, "scales": {k: round(float(v), 4) for k, v in (cm.scales or {}).items()}})
    worst = min(seeds, key=lambda s: s["fitness"])
    total = aggregate([s["fitness"] for s in seeds], ev)
    rejected = [r for s in seeds if s["safety"] for r in s["safety"]["reject_reasons"]]
    margins = [s["safety"]["margin"] for s in seeds if s["safety"] and s["safety"]["margin"] is not None]
    metrics = dict(worst["metrics"])
    metrics["safety"] = min((s["safety"] for s in seeds if s["safety"]), key=lambda r: r["margin"] if r["margin"]
                            is not None else 9.0, default=None)
    metrics["safety_margin"] = min(margins) if margins else None
    metrics["seeds"] = [{"seed": s["seed"], "fitness": round(s["fitness"], 4), "raw_fitness": round(s["raw_fitness"], 4),
                         "penalty": s["penalty"], "fell": s["fell"], "scales": s["scales"],
                         "margin": s["safety"]["margin"] if s["safety"] else None,
                         "violations": s["safety"]["violations"] if s["safety"] else []} for s in seeds]
    metrics["aggregate"] = {"method": ev.aggregate, "spread_k": ev.spread_k, "value": round(total, 4),
                            "mean": round(float(np.mean([s["fitness"] for s in seeds])), 4),
                            "spread": round(float(np.std([s["fitness"] for s in seeds])), 4)}
    return {"fitness": total, "terms": worst["terms"], "metrics": metrics, "rejected": sorted(set(rejected)),
            "evals": len(seeds)}
