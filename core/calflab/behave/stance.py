"""Hooves in support stay planted, and the body stays over them (ADR-084).

A clip retargeted from footage moves each joint as the animal's did. A robot
is not the animal: with several hooves on the ground it is a closed chain, so
angles that would make a supporting hoof slide cannot all be reached (position
servos then push the legs against each other through the floor: in physics,
servos at stall while hardly moving), and a pose the calf balanced
dynamically, on its own mass distribution, may tip this body over.

This step changes the clip, quasi-statically:

1. **Which hooves support, per frame**: the hoof heights of the clip pose
   with the trunk pitched and rolled as the clip's root says (its heading is
   ignored; no root = level). A hoof within ``lift_mm`` of the lowest supports;
   a hoof raised more swings. Runs shorter than ``min_run_frames`` join their
   neighbours.
2. **Contact phases**: at least ``min_support`` hooves (3) stay down. Where
   the clip lifts more at once, the hooves lifted least are put back on the
   ground (they are planted by step 3), so a slow robot always stands on a
   tripod. The frames changed are counted.
3. **Per frame, least squares** (SciPy's bounded trust-region solver, numerical
   Jacobian through MuJoCo's forward kinematics) over the trunk's pose (6) and the servo joint
   angles: supporting hooves at their anchors (where they touched down, on the
   ground), swinging hooves not below the ground, the centre of mass over the
   support polygon shrunk by ``stability_margin_mm`` (a hinge: zero inside),
   every joint near the clip's angle, the trunk near the last frame's (weak).
   Angles stay in their ranges.

Only the joint angles are kept: the simulator decides where the trunk goes.
This is quasi-static (no inertia, no momentum): slow the clip to make it hold
in physics, which the adaptation of :mod:`calflab.behave.adapt` does. The
result reports per hoof the support share, how far the clip as given moves a
supporting hoof relative to the trunk (summed), how far a supporting hoof is
off its anchor after the correction, how often the centre of mass is outside
the shrunk polygon before and after, and how much each joint changed.

Units: mm, deg.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel
from scipy.optimize import least_squares

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.project.motions import MotionClip
from calflab.schema import P


class StanceSettings(BaseModel):
    lift_mm: float = P(15.0, unit="mm", ge=1.0, le=100.0,
                       desc="A hoof raised more than this above the lowest one is swinging (PROVISIONAL).")
    min_run_frames: int = P(3, ge=1, le=30, desc="Shorter support or swing runs join their neighbours.")
    min_support: int = P(3, ge=0, le=4, desc="Hooves kept on the ground at every moment (0 = as the clip has them).")
    stability_margin_mm: float = P(15.0, unit="mm", ge=0.0, le=100.0,
                                   desc="Keep the centre of mass this far inside the support polygon (PROVISIONAL).")
    range_margin_deg: float = P(0.0, unit="deg", ge=0.0, le=20.0,
                                desc="Keep the solved angles this far inside each joint's range.")
    transition_frames: int = P(20, ge=2, le=200, advanced=True,
                               desc="Poses solved for the way in from standing and the way back (planted the same way).")
    iterations: int = P(20, ge=1, le=200, advanced=True, desc="Solver iterations per frame (each costs one Jacobian).")
    angle_sd_deg: float = P(5.0, unit="deg", ge=0.1, le=30.0, advanced=True,
                            desc="How strongly joints stay near the clip's angles (smaller = stronger).")
    hoof_sd_mm: float = P(0.2, unit="mm", ge=0.1, le=30.0, advanced=True,
                          desc="How strongly supporting hooves stay put and the centre of mass over them.")


def _quat_from_rotvec(v: np.ndarray) -> np.ndarray:
    a = float(np.linalg.norm(v))
    if a < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    s = np.sin(a / 2) / a
    return np.array([np.cos(a / 2), v[0] * s, v[1] * s, v[2] * s])


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _level(q: tuple[float, float, float, float]) -> np.ndarray:
    """The quaternion without its heading (yaw about world z): pitch and roll only."""
    w, x, y, z = (float(v) for v in q)
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    unyaw = np.array([np.cos(-yaw / 2), 0.0, 0.0, np.sin(-yaw / 2)])
    out = _qmul(unyaw, np.array([w, x, y, z]))
    return out / np.linalg.norm(out)


class _Kinematics:
    """Forward kinematics of the design through MuJoCo (fast): hoof bottoms and the centre of mass (m)."""

    def __init__(self, spec: RobotSpec, lib: Any, joints: list[str]):
        import mujoco

        from calflab.sim import CompileOptions, compile_mjcf

        cm = compile_mjcf(spec, lib, CompileOptions(include_skin=False))
        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_string(cm.xml)
        self.data = mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        self.q0 = self.data.qpos.copy()
        self.adr = np.array([self.model.jnt_qposadr[self.model.joint(j).id] for j in joints], dtype=int)
        self.feet = np.array([self.model.geom(g).id for g in cm.foot_geoms], dtype=int)
        self.radius = np.array([float(self.model.geom_size[g][0]) for g in self.feet])
        self.foot_names = list(cm.foot_geoms)
        self.root_h = cm.root_height
        self.trunk = self.model.body(cm.body_ids[0]).id

    def pose(self, pos: np.ndarray, quat: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        d = self.data
        d.qpos[:] = self.q0
        d.qpos[0:3] = pos
        d.qpos[3:7] = quat
        d.qpos[self.adr] = q
        self.mj.mj_kinematics(self.model, d)
        self.mj.mj_comPos(self.model, d)
        p = d.geom_xpos[self.feet].copy()
        p[:, 2] -= self.radius  # the bottom of the hoof sphere
        return p, d.subtree_com[self.trunk].copy()


def _runs(flags: np.ndarray, min_run: int) -> np.ndarray:
    """Merge runs shorter than ``min_run`` into the run before them."""
    f = flags.copy()
    n = len(f)
    i = 0
    while i < n:
        j = i
        while j < n and f[j] == f[i]:
            j += 1
        if j - i < min_run and i > 0:
            f[i:j] = f[i - 1]
        i = j
    return f


def _hull(pts: np.ndarray) -> np.ndarray:
    """Convex hull of 2D points, counter-clockwise (monotone chain)."""
    p = sorted({(float(a), float(b)) for a, b in pts})
    if len(p) <= 2:
        return np.array(p)

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[tuple[float, float]] = []
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.array(lower[:-1] + upper[:-1])


def outside(c: np.ndarray, poly: np.ndarray, margin: float) -> float:
    """How far (m) the point c is outside the polygon shrunk by ``margin``; 0 inside. Fewer than 3 corners: the
    distance to the segment or point, plus the margin."""
    if len(poly) == 0:
        return 0.0
    if len(poly) < 3:
        a, b = poly[0], poly[-1]
        ab = b - a
        t = float(np.clip(np.dot(c - a, ab) / max(float(np.dot(ab, ab)), 1e-12), 0.0, 1.0))
        return float(np.linalg.norm(c - (a + t * ab))) + margin
    worst = -np.inf
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        e = b - a
        nrm = np.array([e[1], -e[0]]) / max(float(np.linalg.norm(e)), 1e-12)  # outward for a ccw polygon
        worst = max(worst, float(np.dot(c - a, nrm)))
    return max(0.0, worst + margin)


def plant(clip: MotionClip, spec: RobotSpec, lib: Any, s: StanceSettings | None = None) -> tuple[MotionClip, dict[str, Any]]:
    """The clip with its supporting hooves kept planted and the body over them (a new clip), and what changed."""
    s = s or StanceSettings()
    acts = [a.joint for a in spec.actuators]
    ids = [j for j in acts if j in clip.joints]
    if not ids:
        return clip, {"applied": False, "reason": "the clip moves no servo joint"}
    rest = spec.rest_angles()
    rm = s.range_margin_deg
    lo = np.array([u.deg_to_rad(min(spec.joint(j).range_deg[0] + rm, sum(spec.joint(j).range_deg) / 2)) for j in ids])
    hi = np.array([u.deg_to_rad(max(spec.joint(j).range_deg[1] - rm, sum(spec.joint(j).range_deg) / 2 + 1e-6))
                   for j in ids])
    target = np.array([[u.deg_to_rad(rest[j] + v) for j, v in zip(ids, row, strict=True)]
                       for row in zip(*[clip.joints[j] for j in ids], strict=True)])
    target = np.clip(target, lo, hi)
    n, _nj = target.shape
    kin = _Kinematics(spec, lib, ids)
    ident = np.array([1.0, 0.0, 0.0, 0.0])
    origin = np.zeros(3)
    nf = len(kin.feet)
    # 1. support per frame, from hoof heights with the clip's pitch and roll
    raised = np.zeros((n, nf))
    for f in range(n):
        tilt = _level(clip.root_quat[f]) if clip.root_quat and len(clip.root_quat) == n else ident
        raised[f] = kin.pose(origin, tilt, target[f])[0][:, 2]
    raised -= raised.min(axis=1, keepdims=True)
    support = raised <= s.lift_mm / 1000.0
    for k in range(nf):
        support[:, k] = _runs(support[:, k], s.min_run_frames)
    as_clip = support.copy()
    # 2. contact phases: at least min_support hooves down, the least lifted put back first
    need = min(s.min_support, nf)
    for f in range(n):
        while int(support[f].sum()) < need:
            swing = [k for k in range(nf) if not support[f, k]]
            support[f, min(swing, key=lambda k: raised[f, k])] = True
    for k in range(nf):
        support[:, k] = _runs(support[:, k], s.min_run_frames)
    # 3. least squares per frame
    w_f = 1.0 / (s.hoof_sd_mm / 1000.0)
    w_a = 1.0 / u.deg_to_rad(s.angle_sd_deg)
    w_t = 10.0  # trunk: weak, 1e-2 per mm of change from the last frame
    margin = s.stability_margin_mm / 1000.0
    big = np.full(6, np.inf)
    bounds_lo, bounds_hi = np.concatenate([-big, lo]), np.concatenate([big, hi])

    def solve(tgt: np.ndarray, p_last: np.ndarray, q_last: np.ndarray, q_init: np.ndarray, anchors: dict[int, np.ndarray],
              down: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """One pose: trunk and angles near ``tgt`` with the anchored hooves on their anchors, the other hooves not
        below the floor (pulled onto it with weight ``down`` x the hoof weight) and the centre of mass over the
        anchored hooves. Returns trunk position and quaternion, angles, hoof bottoms, centre of mass, polygon."""
        stance = sorted(anchors)
        poly = _hull(np.array([anchors[k][:2] for k in stance])) if stance else np.zeros((0, 2))

        def resid(xv: np.ndarray) -> np.ndarray:
            h, com = kin.pose(p_last + xv[0:3], _qmul(_quat_from_rotvec(xv[3:6]), q_last), np.clip(xv[6:], lo, hi))
            r = [w_a * (xv[6:] - tgt), w_t * xv[0:3], w_t * 0.1 * xv[3:6],
                 np.array([w_f * outside(com[:2], poly, margin)])]
            for k in range(nf):
                if k in anchors:
                    r.append(w_f * (h[k] - anchors[k]))
                else:
                    r.append(np.array([w_f * min(0.0, h[k, 2]) + w_f * down * max(0.0, h[k, 2])]))
            return np.concatenate(r)

        x0 = np.concatenate([np.zeros(6), np.clip(q_init, lo + 1e-9, hi - 1e-9)])
        sol = least_squares(resid, x0, bounds=(bounds_lo, bounds_hi), method="trf", diff_step=1e-6,
                            max_nfev=s.iterations * (len(x0) + 1), x_scale="jac")
        x = sol.x
        p = p_last + x[0:3]
        qt = _qmul(_quat_from_rotvec(x[3:6]), q_last)
        qt = qt / np.linalg.norm(qt)
        h, com = kin.pose(p, qt, x[6:])
        return p, qt, x[6:].copy(), h, com, poly

    # the first frame's supporting hooves stay where they stand, so the lead-in from standing moves the trunk
    # over planted hooves rather than dragging them to new places (ADR-084)
    q_stand = np.clip(np.array([u.deg_to_rad(rest[j]) for j in ids]), lo, hi)
    p_stand = np.array([0.0, 0.0, kin.root_h])
    h_stand, _ = kin.pose(p_stand, ident, q_stand)
    p_stand[2] -= float(h_stand[:, 2].min())
    h_stand[:, 2] -= float(h_stand[:, 2].min())
    anchors: dict[int, np.ndarray] = {k: np.array([h_stand[k, 0], h_stand[k, 1], 0.0]) for k in range(nf) if support[0, k]}
    first_anchors = {k: v.copy() for k, v in anchors.items()}
    pos, quat, q = p_stand.copy(), ident.copy(), target[0].copy()
    out = np.zeros_like(target)
    trunk = np.zeros((n, 7))
    travel = np.zeros(nf)
    slip_after = np.zeros(nf)
    com_out_before = 0
    com_out_after = 0
    for f in range(n):
        if f > 0:
            # before: the clip's own angles with the trunk held, for the centre-of-mass count and hoof travel
            stance_now = [k for k in range(nf) if k in anchors]
            poly_now = _hull(np.array([anchors[k][:2] for k in stance_now])) if stance_now else np.zeros((0, 2))
            h_raw, com_raw = kin.pose(pos, quat, target[f])
            h_prev, _ = kin.pose(pos, quat, target[f - 1])
            com_out_before += int(outside(com_raw[:2], poly_now, margin) > 0)
            for k in range(nf):
                if as_clip[f, k] and as_clip[f - 1, k]:
                    travel[k] += float(np.linalg.norm(h_raw[k, :2] - h_prev[k, :2]))
        pos, quat, q, h, com, poly = solve(target[f], pos, quat, q, anchors)
        out[f] = q
        trunk[f] = np.concatenate([pos, quat])
        com_out_after += int(outside(com[:2], poly, margin) > 1e-3)
        for k in anchors:
            slip_after[k] = max(slip_after[k], float(np.linalg.norm(h[k, :2] - anchors[k][:2])))
        # a hoof that starts supporting next frame is anchored where it is now, on the ground
        if f + 1 < n:
            for k in range(nf):
                if support[f + 1, k] and not support[f, k]:
                    anchors[k] = np.array([h[k, 0], h[k, 1], 0.0])
                elif not support[f + 1, k]:
                    anchors.pop(k, None)
    # 4. the way in from standing and the way back, planted the same way (the physics playback uses them in place
    # of a blend of angles, which would drag the hooves)
    m = max(2, s.transition_frames)
    w = 0.5 - 0.5 * np.cos(np.pi * np.arange(1, m + 1) / m)
    lead = np.zeros((m, len(ids)))
    p, qt, qq = p_stand.copy(), ident.copy(), q_stand.copy()
    for i in range(m):
        p, qt, qq, h, _com, _ = solve(q_stand + w[i] * (out[0] - q_stand), p, qt, qq, first_anchors)
        lead[i] = qq
    lead[-1] = out[0]
    back = np.zeros((m, len(ids)))
    p, qt, qq = pos, quat, out[-1].copy()
    for i in range(m):
        p, qt, qq, h, _com, _ = solve(out[-1] + w[i] * (q_stand - out[-1]), p, qt, qq, anchors, down=float(w[i]))
        back[i] = qq
    end_slip = max((float(np.linalg.norm(h[k, :2] - anchors[k][:2])) for k in anchors), default=0.0)
    end_lift = float(max(0.0, h[:, 2].max()))
    joints = dict(clip.joints)
    change = {}
    for i, j in enumerate(ids):
        deg = u.rad_to_deg(out[:, i]) - rest[j]
        joints[j] = [round(float(v), 4) for v in deg]
        change[j] = float(np.sqrt(np.mean((u.rad_to_deg(out[:, i] - target[:, i])) ** 2)))

    def rel(rows: np.ndarray) -> dict[str, list[float]]:
        return {j: [round(float(u.rad_to_deg(rows[r, i]) - rest[j]), 4) for r in range(len(rows))] for i, j in enumerate(ids)}

    paths = {"lead_in": rel(lead), "return": rel(back)}
    new = clip.model_copy(update={"joints": joints, "meta": {**clip.meta, "stance_paths": paths}})
    names = kin.foot_names
    info = {
        "applied": True, "settings": s.model_dump(mode="json"), "feet": names,
        "support": ["".join("X" if support[f, k] else "." for k in range(nf)) for f in range(n)],
        "support_fraction_clip": {names[k]: round(float(np.mean(as_clip[:, k])), 3) for k in range(nf)},
        "support_fraction": {names[k]: round(float(np.mean(support[:, k])), 3) for k in range(nf)},
        "fewer_than_min_support_frames": int(np.sum(as_clip.sum(axis=1) < need)),
        "frames": n,
        "support_travel_before_mm": {names[k]: round(float(1000.0 * travel[k]), 1) for k in range(nf)},
        "slip_after_mm": {names[k]: round(float(1000.0 * slip_after[k]), 2) for k in range(nf)},
        "com_outside_before_fraction": round(com_out_before / max(1, n - 1), 3),
        "com_outside_after_fraction": round(com_out_after / max(1, n), 3),
        "angle_change_rms_deg": {j: round(v, 2) for j, v in change.items()},
        "transition_frames": m,
        "trunk_pose": [[round(float(v), 6) for v in row] for row in trunk],  # solved trunk (m, quaternion w-first)
        "return_end": {"standing_change_rms_deg": round(float(u.rad_to_deg(np.sqrt(np.mean((back[-1] - q_stand) ** 2)))), 2),
                       "hoof_slip_mm": round(1000.0 * end_slip, 2), "highest_hoof_mm": round(1000.0 * end_lift, 2)},
    }
    return new, info
