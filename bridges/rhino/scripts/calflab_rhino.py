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


# ---------------------------------------------------------------------- settings
def _settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "calflab", "rhino_bridge.json")


def load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"url": DEFAULT_URL}


def save_settings(settings):
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
    doc.redraw()
    return {"objects": count, "annotations": lines, "layers": len(layer_index), "blocks": len(build_list["blocks"])}


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
    """A Brep for a primitive in its local frame (centred on the origin, axis +Z)."""
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
        return self.doc.Objects.AddBrep(brep, self._attrs(layer, name, user_text, color))

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
    joined = rg.Mesh()
    for obj in objects:
        geom = obj.Geometry
        if isinstance(geom, rg.Mesh):
            joined.Append(geom)
        elif isinstance(geom, rg.Brep):
            for m in rg.Mesh.CreateFromBrep(geom, rg.MeshingParameters.Default) or []:
                joined.Append(m)
        elif isinstance(geom, rg.Extrusion):
            for m in rg.Mesh.CreateFromBrep(geom.ToBrep(), rg.MeshingParameters.Default) or []:
                joined.Append(m)
        elif isinstance(geom, rg.SubD):
            joined.Append(rg.Mesh.CreateFromSubD(geom, 2))
    joined.Faces.ConvertQuadsToTriangles()
    joined.Vertices.CombineIdentical(True, True)
    vertices = [[v.X, v.Y, v.Z] for v in joined.Vertices]
    faces = [[f.A, f.B, f.C] for f in joined.Faces]
    return vertices, faces


def push(objects, target, name="", layer="Skin"):
    """Send edited geometry back to CALFLAB as an explicit geometry override."""
    vertices, faces = selection_to_mesh(objects)
    if not faces:
        raise BridgeError("The selection has no surface geometry to push.")
    return request(
        "/api/bridge/rhino/push",
        {"target": target, "name": name, "layer": layer, "vertices": vertices, "faces": faces, "source": CLIENT},
        timeout=60.0,
    )


def guess_target(objects):
    """The body id recorded on the selection by CalflabPull, if any."""
    for obj in objects:
        body = obj.Attributes.GetUserString("calflab.body")
        if body:
            return body
    return ""
