"""A clip played kinematically on the body, for looking at it (ADR-073).

No physics: every frame is the body posed by forward kinematics at the clip's
joint angles (clamped to the joint ranges, as the robot would), with the trunk
on the clip's root path if it has one, else at standing height. The result is
a ``Rollout`` so the viewport and timeline replay it like any run; torques,
contacts and temperatures are zero, because nothing was simulated.
"""

from __future__ import annotations

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.model.xform import quat_mul, quat_rotate
from calflab.project.motions import MotionClip
from calflab.sim.rollout import Rollout


def preview_rollout(clip: MotionClip, spec: RobotSpec, speed: float = 1.0) -> Rollout:
    if clip.frames == 0:
        raise ValueError(f"Clip {clip.id or clip.name!r} has no frames")
    rest = spec.rest_angles()
    hinge = [j for j in spec.joints if j.type == "hinge"]
    acts = [a for a in spec.actuators]
    n = clip.frames
    dt = 1.0 / (clip.fps * speed)
    stand = spec.root.pos
    body_pos = np.zeros((n, len(spec.bodies), 3), dtype=np.float32)
    body_quat = np.zeros((n, len(spec.bodies), 4), dtype=np.float32)
    q = np.zeros((n, len(hinge)), dtype=np.float32)
    ctrl = np.zeros((n, len(acts)), dtype=np.float32)
    com = np.zeros((n, 3), dtype=np.float32)
    for f in range(n):
        angles = dict(rest)
        for j in hinge:
            v = clip.joints.get(j.id)
            if v is not None:
                lo, hi = j.range_deg
                angles[j.id] = float(np.clip(rest[j.id] + v[f], lo, hi))  # ranges are absolute joint angles
        root = clip.root_pos[f] if clip.root_pos else (0.0, 0.0, stand[2])
        poses = spec.world_poses(angles, root_pos=(root[0], root[1], root[2]))
        if clip.root_quat:  # pitch the whole posed body about its root
            rq = clip.root_quat[f]
            rp = poses[spec.root.id][0]
            pitched = {}
            for bid, (bp, bq) in poses.items():
                r = quat_rotate(rq, (bp[0] - rp[0], bp[1] - rp[1], bp[2] - rp[2]))
                pitched[bid] = ((rp[0] + r[0], rp[1] + r[1], rp[2] + r[2]), quat_mul(rq, bq))
            poses = pitched
        for i, b in enumerate(spec.bodies):
            p, qq = poses[b.id]
            body_pos[f, i] = u.vec_mm_to_m(p)
            body_quat[f, i] = qq
        for i, j in enumerate(hinge):
            q[f, i] = u.deg_to_rad(angles[j.id])
        for i, a in enumerate(acts):
            ctrl[f, i] = u.deg_to_rad(angles.get(a.joint, 0.0))
        com[f] = u.vec_mm_to_m(spec.center_of_mass(poses))
    zeros = np.zeros((n, len(acts)), dtype=np.float32)
    feet = [g.id for b in spec.bodies for g in b.geoms if g.foot]
    return Rollout(
        body_ids=[b.id for b in spec.bodies],
        joint_ids=[j.id for j in hinge],
        actuator_ids=[a.id for a in acts],
        foot_geoms=feet,
        t=np.arange(n, dtype=np.float64) * dt,
        body_pos=body_pos,
        body_quat=body_quat,
        q=q,
        ctrl=ctrl,
        torque=zeros,
        dq=zeros.copy(),
        foot_force=np.zeros((n, len(feet)), dtype=np.float32),
        com=com,
        temp=zeros.copy(),
        meta={"kinematic_preview": True, "clip": clip.id, "speed": speed, "record_dt": dt, "duration_s": n * dt,
              "settle_s": 0.0, "fell": False, "energy_j": 0.0, "total_mass_kg": u.g_to_kg(spec.total_mass_g()),
              "root_height": u.mm_to_m(stand[2])},
    )
