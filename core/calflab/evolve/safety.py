"""Safety as constraints on a rollout (ADR-079), from the load analysis of ADR-069.

Six constraints, each reported with its value, limit and verdict:

* ``servo_sustained``: a servo above ``rated_fraction`` x rated torque for more
  than ``sustained_fraction`` of any window of ``window_s``;
* ``stall``: a servo at or above its stall torque at any moment;
* ``belt_sustained``: a belt above its allowable working tension for more than
  ``sustained_fraction`` of a window ("unknown" where the catalog has no
  allowable tension);
* ``belt_breaking``: a belt tension peak above ``breaking_fraction`` x breaking
  strength;
* ``joint_speed``: a joint faster than its servo's no-load speed at that joint;
* ``joint_limit``: the share of time a joint is within 1 deg of a range limit,
  above ``joint_limit_max``;
* ``envelope`` (ADR-084): a servo at the edge of its torque-speed envelope
  (|torque| / stall + |speed| / no-load speed when driving), from
  :mod:`calflab.mech.limits`, the same numbers the physics review shows;
* ``fall``: the body fell (reported; survival is in the fitness).

``margin`` (0 = none, as before) is the safety margin the researcher sets
(ADR-084): every physical limit is lowered to (1 - margin) x itself, i.e. the
stall torque, the rated-torque fraction, the no-load speed, the envelope, the
belt's allowable working tension and its breaking fraction.

The policy decides what a violation does: ``reject`` (the candidate is not
kept) or ``penalise`` (fitness minus ``weight`` x the relative excess, at most
``weight``). The researcher's default (2026-11-03): reject breaking and stall,
penalise the rest. Thresholds come from the body's own checks
(``spec.metadata["feral"]["checks"]``, ADR-069) when it has them.

``margin`` is the smallest headroom over the known constraints
(1 - value / limit, so 1 = unloaded, 0 = at the limit, < 0 = over), an
archive axis.

Units: fractions, N, N*m, deg/s.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab import units as u
from calflab.mech.loads import analyse

CONSTRAINTS: dict[str, str] = {
    "servo_sustained": "Servo above its rated-torque fraction for too much of a window",
    "stall": "Servo at stall torque",
    "belt_sustained": "Belt above its allowable working tension for too much of a window",
    "belt_breaking": "Belt tension peak near its breaking strength",
    "joint_speed": "Joint faster than its servo",
    "joint_limit": "Time at joint limits",
    "envelope": "Servo at the edge of its torque-speed envelope",
    "fall": "The body fell",
}
Action = Literal["reject", "penalise", "report"]


class SafetyPolicy(BaseModel):
    """What each constraint does when violated, and the thresholds not taken from the body."""

    actions: dict[str, Action] = Field(default_factory=lambda: {  # type: ignore[arg-type]
        "servo_sustained": "penalise", "stall": "reject", "belt_sustained": "penalise", "belt_breaking": "reject",
        "joint_speed": "penalise", "joint_limit": "penalise", "envelope": "penalise", "fall": "report"})
    weights: dict[str, float] = Field(default_factory=lambda: {k: 0.5 for k in CONSTRAINTS})
    #: window over which "sustained" is judged (s); a repertoire has no single gait cycle (ADR-079)
    window_s: float = 2.0
    #: largest share of time within 1 deg of a joint limit before it counts as a violation (assumption, ADR-079)
    joint_limit_max: float = 0.05
    #: used when the body has no checks of its own (ADR-069 defaults)
    rated_fraction: float = 0.6
    sustained_fraction: float = 0.25
    breaking_fraction: float = 0.25
    #: safety margin on every physical limit (ADR-084): a limit L becomes (1 - margin) x L; 0 = as before
    margin: float = Field(0.0, ge=0.0, lt=1.0)


def _row(key: str, value: float | None, limit: float, policy: SafetyPolicy, detail: str = "",
         unknown: bool = False) -> dict[str, Any]:
    violated = bool(value is not None and value > limit)
    action = policy.actions.get(key, "penalise")
    excess = (value / limit - 1.0) if (violated and value is not None and limit > 0) else 0.0
    return {"key": key, "label": CONSTRAINTS[key], "value": None if value is None else round(float(value), 4),
            "limit": round(float(limit), 4), "violated": violated, "unknown": unknown, "action": action,
            "penalty": round(policy.weights.get(key, 0.5) * min(1.0, excess), 4) if violated and action == "penalise" else 0.0,
            "margin": None if value is None or limit <= 0 else round(1.0 - value / limit, 4), "detail": detail}


def until_fall(rollout: Any) -> Any:
    """The rollout up to its fall (loads after a fall are not the motion's loads, ADR-069); unchanged if it stood."""
    ft = rollout.meta.get("fall_time")
    if not rollout.meta.get("fell") or ft is None:
        return rollout
    keep = rollout.t <= float(ft)
    if keep.sum() < 2:
        return rollout
    cut = {f.name: (getattr(rollout, f.name)[keep] if isinstance(getattr(rollout, f.name), np.ndarray)
                    and getattr(rollout, f.name).shape[:1] == rollout.t.shape else getattr(rollout, f.name))
           for f in dataclasses.fields(rollout)}
    return dataclasses.replace(rollout, **cut)


def safety_report(rollout: Any, spec: Any, lib: Any, policy: SafetyPolicy | None = None,
                  metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every constraint on one rollout (up to a fall, if it fell), whether it rejects the candidate, and the
    fitness penalty."""
    policy = policy or SafetyPolicy()
    full = rollout
    rollout = until_fall(rollout)
    feral = spec.metadata.get("feral") or {}
    checks = {"rated_fraction": policy.rated_fraction, "sustained_fraction": policy.sustained_fraction,
              "breaking_fraction": policy.breaking_fraction, **(feral.get("checks") or {})}
    keep = 1.0 - float(policy.margin)  # every physical limit x (1 - margin), ADR-084
    belts = {d: dict(r) for d, r in (feral.get("belt_drives") or {}).items()}
    if keep < 1.0:
        checks = {**checks, "rated_fraction": float(checks["rated_fraction"]) * keep,
                  "breaking_fraction": float(checks["breaking_fraction"]) * keep}
        for r in belts.values():
            if r.get("allowable_working_tension_n") is not None:
                r["allowable_working_tension_n"] = float(r["allowable_working_tension_n"]) * keep
    loads = analyse(rollout, spec, lib, policy.window_s, checks, belts)
    rows = loads["summary"]
    sustained = float(checks["sustained_fraction"])

    def worst(key: str) -> tuple[float | None, str]:
        vals = [(r[key], r["joint"]) for r in rows if r.get(key) is not None and not isinstance(r.get(key), str)]
        if not vals:
            return None, ""
        v, j = max(vals, key=lambda x: float(x[0]))
        return float(v), j.replace("joint.", "")

    out = []
    v, j = worst("above_rated_fraction_of_cycle")
    out.append(_row("servo_sustained", v, sustained, policy,
                    f"{j}: above {checks['rated_fraction']:.0%} of rated for {v:.0%} of a {policy.window_s:g} s window"
                    if v is not None else "no rated torque recorded", unknown=v is None))
    v, j = worst("pct_stall_peak")
    out.append(_row("stall", None if v is None else v / 100.0 / 0.999, keep, policy,
                    f"{j}: peak {v:.0f} % of stall" if v is not None else ""))
    belt_rows = [r for r in rows if "belt_tension_peak_n" in r]
    if belt_rows:
        v, j = worst("above_allowable_fraction_of_cycle")
        unknown = any(r.get("sustained_above_allowable") == "unknown" for r in belt_rows)
        out.append(_row("belt_sustained", v, sustained, policy,
                        (f"{j}: above allowable for {v:.0%} of a window" if v is not None else "")
                        + ("; some belts have no allowable tension in the catalog" if unknown else ""), unknown=v is None))
        v, j = worst("peak_over_breaking")
        out.append(_row("belt_breaking", v, float(checks["breaking_fraction"]), policy,
                        f"{j}: peak {v:.0%} of breaking strength" if v is not None else "breaking strength unknown",
                        unknown=v is None))
    # joint speed against each servo's no-load speed at the joint
    lim = rollout.meta.get("speed_limit") or []
    m = rollout.t >= 0
    if len(lim) == rollout.dq.shape[1] and m.any():
        ratio = np.max(np.abs(rollout.dq[m]), axis=0) / np.maximum(np.asarray(lim, dtype=float), 1e-9)
        k = int(np.argmax(ratio))
        out.append(_row("joint_speed", float(ratio[k]), keep, policy,
                        f"{rollout.actuator_ids[k].replace('act.', '')}: {float(u.rad_to_deg(float(np.max(np.abs(rollout.dq[m][:, k]))))):.0f} "
                        f"deg/s against {float(u.rad_to_deg(float(lim[k]))):.0f}"))
    from calflab.sim import compute_metrics

    jl = (metrics or {}).get("joint_limit_violation") if rollout is full else None
    if jl is None:
        jl = compute_metrics(rollout).get("joint_limit_violation")
    out.append(_row("joint_limit", float(jl or 0.0), policy.joint_limit_max, policy,
                    f"{float(jl or 0.0):.0%} of the time within 1 deg of a limit"))
    # the torque-speed envelope, from the same numbers as the physics review (ADR-084)
    from calflab.mech.limits import servo_columns

    cols = servo_columns(rollout, spec, lib)
    if cols and m.any():
        peaks = [(float(np.max(c["use"])), c) for c in cols if len(c["use"])]
        if peaks:
            use, c = max(peaks, key=lambda x: x[0])
            k = int(np.argmax(c["use"]))
            out.append(_row("envelope", use / 0.999, keep, policy,
                            f"{c['joint'].replace('joint.', '')}: {use:.0%} of its torque-speed envelope "
                            f"({abs(float(c['torque'][k])):.2f} N*m at {abs(float(u.rad_to_deg(float(c['omega'][k])))):.0f} deg/s)"))
    fall = _row("fall", 1.0 if full.meta.get("fell") else 0.0, 0.5, policy,
                f"fell at t = {float(full.meta.get('fall_time') or 0.0):.2f} s" if full.meta.get("fell") else "stood")
    fall["margin"] = None
    out.append(fall)
    rejected = [r["key"] for r in out if r["violated"] and r["action"] == "reject"]
    margins = [r["margin"] for r in out if r["margin"] is not None]
    return {
        "constraints": out,
        "rejected": bool(rejected),
        "reject_reasons": [f"{r['label']}: {r['detail']}" for r in out if r["key"] in rejected],
        "penalty": round(sum(r["penalty"] for r in out), 4),
        "margin": round(min(margins), 4) if margins else None,
        "violations": [r["key"] for r in out if r["violated"]],
        "policy": policy.model_dump(mode="json"),
        "fell": bool(full.meta.get("fell")),
        "judged_until_s": round(float(rollout.t[-1]), 3) if rollout is not full else None,
    }
