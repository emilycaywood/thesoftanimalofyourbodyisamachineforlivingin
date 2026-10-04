"""Scene description for clients: the evaluated design as plain JSON.

Units mm / g / degrees, world frame Z-up. Everything a viewport needs is
computed here (rest poses, joint frames, centre of mass, support polygon,
element property tables) so clients never do geometry or domain logic.
"""

from __future__ import annotations

from typing import Any

from calflab.components import library
from calflab.config import default
from calflab.design import EvaluatedDesign
from calflab.model.xform import Vec3, quat_rotate
from calflab.project.store import LayerState


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain; returns the hull counter-clockwise."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def point_in_hull_margin(hull: list[tuple[float, float]], p: tuple[float, float]) -> float:
    """Signed distance from ``p`` to the nearest hull edge (positive = inside)."""
    if len(hull) < 3:
        return -1.0
    best = float("inf")
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        length = (ex * ex + ey * ey) ** 0.5 or 1.0
        d = (ex * (p[1] - a[1]) - ey * (p[0] - a[0])) / length  # left of edge = inside (CCW)
        best = min(best, d)
    return best


def foot_tracks(rollout: Any, scene: dict[str, Any]) -> dict[str, Any]:
    """Per-frame foot contact points (mm) and support polygons for playback overlays."""
    import numpy as np

    from calflab import units as u

    local: dict[str, tuple[int, list[float], float]] = {}
    for b in scene["bodies"]:
        for g in b["geoms"]:
            if g["foot"] and b["id"] in rollout.body_ids:
                local[g["id"]] = (rollout.body_ids.index(b["id"]), g["pos"], float(g["size"][0]))
    n = rollout.n_frames
    pos = np.zeros((n, len(rollout.foot_geoms), 3))
    for fi, gid in enumerate(rollout.foot_geoms):
        if gid not in local:
            continue
        bi, lp, radius = local[gid]
        q = rollout.body_quat[:, bi, :].astype(float)
        w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
        v = np.asarray(lp, dtype=float)
        # rotate v by each quaternion: v + 2w(q x v) + 2 q x (q x v)
        qv = np.stack([x, y, z], axis=1)
        t = 2.0 * np.cross(qv, v)
        rotated = v + w[:, None] * t + np.cross(qv, t)
        p = u.from_si(rollout.body_pos[:, bi, :].astype(float), "mm") + rotated
        p[:, 2] -= radius  # contact point under the hoof
        pos[:, fi, :] = p
    contact = rollout.foot_force > 1e-6
    polygons = []
    for i in range(n):
        pts = [(float(pos[i, f, 0]), float(pos[i, f, 1])) for f in range(pos.shape[1]) if contact[i, f]]
        polygons.append([[round(px, 1), round(py, 1)] for px, py in convex_hull(pts)])
    return {"foot_pos": np.round(pos, 1).tolist(), "support": polygons}


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _round(v: Any, nd: int = 3) -> list[float]:
    return [round(float(x), nd) for x in v]


