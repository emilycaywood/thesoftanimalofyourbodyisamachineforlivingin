"""Movement that varies below the primitive level (ADR-098).

The ``interpreted`` controller plays each state as a hand-written motion primitive. With a ``variation``
block in its parameters it also varies *within* a movement, each variation bounded so that its extremes are
known and can be played on purpose (coverage, ADR-096/097):

* **posture drift and small noise**: slow random drift of the trunk height (a crouch, never higher than
  standing), the weight over the hooves (lateral and fore-aft) and the head (neck/head joints, if the body has
  any), plus a small faster noise. Each axis is a fixed joint-offset *basis* (deg per unit) solved on the body
  with every hoof planted (:func:`posture_basis`), times a signal in [-1, 1] (height: [0, 1]);
* **cycle-to-cycle variation**: each cycle of a primitive is played at its own tempo (rate ``exp(tempo x u)``,
  u in [-1, 1]) and amplitude (``1 + amp x v``, v in [-1, 1]) about the standing pose;
* **switches**: a state may be left up to ``switch_slack`` of a cycle before an all-hooves-down window opens,
  and each cross-fade lasts ``blend_s x exp(blend_var x w)``, w in [-1, 1].

In ``mode = "extremes"`` every draw is replaced by its bound: the posture visits the four corners of the
weight square at full drift with the trunk at full crouch (head following), with the noise at its full
amplitude and fastest frequency; tempo alternates fastest / slowest cycle, amplitude is the largest; every
switch is at the earliest phase allowed, and cross-fades alternate shortest / longest. This is what coverage
plays. Units: s, deg, mm, Hz.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

#: the posture a drift of 1 stands for
CROUCH_REF_MM = 15.0  # trunk lowered (mm)
SHIFT_REF = 0.3  # share of the way toward a tripod's centroid
HEAD_REF_DEG = 8.0  # neck / head joints
NOISE_HZ = (1.2, 1.9, 2.7)  # the small fast noise
NOISE_HZ_MAX = 2.7
DRIFT_K = (0.6, 1.0, 1.7)  # drift frequencies, times the drift_hz gene
AXES = ("height", "lateral", "fore_aft", "head_pitch", "head_yaw")


def posture_basis(spec: Any) -> dict[str, dict[str, float]]:
    """Per posture axis, joint offsets (deg, keyed by joint id) for a drift of 1 on this body.

    * ``height``: the planted crouch of ``CROUCH_REF_MM`` (solved, every hoof down);
    * ``lateral`` / ``fore_aft``: the linear part of the four planted weight shifts of ``SHIFT_REF`` (one off
      each hoof), fitted as ``P_leg = a_leg L + b_leg F`` with the weight moving left (+lateral) off the right
      hooves and forward (+fore-aft) off the hind ones. The common part of the four (a slight crouch) is left
      out. A linear model of a solved pose: the physics judges what it really does;
    * ``head_pitch`` / ``head_yaw``: ``HEAD_REF_DEG`` on joints named neck/head pitch and yaw (none on a body
      without neck motors)."""
    from calflab.builtin.primitives import designed_pose

    out: dict[str, dict[str, float]] = {}
    out["height"] = {j: float(v) for j, v in designed_pose(spec, None, 0.0, CROUCH_REF_MM)["offsets_deg"].items()}
    legs = {leg: designed_pose(spec, leg, SHIFT_REF, 0.0)["offsets_deg"] for leg in ("hl", "hr", "fl", "fr")}
    sign = {"hr": (1, 1), "hl": (-1, 1), "fr": (1, -1), "fl": (-1, -1)}  # (lateral, fore-aft) of weight off it
    joints = sorted({j for p in legs.values() for j in p})
    out["lateral"] = {j: sum(sign[k][0] * float(legs[k].get(j, 0.0)) for k in legs) / 4.0 for j in joints}
    out["fore_aft"] = {j: sum(sign[k][1] * float(legs[k].get(j, 0.0)) for k in legs) / 4.0 for j in joints}
    ids = [a.joint for a in spec.actuators]
    out["head_pitch"] = {j: HEAD_REF_DEG for j in ids if ("neck" in j or "head" in j) and "pitch" in j}
    out["head_yaw"] = {j: HEAD_REF_DEG for j in ids if ("neck" in j or "head" in j) and "yaw" in j}
    return {k: {j: round(v, 4) for j, v in d.items() if abs(v) > 1e-6} for k, d in out.items()}


class Signals:
    """Bounded random signals for the posture axes, one set per performance (seeded)."""

    def __init__(self, seed: int, drift_hz: float) -> None:
        rng = np.random.default_rng([int(seed), 9173])
        self.drift = {a: (np.array(DRIFT_K) * drift_hz * rng.uniform(0.8, 1.25, 3), rng.uniform(0, 2 * math.pi, 3))
                      for a in AXES}
        self.noise = {a: (np.array(NOISE_HZ) * rng.uniform(0.85, 1.15, 3), rng.uniform(0, 2 * math.pi, 3))
                      for a in AXES}

    @staticmethod
    def _sum(f: np.ndarray, ph: np.ndarray, t: float) -> float:
        return float(np.mean(np.sin(2 * math.pi * f * t + ph)))  # |.| <= 1

    def value(self, axis: str, t: float, drift: float, noise: float) -> float:
        v = drift * self._sum(*self.drift[axis], t) + noise * self._sum(*self.noise[axis], t)
        top = min(1.0, drift + noise)
        if axis == "height":  # a crouch only: 0..top, about top / 2
            return float(0.5 * (top + min(top, max(-top, v)))) if top > 0 else 0.0
        return float(min(top, max(-top, v)))


#: the corners of the weight square visited in the extremes (lateral, fore-aft)
CORNERS = ((1, 1), (-1, 1), (-1, -1), (1, -1))


def extremes_value(axis: str, t: float, step_s: float, drift: float, noise: float) -> float:
    """The posture's bound at time ``t`` (s): the weight square's corners in turn, each reached over 60 % of
    ``step_s`` and held for the rest; full crouch; the head following the weight; the noise at full amplitude and
    its fastest frequency on top (clipped to the same bound as the drawn signal)."""
    top = min(1.0, drift + noise)
    if axis == "height":
        return top
    k = int(t // step_s)
    x = (t - k * step_s) / step_s
    w = 0.5 - 0.5 * math.cos(math.pi * min(1.0, x / 0.6))
    i = 0 if axis in ("lateral", "head_yaw") else 1
    a, b = CORNERS[(k - 1) % 4][i], CORNERS[k % 4][i]
    v = drift * ((1 - w) * a + w * b) + noise * math.sin(2 * math.pi * NOISE_HZ_MAX * t)
    return float(min(top, max(-top, v)))
