"""Parametric fabrication parts with build123d (OpenCascade).

Phase 1: one printable leg segment with an actuator mount and an embossed part
ID, exported as STEP, STL, 3MF and .3dm. build123d is an optional dependency
(``cad`` extra); it is imported lazily so the rest of CALFLAB works without it.

The bolt pattern and horn interface are NOT taken from a datasheet: they are
parameters with placeholder defaults and are reported as unverified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from calflab.plugins import ExportContext, Exporter, register
from calflab.schema import P

FIT_CLEARANCE_MM = {"press": 0.10, "snug": 0.20, "loose": 0.40}


def _b123d() -> Any:
    try:
        import build123d

        return build123d
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "build123d is an optional dependency. Install it with: calflab setup "
            "(or: uv sync --extra cad)"
        ) from exc


def build_leg_segment(
    length: float,
    radius: float,
    wall: float,
    actuator_dims: tuple[float, float, float],
    clearance: float,
    label: str,
    label_mode: str = "emboss",
    bolt_spacing: tuple[float, float] = (0.0, 0.0),
    bolt_diameter: float = 2.7,
    pivot_diameter: float = 8.0,
) -> Any:
    """Solid for a leg segment (mm). Local frame: proximal joint at the origin,
    segment extends along -Z, actuator pocket opens toward +Z.
    """
    bd = _b123d()
    C, MAX, MIN = bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN
    ax, ay, az = (float(v) for v in actuator_dims)
    px, py, pz = ax + 2 * clearance, ay + 2 * clearance, az
    bx, by, bz = px + 2 * wall, py + 2 * wall, pz + wall

    # actuator cradle: a block with a pocket open at the top
    block = bd.Box(bx, by, bz, align=(C, C, MAX))
    pocket = bd.Box(px, py, pz, align=(C, C, MAX))
    part = block - pocket

    # tube from under the cradle to the distal joint
    tube_len = max(length - bz, 10.0)
    outer = bd.Pos(0, 0, -bz) * bd.Cylinder(radius, tube_len, align=(C, C, MAX))
    inner = bd.Pos(0, 0, -bz - wall) * bd.Cylinder(max(radius - wall, 1.0), tube_len, align=(C, C, MAX))
    part = part + (outer - inner)

    # distal pivot bore (axis along Y)
    bore = bd.Pos(0, 0, -length) * bd.Rot(90, 0, 0) * bd.Cylinder(pivot_diameter / 2, radius * 4)
    boss = bd.Pos(0, 0, -length) * bd.Rot(90, 0, 0) * bd.Cylinder(pivot_diameter / 2 + wall, radius * 2)
    part = part + boss - bore

    # mounting holes through the cradle floor
    sx = bolt_spacing[0] or (ax * 0.6)
    sy = bolt_spacing[1] or (ay * 0.6)
    for ix in (-1, 1):
        for iy in (-1, 1):
            hole = bd.Pos(ix * sx / 2, iy * sy / 2, -pz) * bd.Cylinder(
                bolt_diameter / 2, wall * 3, align=(C, C, C)
            )
            part = part - hole

    # part label on the +X face of the cradle
    if label and label_mode != "none":
        size = max(3.0, min(bz * 0.35, by / max(len(label), 1) * 1.4))
        depth = 0.6
        face_x = bx / 2
        plane = bd.Plane(origin=(face_x, 0, -bz / 2), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
        try:
            sketch = plane * bd.Text(label, font_size=size, align=(C, C))
            if label_mode == "engrave":
                part = part - bd.extrude(sketch, amount=-depth)
            else:
                part = part + bd.extrude(sketch, amount=depth)
        except Exception:  # font problems must not block the part
            pass
    _ = MIN
    return part


def write_part_3dm(part: Any, path: Path, part_id: str, tolerance: float = 0.1) -> Path:
    """Tessellate a build123d shape into a layered .3dm with the part ID as user text."""
    import rhino3dm as r3

    verts, tris = part.tessellate(tolerance)
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Millimeters
    parent = r3.Layer()
    parent.Name = "CALFLAB"
    model.Layers.Add(parent)
    layer = r3.Layer()
    layer.Name = "Structure"
    layer.ParentLayerId = model.Layers[0].Id
    idx = model.Layers.Add(layer)
    mesh = r3.Mesh()
    for v in verts:
        mesh.Vertices.Add(float(v.X), float(v.Y), float(v.Z))
    for t in tris:
        mesh.Faces.AddFace(int(t[0]), int(t[1]), int(t[2]))
    mesh.Normals.ComputeNormals()
    attr = r3.ObjectAttributes()
    attr.LayerIndex = idx
    attr.Name = part_id
    attr.SetUserString("calflab.id", part_id)
    attr.SetUserString("calflab.kind", "fabrication-part")
    model.Objects.AddMesh(mesh, attr)
    if not model.Write(str(path), 7):
        raise OSError(f"rhino3dm could not write {path}")
    return path


@register
class LegSegmentCad(Exporter):
    """A printable leg segment with an actuator cradle and an embossed part ID."""

    key = "leg_segment_cad"
    label = "Leg segment (CAD)"
    description = "Printable leg segment with actuator mount and part label: STEP, STL, 3MF, .3dm."
    formats = ["step", "stl", "3mf", "3dm"]
    category = "fabrication"

    class Params(BaseModel):
        part: str = P("leg.fl.shank", desc="Leg segment element ID.")
        fit: Literal["press", "snug", "loose"] = P("snug", desc="Clearance preset around the actuator.")
        label_mode: Literal["emboss", "engrave", "none"] = P("emboss", desc="How the part ID is marked.")
        bolt_spacing_x: float = P(0.0, unit="mm", ge=0, le=100, desc="Mount hole spacing X (0 = placeholder 60% of housing). UNVERIFIED.")
        bolt_spacing_y: float = P(0.0, unit="mm", ge=0, le=100, desc="Mount hole spacing Y (0 = placeholder 60% of housing). UNVERIFIED.")
        bolt_diameter: float = P(2.7, unit="mm", ge=1, le=8, step=0.1, desc="Mount hole diameter (M2.5 clearance by default).")
        pivot_diameter: float = P(8.0, unit="mm", ge=3, le=20, step=0.5, desc="Distal pivot bore diameter.")
        mesh_tolerance: float = P(0.05, unit="mm", ge=0.005, le=1.0, desc="Tessellation tolerance for mesh formats.")

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        bd = _b123d()
        p = self.params
        part_id = (ctx.selection[0] if ctx.selection else p.part)  # type: ignore[attr-defined]
        table = ctx.element_params.get(part_id)
        if table is None or "length" not in table or "radius" not in table:
            raise ValueError(f"{part_id!r} is not a leg segment (needs length and radius parameters)")
        joint = next((j for j in ctx.spec.joints if j.body == part_id), None)
        act = ctx.spec.actuator_for(joint.id) if joint else None
        if act is None:
            raise ValueError(f"No actuator drives {part_id!r}")
        comp = ctx.library.actuator(act.component)
        wall = max(float(ctx.genes.get("wall_thickness", 2.0)), 1.2)
        clearance = FIT_CLEARANCE_MM[p.fit]  # type: ignore[attr-defined]
        part = build_leg_segment(
            length=table["length"].value,
            radius=table["radius"].value,
            wall=wall,
            actuator_dims=comp.dims_mm,
            clearance=clearance,
            label=part_id,
            label_mode=p.label_mode,  # type: ignore[attr-defined]
            bolt_spacing=(p.bolt_spacing_x, p.bolt_spacing_y),  # type: ignore[attr-defined]
            bolt_diameter=p.bolt_diameter,  # type: ignore[attr-defined]
            pivot_diameter=p.pivot_diameter,  # type: ignore[attr-defined]
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{ctx.design_name}_{part_id}"
        paths = [out_dir / f"{stem}.{ext}" for ext in ("step", "stl", "3mf", "3dm", "json")]
        bd.export_step(part, str(paths[0]))
        bd.export_stl(part, str(paths[1]), tolerance=p.mesh_tolerance)  # type: ignore[attr-defined]
        mesher = bd.Mesher()
        mesher.add_shape(part, linear_deflection=p.mesh_tolerance)  # type: ignore[attr-defined]
        mesher.add_meta_data("calflab", "part_id", part_id, "xs:string", must_preserve=False)
        mesher.write(str(paths[2]))
        write_part_3dm(part, paths[3], part_id, p.mesh_tolerance)  # type: ignore[attr-defined]
        bb = part.bounding_box()
        info = {
            "part_id": part_id,
            "actuator": {"id": act.id, "component": comp.key, "verified": comp.verified, "source": comp.source},
            "fit": p.fit,  # type: ignore[attr-defined]
            "clearance_mm": clearance,
            "wall_mm": wall,
            "volume_cm3": round(part.volume / 1000.0, 2),
            "bounding_box_mm": [round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)],
            "label": part_id if p.label_mode != "none" else None,  # type: ignore[attr-defined]
            "unverified": [
                "actuator housing dimensions (component library)",
                "mount hole pattern (placeholder unless bolt_spacing is set)",
            ],
        }
        paths[4].write_text(json.dumps(info, indent=2), encoding="utf-8")
        return paths
