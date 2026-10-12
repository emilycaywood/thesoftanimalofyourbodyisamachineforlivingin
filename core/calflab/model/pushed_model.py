"""A whole robot modelled in Rhino, used in place of the parametric one (ADR-062).

One override of kind ``model`` carries, for the standing pose as modelled:

* ``meta["joints"]``: per joint id a point on its axis and the axis direction
  (world, mm). The skeleton takes them; a joint without an entry keeps its
  parametric place relative to its parent.
* ``meta["bodies"]``: per body id the closed solids that make it up (measured
  when they arrived, in the body frame, exactly as the solids of ADR-053) and
  the convex hulls the simulator collides with.

Everything here is pure: the measuring and storing is done at the push
(:mod:`calflab.bridge.rhino_model`), so building a design needs no file access.

Units: mm, degrees. Frame: X forward, Y left, Z up.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import Geom, RobotSpec
from calflab.model.xform import Quat, Vec3, compose, quat_axis_angle, quat_mul, quat_to_matrix

#: most vertices a collision hull keeps (the full hull of a detailed solid has thousands)
HULL_VERTICES = 32
#: a modelled axis this far from the parametric one is reported as a probable mistake
AXIS_WARN_DEG = 20.0
DOWN: Vec3 = (0.0, 0.0, -1.0)


def _sphere_directions(n: int) -> np.ndarray:
    """``n`` directions spread evenly over the sphere (Fibonacci lattice)."""
    i = np.arange(n) + 0.5
    z = 1.0 - 2.0 * i / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = i * math.pi * (3.0 - math.sqrt(5.0))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def support_hull(vertices: Any, max_vertices: int = HULL_VERTICES, keep: tuple[Vec3, ...] = ()) -> list[Vec3]:
    """Vertices of a simplified convex hull of ``vertices``: at most
    ``max_vertices`` of the hull's own vertices, the furthest one along each of
    a set of evenly spread directions and along every direction in ``keep``
    (e.g. straight down, so the lowest point of a foot is kept exactly).

    The result lies inside the true hull and touches it along the sampled
    directions. Returns an empty list for a set with no volume.
    """
    from scipy.spatial import ConvexHull, QhullError

    v = np.unique(np.round(np.asarray(vertices, dtype=float).reshape(-1, 3), 4), axis=0)
    if len(v) < 4:
        return []
    try:
        full = v[ConvexHull(v).vertices]
    except QhullError:
        return []
    chosen = full
    if len(full) > max_vertices:
        dirs = np.array([*keep, (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], dtype=float)
        dirs = np.vstack([dirs, _sphere_directions(max(max_vertices - len(dirs), 0))])[:max_vertices]
        chosen = full[np.unique(np.argmax(full @ dirs.T, axis=0))]
        try:
            if ConvexHull(chosen).volume <= 1e-9:
                chosen = full
        except QhullError:
            chosen = full
    return [(float(p[0]), float(p[1]), float(p[2])) for p in chosen]


def _unit(v: Any) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    return a / n if n > 0 else a


def joint_world_axes(spec: RobotSpec, poses: dict[str, tuple[Vec3, Quat]]) -> dict[str, tuple[Vec3, Vec3]]:
    """World position (mm) and unit axis of every hinge in the given pose."""
    parent_of = {b.id: b.parent for b in spec.bodies}
    out: dict[str, tuple[Vec3, Vec3]] = {}
    for j in spec.joints:
        if j.type != "hinge":
            continue
        body = spec.body(j.body)
        parent = parent_of[j.body]
        frame = quat_mul(poses[parent][1], body.quat) if parent is not None else poses[j.body][1]
        a = quat_to_matrix(frame) @ _unit(j.axis)
        out[j.id] = (poses[j.body][0], (float(a[0]), float(a[1]), float(a[2])))
    return out


def apply_skeleton(spec: RobotSpec, joints: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Move the hinges of ``spec`` onto modelled axes, in place.

    ``joints``: ``{joint id: {"point": [x, y, z], "axis": [x, y, z]}}`` in the
    world frame of the standing pose. The body a joint carries gets its origin
    at the point, and the joint its axis along the line (pointing the way the
    parametric axis does, so a positive angle still means the same turn).
    Standing angles, ranges and the orientation of the body frames are kept.
    Everything below a moved joint moves with it.

    Returns one row per hinge: where it is now and where the parametric
    skeleton had it (mm, world), the distance between them and the angle
    between the axes.
    """
    before = joint_world_axes(spec, spec.world_poses())
    new: dict[str, tuple[Vec3, Quat]] = {}
    for b in spec.bodies:
        hinges = [j for j in spec.joints_of(b.id) if j.type == "hinge"]
        given = next((j for j in hinges if j.id in joints), None)
        if b.parent is None:
            new[b.id] = (b.pos, b.quat)
            continue
        pp, pq = new[b.parent]
        if given is not None:
            rp = quat_to_matrix(pq)
            local = rp.T @ (np.asarray(joints[given.id]["point"], dtype=float) - np.asarray(pp))
            b.pos = (float(local[0]), float(local[1]), float(local[2]))
            d = _unit(joints[given.id]["axis"])
            if float(d @ np.asarray(before[given.id][1])) < 0:
                d = -d
            a = (rp @ quat_to_matrix(b.quat)).T @ d
            given.axis = (float(a[0]), float(a[1]), float(a[2]))
        q = b.quat
        for j in hinges:
            q = quat_mul(q, quat_axis_angle(j.axis, j.rest_deg))
        new[b.id] = compose(pp, pq, b.pos, q)
    after = joint_world_axes(spec, spec.world_poses())
    rows: list[dict[str, Any]] = []
    for j in spec.joints:
        if j.id not in after:
            continue
        (p1, a1), (p0, a0) = after[j.id], before[j.id]
        delta = [p1[k] - p0[k] for k in range(3)]
        angle = u.rad_to_deg(math.acos(max(-1.0, min(1.0, sum(a1[k] * a0[k] for k in range(3))))))
        rows.append(
            {
                "joint": j.id,
                "name": j.name or j.id,
                "body": j.body,
                #: ``model`` = from a modelled axis line; ``parametric`` = no line, it follows its parent
                "source": "model" if j.id in joints else "parametric",
                "pos_mm": [round(c, 2) for c in p1],
                "axis": [round(c, 5) for c in a1],
                "parametric_pos_mm": [round(c, 2) for c in p0],
                "parametric_axis": [round(c, 5) for c in a0],
                "delta_mm": [round(c, 2) for c in delta],
                "distance_mm": round(math.sqrt(sum(c * c for c in delta)), 2),
                "axis_angle_deg": round(angle, 2),
            }
        )
    return rows


