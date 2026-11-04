"""Poses with every hoof planted and the centre of mass where it is wanted (ADR-085).

The weight shift, step and stand primitives play poses designed here, so they
balance by construction: all four hooves stay where the body stands, and the
centre of mass is moved toward the middle of the three hooves that stay loaded
(the *tripod*), as far as ``shift`` says. A least-squares solve (as in
:func:`calflab.behave.stance.plant`, MuJoCo's forward kinematics) over the
trunk's pose and the servo joints: hooves on their standing places (0.2 mm),
the centre of mass on its target (1 mm), the trunk lowered by ``crouch_mm``,
the joints weakly near standing, inside their ranges with a margin.

What the solve reaches is reported: the centre of mass's shift, and how far
inside the tripod it ends (mm): the margin left for lifting the free hoof. On
this body the front legs have no ab/adduction, so a sideways shift is made by
the hind ab/ad and a roll; the solve finds how far that goes.

Units: mm, deg.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec

LEG_ORDER = ("hl", "hr", "fl", "fr")


def _leg_of_foot(name: str) -> str:
    for leg in LEG_ORDER:
        if f".{leg}." in name or name.startswith(f"{leg}.") or f"leg.{leg}" in name:
            return leg
    return name


def design_pose(spec: RobotSpec, lib: Any, free: str | None = None, shift: float = 0.0, crouch_mm: float = 0.0,
                range_margin_deg: float = 2.0) -> dict[str, Any]:
    """Joint offsets (deg, relative to standing) that keep all four hooves planted, lower the trunk by
    ``crouch_mm`` and move the centre of mass ``shift`` (0..1) of the way from standing to the centroid of the
    tripod without hoof ``free`` (None = no shift). Returns the offsets and what was reached."""
    from scipy.optimize import least_squares

    from calflab.behave.stance import _hull, _Kinematics, _qmul, _quat_from_rotvec, outside

    ids = [a.joint for a in spec.actuators]
    rest = spec.rest_angles()
    lo = np.array([u.deg_to_rad(min(spec.joint(j).range_deg[0] + range_margin_deg, rest[j])) for j in ids])
    hi = np.array([u.deg_to_rad(max(spec.joint(j).range_deg[1] - range_margin_deg, rest[j])) for j in ids])
    kin = _Kinematics(spec, lib, ids)
    ident = np.array([1.0, 0.0, 0.0, 0.0])
    q0 = np.clip(np.array([u.deg_to_rad(rest[j]) for j in ids]), lo, hi)
    p0 = np.array([0.0, 0.0, kin.root_h])
    h0, c0 = kin.pose(p0, ident, q0)
    p0[2] -= float(h0[:, 2].min())
    h0, c0 = kin.pose(p0, ident, q0)
    legs = [_leg_of_foot(n) for n in kin.foot_names]
    if free is not None and free not in legs:
        raise ValueError(f"No hoof {free!r} (hooves: {', '.join(legs)})")
    tri = [k for k, leg in enumerate(legs) if leg != free]
    tri_poly = _hull(h0[tri, :2])
    target = c0[:2].copy()
    if free is not None:
        target = c0[:2] + float(shift) * (h0[tri, :2].mean(axis=0) - c0[:2])
    w_f, w_c, w_a = 1.0 / 0.0002, 1.0 / 0.001, 1.0 / u.deg_to_rad(20.0)
    z_target = p0[2] - crouch_mm / 1000.0

    def resid(x: np.ndarray) -> np.ndarray:
        h, com = kin.pose(p0 + x[0:3], _qmul(_quat_from_rotvec(x[3:6]), ident), np.clip(x[6:], lo, hi))
        return np.concatenate([w_f * (h - h0).ravel(), w_c * (com[:2] - target), [w_c * (p0[2] + x[2] - z_target)],
                               w_a * (x[6:] - q0)])

    big = np.full(6, np.inf)
    sol = least_squares(resid, np.concatenate([np.zeros(6), q0]), bounds=(np.concatenate([-big, lo]),
                        np.concatenate([big, hi])), method="trf", diff_step=1e-6, max_nfev=400, x_scale="jac")
    x = sol.x
    h, com = kin.pose(p0 + x[0:3], _qmul(_quat_from_rotvec(x[3:6]), ident), x[6:])
    inside = -outside(com[:2], tri_poly, 0.0) if outside(com[:2], tri_poly, 0.0) > 0 else _inside(com[:2], tri_poly)
    return {
        "offsets_deg": {j: round(float(u.rad_to_deg(x[6 + i]) - rest[j]), 3) for i, j in enumerate(ids)},
        "free": free, "shift": shift, "crouch_mm": crouch_mm,
        "com_shift_mm": round(float(np.linalg.norm(com[:2] - c0[:2])) * 1000.0, 2),
        "com_target_shift_mm": round(float(np.linalg.norm(target - c0[:2])) * 1000.0, 2),
        "com_inside_tripod_mm": round(float(inside) * 1000.0, 2),
        "com_inside_tripod_standing_mm": round(float(_inside(c0[:2], tri_poly)) * 1000.0, 2),
        "hoof_slip_mm": round(float(np.max(np.linalg.norm(h - h0, axis=1))) * 1000.0, 3),
        "trunk_drop_mm": round(float(-x[2]) * 1000.0, 2),
    }


def _inside(c: np.ndarray, poly: np.ndarray) -> float:
    """Distance (m) of a point inside a ccw polygon to its nearest edge (negative outside)."""
    if len(poly) < 3:
        return 0.0
    best = np.inf
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        e = b - a
        nrm = np.array([e[1], -e[0]]) / max(float(np.linalg.norm(e)), 1e-12)
        best = min(best, -float(np.dot(c - a, nrm)))
    return best


def lift_offsets(spec: RobotSpec, leg: str, lift_deg: float) -> dict[str, float]:
    """Joint offsets (deg) that fold a free leg to lift its hoof: as the feral walk's swing does (hind: stifle and
    1.8 x as much hock; front: carpus and -0.4 x as much shoulder)."""
    joints = {j.id for j in spec.joints}
    out: dict[str, float] = {}
    if leg.startswith("h"):
        for part, k in (("stifle", 1.0), ("hock", 1.8)):
            if f"joint.{leg}.{part}" in joints:
                out[f"joint.{leg}.{part}"] = k * lift_deg
    else:
        for part, k in (("carpus", 1.0), ("shoulder", -0.4)):
            if f"joint.{leg}.{part}" in joints:
                out[f"joint.{leg}.{part}"] = k * lift_deg
    return out
