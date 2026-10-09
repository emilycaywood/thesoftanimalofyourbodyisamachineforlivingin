"""Built-in fitness terms and behavior descriptors.

Every term maps metrics (see ``calflab.sim.metrics.METRIC_DEFS``) to a score
where higher is better, roughly in [0, 1], so preset weights are comparable.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from calflab.model.spec import RobotSpec
from calflab.plugins import BehaviorDescriptor, FitnessTerm, register
from calflab.schema import P


def _m(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    v = metrics.get(key)
    return default if v is None else float(v)


@register
class ForwardSpeed(FitnessTerm):
    key = "forward_speed"
    label = "Forward speed"
    description = "Speed toward +X relative to a target speed (1 at the target, capped)."

    class Params(BaseModel):
        target: float = P(0.5, unit="m/s", ge=0.05, le=3, step=0.05, desc="Speed that earns the full score.")
        cap: float = P(1.5, ge=1, le=5, step=0.1, desc="Maximum score (allows rewarding beyond the target).")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        p = self.params
        return max(-1.0, min(p.cap, _m(metrics, "speed_mps") / p.target))  # type: ignore[attr-defined]


@register
class Efficiency(FitnessTerm):
    key = "efficiency"
    label = "Energy efficiency"
    description = "1 / (1 + cost of transport)."

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return 1.0 / (1.0 + _m(metrics, "cost_of_transport", 100.0))


@register
class Stability(FitnessTerm):
    key = "stability"
    label = "Stability"
    description = "Low trunk roll/pitch variation while staying upright."

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return _m(metrics, "stability")


@register
class Survival(FitnessTerm):
    key = "survival"
    label = "Stays upright"
    description = "Fraction of the rollout spent upright."

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return _m(metrics, "survival")


@register
class TorqueMargin(FitnessTerm):
    key = "torque_margin"
    label = "Torque margin"
    description = "Worst-case margin between peak torque and usable actuator torque."

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return max(-1.0, min(1.0, _m(metrics, "torque_margin_min")))


@register
class CoolRunning(FitnessTerm):
    key = "cool_running"
    label = "Thermal headroom"
    description = "Penalises estimated actuator temperature (first-order model)."

    class Params(BaseModel):
        ambient: float = P(22.0, unit="degC", ge=-10, le=50, desc="Ambient temperature.")
        limit: float = P(70.0, unit="degC", ge=30, le=120, desc="Temperature that scores zero.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        p = self.params
        t = _m(metrics, "temp_peak_c", p.ambient)  # type: ignore[attr-defined]
        return max(0.0, min(1.0, 1.0 - (t - p.ambient) / max(p.limit - p.ambient, 1e-6)))  # type: ignore[attr-defined]


@register
class QuietFeet(FitnessTerm):
    key = "quiet_feet"
    label = "Quiet feet"
    description = "Low hoof impact speed (a proxy for footfall noise)."

    class Params(BaseModel):
        reference: float = P(0.5, unit="m/s", ge=0.05, le=3, step=0.05, desc="Impact speed that scores 1/e.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return math.exp(-_m(metrics, "foot_impact_mps") / self.params.reference)  # type: ignore[attr-defined]


@register
class JointLimits(FitnessTerm):
    key = "joint_limits"
    label = "Away from joint limits"
    description = "1 - fraction of time any joint sits on a limit."

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return 1.0 - _m(metrics, "joint_limit_violation")


@register
class Straightness(FitnessTerm):
    key = "straightness"
    label = "Walks straight"
    description = "Penalises sideways drift."

    class Params(BaseModel):
        reference: float = P(0.3, unit="m", ge=0.05, le=2, step=0.05, desc="Drift that scores 1/e.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        return math.exp(-_m(metrics, "lateral_drift_m") / self.params.reference)  # type: ignore[attr-defined]


@register
class StandUp(FitnessTerm):
    key = "stand_up"
    label = "Stands up quickly"
    description = "Rewards a short time-to-stand from lying (0 if it never stands)."

    class Params(BaseModel):
        reference: float = P(3.0, unit="s", ge=0.5, le=20, step=0.5, desc="Time that scores 1/e.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        t = metrics.get("time_to_stand_s")
        if t is None:
            return 0.0
        return math.exp(-float(t) / self.params.reference)  # type: ignore[attr-defined]


@register
class Imitation(FitnessTerm):
    """Phase 2: reward for tracking a reference-motion clip from Blender."""

    key = "imitation"
    label = "Imitation of a reference clip"
    description = "Tracks joint angles and root trajectory of a motion-library clip (Phase 2)."
    stub = True

    class Params(BaseModel):
        clip: str = P("", desc="Motion-library clip id to imitate.")
        joint_weight: float = P(1.0, ge=0, le=5, step=0.1, desc="Weight of the joint-angle error.")
        root_weight: float = P(0.5, ge=0, le=5, step=0.1, desc="Weight of the root trajectory error.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        # TODO(phase2): needs the rollout and the clip in `context`; compute
        # exp(-w_j * mean joint error^2 - w_r * root error^2).
        raise NotImplementedError("Imitation rewards arrive with the Phase 2 PPO training plugin.")


# ============================================================ behavior descriptors
def _leg_length_mm(spec: RobotSpec) -> float:
    try:
        shank = spec.body("leg.fl.shank")
    except KeyError:
        return 0.0
    thigh_len = abs(shank.pos[2])
    hoof = next((g for g in shank.geoms if g.foot), None)
    return thigh_len + (abs(hoof.pos[2]) if hoof else 0.0)


@register
class LegLength(BehaviorDescriptor):
    key = "leg_length"
    label = "Leg length"
    description = "Thigh + shank length of the front-left leg."
    range = (200.0, 520.0)
    unit = "mm"

    def describe_candidate(self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        # at full size, so the range holds for a scaled calf (ADR-052)
        return _leg_length_mm(spec) / float(spec.metadata.get("scale") or 1.0)


@register
class GaitFrequency(BehaviorDescriptor):
    key = "gait_frequency"
    label = "Stride frequency"
    description = "Stride frequency chosen by the controller optimisation."
    range = (0.6, 3.0)
    unit = "Hz"

    def describe_candidate(self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return float(controller_params.get("frequency", 0.0))


@register
class BodyMass(BehaviorDescriptor):
    key = "body_mass"
    label = "Total mass"
    description = "Total robot mass including skin."
    range = (3500.0, 8000.0)
    unit = "g"

    def describe_candidate(self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return spec.total_mass_g()


@register
class TrunkLength(BehaviorDescriptor):
    key = "trunk_length"
    label = "Trunk length"
    description = "Length of the trunk shell."
    range = (300.0, 560.0)
    unit = "mm"

    def describe_candidate(self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        g = next((g for g in spec.root.geoms if g.id.endswith(".shell")), None)
        # at full size, so the range holds for a scaled calf (ADR-052)
        return float(g.size[0]) / float(spec.metadata.get("scale") or 1.0) if g else 0.0


@register
class Speed(BehaviorDescriptor):
    key = "speed"
    label = "Forward speed"
    description = "Achieved forward speed."
    range = (0.0, 1.0)
    unit = "m/s"

    def describe_candidate(self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return max(0.0, _m(metrics, "speed_mps"))
