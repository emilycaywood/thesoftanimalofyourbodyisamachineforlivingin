"""The feral calf's own movements, as motion primitives for interpretation (ADR-085).

Each balances on the body by construction, has a few parameters and declares
where it may be left or entered (every hoof down):

* ``stand``: standing, optionally crouched (a pose with every hoof planted);
* ``weight_shift``: the body moved over three hooves and back (a pose solved
  with every hoof planted and the centre of mass toward the tripod);
* ``step``: the same, with the free hoof lifted and put back while the body is
  over the tripod;
* ``walk``: the statically stable lateral-sequence walk of ``feral_motion``;
* ``trot``: its trot (diagonal pairs, balanced dynamically, by timing);
* ``turn``: the walk with the left and right legs sweeping differently (turning
  in place when the stride is 0);
* ``lie_rise``: lying down and rising (hind end first).

Units: s, deg, mm.
"""

from __future__ import annotations

import functools
import hashlib
from typing import Any, Literal

from pydantic import BaseModel

from calflab.plugins import MotionPrimitive, VectorDim, register
from calflab.schema import P

_LIFT = {"hind_lift_stifle": 10.0, "hind_lift_hock": 18.0, "front_lift_carpus": 30.0, "front_lift_shoulder": -12.0}


def _spec_key(spec: Any) -> str:
    return hashlib.sha1(spec.model_dump_json().encode("utf-8")).hexdigest()


_SPECS: dict[str, Any] = {}


@functools.lru_cache(maxsize=256)
def _pose(key: str, free: str | None, shift: float, crouch: float) -> dict[str, Any]:
    from calflab.behave.shift_design import design_pose
    from calflab.components import library

    return design_pose(_SPECS[key], library(), free, shift, crouch)


def designed_pose(spec: Any, free: str | None, shift: float, crouch_mm: float) -> dict[str, Any]:
    """The planted pose (cached per body, shift to 0.01, crouch to 1 mm)."""
    key = _spec_key(spec)
    _SPECS[key] = spec
    return _pose(key, free, round(float(shift), 2), round(float(crouch_mm), 0))


def _fits_feral(spec: Any) -> bool:
    return any(j.id.endswith((".stifle", ".shoulder")) for j in spec.joints)


@register
class StandPrimitive(MotionPrimitive):
    key = "stand"
    label = "Stand"
    description = "Standing still, optionally crouched: every hoof planted, the centre of mass over the middle."
    behaviours = ("stand",)
    balance = "Every hoof stays on its standing place; the centre of mass stays over the middle of the four."

    class Params(BaseModel):
        crouch_mm: float = P(0.0, unit="mm", ge=0.0, le=60.0, step=1.0, desc="Trunk lowered by this much.")
        settle_s: float = P(1.0, unit="s", ge=0.2, le=5.0, step=0.1, desc="Time to settle into the pose.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("crouch_mm", 0.0, 40.0)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        pose = designed_pose(spec, None, 0.0, p.crouch_mm) if p.crouch_mm > 0 else {"offsets_deg": {}}  # type: ignore[attr-defined]
        return "weight_shift", {"offsets": pose["offsets_deg"], "shift_s": p.settle_s, "hold_s": -1.0,  # type: ignore[attr-defined]
                                "back_s": 1.0}

    def period_s(self) -> float:
        return 1.0

    def safe_phases(self) -> list[tuple[float, float]]:
        return [(0.0, 1.0)]


class _ShiftParams(BaseModel):
    leg: Literal["hl", "hr", "fl", "fr"] = P("hr", desc="The hoof the weight moves off (the other three carry it).")
    shift: float = P(0.5, ge=0.0, le=1.0, step=0.05,
                     desc="How far the centre of mass moves toward the middle of the other three hooves (1 = there).")
    shift_s: float = P(1.0, unit="s", ge=0.2, le=6.0, step=0.1, desc="Time over.")
    hold_s: float = P(0.8, unit="s", ge=0.0, le=6.0, step=0.1, desc="Time held over the three.")
    back_s: float = P(1.0, unit="s", ge=0.2, le=6.0, step=0.1, desc="Time back.")


@register
class WeightShiftPrimitive(MotionPrimitive):
    key = "weight_shift"
    label = "Weight shift"
    description = "The body moved over three hooves and back, every hoof planted (a pose solved over them)."
    behaviours = ("weight_shift", "stand")
    balance = ("Every hoof stays planted; the centre of mass moves toward the middle of three of them, inside "
               "their triangle (solved, not assumed).")
    one_shot = True

    Params = _ShiftParams

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("shift", 0.1, 1.0), VectorDim("shift_s", 0.3, 4.0), VectorDim("hold_s", 0.0, 3.0)]

    def design(self, spec: Any) -> dict[str, Any]:
        p = self.params
        return designed_pose(spec, p.leg, p.shift, 0.0)  # type: ignore[attr-defined]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        pose = self.design(spec)
        return "weight_shift", {"offsets": pose["offsets_deg"], "shift_s": p.shift_s, "hold_s": p.hold_s,  # type: ignore[attr-defined]
                                "back_s": p.back_s}  # type: ignore[attr-defined]

    def period_s(self) -> float:
        p = self.params
        return float(p.shift_s + p.hold_s + p.back_s)  # type: ignore[attr-defined]

    def safe_phases(self) -> list[tuple[float, float]]:
        return [(0.0, 0.02), (0.98, 1.0)]


