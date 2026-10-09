"""Blender bridge logic (pure; testable without Blender).

``armature_plan`` describes the armature the add-on builds: one bone per
joint (named by the joint's stable ID), joint limits as constraint data, and
part meshes parented to bones. ``rollout_action`` converts a simulation
rollout into keyframes; ``clip_from_action`` validates clips coming back.
All lengths are mm (the add-on applies the scale).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.model.xform import matrix4, quat_rotate
from calflab.sim.rollout import Rollout

ROOT_BONE = "root"


MIN_BONE_MM = 30.0


def _perpendicular_tail(head: np.ndarray, tail: np.ndarray, axis: np.ndarray) -> list[float]:
    """Bone tail moved so the bone is exactly perpendicular to its joint axis.

    A Blender bone can only hinge cleanly about one of its own local axes. With
    the bone perpendicular to the joint axis, rolling the bone puts its local Z
    exactly on that axis, so a single-axis rotation is the true joint motion.
    The bone then points at the child only approximately, which is cosmetic.
    """
    d = tail - head
    length = float(np.linalg.norm(d))
    perp = d - float(np.dot(d, axis)) * axis
    n = float(np.linalg.norm(perp))
    if n < 1e-6:  # the bone ran along the axis: pick any perpendicular direction
        ref = np.array([0.0, 0.0, -1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        perp = ref - float(np.dot(ref, axis)) * axis
        n = float(np.linalg.norm(perp))
    out = head + perp / n * max(length, MIN_BONE_MM)
    return [round(float(v), 3) for v in out]


def armature_plan(spec: RobotSpec) -> dict[str, Any]:
    poses = spec.world_poses()
    parent_of = {b.id: b.parent for b in spec.bodies}
    joint_of_body = {j.body: j for j in spec.joints if j.type in ("hinge", "slide")}
    children: dict[str, list[str]] = {}
    for b in spec.bodies:
        if b.parent:
            children.setdefault(b.parent, []).append(b.id)

    def bone_for_body(body_id: str | None) -> str:
        while body_id is not None:
            if body_id in joint_of_body:
                return joint_of_body[body_id].id
            body_id = parent_of[body_id]
        return ROOT_BONE

    def tail_for(body_id: str) -> list[float]:
        """Bone tail: toward the first child body, else along the body's largest geom."""
        p, q = poses[body_id]
        kids = children.get(body_id, [])
        for k in kids:
            kp = poses[k][0]
            if sum((kp[i] - p[i]) ** 2 for i in range(3)) > 1.0:
                return [round(v, 3) for v in kp]
        body = spec.body(body_id)
        if body.geoms:
            g = max(body.geoms, key=lambda g: g.volume_mm3() if g.role != "visual" else 0.0)
            d = quat_rotate(q, (g.pos[0] * 2, g.pos[1] * 2, g.pos[2] * 2))
            if sum(v * v for v in d) > 1.0:
                return [round(p[i] + d[i], 3) for i in range(3)]
        return [round(p[0], 3), round(p[1], 3), round(p[2] + 40.0, 3)]

    root = spec.root
    rp = poses[root.id][0]
    bones: list[dict[str, Any]] = [
        {
            "name": ROOT_BONE,
            "body": root.id,
            "parent": None,
            "head": [round(v, 3) for v in rp],
            "tail": [round(rp[0] + 60.0, 3), round(rp[1], 3), round(rp[2], 3)],
            "joint": None,
        }
    ]
    for b in spec.bodies:
        j = joint_of_body.get(b.id)
        if j is None:
            continue
        p, q = poses[b.id]
        axis = np.asarray(quat_rotate(q, j.axis), dtype=float)
        axis /= np.linalg.norm(axis) or 1.0
        bones.append(
            {
                "name": j.id,
                "body": b.id,
                "parent": bone_for_body(parent_of[b.id]),
                "head": [round(v, 3) for v in p],
                "tail": _perpendicular_tail(np.asarray(p, dtype=float), np.asarray(tail_for(b.id)), axis),
                "joint": {
                    "type": j.type,
                    "axis_world": [round(float(v), 6) for v in axis],
                    "range_deg": [j.range_deg[0] - j.rest_deg, j.range_deg[1] - j.rest_deg],
                    "rest_deg": j.rest_deg,
                    "cosmetic": j.cosmetic,
                },
            }
        )
    meshes = []
    for b in spec.bodies:
        bp, bq = poses[b.id]
        tb = np.array(matrix4(bp, bq))
        for g in b.geoms:
            if g.shape == "mesh" or g.role == "collision":
                continue
            meshes.append(
                {
                    "id": g.id,
                    "bone": bone_for_body(b.id),
                    "shape": g.shape,
                    "size": list(g.size),
                    "xform": (tb @ np.array(matrix4(g.pos, g.quat))).round(6).tolist(),
                    "layer": g.layer,
                    "color": g.color,
                }
            )
    return {"units": "mm", "scale_to_blender": 0.001, "name": spec.name, "bones": bones, "meshes": meshes}


def rollout_action(rollout: Rollout, rest_deg: dict[str, float]) -> dict[str, Any]:
    """Keyframes for importing a rollout as a Blender action.

    Joint angles are degrees relative to the standing pose (the armature's
    rest pose); the root trajectory is in mm with (w, x, y, z) quaternions.
    """
    dt = float(rollout.meta.get("record_dt", 0.02))
    fps = round(1.0 / dt) if dt > 0 else 50
    joints = {}
    for i, jid in enumerate(rollout.joint_ids):
        deg = u.rad_to_deg(rollout.q[:, i].astype(float)) - rest_deg.get(jid, 0.0)
        joints[jid] = [round(float(v), 3) for v in deg]
    return {
        "fps": fps,
        "frames": rollout.n_frames,
        "joints": joints,
        "root_pos": np.round(u.from_si(rollout.body_pos[:, 0, :].astype(float), "mm"), 2).tolist(),
        "root_quat": np.round(rollout.body_quat[:, 0, :].astype(float), 5).tolist(),
    }


def retarget_keypoints(keypoints: Any, spec: RobotSpec) -> dict[str, Any]:
    """Placeholder for video pose-estimation import (calf keypoints -> retargeted clip).

    TODO(phase2+): accept per-frame 2D/3D keypoints (e.g. from DeepLabCut or
    SuperAnimal quadruped models), fit joint angles of ``spec`` by inverse
    kinematics per leg, smooth, and return a MotionClip dict.
    """
    raise NotImplementedError("Video pose-estimation import is a planned interface (no implementation yet).")
