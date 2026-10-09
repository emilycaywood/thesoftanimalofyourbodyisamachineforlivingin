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
    material: str = "",
    host: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a world-space mesh (mm, standing pose) as a body-local GLB asset and
    register it as a geometry override on ``target`` (an undoable command).

    The mesh is measured as a solid here (ADR-050): closedness, volume, centre
    of mass and inertia in the body frame go into the override. On the
    Structure layer a closed solid then gives the part's mass as volume x the
    density of ``material`` (empty = the part's material); an open one is kept
    for display and reported in ``warning``.

    ``host`` is what the sending program says about the selection
    (``{"closed": bool, "volume_mm3": float}``). Its exact volume is used for
    the mass when it agrees with the mesh volume within 5 % (a meshed curved
    solid is a little small); a larger difference is reported and the mesh
    volume is kept.
    """
    import trimesh

    from calflab.app.lab import LabError
    from calflab.model.solid import HOST_VOLUME_TOLERANCE, analyze_mesh, use_host_volume

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
    solid = analyze_mesh(local, f)
    volume_error = use_host_volume(solid, float((host or {}).get("volume_mm3") or 0.0)) if layer == "Structure" else None
    mesh = trimesh.Trimesh(vertices=local, faces=f, process=False)
    stamp = now_iso().replace(":", "").replace("-", "")
    rel = f"assets/sculpts/{slugify(target)}-{stamp}.glb"
    path = lab.project.path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(trimesh.Scene(mesh).export(file_type="glb"))
    res = lab.execute(
        "add_geometry_override",
        {"target": target, "asset": rel, "name": name or f"{target} sculpt", "layer": layer, "source": source,
         "material": material, "solid": solid.model_dump(mode="json")},
        client=source,
    )
    out: dict[str, Any] = {
        "asset": rel,
        "override": res["result"]["override"],
        "vertices": len(v),
        "faces": len(f),
        "layer": layer,
        "solid": solid.model_dump(mode="json"),
        "mass_from_geometry": False,
        "warning": "",
    }
    if layer != "Structure":
        out["note"] = f"A {layer} push changes the look only: the part keeps its estimated {layer.lower()} mass."
        return out
    st = next(row for row in lab.scene()["mass"]["breakdown"]["bodies"] if row["body"] == target)["structure"]
    out.update({"mass_g": st["mass_g"], "material": st["material"], "replaced_g": st["replaced_g"]})
    if st["source"] == "geometry":
        out["mass_from_geometry"] = True
        if volume_error is not None:
            out["volume_error"] = round(volume_error, 5)  # mesh volume against the sender's exact volume
            if abs(volume_error) > HOST_VOLUME_TOLERANCE:
                out["warning"] = (
                    f"The mesh of the solid pushed onto {target} has a different volume ({volume_error * 100:+.1f} %) than "
                    "the sender reports for the object. The mesh volume is used; check the object for overlapping or "
                    "inside-out pieces."
                )
                lab.bus.emit("log", level="warn", source="push", message=out["warning"])
    else:
        out["warning"] = st["note"]
        if (host or {}).get("closed") and not solid.closed:
            out["warning"] += " Rhino reports the object as closed, so its render mesh has gaps: try _ExtractRenderMesh, or rebuild the joins."
        lab.bus.emit("log", level="warn", source="push", message=out["warning"])
    return out
