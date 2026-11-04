"""Scripted motions for the final feral calf (ADR-069): quiet standing, a slow
walk and lying down then rising.

Joints are found by their IDs (``joint.<leg>.{hip_abd,stifle,hock}`` for the
hind legs, ``joint.<leg>.{shoulder,carpus}`` for the front legs). Angles are
relative to the standing pose (0); positive is flexion at stifle, hock and
carpus, a backward swing at the shoulder and abduction at the hip.

* ``stand``: holds the standing pose.
* ``walk``: a statically stable lateral-sequence walk (hind left, front left,
  hind right, front right), one leg in the air at a time. In swing a leg lifts
  (hind: stifle and hock flex together; front: carpus flexes, shoulder brings
  the hoof forward again) and moves forward; in stance it sweeps back. The hind
  ab/ad joints sway the body over the three supporting legs.
* ``trot``: diagonal pairs (hind left + front right, then hind right + front
  left) swing together, half a cycle apart, with the walk's sweep and lift
  scaled up; no body shift (the two hooves on the ground carry it). A
  faster, dynamically balanced gait.
* ``lie_rise``: kneel on the front carpi, fold the hind legs and lie down,
  hold, then rise the way cattle do: hind end first, then the front from
  kneeling (both front legs reach forward and plant their hooves, then push
  the chest up).

The sweep and lift numbers are joint angles chosen for the default body: a
hind sweep of 1.6 deg at the stifle against 3.8 deg at the hock moves the hoof
about 30 mm fore and aft with no lift; they are starting points, not tuned.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.plugins import ControlInfo, Controller, Observation, VectorDim, register
from calflab.schema import P

HIND = ("hl", "hr")
FRONT = ("fl", "fr")
SEQUENCE = {"hl": 0.0, "fl": 0.25, "hr": 0.5, "fr": 0.75}
#: trot: diagonal pairs move together (hind left with front right), half a cycle apart
DIAGONALS = {"hl": 0.0, "fr": 0.0, "hr": 0.5, "fl": 0.5}
SIDE = {"fl": 1.0, "fr": -1.0, "hl": 1.0, "hr": -1.0}


def smooth(x: float) -> float:
    """0 -> 1 with zero slope at both ends."""
    x = min(1.0, max(0.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


@register
class FeralMotionController(Controller):
    """Stand, slow walk, or lie down and rise, for the feral calf's joint layout."""

    key = "feral_motion"
    label = "Feral calf motions"
    description = "Quiet standing, a slow statically stable walk, a trot, or lying down and rising (hind end first)."
    version = "1"

    class Params(BaseModel):
        mode: Literal["stand", "walk", "trot", "lie_rise"] = P("walk", desc="Which motion to play.")
        cycle_s: float = P(4.0, unit="s", ge=1.0, le=12.0, step=0.1, desc="Walk: one full gait cycle (all four legs step once).")
        swing_fraction: float = P(0.15, ge=0.1, le=0.25, step=0.01, desc="Walk: fraction of the cycle each leg is in the air (<= 0.25: one leg at a time).")
        hind_sweep_stifle: float = P(-1.6, unit="deg", ge=-20, le=20, step=0.1, desc="Walk: stifle angle that moves the hind hoof forward at the end of swing (half sweep).")
        hind_sweep_hock: float = P(3.8, unit="deg", ge=-20, le=20, step=0.1, desc="Walk: hock angle that moves the hind hoof forward at the end of swing (half sweep).")
        hind_lift_stifle: float = P(10.0, unit="deg", ge=0, le=40, step=0.5, desc="Walk: extra stifle flexion at mid-swing (lifts the hind hoof).")
        hind_lift_hock: float = P(18.0, unit="deg", ge=0, le=60, step=0.5, desc="Walk: extra hock flexion at mid-swing.")
        front_sweep_shoulder: float = P(-3.0, unit="deg", ge=-20, le=20, step=0.1, desc="Walk: shoulder angle that moves the front hoof forward at the end of swing (half sweep).")
        front_lift_carpus: float = P(30.0, unit="deg", ge=0, le=90, step=0.5, desc="Walk: carpus flexion at mid-swing (folds the front hoof up).")
        front_lift_shoulder: float = P(-12.0, unit="deg", ge=-40, le=10, step=0.5, desc="Walk: shoulder angle at mid-swing that keeps the folded hoof under the body.")
        sway: float = P(3.0, unit="deg", ge=0, le=15, step=0.1, desc="Walk: hind ab/ad sway that moves the body over the supporting legs.")
        trot_cycle_s: float = P(0.6, unit="s", ge=0.4, le=3.0, step=0.05, desc="Trot: one full cycle (each diagonal pair steps once).")
        trot_swing: float = P(0.45, ge=0.2, le=0.5, step=0.01, desc="Trot: fraction of the cycle each pair is in the air.")
        trot_sweep_scale: float = P(2.0, ge=0.0, le=5.0, step=0.1, desc="Trot: the walk's fore-aft sweep times this (longer strides).")
        trot_lift_scale: float = P(0.3, ge=0.0, le=2.0, step=0.05, desc="Trot: the walk's lift times this.")
        roll_gain: float = P(
            0.5, ge=0.0, le=5.0, step=0.05,
            desc="Trot: hind ab/ad turned by this many degrees per degree of trunk roll (from the IMU), against the roll. "
                 "0 = open loop.",
        )
        pitch_gain: float = P(
            0.0, ge=0.0, le=5.0, step=0.05,
            desc="Trot: shoulders and stifles swung by this many degrees per degree of trunk pitch (IMU), to catch a "
                 "nose-down or nose-up tip. 0 = open loop.",
        )
        # lying down and rising
        kneel_shoulder: float = P(-20.0, unit="deg", ge=-60, le=60, step=0.5, desc="Lie/rise: shoulder angle kneeling on the carpi.")
        kneel_carpus: float = P(110.0, unit="deg", ge=0, le=130, step=0.5, desc="Lie/rise: carpus flexion kneeling.")
        lie_stifle: float = P(75.0, unit="deg", ge=0, le=80, step=0.5, desc="Lie/rise: stifle flexion lying down.")
        lie_hock: float = P(75.0, unit="deg", ge=0, le=80, step=0.5, desc="Lie/rise: hock flexion lying down.")
        lie_shoulder: float = P(-40.0, unit="deg", ge=-60, le=60, step=0.5, desc="Lie/rise: shoulder angle lying down.")
        lie_carpus: float = P(125.0, unit="deg", ge=0, le=130, step=0.5, desc="Lie/rise: carpus flexion lying down.")
        reach_shoulder: float = P(-45.0, unit="deg", ge=-60, le=60, step=0.5, desc="Lie/rise: shoulder angle as each front leg reaches forward from kneeling to plant its hoof.")
        reach_carpus: float = P(50.0, unit="deg", ge=0, le=130, step=0.5, desc="Lie/rise: carpus flexion while reaching forward from kneeling.")
        phase_s: float = P(2.0, unit="s", ge=0.5, le=8.0, step=0.1, desc="Lie/rise: time for each move (kneel, lie, rise hind, reach forward, rise front).")
        hold_s: float = P(1.5, unit="s", ge=0.0, le=10.0, step=0.1, desc="Lie/rise: time lying still before rising.")
        speed_fraction: float = P(
            0.9, ge=0.0, le=1.0, step=0.05,
            desc="Commanded joint speed kept under this fraction of each servo's no-load speed at its joint (a 2:1 "
                 "belt halves it). The simulator limits torque, not speed, so without this a gait can ask more than "
                 "the servos turn. 0 = no limit.",
        )
        ramp: float = P(1.5, unit="s", ge=0.0, le=3.0, step=0.1, desc="Walk: time to ramp in from standing (the body shifts over before the first step).")
        stride: float = P(
            1.0, ge=-1.0, le=2.0, step=0.05,
            desc="Walk and trot: every leg's fore-aft sweep times this (1 = as set; 0 = stepping in place; negative "
                 "= backward). ADR-085.")
        turn: float = P(
            0.0, ge=-1.5, le=1.5, step=0.05,
            desc="Walk and trot: the right legs sweep (stride + turn) and the left legs (stride - turn) times as far: "
                 "+ turns left, - right. With stride 0 the body turns in place. ADR-085.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        """These motions drive the feral calf's joints (stifle, hock, shoulder, carpus)."""
        return any(j.id.endswith((".stifle", ".shoulder")) for j in spec.joints)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        """The walk's numbers, for CMA-ES (evolution's inner loop, ADR-070). Ranges keep one leg in the air at a
        time and every joint near its standing angle; the mode stays as set."""
        return [
            VectorDim("cycle_s", 2.5, 8.0),
            VectorDim("swing_fraction", 0.1, 0.22),
            VectorDim("sway", 0.0, 6.0),
            VectorDim("hind_sweep_stifle", -6.0, 0.0),
            VectorDim("hind_sweep_hock", 0.0, 10.0),
            VectorDim("hind_lift_stifle", 4.0, 25.0),
            VectorDim("hind_lift_hock", 8.0, 40.0),
            VectorDim("front_sweep_shoulder", -8.0, 0.0),
            VectorDim("front_lift_carpus", 10.0, 60.0),
            VectorDim("front_lift_shoulder", -25.0, 0.0),
        ]

    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        super().reset(info, seed)
        self.prev: np.ndarray | None = None
        self.idx: dict[str, int] = {}
        for i, jid in enumerate(info.joint_ids):
            parts = jid.split(".")
            if len(parts) == 3:
                self.idx[f"{parts[1]}.{parts[2]}"] = i

    def _set(self, target: np.ndarray, name: str, deg: float) -> None:
        i = self.idx.get(name)
        if i is not None:
            target[i] = self.info.rest[i] + u.deg_to_rad(deg)

    def pose_at(self, t: float) -> dict[str, float]:
        """Joint angles (deg, relative to standing) at time ``t`` (s)."""
        p = self.params
        if p.mode == "stand":  # type: ignore[attr-defined]
            return {}
        if p.mode == "lie_rise":  # type: ignore[attr-defined]
            return self._lie_rise(t)
        if p.mode == "trot":  # type: ignore[attr-defined]
            return self._trot(t)
        return self._walk(t)

    def _side(self, leg: str) -> float:
        """The sweep factor of this leg: stride, minus turn on the left, plus turn on the right (ADR-085). With the
        defaults (1, 0) it is exactly 1.0, so every earlier rollout is unchanged."""
        p = self.params
        return float(p.stride) - SIDE[leg] * float(p.turn)  # type: ignore[attr-defined]

    def _legs(self, ph: float, sw: float, leg: str, sweep_k: float, lift_k: float, ramp: float) -> dict[str, float]:
        """One leg's joint offsets (deg) at phase ``ph`` of its own cycle: swing first (lift and bring forward),
        then stance (sweep back)."""
        p = self.params
        if ph < sw:
            s = ph / sw
            sweep, lift = -math.cos(math.pi * s), math.sin(math.pi * s)
        else:
            sweep, lift = 1.0 - 2.0 * (ph - sw) / (1.0 - sw), 0.0
        sweep = sweep * self._side(leg)
        sweep, lift = sweep * sweep_k * ramp, lift * lift_k * ramp
        if leg in HIND:
            return {f"{leg}.stifle": sweep * p.hind_sweep_stifle + lift * p.hind_lift_stifle,  # type: ignore[attr-defined]
                    f"{leg}.hock": sweep * p.hind_sweep_hock + lift * p.hind_lift_hock}  # type: ignore[attr-defined]
        return {f"{leg}.shoulder": sweep * p.front_sweep_shoulder + lift * p.front_lift_shoulder,  # type: ignore[attr-defined]
                f"{leg}.carpus": lift * p.front_lift_carpus}  # type: ignore[attr-defined]

    def _trot(self, t: float) -> dict[str, float]:
        p = self.params
        T, sw = p.trot_cycle_s, p.trot_swing  # type: ignore[attr-defined]
        ramp = smooth(t / p.ramp) if p.ramp > 0 else 1.0  # type: ignore[attr-defined]
        out: dict[str, float] = {}
        for leg, off in DIAGONALS.items():
            out.update(self._legs(((t / T) - off) % 1.0, sw, leg, p.trot_sweep_scale, p.trot_lift_scale, ramp))  # type: ignore[attr-defined]
        return out

    def _walk(self, t: float) -> dict[str, float]:
        p = self.params
        T, sw = p.cycle_s, p.swing_fraction  # type: ignore[attr-defined]
        ramp = smooth(t / p.ramp) if p.ramp > 0 else 1.0  # type: ignore[attr-defined]
        out: dict[str, float] = {}
        cyc = ((t - p.ramp) / T) % 1.0 if t >= p.ramp else 0.0  # type: ignore[attr-defined]
        for leg, off in SEQUENCE.items():
            ph = (cyc - off) % 1.0
            if t < p.ramp:  # type: ignore[attr-defined]
                ph = sw + (1.0 - sw) * 0.5  # mid-stance while the body shifts over
            if ph < sw:  # swing: lift and bring forward (sweep -1 -> +1)
                s = ph / sw
                sweep = -math.cos(math.pi * s)
                lift = math.sin(math.pi * s)
            else:  # stance: sweep back (+1 -> -1)
                s = (ph - sw) / (1.0 - sw)
                sweep = 1.0 - 2.0 * s
                lift = 0.0
            sweep = sweep * self._side(leg)
            if leg in HIND:
                out[f"{leg}.stifle"] = ramp * (sweep * p.hind_sweep_stifle + lift * p.hind_lift_stifle)  # type: ignore[attr-defined]
                out[f"{leg}.hock"] = ramp * (sweep * p.hind_sweep_hock + lift * p.hind_lift_hock)  # type: ignore[attr-defined]
            else:
                out[f"{leg}.shoulder"] = ramp * (sweep * p.front_sweep_shoulder + lift * p.front_lift_shoulder)  # type: ignore[attr-defined]
                out[f"{leg}.carpus"] = ramp * lift * p.front_lift_carpus  # type: ignore[attr-defined]
        # the left legs step in the first half of the cycle, the right legs in the second: the body is shifted
        # right (left) over the three supporting hooves before and during those steps, moving across in the
        # gaps between them (a statically stable crawl needs the centre of mass inside the support triangle)
        a0, a1 = 0.25 + sw, 0.5  # shift right -> left between the second left step and the first right step
        b0, b1 = 0.75 + sw, 1.0  # left -> right after the second right step
        if cyc < a0:
            lean = 1.0
        elif cyc < a1:
            lean = 1.0 - 2.0 * smooth((cyc - a0) / (a1 - a0))
        elif cyc < b0:
            lean = -1.0
        else:
            lean = -1.0 + 2.0 * smooth((cyc - b0) / (b1 - b0))
        for leg in HIND:
            out[f"{leg}.hip_abd"] = ramp * SIDE[leg] * p.sway * lean  # type: ignore[attr-defined]
        return out

    def _lie_rise(self, t: float) -> dict[str, float]:
        p = self.params
        stand: dict[str, float] = {}
        kneel = {**{f"{k}.shoulder": p.kneel_shoulder for k in FRONT}, **{f"{k}.carpus": p.kneel_carpus for k in FRONT}}  # type: ignore[attr-defined]
        lie = {**{f"{k}.shoulder": p.lie_shoulder for k in FRONT}, **{f"{k}.carpus": p.lie_carpus for k in FRONT},  # type: ignore[attr-defined]
               **{f"{k}.stifle": p.lie_stifle for k in HIND}, **{f"{k}.hock": p.lie_hock for k in HIND}}  # type: ignore[attr-defined]
        hind_up = dict(kneel)  # hind legs straight, still kneeling in front
        # rising in front: both legs reach forward together and plant their hooves ahead, then push the chest up
        # (one leg at a time tips this body over: it has no front ab/ad to shift its weight)
        reach = {**kneel, **{f"{k}.shoulder": p.reach_shoulder for k in FRONT},  # type: ignore[attr-defined]
                 **{f"{k}.carpus": p.reach_carpus for k in FRONT}}  # type: ignore[attr-defined]
        frames = [stand, kneel, lie, lie, hind_up, reach, stand]
        d, hold = p.phase_s, p.hold_s  # type: ignore[attr-defined]
        times = [0.0, d, 2 * d, 2 * d + hold, 3 * d + hold, 4 * d + hold, 5 * d + hold]
        if t >= times[-1]:
            return dict(frames[-1])
        i = max(k for k in range(len(times)) if times[k] <= t)
        a, b = frames[i], frames[i + 1]
        span = times[i + 1] - times[i]
        w = smooth((t - times[i]) / span) if span > 0 else 1.0
        keys = set(a) | set(b)
        return {k: (1 - w) * a.get(k, 0.0) + w * b.get(k, 0.0) for k in keys}

    def act(self, obs: Observation) -> np.ndarray:
        target = self.info.rest.copy()
        pose = self.pose_at(obs.t)
        p = self.params
        if p.mode == "trot" and (p.roll_gain or p.pitch_gain):  # type: ignore[attr-defined]
            w, x, y, z = (float(v) for v in obs.trunk_quat)
            roll = u.rad_to_deg(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
            pitch = u.rad_to_deg(math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))))
            for leg in HIND:  # positive roll = left side up, tipping right: the right hind leg steps out, the left in
                pose[f"{leg}.hip_abd"] = pose.get(f"{leg}.hip_abd", 0.0) - SIDE[leg] * p.roll_gain * roll  # type: ignore[attr-defined]
            for leg in FRONT:  # nose down (positive pitch): swing the front legs forward under it
                pose[f"{leg}.shoulder"] = pose.get(f"{leg}.shoulder", 0.0) - p.pitch_gain * pitch  # type: ignore[attr-defined]
        for name, deg in pose.items():
            self._set(target, name, deg)
        return self.rate_limit(target)

    def rate_limit(self, target: np.ndarray) -> np.ndarray:
        """Move each commanded angle no faster than ``speed_fraction`` of its servo's speed at the joint."""
        frac = float(self.params.speed_fraction)  # type: ignore[attr-defined]
        lim = self.info.speed_limit
        if frac <= 0 or lim is None:
            return target
        prev = self.info.rest if self.prev is None else self.prev
        step = np.asarray(lim, dtype=float) * frac * self.info.control_dt
        out = prev + np.clip(target - prev, -step, step)
        self.prev = out
        return out

    def cycle_period_s(self) -> float:
        """The window the 'sustained' checks use (one gait cycle)."""
        p = self.params
        return float(p.trot_cycle_s if p.mode == "trot" else p.cycle_s)  # type: ignore[attr-defined]
