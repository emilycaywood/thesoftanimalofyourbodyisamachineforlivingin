"""Poses played over planted hooves: a weight shift, a step, a held crouch (ADR-085).

The poses come from :func:`calflab.behave.shift_design.design_pose` (all four
hooves planted, the centre of mass inside the tripod) and are inlined in the
parameters by the motion primitive that uses this controller, so the
controller itself does no kinematics. One cycle:

* ``shift_s``: from standing into ``offsets`` (a cosine ramp);
* ``hold_s``: held; with ``lift`` given, the free leg folds and unfolds in the
  middle ``lift_share`` of the hold (a sine bump): a step on three hooves;
* ``back_s``: back to standing.

With ``loop`` the cycle repeats; otherwise the body stays standing after it
(``hold_s`` negative = hold the pose for ever: a crouch or a stand).
Commanded joint speed stays under ``speed_fraction`` of each servo's speed at
its joint. Units: s, deg.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.plugins import ControlInfo, Controller, Observation, register
from calflab.schema import P


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


@register
class WeightShiftController(Controller):
    """Shift the body over three hooves and back; optionally lift the fourth (a step)."""

    key = "weight_shift"
    label = "Weight shift / step"
    description = ("Moves the body into a pose designed with every hoof planted and the centre of mass over three "
                   "hooves, holds it (optionally lifting the free hoof: a step), and back.")
    version = "1"

    class Params(BaseModel):
        offsets: dict[str, float] = P(default_factory=dict, ui="json",
                                      desc="Joint angles (deg, relative to standing) of the shifted pose; filled in "
                                           "by the motion primitive.")
        lift: dict[str, float] = P(default_factory=dict, ui="json",
                                   desc="Extra joint angles (deg) of the free leg at the top of its lift (a step).")
        shift_s: float = P(1.0, unit="s", ge=0.1, le=10.0, step=0.1, desc="Time into the shifted pose.")
        hold_s: float = P(1.0, unit="s", ge=-1.0, le=20.0, step=0.1, desc="Time held (negative: for ever).")
        back_s: float = P(1.0, unit="s", ge=0.1, le=10.0, step=0.1, desc="Time back to standing.")
        lift_share: float = P(0.6, ge=0.1, le=1.0, step=0.05, desc="Share of the hold the free hoof is up.")
        loop: bool = P(False, desc="Repeat the cycle.")
        speed_fraction: float = P(0.9, ge=0.0, le=1.0, step=0.05,
                                  desc="Commanded joint speed kept under this fraction of each servo's speed.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return bool(spec.actuators)

    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        super().reset(info, seed)
        self.prev: np.ndarray | None = None
        self.idx = {jid: i for i, jid in enumerate(info.joint_ids)}

    def period_s(self) -> float:
        p = self.params
        return float(p.shift_s + max(0.0, p.hold_s) + p.back_s)  # type: ignore[attr-defined]

    def pose_at(self, t: float) -> dict[str, float]:
        p = self.params
        hold = float(p.hold_s)  # type: ignore[attr-defined]
        T = self.period_s()
        if p.loop and hold >= 0 and T > 0:  # type: ignore[attr-defined]
            t = t % T
        s0, s1 = float(p.shift_s), float(p.shift_s) + max(0.0, hold)  # type: ignore[attr-defined]
        if t < s0:
            w = _smooth(t / s0)
        elif hold < 0 or t < s1:
            w = 1.0
        else:
            w = 1.0 - _smooth((t - s1) / float(p.back_s))  # type: ignore[attr-defined]
        out = {j: w * v for j, v in p.offsets.items()}  # type: ignore[attr-defined]
        if p.lift and hold > 0 and s0 <= t < s1:  # type: ignore[attr-defined]
            share = float(p.lift_share)  # type: ignore[attr-defined]
            a = s0 + 0.5 * (1 - share) * hold
            x = (t - a) / (share * hold)
            if 0.0 <= x <= 1.0:
                bump = math.sin(math.pi * x)
                for j, v in p.lift.items():  # type: ignore[attr-defined]
                    out[j] = out.get(j, 0.0) + bump * v
        return out

    def act(self, obs: Observation) -> np.ndarray:
        target = self.info.rest.copy()
        for j, deg in self.pose_at(obs.t).items():
            i = self.idx.get(j)
            if i is not None:
                target[i] = self.info.rest[i] + u.deg_to_rad(deg)
        target = np.clip(target, self.info.lo, self.info.hi)
        frac = float(self.params.speed_fraction)  # type: ignore[attr-defined]
        if frac > 0 and self.info.speed_limit is not None:
            prev = self.info.rest if self.prev is None else self.prev
            step = np.asarray(self.info.speed_limit, dtype=float) * frac * self.info.control_dt
            target = prev + np.clip(target - prev, -step, step)
        self.prev = target.copy()
        return target

    def cycle_period_s(self) -> float:
        return max(0.5, self.period_s())
