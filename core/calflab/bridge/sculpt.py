"""Store geometry pushed from Rhino (or Blender) as an explicit geometry override."""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.model.xform import quat_to_matrix
from calflab.project.store import now_iso, slugify


def save_pushed_mesh(
    lab: Any,
    target: str,
    vertices: list[list[float]],
    faces: list[list[int]],
    name: str = "",
    layer: str = "Skin",
    source: str = "rhino",
) -> dict[str, Any]:
    """Save a world-space mesh (mm, standing pose) as a body-local GLB asset and
    register it as a geometry override on ``target`` (an undoable command)."""
    import trimesh

    from calflab.app.lab import LabError

    design = lab.design()
    try:
        design.spec.body(target)
    except KeyError as exc:
        raise LabError(f"{target!r} is not a body; push geometry onto a body id such as 'head'") from exc
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=int)
    if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3 or len(v) == 0:
        raise LabError("Pushed geometry must be a triangle mesh: vertices [[x,y,z]], faces [[a,b,c]]")
    p, q = design.spec.world_poses()[target]
    r = quat_to_matrix(q)
    local = (v - np.asarray(p)) @ r  # R^T (v - p), written for row vectors
    mesh = trimesh.Trimesh(vertices=local, faces=f, process=False)
    stamp = now_iso().replace(":", "").replace("-", "")
    rel = f"assets/sculpts/{slugify(target)}-{stamp}.glb"
    path = lab.project.path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(trimesh.Scene(mesh).export(file_type="glb"))
    res = lab.execute(
        "add_geometry_override",
        {"target": target, "asset": rel, "name": name or f"{target} sculpt", "layer": layer, "source": source},
        client=source,
    )
    return {"asset": rel, "override": res["result"]["override"], "vertices": len(v), "faces": len(f)}
