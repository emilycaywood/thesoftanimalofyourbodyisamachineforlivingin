"""Central pattern generator gait controller for the calf's 3-DOF legs.

Each leg has a phase in [0, 1). During stance the hip sweeps the leg backward
at constant rate; during swing it returns forward on a cosine while the knee
flexes to lift the hoof. Gaits differ only in the phase offsets between legs.

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
        frequency: float = P(1.6, unit="Hz", ge=0.4, le=3.5, step=0.05, desc="Stride frequency.")
        hip_amplitude: float = P(14.0, unit="deg", ge=0, le=40, step=0.5, desc="Half of the hip sweep.")
        knee_amplitude: float = P(24.0, unit="deg", ge=0, le=60, step=0.5, desc="Extra knee flexion during swing.")
        swing_fraction: float = P(0.4, ge=0.2, le=0.6, step=0.01, desc="Fraction of the stride spent in swing.")
        hip_offset: float = P(0.0, unit="deg", ge=-20, le=20, step=0.5, desc="Constant hip bias (positive = legs further back).")
        crouch: float = P(0.0, unit="deg", ge=-15, le=30, step=0.5, desc="Extra knee flexion in stance.")
        abduction_amplitude: float = P(0.0, unit="deg", ge=0, le=15, step=0.5, desc="Lateral sway of the hips.")
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
        ]

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
        off = u.deg_to_rad(p.hip_offset) * ramp  # type: ignore[attr-defined]
        crouch = u.deg_to_rad(p.crouch) * ramp  # type: ignore[attr-defined]
        swing = float(p.swing_fraction)  # type: ignore[attr-defined]
        stance = 1.0 - swing
        base = obs.t * p.frequency  # type: ignore[attr-defined]
        for abd, hip, knee, phase, side in self._legs:
            ph = (base + phase) % 1.0
            if ph < stance:  # stance: leg sweeps back (hip angle increases)
                s = ph / stance
                hip_delta = -a_hip + 2.0 * a_hip * s
                lift = 0.0
            else:  # swing: leg returns forward, knee flexes
                s = (ph - stance) / swing
                hip_delta = a_hip * math.cos(math.pi * s)
                lift = math.sin(math.pi * s)
            if hip is not None:
                target[hip] = info.rest[hip] + off + hip_delta
            if knee is not None:
                flex = -1.0 if info.rest[knee] <= 0 else 1.0  # direction of more flexion
                target[knee] = info.rest[knee] + flex * (crouch + a_knee * lift)
            if abd is not None and a_abd:
                target[abd] = info.rest[abd] + side * a_abd * math.sin(2 * math.pi * ph)
        return target
