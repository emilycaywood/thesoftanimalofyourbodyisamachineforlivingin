"""Geometry exporters: glTF, STL, 3MF, Rhino .3dm, MJCF, URDF."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel

from calflab import units as u
from calflab.export.meshes import hex_to_rgba, spec_meshes
from calflab.model.spec import LAYER_COLORS, LAYERS, RobotSpec
from calflab.plugins import ExportContext, Exporter, register
from calflab.schema import P


class _LayerParams(BaseModel):
    layers: list[str] = P(
        default_factory=lambda: ["Structure", "Actuators", "Transmission", "Electronics", "Sensors", "Skin"],
        ui="json",
        desc="Layers to include.",
    )


@register
class GltfExporter(Exporter):
    """Whole design as binary glTF (mm, Z-up), one node per element ID."""

    key = "gltf"
    label = "glTF (.glb)"
    description = "Meshes of the design in the standing pose, named by stable ID."
    formats = ["glb"]
    Params = _LayerParams

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        import trimesh

        scene = trimesh.Scene()
        for gm in spec_meshes(ctx.spec, self.params.layers, ctx.selection, ctx.project_dir):  # type: ignore[attr-defined]
            color = gm.geom.color or LAYER_COLORS.get(gm.geom.layer)
            gm.mesh.visual.face_colors = hex_to_rgba(color, 110 if gm.geom.layer == "Skin" else 255)
            scene.add_geometry(gm.mesh, node_name=gm.geom.id, geom_name=gm.geom.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{ctx.design_name}.glb"
        path.write_bytes(scene.export(file_type="glb"))
        return [path]


class _MeshParams(BaseModel):
    layers: list[str] = P(default_factory=lambda: ["Structure"], ui="json", desc="Layers to include.")
    per_part: bool = P(True, desc="One file per body (named by its ID) instead of one assembly file.")


def _export_meshes(ctx: ExportContext, out_dir: Path, params: BaseModel, ext: str) -> list[Path]:
    import trimesh

    out_dir.mkdir(parents=True, exist_ok=True)
    meshes = spec_meshes(ctx.spec, params.layers, ctx.selection, ctx.project_dir)  # type: ignore[attr-defined]
    if not meshes:
        raise ValueError("Nothing to export: no geometry on the chosen layers/selection")
    paths: list[Path] = []
    if params.per_part:  # type: ignore[attr-defined]
        by_body: dict[str, list] = {}
        for gm in meshes:
            by_body.setdefault(gm.body_id, []).append(gm.mesh)
        for body_id, parts in by_body.items():
            mesh = trimesh.util.concatenate(parts)
            path = out_dir / f"{ctx.design_name}_{body_id}.{ext}"
            path.write_bytes(mesh.export(file_type=ext))
            paths.append(path)
    else:
        mesh = trimesh.util.concatenate([gm.mesh for gm in meshes])
        path = out_dir / f"{ctx.design_name}.{ext}"
        path.write_bytes(mesh.export(file_type=ext))
        paths.append(path)
    return paths


@register
class StlExporter(Exporter):
    key = "stl"
    label = "STL meshes"
    description = "Envelope meshes of the parts (mm). For printable parts use the CAD exporters."
    formats = ["stl"]
    category = "fabrication"
    Params = _MeshParams

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        return _export_meshes(ctx, out_dir, self.params, "stl")


@register
class ThreeMfExporter(Exporter):
    key = "threemf"
    label = "3MF meshes"
    description = "Envelope meshes of the parts as 3MF (mm)."
    formats = ["3mf"]
    category = "fabrication"
    Params = _MeshParams

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        return _export_meshes(ctx, out_dir, self.params, "3mf")


def write_3dm(spec: RobotSpec, path: Path, layers: list[str] | None = None, selection: list[str] | None = None,
              project_dir: Path | None = None) -> Path:
    """Layered .3dm: CALFLAB::<Layer> layers, one mesh per geom, stable IDs as user text."""
    import rhino3dm as r3

    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Millimeters
    parent = r3.Layer()
    parent.Name = "CALFLAB"
    model.Layers.Add(parent)
    parent_id = model.Layers[0].Id
    index: dict[str, int] = {}
    for name in LAYERS:
        layer = r3.Layer()
        layer.Name = name
        layer.ParentLayerId = parent_id
        rgba = hex_to_rgba(LAYER_COLORS[name])
        layer.Color = (rgba[0], rgba[1], rgba[2], 255)
        index[name] = model.Layers.Add(layer)
    for gm in spec_meshes(spec, layers, selection, project_dir):
        mesh = r3.Mesh()
        for v in gm.mesh.vertices:
            mesh.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for f in gm.mesh.faces:
            mesh.Faces.AddFace(int(f[0]), int(f[1]), int(f[2]))
        mesh.Normals.ComputeNormals()
        attr = r3.ObjectAttributes()
        attr.LayerIndex = index[gm.geom.layer]
        attr.Name = gm.geom.id
        attr.SetUserString("calflab.id", gm.geom.id)
        attr.SetUserString("calflab.body", gm.body_id)
        attr.SetUserString("calflab.layer", gm.geom.layer)
        if gm.geom.component:
            attr.SetUserString("calflab.component", gm.geom.component)
        model.Objects.AddMesh(mesh, attr)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(path), 7):
        raise OSError(f"rhino3dm could not write {path}")
    return path


@register
class Rhino3dmExporter(Exporter):
    key = "rhino_3dm"
    label = "Rhino (.3dm)"
    description = "Layered Rhino file: CALFLAB layer tree, element IDs as object names and user text."
    formats = ["3dm"]
    Params = _LayerParams

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        return [write_3dm(ctx.spec, out_dir / f"{ctx.design_name}.3dm", self.params.layers, ctx.selection, ctx.project_dir)]  # type: ignore[attr-defined]


@register
class MjcfExporter(Exporter):
    key = "mjcf"
    label = "MuJoCo MJCF (.xml)"
    description = "The simulation model compiled from the design (SI units)."
    formats = ["xml"]
    category = "simulation"

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        from calflab.sim.mjcf import compile_mjcf

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{ctx.design_name}.mjcf.xml"
        path.write_text(compile_mjcf(ctx.spec, ctx.library).xml, encoding="utf-8")
        return [path]


def spec_to_urdf(spec: RobotSpec) -> str:
    """URDF with primitive visuals/collisions (capsules become cylinders). SI units."""
    robot = ET.Element("robot", name=spec.name)

    def origin(parent: ET.Element, pos, quat) -> None:  # type: ignore[no-untyped-def]
        import math

        w, x, y, z = quat
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        ET.SubElement(
            parent,
            "origin",
            xyz=" ".join(f"{u.mm_to_m(v):.6g}" for v in pos),
            rpy=f"{roll:.6g} {pitch:.6g} {yaw:.6g}",
        )

    for b in spec.bodies:
        link = ET.SubElement(robot, "link", name=b.id)
        mass = u.g_to_kg(b.mass_g())
        if mass > 0:
            inertial = ET.SubElement(link, "inertial")
            ET.SubElement(inertial, "mass", value=f"{mass:.6g}")
            i = max(mass * 1e-3, 1e-8)  # placeholder isotropic inertia; MuJoCo computes the real one
            ET.SubElement(inertial, "inertia", ixx=f"{i:.4g}", iyy=f"{i:.4g}", izz=f"{i:.4g}", ixy="0", ixz="0", iyz="0")
        for g in b.geoms:
            if g.shape == "mesh":
                continue
            for tag in (["visual"] + (["collision"] if g.role != "visual" else [])):
                el = ET.SubElement(link, tag, name=g.id)
                origin(el, g.pos, g.quat)
                geo = ET.SubElement(el, "geometry")
                a, bb, c = (u.mm_to_m(v) for v in g.size)
                if g.shape == "box":
                    ET.SubElement(geo, "box", size=f"{a:.6g} {bb:.6g} {c:.6g}")
                elif g.shape in ("sphere", "ellipsoid"):
                    ET.SubElement(geo, "sphere", radius=f"{a:.6g}")
                else:
                    ET.SubElement(geo, "cylinder", radius=f"{a:.6g}", length=f"{bb + (2 * a if g.shape == 'capsule' else 0):.6g}")
    joints_by_body = {j.body: j for j in spec.joints if j.type in ("hinge", "slide")}
    for b in spec.bodies:
        if b.parent is None:
            continue
        j = joints_by_body.get(b.id)
        jtype = "fixed" if j is None else ("revolute" if j.type == "hinge" else "prismatic")
        jel = ET.SubElement(robot, "joint", name=j.id if j else f"fixed.{b.id}", type=jtype)
        ET.SubElement(jel, "parent", link=b.parent)
        ET.SubElement(jel, "child", link=b.id)
        origin(jel, b.pos, b.quat)
        if j is not None:
            ET.SubElement(jel, "axis", xyz=" ".join(f"{v:.6g}" for v in j.axis))
            ET.SubElement(
                jel,
                "limit",
                lower=f"{u.deg_to_rad(j.range_deg[0]):.6g}",
                upper=f"{u.deg_to_rad(j.range_deg[1]):.6g}",
                effort="10",
                velocity="6",
            )
    ET.indent(robot)
    return '<?xml version="1.0"?>\n' + ET.tostring(robot, encoding="unicode")


@register
class UrdfExporter(Exporter):
    key = "urdf"
    label = "URDF"
    description = "Kinematic tree with primitive geometry for other robotics tools."
    formats = ["urdf"]
    category = "simulation"

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{ctx.design_name}.urdf"
        path.write_text(spec_to_urdf(ctx.spec), encoding="utf-8")
        return [path]
