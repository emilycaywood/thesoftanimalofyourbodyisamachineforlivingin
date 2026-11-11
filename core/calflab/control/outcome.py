"""One controller family for behaviours defined by their outcome (ADR-110, session R15).

The earlier behaviours were motions written for the light working body (``feral_motion``'s trot, walk and
lie_rise, the R6c/R7 generators). Here a behaviour is a score (``calflab.fitness.outcomes``) and this controller is
the space a per-body search moves in. It is deliberately small and cheap (no learning, a few dozen numbers), so it can
be optimised inside a body search on a CPU:

* **Posture keyframes** ``p1``, ``p2``, ``p3``: joint angles per group (hip ab/ad, stifle, hock, shoulder, carpus;
  the same on both sides), each reached by a smooth move of ``p*_s`` seconds (0 = keyframe not used), then held.
  Standing is one keyframe; pushing is a brace then a lean; lying down is two or three.
* **Rise** (lying down's bonus): after ``hold_s`` the keyframes are played back in reverse to standing, each move
  ``rise_scale`` times as long (0 = stay down).
* **Rhythm** (``gait_amp`` > 0): every leg swings (lift and bring forward) and sweeps back on its own phase. The
  phases of the front-left, hind-right and front-right legs relative to the hind-left leg are free numbers, so a trot,
  pace, bound or walk can emerge; nothing is required. With the phases of a diagonal trot and the amplitudes of
  ``feral_motion``'s trot it plays that trot (``from_feral_trot``), a warm start, not a definition.
* **Reflexes** on the IMU only: trunk roll -> hind ab/ad, trunk pitch -> shoulders and stifles, heading -> a left/right
  stride difference (rhythm only). Foot contact is recorded by the simulator for the footfall pattern but not used:
  a contact reflex would need a phase-reset rule, more numbers to search, and the robot has no foot sensors in the
  model's harness yet (ADR-043).

Angles in degrees relative to the standing pose (0), signs as ``feral_motion``: positive = flexion at stifle, hock and
carpus, a backward swing at the shoulder, abduction at the hip (both sides). Times in s.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.control.feral_motion import FRONT, HIND, SIDE, smooth
from calflab.plugins import ControlInfo, Controller, Observation, VectorDim, register
from calflab.schema import P

#: joint groups of a posture and the legs they act on
GROUPS = {"abd": ("hip_abd", HIND), "stifle": ("stifle", HIND), "hock": ("hock", HIND),
          "shoulder": ("shoulder", FRONT), "carpus": ("carpus", FRONT)}
KEYFRAMES = ("p1", "p2", "p3")
#: commanded posture angles stay this far (deg) inside each joint's range (as lie_rise, ADR-107)
RANGE_CLEARANCE_DEG = 2.0


@register
class OutcomeMotionController(Controller):
    """Posture keyframes, an optional free-phase rhythm and IMU reflexes (ADR-110)."""

    key = "outcome_motion"
    label = "Outcome motion (keyframes + rhythm + reflexes)"
    description = ("Up to three posture keyframes, an optional rhythm whose leg phases are free, and trunk-attitude "
                   "reflexes. The space in which behaviours defined by their outcome are searched per body.")
    version = "1"

    class Params(BaseModel):
        # keyframes
        p1_abd: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 1: hip ab/ad (both sides).")
        p1_stifle: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 1: stifle.")
        p1_hock: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 1: hock.")
        p1_shoulder: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 1: shoulder.")
        p1_carpus: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 1: carpus.")
        p1_s: float = P(0.0, unit="s", ge=0.0, le=10.0, step=0.1, desc="Keyframe 1: time to reach it (0 = not used).")
        p2_abd: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 2: hip ab/ad (both sides).")
        p2_stifle: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 2: stifle.")
        p2_hock: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 2: hock.")
        p2_shoulder: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 2: shoulder.")
        p2_carpus: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 2: carpus.")
        p2_s: float = P(0.0, unit="s", ge=0.0, le=10.0, step=0.1, desc="Keyframe 2: time to reach it (0 = not used).")
        p3_abd: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 3: hip ab/ad (both sides).")
        p3_stifle: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 3: stifle.")
        p3_hock: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 3: hock.")
        p3_shoulder: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 3: shoulder.")
        p3_carpus: float = P(0.0, unit="deg", ge=-60, le=130, step=0.5, desc="Keyframe 3: carpus.")
        p3_s: float = P(0.0, unit="s", ge=0.0, le=40.0, step=0.1,
                        desc="Keyframe 3: time to reach it (0 = not used); long = a slow continuing lean.")
        hold_s: float = P(0.0, unit="s", ge=0.0, le=30.0, step=0.1,
                          desc="Rise: time at the last keyframe before rising (used only with rise_scale > 0).")
        rise_scale: float = P(0.0, ge=0.0, le=4.0, step=0.05,
                              desc="Rise: the keyframes played back in reverse to standing, each move this many times "
                                   "as long as on the way down. 0 = stay at the last keyframe.")
        # rhythm
        gait_amp: float = P(0.0, ge=0.0, le=3.0, step=0.05, desc="Rhythm: overall amplitude (0 = no rhythm).")
        cycle_s: float = P(0.6, unit="s", ge=0.25, le=4.0, step=0.05, desc="Rhythm: one cycle of every leg.")
        swing: float = P(0.45, ge=0.1, le=0.6, step=0.01, desc="Rhythm: fraction of its cycle each leg is in the air.")
        phase_fl: float = P(0.5, ge=0.0, le=1.0, step=0.01, desc="Rhythm: front-left phase after the hind-left (cycles).")
        phase_hr: float = P(0.5, ge=0.0, le=1.0, step=0.01, desc="Rhythm: hind-right phase after the hind-left.")
        phase_fr: float = P(0.0, ge=0.0, le=1.0, step=0.01, desc="Rhythm: front-right phase after the hind-left.")
        sweep_stifle: float = P(-3.2, unit="deg", ge=-30, le=30, step=0.1, desc="Rhythm: stifle half sweep (fore-aft).")
        sweep_hock: float = P(7.6, unit="deg", ge=-30, le=30, step=0.1, desc="Rhythm: hock half sweep.")
        sweep_shoulder: float = P(-6.0, unit="deg", ge=-30, le=30, step=0.1, desc="Rhythm: shoulder half sweep.")
        lift_stifle: float = P(6.0, unit="deg", ge=0, le=60, step=0.5, desc="Rhythm: stifle flexion at mid-swing.")
        lift_hock: float = P(10.8, unit="deg", ge=0, le=60, step=0.5, desc="Rhythm: hock flexion at mid-swing.")
        lift_carpus: float = P(18.0, unit="deg", ge=0, le=90, step=0.5, desc="Rhythm: carpus flexion at mid-swing.")
        lift_shoulder: float = P(-7.2, unit="deg", ge=-40, le=20, step=0.5,
                                 desc="Rhythm: shoulder angle at mid-swing (keeps the folded hoof under the body).")
        abd_sway: float = P(0.0, unit="deg", ge=-15, le=15, step=0.1,
                            desc="Rhythm: hind ab/ad moved with each hind leg's own cycle (+ = out in swing).")
        turn: float = P(0.0, ge=-1.0, le=1.0, step=0.01,
                        desc="Rhythm: right legs sweep (1 + turn), left legs (1 - turn) times as far (+ turns left).")
        ramp_s: float = P(1.5, unit="s", ge=0.0, le=5.0, step=0.1, desc="Rhythm: time to grow from nothing to full.")
        # reflexes
        roll_gain: float = P(0.0, ge=-3.0, le=3.0, step=0.05,
                             desc="Hind ab/ad turned by this many degrees per degree of trunk roll, against it.")
        pitch_gain: float = P(0.0, ge=-3.0, le=3.0, step=0.05,
                              desc="Shoulders swung forward by this many degrees per degree of nose-down pitch.")
        pitch_gain_hind: float = P(0.0, ge=-3.0, le=3.0, step=0.05,
                                   desc="Stifles flexed by this many degrees per degree of nose-down pitch.")
        yaw_gain: float = P(0.0, ge=0.0, le=5.0, step=0.05,
                            desc="Rhythm: turn added per radian of heading away from the start, against it.")
        speed_fraction: float = P(0.9, ge=0.0, le=1.0, step=0.05,
                                  desc="Commanded joint speed kept under this fraction of each servo's no-load speed at "
                                       "its joint (as feral_motion). 0 = no limit.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return any(j.id.endswith((".stifle", ".shoulder")) for j in spec.joints)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        """A standing posture (the smallest useful space); behaviour searches choose their own dims."""
        return [VectorDim("p1_abd", -10.0, 10.0), VectorDim("p1_stifle", -20.0, 40.0),
                VectorDim("p1_hock", -20.0, 40.0), VectorDim("p1_shoulder", -30.0, 30.0),
                VectorDim("p1_carpus", -5.0, 40.0)]

    # ------------------------------------------------------------------ timeline
    def keyframes(self) -> list[tuple[dict[str, float], float]]:
        """(pose by short joint name, time to reach it) for each used keyframe, from standing."""
        p: Any = self.params
        out = []
        for k in KEYFRAMES:
            d = float(getattr(p, f"{k}_s"))
            if d <= 0.0:
                continue
            pose: dict[str, float] = {}
            for g, (joint, legs) in GROUPS.items():
                for leg in legs:
                    pose[f"{leg}.{joint}"] = float(getattr(p, f"{k}_{g}"))
            out.append((pose, d))
        return out

    def timeline(self) -> list[tuple[dict[str, float], float]]:
        """The keyframes, then (with a rise) a hold and the way back up, as (pose, time to reach it)."""
        kf = self.keyframes()
        p: Any = self.params
        if not kf or float(p.rise_scale) <= 0.0:
            return kf
        back = [(kf[i - 1][0] if i > 0 else {}, d * float(p.rise_scale)) for i, (_pose, d) in reversed(list(enumerate(kf)))]
        return [*kf, (kf[-1][0], float(p.hold_s)), *back]

    def length_s(self) -> float:
        return float(sum(d for _p, d in self.timeline()))

    def posture_at(self, t: float) -> dict[str, float]:
        frames: list[dict[str, float]] = [{}]
        times = [0.0]
        for pose, d in self.timeline():
            frames.append(pose)
            times.append(times[-1] + d)
        if t >= times[-1]:
            return dict(frames[-1])
        i = max(k for k in range(len(times)) if times[k] <= t)
        a, b = frames[i], frames[i + 1]
        span = times[i + 1] - times[i]
        w = smooth((t - times[i]) / span) if span > 0 else 1.0
        return {k: (1 - w) * a.get(k, 0.0) + w * b.get(k, 0.0) for k in set(a) | set(b)}

    def _phase(self, leg: str) -> float:
        p: Any = self.params
        return {"hl": 0.0, "fl": float(p.phase_fl), "hr": float(p.phase_hr), "fr": float(p.phase_fr)}[leg]

    def rhythm_at(self, t: float, turn: float) -> dict[str, float]:
        """The rhythm's offsets (deg) at ``t``; ``turn`` is the effective left/right stride difference."""
        p: Any = self.params
        amp = float(p.gait_amp)
        if amp <= 0.0:
            return {}
        ramp = smooth(t / float(p.ramp_s)) if float(p.ramp_s) > 0 else 1.0
        out: dict[str, float] = {}
        for leg in ("hl", "fl", "hr", "fr"):
            ph = ((t / float(p.cycle_s)) - self._phase(leg)) % 1.0
            sw = float(p.swing)
            if ph < sw:
                s = ph / sw
                sweep, lift = -math.cos(math.pi * s), math.sin(math.pi * s)
            else:
                sweep, lift = 1.0 - 2.0 * (ph - sw) / (1.0 - sw), 0.0
            sweep *= (1.0 - SIDE[leg] * turn) * amp * ramp
            lift *= amp * ramp
            if leg in HIND:
                out[f"{leg}.stifle"] = sweep * p.sweep_stifle + lift * p.lift_stifle
                out[f"{leg}.hock"] = sweep * p.sweep_hock + lift * p.lift_hock
                if p.abd_sway:
                    out[f"{leg}.hip_abd"] = lift * p.abd_sway * ramp
            else:
                out[f"{leg}.shoulder"] = sweep * p.sweep_shoulder + lift * p.lift_shoulder
                out[f"{leg}.carpus"] = lift * p.lift_carpus
        return out

    # ------------------------------------------------------------------ control
    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        super().reset(info, seed)
        self.prev: np.ndarray | None = None
        self.idx: dict[str, int] = {}
        for i, jid in enumerate(info.joint_ids):
            parts = jid.split(".")
            if len(parts) == 3:
                self.idx[f"{parts[1]}.{parts[2]}"] = i
        self.yaw0: float | None = None

    def _ranges(self) -> dict[str, tuple[float, float]]:
        info = self.info
        if info.lo is None or info.hi is None:
            return {}
        return {n: (u.rad_to_deg(float(info.lo[i] - info.rest[i])), u.rad_to_deg(float(info.hi[i] - info.rest[i])))
                for n, i in self.idx.items()}

    def act(self, obs: Observation) -> np.ndarray:
        p: Any = self.params
        w, x, y, z = (float(v) for v in obs.trunk_quat)
        roll = u.rad_to_deg(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
        pitch = u.rad_to_deg(math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))))
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        if self.yaw0 is None:
            self.yaw0 = yaw
        dyaw = (yaw - self.yaw0 + math.pi) % (2 * math.pi) - math.pi
        turn = max(-1.0, min(1.0, float(p.turn) - float(p.yaw_gain) * dyaw))
        pose = self.posture_at(obs.t)
        ranges = self._ranges()
        for k, v in pose.items():  # postures stay inside the joint ranges (rhythm and reflexes are clipped by the sim)
            if k in ranges:
                lo, hi = ranges[k]
                pose[k] = min(hi - RANGE_CLEARANCE_DEG, max(lo + RANGE_CLEARANCE_DEG, v))
        for k, v in self.rhythm_at(obs.t, turn).items():
            pose[k] = pose.get(k, 0.0) + v
        if p.roll_gain:
            for leg in HIND:
                pose[f"{leg}.hip_abd"] = pose.get(f"{leg}.hip_abd", 0.0) - SIDE[leg] * p.roll_gain * roll
        if p.pitch_gain:
            for leg in FRONT:
                pose[f"{leg}.shoulder"] = pose.get(f"{leg}.shoulder", 0.0) - p.pitch_gain * pitch
        if p.pitch_gain_hind:
            for leg in HIND:
                pose[f"{leg}.stifle"] = pose.get(f"{leg}.stifle", 0.0) + p.pitch_gain_hind * pitch
        target = self.info.rest.copy()
        for name, deg in pose.items():
            i = self.idx.get(name)
            if i is not None:
                target[i] = self.info.rest[i] + u.deg_to_rad(deg)
        return self._rate_limit(target)

    def _rate_limit(self, target: np.ndarray) -> np.ndarray:
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
        return float(self.params.cycle_s) if float(self.params.gait_amp) > 0 else 2.0  # type: ignore[attr-defined]


