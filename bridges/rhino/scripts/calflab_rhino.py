#! python3
"""CALFLAB <-> Rhino 8 bridge (shared module for the Calflab* commands).

This file deliberately contains no design logic: the CALFLAB server sends an
explicit build list (layers, block definitions, objects with transforms and
user text) and this module follows it. It uses only the Python standard
library plus RhinoCommon, so nothing needs to be pip-installed inside Rhino.

``build`` works against a ``DocAdapter`` so it can be tested outside Rhino.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000"
CLIENT = "rhino"
ID_KEY = "calflab.id"
#: set for one Rhino process (by ``calflab bridge rhino --check``) to talk to another lab than the saved one
URL_ENV = "CALFLAB_RHINO_URL"


# ---------------------------------------------------------------------- settings
def _settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "calflab", "rhino_bridge.json")


def load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            settings = json.load(fh)
    except (OSError, ValueError):
        settings = {"url": DEFAULT_URL}
    if os.environ.get(URL_ENV):
        settings["url"] = os.environ[URL_ENV]
    return settings


def save_settings(settings):
    if os.environ.get(URL_ENV):
        return  # a check run against another lab must not repoint the Rhino you are working in
    path = _settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


def server_url():
    return load_settings().get("url", DEFAULT_URL).rstrip("/")


# ---------------------------------------------------------------------- http
class BridgeError(Exception):
    pass


def request(path, body=None, timeout=20.0, url=None):
    """GET (body is None) or POST JSON to the CALFLAB server."""
    full = (url or server_url()) + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(full, data=data, method="GET" if body is None else "POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-calflab-client", CLIENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
        except ValueError:
            message = str(exc)
        raise BridgeError(message)
    except (urllib.error.URLError, OSError) as exc:
        raise BridgeError(
            "No CALFLAB server at %s (%s). Start it with: calflab lab" % (url or server_url(), exc)
        )


# ---------------------------------------------------------------------- building
class DocAdapter(object):
    """What ``build`` needs from a document. ``RhinoDocAdapter`` is the real one."""

    def ensure_layer(self, path, color):
        raise NotImplementedError

    def ensure_block(self, name, description, geoms):
        raise NotImplementedError

    def delete_objects_with_key(self, key):
        raise NotImplementedError

    def add_primitive(self, shape, size, xform, layer, name, color, user_text):
        raise NotImplementedError

    def add_block_instance(self, block, xform, layer, name, user_text):
        raise NotImplementedError

    def add_mesh_asset(self, asset, xform, layer, name, user_text):
        raise NotImplementedError

    def add_line(self, a, b, layer, name, user_text):
        raise NotImplementedError

    def add_polyline(self, points, layer, name, user_text):
        raise NotImplementedError

    def redraw(self):
        raise NotImplementedError


def build(doc, build_list, annotations=True):
    """Replace all CALFLAB objects in ``doc`` with the ones in ``build_list``."""
    layer_index = {}
    for layer in build_list["layers"]:
        layer_index[layer["path"]] = doc.ensure_layer(layer["path"], layer["color"])
    for block in build_list["blocks"]:
        doc.ensure_block(block["name"], block.get("description", ""), block["geoms"])
    doc.delete_objects_with_key(build_list.get("id_key", ID_KEY))
    count = 0
    for obj in build_list["objects"]:
        layer = layer_index[obj["layer"]]
        kind = obj["kind"]
        if kind == "block":
            doc.add_block_instance(obj["block"], obj["xform"], layer, obj["name"], obj["user_text"])
        elif kind == "mesh":
            doc.add_mesh_asset(obj["asset"], obj["xform"], layer, obj["name"], obj["user_text"])
        else:
            doc.add_primitive(obj["shape"], obj["size"], obj["xform"], layer, obj["name"], obj.get("color"), obj["user_text"])
        count += 1
    lines = 0
    if annotations:
        for ann in build_list.get("annotations", []):
            doc.add_line(ann["from"], ann["to"], layer_index[ann["layer"]], ann["id"], ann["user_text"])
            lines += 1
    curves = 0
    for curve in build_list.get("curves", []):  # harness routes
        doc.add_polyline(curve["points"], layer_index[curve["layer"]], curve["id"], curve["user_text"])
        curves += 1
    doc.redraw()
    return {
        "objects": count,
        "annotations": lines,
        "curves": curves,
        "layers": len(layer_index),
        "blocks": len(build_list["blocks"]),
    }


# ---------------------------------------------------------------------- Rhino implementation
def _hex_to_color(hex_color):
    import System

    h = (hex_color or "#b9c0c9").lstrip("#")
    return System.Drawing.Color.FromArgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _transform(m):
    import Rhino

    t = Rhino.Geometry.Transform(1.0)
    for i in range(4):
        for j in range(4):
            setattr(t, "M%d%d" % (i, j), float(m[i][j]))
    return t


def _primitive_brep(shape, size):
    """A NURBS Brep for a primitive in its local frame (centred on the origin, axis +Z).

    Spheres, capsules and cylinders start as surfaces of revolution. The
    server's transforms are rounded to six decimals, so they are not exactly
    rigid; a revolved capsule can come out of such a transform invalid (its
    profile segments no longer meet) and Rhino then refuses to add it. NURBS
    surfaces take any affine transform. Found in Rhino 8.34: the shanks
    vanished when the shank length changed.
    """
    brep = _exact_primitive_brep(shape, size)
    brep.MakeValidForV2()  # converts every surface to NURBS
    return brep


def _exact_primitive_brep(shape, size):
    import Rhino

    rg = Rhino.Geometry
    a, b, c = float(size[0]), float(size[1]), float(size[2])
    plane = rg.Plane.WorldXY
    if shape == "box":
        return rg.Box(plane, rg.Interval(-a / 2, a / 2), rg.Interval(-b / 2, b / 2), rg.Interval(-c / 2, c / 2)).ToBrep()
    if shape == "sphere":
        return rg.Sphere(rg.Point3d.Origin, a).ToBrep()
    if shape == "ellipsoid":
        brep = rg.Sphere(rg.Point3d.Origin, 1.0).ToNurbsSurface().ToBrep()
        brep.Transform(rg.Transform.Scale(plane, a, b, c))
        return brep
    base = rg.Plane(rg.Point3d(0, 0, -b / 2), rg.Vector3d.ZAxis)
    if shape == "capsule":
        try:  # revolve a line with two quarter arcs about Z
            top, bottom = rg.Point3d(0, 0, b / 2 + a), rg.Point3d(0, 0, -b / 2 - a)
            profile = rg.PolyCurve()
            profile.Append(rg.Arc(bottom, rg.Vector3d.XAxis, rg.Point3d(a, 0, -b / 2)))
            profile.Append(rg.LineCurve(rg.Point3d(a, 0, -b / 2), rg.Point3d(a, 0, b / 2)))
            profile.Append(rg.Arc(rg.Point3d(a, 0, b / 2), rg.Vector3d.ZAxis, top))
            rev = rg.RevSurface.Create(profile, rg.Line(bottom, top))
            brep = rg.Brep.CreateFromRevSurface(rev, False, False)
            if brep is not None and brep.IsValid:
                return brep
        except Exception:
            pass
    return rg.Cylinder(rg.Circle(base, a), b).ToBrep(True, True)


class RhinoDocAdapter(DocAdapter):
    def __init__(self, doc=None):
        import Rhino

        self.Rhino = Rhino
        self.doc = doc or Rhino.RhinoDoc.ActiveDoc

    def ensure_layer(self, path, color):
        Rhino, doc = self.Rhino, self.doc
        parts = path.split("::")
        parent_id = None
        index = -1
        for depth in range(len(parts)):
            full = "::".join(parts[: depth + 1])
            index = doc.Layers.FindByFullPath(full, -1)
            if index < 0:
                layer = Rhino.DocObjects.Layer()
                layer.Name = parts[depth]
                if parent_id is not None:
                    layer.ParentLayerId = parent_id
                if depth == len(parts) - 1:
                    layer.Color = _hex_to_color(color)
                index = doc.Layers.Add(layer)
            parent_id = doc.Layers[index].Id
        return index

    def ensure_block(self, name, description, geoms):
        Rhino, doc = self.Rhino, self.doc
        breps = [_primitive_brep(g["shape"], g["size"]) for g in geoms]
        attrs = [Rhino.DocObjects.ObjectAttributes() for _ in breps]
        existing = doc.InstanceDefinitions.Find(name)
        if existing is not None:
            doc.InstanceDefinitions.ModifyGeometry(existing.Index, breps, attrs)
            return existing.Index
        return doc.InstanceDefinitions.Add(name, description, Rhino.Geometry.Point3d.Origin, breps, attrs)

    def delete_objects_with_key(self, key):
        doc = self.doc
        doomed = [o.Id for o in doc.Objects if o.Attributes.GetUserString(key)]
        for oid in doomed:
            doc.Objects.Delete(oid, True)
        return len(doomed)

    def _attrs(self, layer, name, user_text, color=None):
        Rhino = self.Rhino
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = layer
        attrs.Name = name
        for k, v in user_text.items():
            attrs.SetUserString(k, str(v))
        if color:
            attrs.ObjectColor = _hex_to_color(color)
            attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        return attrs

    def add_primitive(self, shape, size, xform, layer, name, color, user_text):
        brep = _primitive_brep(shape, size)
        brep.Transform(_transform(xform))
        oid = self.doc.Objects.AddBrep(brep, self._attrs(layer, name, user_text, color))
        if str(oid) == "00000000-0000-0000-0000-000000000000":
            raise BridgeError("Rhino rejected the geometry of %s (%s %s)" % (name, shape, list(size)))
        return oid

    def add_block_instance(self, block, xform, layer, name, user_text):
        idef = self.doc.InstanceDefinitions.Find(block)
        return self.doc.Objects.AddInstanceObject(idef.Index, _transform(xform), self._attrs(layer, name, user_text))

    def add_mesh_asset(self, asset, xform, layer, name, user_text):
        Rhino = self.Rhino
        data = request("/api/bridge/mesh?asset=" + urllib.request.quote(asset))
        mesh = Rhino.Geometry.Mesh()
        for v in data["vertices"]:
            mesh.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for f in data["faces"]:
            mesh.Faces.AddFace(int(f[0]), int(f[1]), int(f[2]))
        mesh.Normals.ComputeNormals()
        mesh.Transform(_transform(xform))
        return self.doc.Objects.AddMesh(mesh, self._attrs(layer, name, user_text))

    def add_line(self, a, b, layer, name, user_text):
        rg = self.Rhino.Geometry
        line = rg.Line(rg.Point3d(a[0], a[1], a[2]), rg.Point3d(b[0], b[1], b[2]))
        return self.doc.Objects.AddLine(line, self._attrs(layer, name, user_text))

    def add_polyline(self, points, layer, name, user_text):
        rg = self.Rhino.Geometry
        pts = [rg.Point3d(float(p[0]), float(p[1]), float(p[2])) for p in points]
        oid = self.doc.Objects.AddPolyline(pts, self._attrs(layer, name, user_text))
        if str(oid) == "00000000-0000-0000-0000-000000000000":
            raise BridgeError("Rhino rejected the harness route %s" % name)
        return oid

    def redraw(self):
        self.doc.Views.Redraw()


# ---------------------------------------------------------------------- commands
def connect(url=None):
    """Check the server and remember its URL."""
    settings = load_settings()
    if url:
        settings["url"] = url.rstrip("/")
    health = request("/api/health", url=settings["url"])
    save_settings(settings)
    return health


def pull(annotations=True):
    """Fetch the current design and rebuild it in the active Rhino document."""
    build_list = request("/api/bridge/rhino/scene")
    doc = RhinoDocAdapter()
    undo = doc.doc.BeginUndoRecord("CalflabPull")
    try:
        summary = build(doc, build_list, annotations)
    finally:
        doc.doc.EndUndoRecord(undo)
    summary["revision"] = build_list.get("revision")
    return summary


def selection_to_mesh(objects):
    """Triangle mesh (vertices, faces) of Rhino objects in world coordinates (mm)."""
    import Rhino

    rg = Rhino.Geometry
    vertices, faces = [], []
    for obj in objects:
        geom = obj.Geometry
        mesh = None
        if isinstance(geom, rg.Mesh):
            mesh = _tidy_mesh(geom.DuplicateMesh())
            if not mesh.IsClosed:
                mesh = _heal(mesh)
        elif isinstance(geom, rg.Extrusion):
            mesh = _mesh_of_brep(geom.ToBrep())
        elif isinstance(geom, rg.Brep):
            mesh = _mesh_of_brep(geom)
        elif isinstance(geom, rg.SubD):
            mesh = _tidy_mesh(rg.Mesh.CreateFromSubD(geom, 2))
        if mesh is None:
            continue
        base = len(vertices)
        for i in range(mesh.Vertices.Count):
            p = mesh.Vertices.Point3dAt(i)  # double precision where the mesh has it
            vertices.append([p.X, p.Y, p.Z])
        faces.extend([f.A + base, f.B + base, f.C + base] for f in mesh.Faces)
    return vertices, faces


def _tidy_mesh(mesh):
    mesh.Faces.ConvertQuadsToTriangles()
    mesh.Vertices.CombineIdentical(True, True)
    return mesh


def _naked_edges(mesh):
    edges = mesh.GetNakedEdges()
    return len(edges) if edges else 0


def _heal(mesh):
    """Close hairline seams of a mesh that should be closed (returns the mesh, healed or not)."""
    try:
        healed = mesh.DuplicateMesh()
        healed.HealNakedEdges(0.01)
        healed.Vertices.CombineIdentical(True, True)
        if healed.IsClosed:
            return healed
    except Exception:
        pass
    return mesh


def _mesh_of_brep(brep):
    """One triangle mesh of a Brep, closed if the Brep is.

    Rhino meshes a polysurface face by face. With some settings the faces of
    a closed polysurface do not meet exactly along every edge, and a very
    small part can come back with no mesh at all. So several settings are
    tried, in this order, and the first mesh that is closed is used; if none
    is, the one with the fewest open edges, after healing hairline seams.
    Returns None if Rhino cannot mesh the object at all.
    """
    import Rhino

    rg = Rhino.Geometry
    doc = Rhino.RhinoDoc.ActiveDoc
    settings = [
        lambda: rg.MeshingParameters.Default,
        lambda: rg.MeshingParameters.QualityRenderMesh,
        lambda: rg.MeshingParameters.DocumentCurrentSetting(doc),
        lambda: rg.MeshingParameters.DefaultAnalysisMesh,
        lambda: rg.MeshingParameters.FastRenderMesh,
        lambda: rg.MeshingParameters.Minimal,
    ]
    best = None
    for make in settings:
        try:
            params = make()
            try:
                params.JaggedSeams = False
                params.ClosedObjectPostProcess = True
            except Exception:
                pass
            pieces = rg.Mesh.CreateFromBrep(brep, params)
        except Exception:
            continue
        if not pieces:
            continue
        mesh = rg.Mesh()
        for piece in pieces:
            mesh.Append(piece)
        _tidy_mesh(mesh)
        if mesh.Faces.Count == 0:
            continue
        if mesh.IsClosed or not brep.IsSolid:
            return mesh
        mesh = _heal(mesh)
        if mesh.IsClosed:
            return mesh
        if best is None or _naked_edges(mesh) < _naked_edges(best):
            best = mesh
    return best


def selection_solid(objects):
    """What Rhino itself says about the selection as a solid: are all objects
    closed, and their exact total volume (mm^3). CALFLAB measures the mesh; it
    uses this only to word its warning and to report the meshing error."""
    import Rhino

    rg = Rhino.Geometry
    closed, volume = bool(objects), 0.0
    for obj in objects:
        geom = obj.Geometry
        if isinstance(geom, rg.Extrusion):
            geom = geom.ToBrep()
        if isinstance(geom, rg.Brep):
            ok = geom.IsSolid
        elif isinstance(geom, rg.Mesh):
            ok = geom.IsClosed
        elif isinstance(geom, rg.SubD):
            ok = geom.IsSolid
        else:
            ok = False
        closed = closed and bool(ok)
        if ok:
            try:
                props = rg.VolumeMassProperties.Compute(geom)
                volume += abs(props.Volume) if props is not None else 0.0
            except Exception:
                pass
    return {"closed": closed, "volume_mm3": volume if closed else 0.0}


def push(objects, target, name="", layer="Skin", material=""):
    """Send edited geometry back to CALFLAB as an explicit geometry override.

    On the Structure layer a closed solid gives the part's mass (volume x the
    density of its material); the reply says whether it did. There each object
    is sent as its own solid with its own ``calflab.material`` user text, so a
    part of printed plastic and steel rods is weighed solid by solid;
    ``material`` is for the objects that carry none. An object's
    ``calflab.print.*`` user text (infill, perimeters, line_width) is sent as
    written; the server then weighs that solid as printed with infill.
    """
    body = {"target": target, "name": name, "layer": layer, "material": material, "source": CLIENT}
    if layer == "Structure":
        parts = []
        for obj in objects:
            vertices, faces = selection_to_mesh([obj])
            if faces:
                parts.append({"name": obj.Attributes.Name or "", "material": own_material(obj), "vertices": vertices,
                              "faces": faces, "host": selection_solid([obj]), "print": own_print(obj)})
        if not parts:
            raise BridgeError("The selection has no surface geometry to push.")
        body["parts"] = parts
    else:
        vertices, faces = selection_to_mesh(objects)
        if not faces:
            raise BridgeError("The selection has no surface geometry to push.")
        body.update({"vertices": vertices, "faces": faces, "host": selection_solid(objects)})
    return request("/api/bridge/rhino/push", body, timeout=60.0)


def push_report(reply, target):
    """The lines CalflabPush prints for a reply of ``push`` (all wording comes from the server's fields)."""
    lines = ["CALFLAB: pushed %d faces as override %s on %s" % (reply["faces"], reply["override"], target)]
    if reply.get("mass_from_geometry"):
        wording = "CALFLAB: %s structure mass is now %.1f g (%.1f cm3 of %s; the estimate it replaces was %.1f g)"
        if reply.get("estimate") == "infill":  # printed with infill: the number is an estimate, and says so
            wording = ("CALFLAB: %s structure mass is now %.1f g, an INFILL ESTIMATE (%.1f cm3 outer volume of %s; "
                       "the envelope estimate it replaces was %.1f g)")
        line = wording % (
            target, reply["mass_g"], reply["solid"]["volume_mm3"] / 1000.0, reply["material"], reply.get("replaced_g") or 0.0)
        lines.append(line)
        if reply.get("infill"):
            lines.append("CALFLAB:   %s" % reply["infill"]["label"])
        if reply["solid"].get("volume_source") == "host" and reply.get("volume_error") is not None:
            lines.append("CALFLAB: the volume is Rhino's exact one (the mesh alone would be %+.2f %% off)" % (reply["volume_error"] * 100.0))
        for n, solid in enumerate(reply.get("solids") or [], start=1):  # a part of several solids, each with its own material
            lines.append("CALFLAB:   solid %d (%s): %.1f cm3 of %s = %.1f g%s" % (
                n, solid["name"], solid["volume_mm3"] / 1000.0, solid["material"], solid["mass_g"],
                " (infill estimate)" if solid.get("infill") else ""))
            if solid.get("infill"):
                lines.append("CALFLAB:     %s" % solid["infill"]["label"])
        if reply.get("com_world_mm"):
            lines.append("CALFLAB: %s structure centre of mass is at (%.1f, %.1f, %.1f) mm" % ((target,) + tuple(reply["com_world_mm"])))
    if reply.get("estimate_note"):
        lines.append("CALFLAB: %s" % reply["estimate_note"])
    if reply.get("warning"):
        lines.append("CALFLAB WARNING: %s" % reply["warning"])
    if reply.get("note"):
        lines.append("CALFLAB: %s" % reply["note"])
    return lines


def structure_materials():
    """Keys of the structure materials in the library (for the CalflabPush prompt)."""
    return [m["key"] for m in request("/api/bridge/rhino/materials")["materials"]]


def own_material(obj):
    """The object's ``calflab.material`` user text ("" if it has none)."""
    return obj.Attributes.GetUserString("calflab.material") or ""


def own_print(obj):
    """The object's ``calflab.print.*`` user text as {name: text} (empty if it has none)."""
    prefix = "calflab.print."
    strings = obj.Attributes.GetUserStrings()
    return dict((key[len(prefix):], strings[key]) for key in strings.AllKeys if key.startswith(prefix))


def guess_material(objects):
    """The material recorded on the selection: your own ``calflab.material``
    user text, or the one CalflabPull wrote."""
    for obj in objects:
        material = obj.Attributes.GetUserString("calflab.material")
        if material:
            return material
    return ""


def guess_target(objects):
    """The body id recorded on the selection by CalflabPull, if any."""
    for obj in objects:
        body = obj.Attributes.GetUserString("calflab.body")
        if body:
            return body
    return ""


# ---------------------------------------------------------------------- a whole modelled robot (ADR-062)
MODEL_TIMEOUT_S = 900.0


def _layer_path(doc, obj):
    return doc.Layers[obj.Attributes.LayerIndex].FullPath


def model_setup():
    """Create the CALFLAB::Model layers (one per body) and, on CALFLAB::Model::Joints,
    an axis line per joint where the pulled calf has it. A joint that already has
    a line there is left alone, so running this again never moves your lines."""
    import Rhino

    layout = request("/api/bridge/rhino/model")
    doc = RhinoDocAdapter()
    undo = doc.doc.BeginUndoRecord("CalflabModelSetup")
    try:
        index = dict((layer["path"], doc.ensure_layer(layer["path"], layer["color"])) for layer in layout["layers"])
        have = set()
        joints_layer = layout["joints_layer"]
        for obj in doc.doc.Objects:
            path = _layer_path(doc.doc, obj)
            if (path == joints_layer or path.startswith(joints_layer + "::")) and isinstance(obj.Geometry, Rhino.Geometry.Curve):
                have.add(model_joint(obj, layout))
        added = []
        for axis in layout["axes"]:
            if axis["id"] in have:
                continue
            doc.add_line(axis["from"], axis["to"], index[layout["joints_layer"]], axis["id"], {layout["joint_key"]: axis["id"]})
            added.append(axis["id"])
    finally:
        doc.doc.EndUndoRecord(undo)
    doc.redraw()
    return {"layout": layout, "added": added, "kept": sorted(have)}


def collect_model():
    """What is on the CALFLAB::Model layers: (layout, axis lines, solids). A solid's
    body is its ``calflab.body`` user text, else the body layer it is on (or under)."""
    import Rhino

    rg = Rhino.Geometry
    layout = request("/api/bridge/rhino/model")
    doc = Rhino.RhinoDoc.ActiveDoc
    root, joints_layer = layout["root_layer"], layout["joints_layer"]
    lines, solids, not_lines = [], [], 0
    for obj in doc.Objects:
        path = _layer_path(doc, obj)
        if path != root and not path.startswith(root + "::"):
            continue
        if path == joints_layer or path.startswith(joints_layer + "::"):
            if isinstance(obj.Geometry, rg.Curve):
                lines.append(obj)
            else:
                not_lines += 1
            continue
        solids.append(obj)
    layout["not_lines"] = not_lines  # objects on the Joints layer that are not curves: they are not axis lines
    return layout, lines, solids


def model_body(obj, layout):
    """The body id a solid on the model layers belongs to ("" if it is on none).

    The body layer it is on (or under) decides. ``calflab.body`` user text is
    only read for a solid that is on no body layer: a copy or mirror of an
    object keeps the user text of its original, and CalflabPull writes
    ``calflab.body`` onto everything it creates, so the text is often stale.
    """
    import Rhino

    rest = _layer_path(Rhino.RhinoDoc.ActiveDoc, obj)[len(layout["root_layer"]):].lstrip(":")
    on_layer = rest.split("::")[0] if rest else ""
    if on_layer in [b["id"] for b in layout["bodies"]]:
        return on_layer
    return obj.Attributes.GetUserString("calflab.body") or on_layer


def model_joint(obj, layout):
    """The joint id of an axis line. The object's name decides when it is a
    joint id (a line you drew, or copied and renamed); otherwise its
    ``calflab.joint`` user text, which a copy keeps from its original."""
    name = (obj.Attributes.Name or "").strip()
    if name in [a["id"] for a in layout["axes"]]:
        return name
    return (obj.Attributes.GetUserString(layout["joint_key"]) or "").strip() or name


def model_summary(layout, lines, solids):
    """What CalflabPushModel is about to send, as lines of text: which joint each
    axis line is for and which solids are feet, so a wrong tag shows before the push."""
    out = []
    joints = sorted(model_joint(o, layout) or "(unnamed)" for o in lines)
    out.append("axis lines (%d): %s" % (len(joints), ", ".join(joints) or "none"))
    known = [a["id"] for a in layout["axes"]]
    for joint in sorted(set(joints)):
        if joints.count(joint) > 1:
            out.append("  %d lines are for %s: keep one, or rename the others (object name = joint id)" % (joints.count(joint), joint))
        if joint not in known:
            out.append("  %s is not a joint of this design. The joints are: %s" % (joint, ", ".join(known)))
    if layout.get("not_lines"):
        out.append("  %d objects on %s are not curves and are ignored: an axis must be a line" % (layout["not_lines"], layout["joints_layer"]))
    feet = {}
    for obj in solids:
        if is_foot(obj, layout):
            feet.setdefault(model_body(obj, layout) or "(no body layer)", []).append(obj.Attributes.Name or "unnamed")
    out.append("foot solids (%d): %s" % (
        sum(len(v) for v in feet.values()),
        "; ".join("%s: %s" % (body, ", ".join(names)) for body, names in sorted(feet.items())) or "none tagged calflab.foot = yes"))
    return out


def is_foot(obj, layout):
    return (obj.Attributes.GetUserString(layout["foot_key"]) or "").strip().lower() in ("yes", "true", "1", "y")


def set_user_text(objects, values):
    """Write user text {key: text} onto objects (None removes the key)."""
    import Rhino

    doc = Rhino.RhinoDoc.ActiveDoc
    for obj in objects:
        attrs = obj.Attributes.Duplicate()
        for key, text in values.items():
            if text is None:
                attrs.DeleteUserString(key)
            else:
                attrs.SetUserString(key, str(text))
        doc.Objects.ModifyAttributes(obj, attrs, True)


def push_model(check_only=False, name="Rhino model"):
    """Send everything on the CALFLAB::Model layers; returns the server's report.

    The server checks and measures it all, and stores nothing unless every
    solid is closed, on a body and has a material. ``calflab.id`` user text is
    removed from the objects sent: CalflabPull deletes whatever carries it.
    """
    import Rhino

    layout, lines, objects = collect_model()
    doc = Rhino.RhinoDoc.ActiveDoc
    pulled = [o for o in lines + objects if o.Attributes.GetUserString(ID_KEY)]
    if pulled:
        set_user_text(pulled, {ID_KEY: None})
    joints = []
    stale = 0
    for obj in lines:
        joint = model_joint(obj, layout)
        if joint and obj.Attributes.GetUserString(layout["joint_key"]) != joint:
            set_user_text([obj], {layout["joint_key"]: joint})  # the tag now says what the name says
            stale += 1
        a, b = obj.Geometry.PointAtStart, obj.Geometry.PointAtEnd
        joints.append({"id": joint, "from": [a.X, a.Y, a.Z], "to": [b.X, b.Y, b.Z]})
    for obj in objects:
        own, body = obj.Attributes.GetUserString("calflab.body"), model_body(obj, layout)
        if own and body and own != body:
            set_user_text([obj], {"calflab.body": body})  # a copy's leftover: the layer decides
            stale += 1
    solids = []
    for n, obj in enumerate(objects, start=1):
        vertices, faces = selection_to_mesh([obj])
        solids.append({"body": model_body(obj, layout), "name": obj.Attributes.Name or "solid %d" % n,
                       "type": str(obj.Geometry.ObjectType), "layer": _layer_path(doc, obj),
                       "material": own_material(obj), "foot": is_foot(obj, layout), "vertices": vertices, "faces": faces,
                       "host": selection_solid([obj]), "print": own_print(obj) or None})
    body = {"file": os.path.basename(doc.Path or "") or (doc.Name or ""), "name": name, "source": CLIENT,
            "check_only": bool(check_only), "joints": joints, "solids": solids}
    reply = request("/api/bridge/rhino/model", body, timeout=MODEL_TIMEOUT_S)
    reply["unprotected"] = len(pulled)
    reply["relabelled"] = stale
    return reply