@register
class StepPrimitive(WeightShiftPrimitive):
    key = "step"
    label = "Step"
    description = ("The body moved over three hooves, the fourth lifted and put back down, and back: a step in "
                   "place.")
    behaviours = ("step", "weight_shift")
    balance = ("The free hoof lifts only while the centre of mass is over the other three (solved with every hoof "
               "planted first).")

    class Params(_ShiftParams):
        shift: float = P(0.8, ge=0.0, le=1.0, step=0.05,
                         desc="How far the centre of mass moves toward the middle of the other three hooves.")
        lift_deg: float = P(15.0, unit="deg", ge=0.0, le=45.0, step=1.0,
                            desc="How far the free leg folds (stifle or carpus; hock 1.8x, shoulder -0.4x).")
        lift_share: float = P(0.6, ge=0.2, le=1.0, step=0.05, desc="Share of the hold the hoof is up.")

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("shift", 0.5, 1.0), VectorDim("shift_s", 0.3, 3.0), VectorDim("hold_s", 0.3, 3.0),
                VectorDim("lift_deg", 5.0, 35.0)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        from calflab.behave.shift_design import lift_offsets

        key, params = super().controller(spec, lib)
        p = self.params
        params.update(lift=lift_offsets(spec, p.leg, p.lift_deg), lift_share=p.lift_share)  # type: ignore[attr-defined]
        return key, params


class _GaitParams(BaseModel):
    cycle_s: float = P(4.0, unit="s", ge=1.0, le=12.0, step=0.1, desc="One cycle (each leg steps once).")
    stride: float = P(1.0, ge=0.0, le=2.0, step=0.05, desc="Fore-aft sweep, times the walk's.")
    lift: float = P(1.0, ge=0.3, le=2.0, step=0.05, desc="Hoof lift, times the walk's.")
    sway: float = P(3.0, unit="deg", ge=0.0, le=8.0, step=0.1, desc="Hind ab/ad sway over the supporting legs.")


def _walk_params(cycle_s: float, stride: float, lift: float, sway: float, turn: float = 0.0) -> dict[str, Any]:
    out: dict[str, Any] = {"mode": "walk", "cycle_s": cycle_s, "sway": sway, "stride": stride, "turn": turn}
    out.update({k: v * lift for k, v in _LIFT.items()})
    return out


def _walk_safe(sw: float) -> list[tuple[float, float]]:
    """Every hoof down in the lateral-sequence walk: after each quarter's swing, until the next."""
    return [(round(k * 0.25 + sw, 4), round((k + 1) * 0.25, 4)) for k in range(4)]


@register
class WalkPrimitive(MotionPrimitive):
    key = "walk"
    label = "Walk"
    description = "The statically stable lateral-sequence walk: one hoof up at a time, the body swayed over the rest."
    behaviours = ("walk", "turn", "step")
    balance = "One hoof up at a time, the body swayed over the three supporting hooves before each lift."

    Params = _GaitParams

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("cycle_s", 2.0, 8.0), VectorDim("stride", 0.3, 2.0), VectorDim("lift", 0.5, 1.6),
                VectorDim("sway", 0.0, 6.0)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        return "feral_motion", _walk_params(p.cycle_s, p.stride, p.lift, p.sway)  # type: ignore[attr-defined]

    def period_s(self) -> float:
        return float(self.params.cycle_s)  # type: ignore[attr-defined]

    def phase_offset_s(self) -> float:
        return 1.5  # feral_motion's ramp

    def safe_phases(self) -> list[tuple[float, float]]:
        return _walk_safe(0.15)