def build_scene(design: EvaluatedDesign, layers: dict[str, LayerState] | None = None) -> dict[str, Any]:
    spec = design.spec
    lib = library()
    poses = spec.world_poses()
    parent_of = {b.id: b.parent for b in spec.bodies}
    elements: dict[str, dict[str, Any]] = {}

    def comp_info(key: str | None) -> dict[str, Any] | None:
        if not key or not lib.has(key):
            return None
        return lib.get(key).model_dump(mode="json")

    def params_of(element_id: str) -> dict[str, Any]:
        return {
            name: pv.model_dump(mode="json")
            for name, pv in design.element_params.get(element_id, {}).items()
        }

    bodies = []
    feet: list[dict[str, Any]] = []
    geom_world: dict[str, Vec3] = {}
    for b in spec.bodies:
        bp, bq = poses[b.id]
        geoms = []
        for g in b.geoms:
            geoms.append(
                {
                    "id": g.id,
                    "shape": g.shape,
                    "size": _round(g.size),
                    "pos": _round(g.pos),
                    "quat": _round(g.quat, 6),
                    "layer": g.layer,
                    "role": g.role,
                    "color": g.color,
                    "component": g.component,
                    "label": g.label,
                    "mass_g": round(g.mass_g, 2),
                    "foot": g.foot,
                    "mesh": g.mesh,
                }
            )
            wp = _add(bp, quat_rotate(bq, g.pos))
            geom_world[g.id] = wp
            if g.foot:
                feet.append({"id": g.id, "body": b.id, "pos": _round(wp), "radius": g.size[0]})
            elements[g.id] = {
                "kind": "geom",
                "name": g.label or g.id,
                "layer": g.layer,
                "body": b.id,
                "mass_g": round(g.mass_g, 2),
                "shape": g.shape,
                "size_mm": _round(g.size),
                "component": comp_info(g.component),
            }
        bodies.append(
            {
                "id": b.id,
                "name": b.name or b.id,
                "parent": b.parent,
                "layer": b.layer,
                "part": b.part,
                "pos": _round(bp),
                "quat": _round(bq, 6),
                "local_pos": _round(b.pos),
                "local_quat": _round(b.quat, 6),
                "geoms": geoms,
            }
        )
        elements[b.id] = {
            "kind": "body",
            "name": b.name or b.id,
            "layer": b.layer,
            "parent": b.parent,
            "mass_g": round(b.mass_g(), 2),
            "params": params_of(b.id),
            "joints": [j.id for j in spec.joints_of(b.id)],
        }

    act_by_joint = {a.joint: a for a in spec.actuators}
    trans = {t.id: t for t in spec.transmissions}
    joints = []
    for j in spec.joints:
        bp, bq = poses[j.body]
        parent = parent_of[j.body]
        # the joint axis is fixed in the parent frame; express it in world at rest
        if parent is not None:
            pq = poses[parent][1]
            from calflab.model.xform import quat_mul

            axis_frame = quat_mul(pq, spec.body(j.body).quat)
        else:
            axis_frame = bq
        act = act_by_joint.get(j.id)
        act_info = None
        if act is not None:
            c = lib.actuator(act.component)
            tr = trans.get(act.transmission) if act.transmission else None
            act_info = {
                "id": act.id,
                "component": c.model_dump(mode="json"),
                "transmission": tr.model_dump(mode="json") if tr else {"type": "direct", "ratio": 1.0},
            }
            elements[act.id] = {
                "kind": "actuator",
                "name": f"{c.name} on {j.name or j.id}",
                "layer": "Actuators",
                "joint": j.id,
                "component": c.model_dump(mode="json"),
                "transmission": act_info["transmission"],
            }
        joints.append(
            {
                "id": j.id,
                "name": j.name or j.id,
                "body": j.body,
                "parent_body": parent,
                "type": j.type,
                "axis": _round(j.axis),
                "world_pos": _round(bp),
                "world_axis": _round(quat_rotate(axis_frame, j.axis), 5),
                "range_deg": list(j.range_deg),
                "rest_deg": round(j.rest_deg, 3),
                "group": j.group,
                "cosmetic": j.cosmetic,
                "actuator": act_info,
            }
        )
        elements[j.id] = {
            "kind": "joint",
            "name": j.name or j.id,
            "layer": "Annotations",
            "body": j.body,
            "type": j.type,
            "range_deg": list(j.range_deg),
            "rest_deg": round(j.rest_deg, 3),
            "group": j.group,
            "actuator": act.id if act else None,
        }

    sensors = []
    for s in spec.sensors:
        bp, bq = poses[s.body]
        wp = _add(bp, quat_rotate(bq, s.pos))
        sensors.append({"id": s.id, "type": s.type, "body": s.body, "pos": _round(wp), "local_pos": _round(s.pos)})
        elements[s.id] = {
            "kind": "sensor",
            "name": s.id,
            "layer": "Sensors",
            "body": s.body,
            "type": s.type,
            "component": comp_info(s.component),
        }

    for r in spec.skin_regions:
        elements[r.id] = {
            "kind": "skin",
            "name": r.id,
            "layer": "Skin",
            "bodies": r.bodies,
            "joints": r.joints,
            "thickness_mm": r.thickness_mm,
            "area_cm2": round(r.area_mm2 / 100.0, 1),
            "component": comp_info(r.material),
        }

    from calflab.wiring.harness import harness_paths

    harness = []
    paths = harness_paths(spec)
    for h in spec.harness_routes:
        harness.append(
            {
                "id": h.id,
                "src": h.src,
                "dst": h.dst,
                "points": [_round(p) for p in paths[h.id]],
                "length_mm": h.length_mm,
                "wires": [w.model_dump() for w in h.wires],
                "connector": h.connector,
            }
        )
        elements[h.id] = {
            "kind": "harness",
            "name": h.id,
            "layer": "Harness",
            "src": h.src,
            "dst": h.dst,
            "length_mm": h.length_mm,
            "connector": h.connector,
            "wires": [w.model_dump() for w in h.wires],
        }

    com = spec.center_of_mass(poses)
    hull = convex_hull([(f["pos"][0], f["pos"][1]) for f in feet])
    margin = point_in_hull_margin(hull, (com[0], com[1]))
    zs = [p[2] for p in geom_world.values()]
    xs = [p[0] for p in geom_world.values()]
    total = spec.total_mass_g()
    target = float(default("targets.max_mass_g", 7000))
    return {
        "name": spec.name,
        "units": {"length": "mm", "mass": "g", "angle": "deg"},
        "bodies": bodies,
        "joints": joints,
        "sensors": sensors,
        "harness": harness,
        "feet": feet,
        "com": _round(com),
        "support_polygon": [[round(x, 2), round(y, 2)] for x, y in hull],
        "com_margin_mm": round(margin, 2),
        "mass": {
            "total_g": round(total, 1),
            "target_g": target,
            "over_budget": total > target,
            "by_layer_g": {k: round(v, 1) for k, v in spec.mass_by_layer().items()},
            "by_body_g": {b.id: round(b.mass_g(), 1) for b in spec.bodies},
        },
        "extents": {
            "height_mm": round(max(zs) if zs else 0.0, 1),
            "length_mm": round((max(xs) - min(xs)) if xs else 0.0, 1),
            "target_height_mm": default("targets.height_mm"),
            "target_length_mm": default("targets.body_length_mm"),
        },
        "elements": elements,
        "layers": {k: v.model_dump() for k, v in (layers or {}).items()},
        "warnings": list(design.warnings),
        "genome": design.genome.model_dump(mode="json"),
    }