def collision_geoms(body_id: str, entry: dict[str, Any], hull_assets: bool = True) -> list[Geom]:
    """The collision geoms of one modelled body: a convex hull per solid, and
    one hull round all its foot solids (the ground-contact geom of that leg)."""
    out: list[Geom] = []
    for n, solid in enumerate(entry.get("solids") or [], start=1):
        if solid.get("foot") or not solid.get("hull"):
            continue
        out.append(
            Geom(
                id=f"{body_id}.hull.{n}",
                shape="mesh",
                size=(0.0, 0.0, 0.0),
                role="collision",
                mesh=solid.get("hull_asset") if hull_assets else None,
                hull=[tuple(p) for p in solid["hull"]],
                label=f"Collision hull of {solid.get('name') or f'solid {n}'}",
            )
        )
    foot = entry.get("foot") or {}
    if foot.get("hull"):
        out.append(
            Geom(
                id=f"{body_id}.foot",
                shape="mesh",
                size=(0.0, 0.0, 0.0),
                role="collision",
                mesh=foot.get("hull_asset") if hull_assets else None,
                hull=[tuple(p) for p in foot["hull"]],
                foot=True,
                color="#3b3531",
                label="Foot (collision hull of the modelled foot)",
            )
        )
    return out


def lowest_point(spec: RobotSpec, geom_id: str | None = None) -> tuple[float, dict[str, Vec3]]:
    """Height (mm, world, standing pose) of the lowest collision-hull vertex, and
    per hull geom its lowest vertex in the body frame. ``inf`` without hulls."""
    poses = spec.world_poses()
    lowest = math.inf
    contact: dict[str, Vec3] = {}
    for b in spec.bodies:
        bp, bq = poses[b.id]
        r = quat_to_matrix(bq)
        for g in b.geoms:
            if not g.hull or (geom_id is not None and g.id != geom_id):
                continue
            local = np.asarray(g.hull, dtype=float) @ quat_to_matrix(g.quat).T + np.asarray(g.pos)
            z = local @ r[2] + bp[2]
            i = int(np.argmin(z))
            contact[g.id] = (float(local[i][0]), float(local[i][1]), float(local[i][2]))
            lowest = min(lowest, float(z[i]))
    return lowest, contact
