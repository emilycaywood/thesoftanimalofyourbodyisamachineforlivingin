"""RobotSpec primitives -> triangle meshes (mm), shared by mesh exporters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from calflab.model.spec import Geom, RobotSpec
from calflab.model.xform import matrix4


@dataclass
class GeomMesh:
    geom: Geom
    body_id: str
    mesh: Any  # trimesh.Trimesh in world coordinates (standing pose), mm


def geom_mesh(g: Geom, project_dir: Path | None = None) -> Any:
    """Mesh of one geom in its own local frame (before pos/quat)."""
    import trimesh

    a, b, c = g.size
    if g.shape == "box":
        return trimesh.creation.box(extents=(a, b, c))
    if g.shape == "sphere":
        return trimesh.creation.icosphere(subdivisions=3, radius=a)
    if g.shape == "capsule":
        return trimesh.creation.capsule(height=b, radius=a, count=[24, 24])
    if g.shape == "cylinder":
        return trimesh.creation.cylinder(radius=a, height=b, sections=32)
    if g.shape == "ellipsoid":
        m = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
        m.apply_scale((a, b, c))
        return m
    if g.shape == "mesh" and g.mesh and project_dir is not None:
        loaded = trimesh.load(project_dir / g.mesh, force="mesh")
        return loaded
    return None


def spec_meshes(
    spec: RobotSpec,
    layers: list[str] | None = None,
    selection: list[str] | None = None,
    project_dir: Path | None = None,
) -> list[GeomMesh]:
    """World-space meshes of every geom in the standing pose.

    ``selection`` may contain body ids or geom ids; empty = everything.
    """
    poses = spec.world_poses()
    sel = set(selection or [])
    out: list[GeomMesh] = []
    for body in spec.bodies:
        bp, bq = poses[body.id]
        tb = np.array(matrix4(bp, bq))
        for g in body.geoms:
            if layers and g.layer not in layers:
                continue
            if sel and body.id not in sel and g.id not in sel:
                continue
            m = geom_mesh(g, project_dir)
            if m is None:
                continue
            m.apply_transform(tb @ np.array(matrix4(g.pos, g.quat)))
            out.append(GeomMesh(geom=g, body_id=body.id, mesh=m))
    return out


def hex_to_rgba(color: str | None, alpha: int = 255) -> list[int]:
    c = (color or "#b9c0c9").lstrip("#")
    try:
        return [int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha]
    except ValueError:
        return [185, 192, 201, alpha]
