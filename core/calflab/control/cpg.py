"""Central pattern generator gait controller for the calf's 3-DOF legs.

Each leg has a phase in [0, 1). During stance the hip sweeps the leg backward
at constant rate; during swing it returns forward on a cosine while the knee
flexes to lift the hoof. Gaits differ only in the phase offsets between legs.

The default numbers are a trot tuned on 2026-10-04 for the default body
(front knees forward, hind knees backward) with the peak commanded joint speed
held at 120 deg/s; see ADR-047. They are starting points, not measurements.

A leg without a hip-flexion motor (two-motor front legs) steps differently:
its knee does the fore-and-aft sweep (``elbow_amplitude``) and its hip
abduction lifts the hoof clear during swing (``swing_abduction``).

Joints are found by the ID convention ``joint.<leg>.{hip_abd,hip_flex,knee}``
with leg in (fl, fr, hl, hr). Other actuators hold their standing angle.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.plugins import ControlInfo, Controller, Observation, VectorDim, register
from calflab.schema import P

GAITS: dict[str, tuple[float, float, float, float]] = {  # fl, fr, hl, hr
    "trot": (0.0, 0.5, 0.5, 0.0),
    "walk": (0.0, 0.5, 0.75, 0.25),
    "pace": (0.0, 0.5, 0.0, 0.5),
    "bound": (0.0, 0.0, 0.5, 0.5),
}
LEG_ORDER = ("fl", "fr", "hl", "hr")


@register
class CPGController(Controller):
    """Open-loop CPG gait generator."""

    key = "cpg"
    label = "CPG gait"
    description = "Open-loop central pattern generator (trot, walk, pace, bound)."
    version = "1"

    class Params(BaseModel):
        gait: Literal["trot", "walk", "pace", "bound"] = P("trot", desc="Footfall pattern.")
        frequency: float = P(2.0, unit="Hz", ge=0.4, le=3.5, step=0.05, desc="Stride frequency.")
        hip_amplitude: float = P(10.5, unit="deg", ge=0, le=40, step=0.5, desc="Half of the hip sweep.")
        knee_amplitude: float = P(10.5, unit="deg", ge=0, le=60, step=0.5, desc="Extra knee flexion during swing.")
        swing_fraction: float = P(0.55, ge=0.2, le=0.6, step=0.01, desc="Fraction of the stride spent in swing.")
        hip_offset: float = P(-3.0, unit="deg", ge=-20, le=20, step=0.5, desc="Constant hip bias (positive = legs further back).")
        crouch: float = P(-7.0, unit="deg", ge=-15, le=30, step=0.5, desc="Extra knee flexion in stance (negative = straighter legs).")
        abduction_amplitude: float = P(0.0, unit="deg", ge=0, le=15, step=0.5, desc="Lateral sway of the hips.")
        elbow_amplitude: float = P(
            13.0, unit="deg", ge=0, le=40, step=0.5,
            desc="Two-motor legs only: half of the fore-and-aft sweep made by the knee (elbow).",
        )
        elbow_offset: float = P(
            0.0, unit="deg", ge=-25, le=25, step=0.5,
            desc="Two-motor legs only: constant bias of that sweep (positive = hoof further back).",
        )
        swing_abduction: float = P(
            6.5, unit="deg", ge=0, le=28, step=0.5,
            desc="Two-motor legs only: how far the leg swings outward to lift the hoof during swing.",
        )
        ramp: float = P(0.8, unit="s", ge=0.0, le=3.0, step=0.1, desc="Time to ramp the gait in from standing.")

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [
            VectorDim("frequency", 0.6, 3.0),
            VectorDim("hip_amplitude", 2.0, 35.0),
            VectorDim("knee_amplitude", 5.0, 55.0),
            VectorDim("swing_fraction", 0.25, 0.55),
            VectorDim("hip_offset", -15.0, 15.0),
            VectorDim("crouch", -10.0, 25.0),
            VectorDim("elbow_amplitude", 2.0, 35.0),
            VectorDim("elbow_offset", -20.0, 20.0),
            VectorDim("swing_abduction", 0.0, 25.0),
        ]

    @classmethod
    def relevant_dims(cls, joint_ids: list[str]) -> list[str]:
        ids = set(joint_ids)
        legs = [leg for leg in LEG_ORDER if f"joint.{leg}.knee" in ids or f"joint.{leg}.hip_flex" in ids]
        three = any(f"joint.{leg}.hip_flex" in ids for leg in legs)
        two = any(f"joint.{leg}.hip_flex" not in ids for leg in legs)
        skip: set[str] = set()
        if not two:
            skip |= {"elbow_amplitude", "elbow_offset", "swing_abduction"}
        if not three:
            skip |= {"hip_amplitude", "knee_amplitude", "hip_offset", "crouch"}
        return [d.name for d in cls.vector_dims() if d.name not in skip]

    @classmethod
    def peak_joint_speeds(cls, params: dict[str, object], joint_ids: list[str]) -> dict[str, float]:
        p = cls.Params.model_validate(params)
        t_swing, t_stance = p.swing_fraction / p.frequency, (1.0 - p.swing_fraction) / p.frequency
        ids = set(joint_ids)
        out: dict[str, float] = {}

        def sweep(a: float) -> float:  # steady in stance, a cosine in swing
            return max(2.0 * a / t_stance, math.pi * a / t_swing)

        for leg in LEG_ORDER:
            abd, hip, knee = (f"joint.{leg}.{j}" for j in ("hip_abd", "hip_flex", "knee"))
            sway = 2.0 * math.pi * p.frequency * p.abduction_amplitude
            if hip in ids:
                out[hip] = sweep(p.hip_amplitude)
                if knee in ids:
                    out[knee] = math.pi * p.knee_amplitude / t_swing
                if abd in ids:
                    out[abd] = sway
            else:
                if knee in ids:
                    out[knee] = sweep(p.elbow_amplitude)
                if abd in ids:
                    out[abd] = sway + math.pi * p.swing_abduction / t_swing
        return out

    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        self.info = info
        self._legs: list[tuple[int | None, int | None, int | None, float, float]] = []
        offsets = GAITS[self.params.gait]  # type: ignore[attr-defined]
        for leg, phase in zip(LEG_ORDER, offsets, strict=True):
            abd = info.index(f"joint.{leg}.hip_abd")
            hip = info.index(f"joint.{leg}.hip_flex")
            knee = info.index(f"joint.{leg}.knee")
            side = 1.0 if leg.endswith("l") else -1.0
            self._legs.append((abd, hip, knee, phase, side))

    def act(self, obs: Observation) -> np.ndarray:
        p = self.params
        info = self.info
        target = info.rest.copy()
        ramp = 1.0 if p.ramp <= 0 else min(1.0, obs.t / p.ramp)  # type: ignore[attr-defined]
        a_hip = u.deg_to_rad(p.hip_amplitude) * ramp  # type: ignore[attr-defined]
        a_knee = u.deg_to_rad(p.knee_amplitude) * ramp  # type: ignore[attr-defined]
        a_abd = u.deg_to_rad(p.abduction_amplitude) * ramp  # type: ignore[attr-defined]
        a_elbow = u.deg_to_rad(p.elbow_amplitude) * ramp  # type: ignore[attr-defined]
        a_lift = u.deg_to_rad(p.swing_abduction) * ramp  # type: ignore[attr-defined]
        elbow_off = u.deg_to_rad(p.elbow_offset) * ramp  # type: ignore[attr-defined]
        off = u.deg_to_rad(p.hip_offset) * ramp  # type: ignore[attr-defined]
        crouch = u.deg_to_rad(p.crouch) * ramp  # type: ignore[attr-defined]
        swing = float(p.swing_fraction)  # type: ignore[attr-defined]
        stance = 1.0 - swing
        base = obs.t * p.frequency  # type: ignore[attr-defined]
        for abd, hip, knee, phase, side in self._legs:
            ph = (base + phase) % 1.0
            if ph < stance:  # stance: leg sweeps back (angle increases)
                s = ph / stance
                sweep = -1.0 + 2.0 * s
                lift = 0.0
            else:  # swing: leg returns forward and is lifted
                s = (ph - stance) / swing
                sweep = math.cos(math.pi * s)
                lift = math.sin(math.pi * s)
            sway = side * a_abd * math.sin(2 * math.pi * ph)
            if hip is not None:
                target[hip] = info.rest[hip] + off + a_hip * sweep
                if knee is not None:
                    flex = -1.0 if info.rest[knee] <= 0 else 1.0  # direction of more flexion
                    target[knee] = info.rest[knee] + flex * (crouch + a_knee * lift)
                if abd is not None and a_abd:
                    target[abd] = info.rest[abd] + sway
            else:  # two-motor leg: the knee sweeps, abduction lifts the hoof outward
                if knee is not None:
                    target[knee] = info.rest[knee] + elbow_off + a_elbow * sweep
                if abd is not None:
                    target[abd] = info.rest[abd] + sway + side * a_lift * lift
        return target