def from_feral_trot(cycle_s: float = 0.6, stride: float = 1.0, lift: float = 0.3, swing: float = 0.45,
                    roll_gain: float = 0.5, ramp_s: float = 1.5) -> dict[str, float]:
    """``outcome_motion`` params that play ``feral_motion``'s trot (diagonal pairs; the trot primitive's
    ``cycle_s``/``stride``/``lift`` = ``trot_cycle_s``/``trot_sweep_scale``/``trot_lift_scale``) with its default leg
    numbers. A warm start for the trot search (ADR-110)."""
    from calflab.control.feral_motion import FeralMotionController

    d = FeralMotionController.Params()
    return {"gait_amp": 1.0, "cycle_s": cycle_s, "swing": swing, "phase_fl": 0.5, "phase_hr": 0.5, "phase_fr": 0.0,
            "sweep_stifle": d.hind_sweep_stifle * stride, "sweep_hock": d.hind_sweep_hock * stride,
            "sweep_shoulder": d.front_sweep_shoulder * stride, "lift_stifle": d.hind_lift_stifle * lift,
            "lift_hock": d.hind_lift_hock * lift, "lift_carpus": d.front_lift_carpus * lift,
            "lift_shoulder": d.front_lift_shoulder * lift, "roll_gain": roll_gain, "ramp_s": ramp_s}