@register
class TurnPrimitive(MotionPrimitive):
    key = "turn"
    label = "Turn"
    description = ("The walk with the left and right legs sweeping differently: turns as it walks, or in place "
                   "with stride 0.")
    behaviours = ("turn", "walk")
    balance = "The walk's: one hoof up at a time over the other three; only the fore-aft sweeps differ by side."

    class Params(_GaitParams):
        stride: float = P(0.2, ge=0.0, le=2.0, step=0.05, desc="Forward sweep, times the walk's (0 = in place).")
        turn: float = P(0.8, ge=-1.5, le=1.5, step=0.05, desc="Sweep difference between the sides: + left, - right.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("cycle_s", 2.0, 8.0), VectorDim("stride", 0.0, 1.0), VectorDim("turn", -1.5, 1.5),
                VectorDim("lift", 0.5, 1.6)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        return "feral_motion", _walk_params(p.cycle_s, p.stride, p.lift, p.sway, p.turn)  # type: ignore[attr-defined]

    def period_s(self) -> float:
        return float(self.params.cycle_s)  # type: ignore[attr-defined]

    def phase_offset_s(self) -> float:
        return 1.5

    def safe_phases(self) -> list[tuple[float, float]]:
        return _walk_safe(0.15)


@register
class TrotPrimitive(MotionPrimitive):
    key = "trot"
    label = "Trot"
    description = "Diagonal pairs swinging together, balanced dynamically (by timing), with IMU roll feedback."
    behaviours = ("other", "walk", "turn")
    balance = ("Dynamic: each diagonal pair carries the body for half a cycle; the hind ab/ad push against the "
               "trunk's roll (IMU feedback).")

    class Params(BaseModel):
        cycle_s: float = P(0.6, unit="s", ge=0.4, le=3.0, step=0.05, desc="One cycle (each pair steps once).")
        stride: float = P(2.0, ge=0.0, le=5.0, step=0.1, desc="Fore-aft sweep, times the walk's.")
        lift: float = P(0.3, ge=0.0, le=2.0, step=0.05, desc="Hoof lift, times the walk's.")
        turn: float = P(0.0, ge=-1.0, le=1.0, step=0.05, desc="Sweep difference between the sides: + left.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("cycle_s", 0.45, 1.5), VectorDim("stride", 0.3, 3.0), VectorDim("lift", 0.1, 1.0),
                VectorDim("turn", -1.0, 1.0)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        return "feral_motion", {"mode": "trot", "trot_cycle_s": p.cycle_s, "trot_sweep_scale": p.stride,  # type: ignore[attr-defined]
                                "trot_lift_scale": p.lift, "turn": p.turn}  # type: ignore[attr-defined]

    def period_s(self) -> float:
        return float(self.params.cycle_s)  # type: ignore[attr-defined]

    def warmup_s(self) -> float:
        return 1.5  # feral_motion's ramp scales the trot in from standing

    def safe_phases(self) -> list[tuple[float, float]]:
        sw = 0.45  # feral_motion's trot_swing: double support after each pair's swing
        return [(sw, 0.5), (0.5 + sw, 1.0)]


@register
class LieRisePrimitive(MotionPrimitive):
    key = "lie_rise"
    label = "Lie down and rise"
    description = "Kneel on the carpi, lie down, hold, rise hind end first, then the front from kneeling."
    behaviours = ("other",)
    balance = "Quasi-static: the body is lowered and raised over at least three supports (hooves, carpi, belly)."
    one_shot = True

    class Params(BaseModel):
        phase_s: float = P(2.0, unit="s", ge=0.5, le=8.0, step=0.1, desc="Time for each move.")
        hold_s: float = P(1.5, unit="s", ge=0.0, le=10.0, step=0.1, desc="Time lying still.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return _fits_feral(spec)

    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return [VectorDim("phase_s", 1.0, 6.0), VectorDim("hold_s", 0.0, 5.0)]

    def controller(self, spec: Any, lib: Any) -> tuple[str, dict[str, Any]]:
        p = self.params
        return "feral_motion", {"mode": "lie_rise", "phase_s": p.phase_s, "hold_s": p.hold_s}  # type: ignore[attr-defined]

    def period_s(self) -> float:
        p = self.params
        return float(5 * p.phase_s + p.hold_s)  # type: ignore[attr-defined]

    def safe_phases(self) -> list[tuple[float, float]]:
        return [(0.0, 0.0), (1.0, 1.0)]
