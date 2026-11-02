"""Static joint loads in a pose: what the servos must hold against gravity,
and what the springs take off them (ADR-065).

Quasi-static and rigid: the ground reactions are the vertical forces at the
contact points with the smallest sum of squares that balance the weight and
put the centre of pressure under the centre of mass. For a symmetric
four-footed stance that is the lever rule between front and hind feet, split
equally left and right. Friction and dynamics are ignored; the simulator gives
the dynamic loads.

Torques are on the segment below each joint, about the joint axis (N*m): the
torque the weight and the ground put there tends to turn the joint that way,
and the servo (through its belt, if any) must supply the opposite.
"""

from __future__ import annotations

import numpy as np

from calflab import units as u
from calflab.mech.springs import spring_state
from calflab.model.spec import RobotSpec
from calflab.model.xform import Quat, Vec3, quat_mul, quat_rotate

G = 9.81  # m/s^2


def joint_frames(spec: RobotSpec, poses: dict[str, tuple[Vec3, Quat]]) -> dict[str, tuple[Vec3, Vec3]]:
    """World position (mm) and axis of every hinge in a pose."""
    out: dict[str, tuple[Vec3, Vec3]] = {}
    parent_of = {b.id: b.parent for b in spec.bodies}
    for j in spec.joints:
        bp, _ = poses[j.body]
        par = parent_of[j.body]
        frame = quat_mul(poses[par][1], spec.body(j.body).quat) if par is not None else poses[j.body][1]
        out[j.id] = (bp, quat_rotate(frame, j.axis))
    return out


def subtree(spec: RobotSpec, body_id: str) -> set[str]:
    out = {body_id}
    for b in spec.bodies:  # parents precede children
        if b.parent in out:
            out.add(b.id)
    return out


def default_contacts(spec: RobotSpec, poses: dict[str, tuple[Vec3, Quat]]) -> list[tuple[str, Vec3]]:
    """The bottom of every foot geom (body, world point in mm)."""
    out: list[tuple[str, Vec3]] = []
    for b in spec.bodies:
        bp, bq = poses[b.id]
        for g in b.geoms:
            if g.foot:
                r = quat_rotate(bq, g.pos)
                lift = g.size[0] if g.shape == "sphere" else 0.0
                out.append((b.id, (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2] - lift)))
    return out


def ground_reactions(weight_n: float, com: Vec3, contacts: list[Vec3]) -> np.ndarray:
    """Vertical reactions (N) at ``contacts`` that balance ``weight_n`` acting at ``com`` (min norm)."""
    A = np.array([[1.0] * len(contacts), [c[0] for c in contacts], [c[1] for c in contacts]])
    b = np.array([weight_n, weight_n * com[0], weight_n * com[1]])
    return np.linalg.pinv(A) @ b


def static_loads(
    spec: RobotSpec,
    angles_deg: dict[str, float] | None = None,
    contacts: list[tuple[str, Vec3]] | None = None,
) -> dict[str, dict[str, float]]:
    """Per hinge joint: ``gravity_nm`` (weight + ground on the segment below),
    ``spring_nm`` (springs acting on that segment), ``net_nm`` (their sum; the
    servo holds minus this at the joint) in the given pose (default standing)."""
    poses = spec.world_poses(angles_deg)
    frames = joint_frames(spec, poses)
    pts = contacts if contacts is not None else default_contacts(spec, poses)
    com = spec.center_of_mass(poses)
    weight = u.g_to_kg(spec.total_mass_g()) * G
    reactions = ground_reactions(weight, com, [p for _, p in pts]) if pts else np.zeros(0)
    # spring forces on each anchor (N, world), as point loads on their bodies
    loads: list[tuple[str, np.ndarray, np.ndarray]] = []  # (body, point mm, force N)
    for sp in spec.springs:
        pa = _world(poses, sp.upper_body, sp.upper_pos)
        pb = _world(poses, sp.lower_body, sp.lower_pos)
        jp, ax = frames[sp.joint]
        st = spring_state(pa, pb, jp, ax, sp.k_n_per_mm, sp.free_length_mm)
        d = np.asarray(pa) - np.asarray(pb)
        n = float(np.linalg.norm(d)) or 1.0
        f = st.force_n * d / n
        loads.append((sp.lower_body, np.asarray(pb), f))
        loads.append((sp.upper_body, np.asarray(pa), -f))
    out: dict[str, dict[str, float]] = {}
    for j in spec.joints:
        if j.type != "hinge":
            continue
        jp, ax = frames[j.id]
        jpv, axv = np.asarray(jp), np.asarray(ax)
        below = subtree(spec, j.body)
        grav = 0.0
        for b in spec.bodies:
            if b.id not in below:
                continue
            bp, bq = poses[b.id]
            for g in b.geoms:
                if g.mass_g <= 0:
                    continue
                r = np.asarray(bp) + np.asarray(quat_rotate(bq, g.mass_center())) - jpv
                grav += float(np.dot(np.cross(r, (0.0, 0.0, -u.g_to_kg(g.mass_g) * G)), axv))
        for (body, p), fz in zip(pts, reactions, strict=True):
            if body in below:
                grav += float(np.dot(np.cross(np.asarray(p) - jpv, (0.0, 0.0, fz)), axv))
        spring = 0.0
        for body, point, f in loads:
            if body in below:
                spring += float(np.dot(np.cross(point - jpv, f), axv))
        out[j.id] = {"gravity_nm": u.nmm_to_nm(grav), "spring_nm": u.nmm_to_nm(spring), "net_nm": u.nmm_to_nm(grav + spring)}
    return out


def _world(poses: dict[str, tuple[Vec3, Quat]], body: str, pos: Vec3) -> Vec3:
    bp, bq = poses[body]
    r = quat_rotate(bq, pos)
    return (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2])
