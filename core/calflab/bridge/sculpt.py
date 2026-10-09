"""Store geometry pushed from Rhino (or Blender) as an explicit geometry override."""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.model.xform import quat_rotate, quat_to_matrix
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
    parts: list[dict[str, Any]] | None = None,
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

    ``parts`` sends the selection object by object instead of as one mesh:
    ``[{"name", "material", "vertices", "faces", "host"}]``. On the Structure
    layer each is then measured, stored and weighed as its own solid with its
    own material (empty = ``material``), so a part of printed plastic and
    steel rods gets the right mass, centre of mass and inertia (ADR-053). On
    any other layer the parts are simply joined.

    A part may carry ``print``: its ``calflab.print.*`` user text as sent
    (``{"infill": "15", "perimeters": "2", "line_width": "0.4"}``). Such a
    solid is weighed as printed, a shell of the wall thickness at full density
    plus the core at the infill percentage (ADR-054); the core is measured
    here and stored with the solid. A solid without print tags stays fully
    dense. Incomplete or unreadable tags refuse the push: no value is assumed.
    """
    import trimesh

    from calflab.app.lab import LabError
    from calflab.model.infill import PrintSettings, measure_core, parse_print_tags, scale_core
    from calflab.model.solid import HOST_VOLUME_TOLERANCE, analyze_mesh, use_host_volume

    design = lab.design()
    try:
        design.spec.body(target)
    except KeyError as exc:
        raise LabError(f"{target!r} is not a body; push geometry onto a body id such as 'head'") from exc
    parts = [p for p in parts or [] if p.get("faces")]

    def print_settings(part: dict[str, Any], label: str) -> PrintSettings | None:
        """The part's print tags, read before anything is stored."""
        if layer != "Structure" or not isinstance(part.get("print"), dict):
            return None
        try:
            return parse_print_tags(part["print"])
        except ValueError as exc:
            raise LabError(f"{label}: {exc}. Nothing was pushed.") from exc

    settings = [print_settings(part, f"Solid {str(part.get('name') or n)!r}") for n, part in enumerate(parts, start=1)]
    single: PrintSettings | None = None
    if len(parts) == 1 or (parts and layer != "Structure"):
        if len(parts) == 1:  # one solid: exactly a plain push with that object's material
            material = str(parts[0].get("material") or material)
            host = parts[0].get("host") if isinstance(parts[0].get("host"), dict) else host
            single = settings[0]
        vertices, faces = _joined(parts)
        parts = []
    p, q = design.spec.world_poses()[target]
    r = quat_to_matrix(q)
    stamp = now_iso().replace(":", "").replace("-", "")

    def measure(
        vertices: Any, faces: Any, host: dict[str, Any] | None, suffix: str, how: PrintSettings | None
    ) -> tuple[Any, float | None, str, dict[str, Any]]:
        """Analyse one world-space mesh in the body frame and store it; (solid, volume error, asset,
        print settings and measured core of a solid tagged with them)."""
        v = np.asarray(vertices, dtype=float)
        f = np.asarray(faces, dtype=int)
        if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3 or len(v) == 0:
            raise LabError("Pushed geometry must be a triangle mesh: vertices [[x,y,z]], faces [[a,b,c]]")
        local = (v - np.asarray(p)) @ r  # R^T (v - p), written for row vectors
        solid = analyze_mesh(local, f)
        error = use_host_volume(solid, float((host or {}).get("volume_mm3") or 0.0)) if layer == "Structure" else None
        rel = f"assets/sculpts/{slugify(target)}-{stamp}{suffix}.glb"
        path = lab.project.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(trimesh.Scene(trimesh.Trimesh(vertices=local, faces=f, process=False)).export(file_type="glb"))
        printed: dict[str, Any] = {}
        if how is not None:
            printed["print"] = how.model_dump(mode="json")
            if solid.closed:
                core = measure_core(local, f, how.wall_mm)
                if solid.volume_source == "host":  # the core follows the solid to the sender's exact volume
                    scale_core(core, solid.volume_mm3 / solid.mesh_volume_mm3)
                printed["print_core"] = core.model_dump(mode="json")
        return solid, error, rel, printed

    args: dict[str, Any] = {"target": target, "name": name or f"{target} sculpt", "layer": layer, "source": source,
                            "material": material}
    measured: list[dict[str, Any]] = []  # one row per solid of a several-solid push
    if parts:
        for n, part in enumerate(parts, start=1):
            part_host = part.get("host") if isinstance(part.get("host"), dict) else None
            solid, error, rel, printed = measure(part.get("vertices", []), part.get("faces", []), part_host, f"-{n}", settings[n - 1])
            measured.append({"name": str(part.get("name") or f"solid {n}"), "asset": rel, "material": str(part.get("material") or ""),
                             "solid": solid, "error": error, "host_closed": bool((part_host or {}).get("closed")), "printed": printed})
        args.update({
            "asset": measured[0]["asset"],
            "solids": [{**{k: m[k] for k in ("name", "asset", "material")}, "solid": m["solid"].model_dump(mode="json"), **m["printed"]}
                       for m in measured],
        })
        n_vertices = sum(len(part.get("vertices", [])) for part in parts)
        n_faces = sum(len(part.get("faces", [])) for part in parts)
        summary = {
            "closed": all(m["solid"].closed for m in measured),
            "volume_mm3": sum(m["solid"].volume_mm3 for m in measured),
            "volume_source": "host" if all(m["solid"].volume_source == "host" for m in measured) else "mesh",
        }
        volume_error = None
    else:
        solid, volume_error, rel, printed = measure(vertices, faces, host, "", single)
        args.update({"asset": rel, "solid": solid.model_dump(mode="json"),
                     "print_settings": printed.get("print", {}), "print_core": printed.get("print_core", {})})
        n_vertices, n_faces = len(vertices), len(faces)
        summary = solid.model_dump(mode="json")
    res = lab.execute("add_geometry_override", args, client=source)
    out: dict[str, Any] = {
        "asset": args["asset"],
        "override": res["result"]["override"],
        "vertices": n_vertices,
        "faces": n_faces,
        "layer": layer,
        "solid": summary,
        "mass_from_geometry": False,
        "warning": "",
    }
    if layer != "Structure":
        out["note"] = f"A {layer} push changes the look only: the part keeps its estimated {layer.lower()} mass."
        return out
    st = next(row for row in lab.scene()["mass"]["breakdown"]["bodies"] if row["body"] == target)["structure"]
    out.update({"mass_g": st["mass_g"], "material": st["material"] or st["material_label"], "materials": st["materials"],
                "replaced_g": st["replaced_g"]})
    warnings: list[str] = []
    if st["source"] in ("geometry", "infill"):
        out["mass_from_geometry"] = True
        if st["source"] == "infill":
            # the mass is an estimate of the printed part, not volume x density: every printout says so
            out["estimate"] = "infill"
            out["estimate_note"] = st["estimate_note"]
            if not measured:
                out["infill"] = st["solids"][0]["infill"]
        unused = sorted({key for row in st["solids"] for key in (row["infill"] or {}).get("ignored", [])})
        if unused:
            out["note"] = (f"{', '.join(unused)} {'is' if len(unused) == 1 else 'are'} not used: the infill estimate takes one wall "
                           "thickness all round (perimeters x line width).")
        if st["com_mm"] is not None:
            out["com_mm"] = st["com_mm"]  # body frame
            c = quat_rotate(q, tuple(st["com_mm"]))
            out["com_world_mm"] = [round(float(p[k]) + c[k], 2) for k in range(3)]  # as modelled (standing pose)
        if measured:
            rows = {s["id"]: s for s in st["solids"]}
            out["solids"] = []
            for n, m in enumerate(measured, start=1):
                row = rows[f"{target}.override.{out['override']}.{n}"]
                out["solids"].append(
                    {"name": m["name"], "material": row["material"], "mass_g": row["mass_g"],
                     "volume_mm3": m["solid"].volume_mm3, "volume_source": m["solid"].volume_source,
                     "volume_error": None if m["error"] is None else round(m["error"], 5), "infill": row["infill"]}
                )
        if volume_error is not None:
            out["volume_error"] = round(volume_error, 5)  # mesh volume against the sender's exact volume
        for label, error in [(f"solid {m['name']!r} pushed", m["error"]) for m in measured] or [("solid pushed", volume_error)]:
            if error is not None and abs(error) > HOST_VOLUME_TOLERANCE:
                warnings.append(
                    f"The mesh of the {label} onto {target} has a different volume ({error * 100:+.1f} %) than "
                    "the sender reports for the object. The mesh volume is used; check the object for overlapping or "
                    "inside-out pieces."
                )
    else:
        warnings.append(st["note"])
        gaps = [m["name"] for m in measured if m["host_closed"] and not m["solid"].closed]
        if measured and gaps:
            warnings.append(f"Rhino reports {', '.join(gaps)} as closed, so the render mesh has gaps: try _ExtractRenderMesh, or rebuild the joins.")
        elif not measured and (host or {}).get("closed") and not summary["closed"]:
            warnings.append("Rhino reports the object as closed, so its render mesh has gaps: try _ExtractRenderMesh, or rebuild the joins.")
    if any(warnings):
        out["warning"] = " ".join(w for w in warnings if w)
        lab.bus.emit("log", level="warn", source="push", message=out["warning"])
    return out


def _joined(parts: list[dict[str, Any]]) -> tuple[list[list[float]], list[list[int]]]:
    """Several meshes as one (vertices, faces)."""
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for part in parts:
        base = len(vertices)
        vertices.extend(part.get("vertices", []))
        faces.extend([[int(i) + base for i in face] for face in part.get("faces", [])])
    return vertices, faces
