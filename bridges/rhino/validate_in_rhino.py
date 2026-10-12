#! python3
"""Check of the CALFLAB Rhino commands, run inside Rhino 8 against a live lab.

    calflab bridge rhino --check            (the lab must be running)

which starts Rhino with this macro (the script runs twice, with the real
CalflabPush command typed in between):

    _-ScriptEditor _Run <this file>
    CalflabPush head Skin head_sculpt
    _-ScriptEditor _Run <this file>

Pass 1 installs the aliases (CalflabInstall), connects, pulls, and models a
stand-in "sculpted" head shell that it leaves selected. Pass 2 checks that the
push arrived as a geometry override, that a second pull brings it back as a
mesh in the same place and leaves the user's own object alone. It then pushes
three Breps onto the trunk's Structure layer (a 100 mm box, a sphere, a box
with a face removed) and checks that the closed ones give the trunk its mass
as volume x density and the open one is refused with a warning. Then it lays
out the model layers (CalflabModelSetup), moves the axis lines, adds a trunk
box, a shank and a foot, and pushes them whole (ADR-062). Last it turns
CalflabLiveSync on, edits a gene on the server and waits for Rhino to follow.
It undoes its edits, writes a JSON report and closes Rhino.

Use a scratch project: the check adds (and undoes) an override and a gene edit.
"""
import json
import os
import runpy
import time
import traceback

import Rhino
import scriptcontext as sc

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
REPORT = os.environ.get("CALFLAB_RHINO_REPORT") or os.path.join(os.environ.get("TEMP", HERE), "calflab_rhino_check.json")
STATE = REPORT + ".pass1"
TARGET = "head"
SCULPT_NAME = "calflab validation sculpt"
GENE = "shank_length"
TOL_MM = 0.5
SYNC_TIMEOUT_S = 25.0

import sys  # noqa: E402

sys.path.insert(0, SCRIPTS)
import calflab_rhino as cr  # noqa: E402


def run_command_script(name):
    runpy.run_path(os.path.join(SCRIPTS, name + ".py"), run_name="__main__")


def calflab_objects(doc):
    return [o for o in doc.Objects if o.Attributes.GetUserString(cr.ID_KEY)]


def bbox_of(objects):
    """Bounding box from render-quality meshes. (Rhino's "accurate" box of a
    NURBS sphere or capsule Brep only covers its seam, so it is not used.)"""
    rg = Rhino.Geometry
    box = rg.BoundingBox.Empty
    for o in objects:
        g = o.Geometry
        if isinstance(g, rg.Brep):
            for m in rg.Mesh.CreateFromBrep(g, rg.MeshingParameters.QualityRenderMesh) or []:
                box = rg.BoundingBox.Union(box, m.GetBoundingBox(False))
        else:
            box = rg.BoundingBox.Union(box, g.GetBoundingBox(False))
    return box


def box_list(box):
    return [round(v, 3) for v in (box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y, box.Max.Z)]


def check_geometry(doc):
    """Every pulled object exists, every solid has real extent, spheres are where the server says."""
    build_list = cr.request("/api/bridge/rhino/scene")
    by_id = {o.Attributes.GetUserString(cr.ID_KEY): o for o in calflab_objects(doc)}
    curves = build_list.get("curves", [])
    expected = (
        [o["id"] for o in build_list["objects"]]
        + [a["id"] for a in build_list.get("annotations", [])]
        + [c["id"] for c in curves]
    )
    missing = [i for i in expected if i not in by_id]
    assert not missing, "objects in the build list but not in Rhino: %s" % missing[:6]
    flat, worst, spheres = [], 0.0, 0
    for o in build_list["objects"]:
        box = bbox_of([by_id[o["id"]]])
        if o["kind"] != "block" and min(box.Diagonal.X, box.Diagonal.Y, box.Diagonal.Z) < 0.5:
            flat.append(o["id"])
        if o["kind"] == "primitive" and o["shape"] == "sphere":
            spheres += 1
            r, x = float(o["size"][0]), o["xform"]
            want = [x[0][3] - r, x[1][3] - r, x[2][3] - r, x[0][3] + r, x[1][3] + r, x[2][3] + r]
            worst = max(worst, max(abs(a - b) for a, b in zip(want, box_list(box))))
    assert not flat, "objects with no thickness in Rhino: %s" % flat[:6]
    assert worst <= TOL_MM, "a sphere is %.3f mm away from where the server put it" % worst
    assert curves, "the build list has no harness routes"
    curve_error = 0.0
    for c in curves:
        obj = by_id[c["id"]]
        layer = doc.Layers[obj.Attributes.LayerIndex].FullPath
        assert layer == c["layer"], "%s is on layer %s, not %s" % (c["id"], layer, c["layer"])
        pts = c["points"]
        want = sum(
            sum((pts[i + 1][k] - pts[i][k]) ** 2 for k in range(3)) ** 0.5 for i in range(len(pts) - 1)
        )
        curve_error = max(curve_error, abs(obj.Geometry.GetLength() - want))
    assert curve_error <= TOL_MM, "a harness curve is %.3f mm longer or shorter than its route" % curve_error
    return {
        "objects": len(expected),
        "spheres_checked": spheres,
        "sphere_bbox_error_mm": round(worst, 4),
        "harness_curves": len(curves),
        "harness_length_error_mm": round(curve_error, 4),
    }


def check_solid_push(doc):
    """Closed Breps pushed onto Structure weigh volume x density; an open one is refused, with a warning."""
    import math

    rg = Rhino.Geometry
    scene = cr.request("/api/scene")
    trunk = [b for b in scene["bodies"] if b["id"] == "trunk"][0]
    density = [m for m in scene["materials"] if m["key"] == "pla"][0]["density_g_cm3"]
    assert "pla" in cr.structure_materials(), "the material list for the CalflabPush prompt has no pla"
    c = rg.Point3d(trunk["pos"][0], trunk["pos"][1], trunk["pos"][2])
    side = rg.Interval(-50.0, 50.0)
    box = rg.Box(rg.Plane(c, rg.Vector3d.ZAxis), side, side, side).ToBrep()
    open_box = box.DuplicateBrep()
    open_box.Faces.RemoveAt(0)
    shapes = [
        ("box", box, 1000.0 * density),
        ("sphere", rg.Sphere(c, 40.0).ToBrep(), 4.0 / 3.0 * math.pi * 40.0**3 / 1000.0 * density),
        ("open_box", open_box, None),
    ]
    out = {}
    for name, brep, want in shapes:
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.Name = "calflab validation " + name
        attrs.SetUserString("calflab.material", "pla")
        oid = doc.Objects.AddBrep(brep, attrs)
        obj = doc.Objects.FindId(oid)
        assert cr.guess_material([obj]) == "pla", "calflab.material user text was not read"
        try:
            reply = cr.push([obj], "trunk", attrs.Name, "Structure", cr.guess_material([obj]))
        finally:
            doc.Objects.Delete(oid, True)
        cr.request("/api/undo", {})
        row = {"closed": reply["solid"]["closed"], "from_geometry": reply["mass_from_geometry"],
               "mass_g": reply.get("mass_g"), "volume_error": reply.get("volume_error"), "warning": reply.get("warning", ""),
               "report": cr.push_report(reply, "trunk")}
        out[name] = row
        if want is None:
            assert not row["from_geometry"] and "not used for mass" in row["warning"], "an open Brep was used for mass: %s" % row
        else:
            assert row["from_geometry"], "a closed %s was not used for mass: %s" % (name, row["warning"])
            # exact for the sphere too: the mass uses Rhino's volume, not the (slightly small) mesh volume
            assert abs(row["mass_g"] - want) <= 0.02, "%s weighs %.2f g, expected %.2f g" % (name, row["mass_g"], want)

    # two solids in one push, each with its own calflab.material (ADR-053): a pla box and a petg rod beside it
    other = [m for m in scene["materials"] if m["key"] == "petg"][0]["density_g_cm3"]
    rod_c = rg.Point3d(c.X + 100.0, c.Y, c.Z)
    rod = rg.Box(rg.Plane(rod_c, rg.Vector3d.ZAxis), rg.Interval(-5.0, 5.0), rg.Interval(-5.0, 5.0), side).ToBrep()
    ids = []
    for name, brep, material in (("body", box, "pla"), ("rod", rod, "petg")):
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.Name = name
        attrs.SetUserString("calflab.material", material)
        ids.append(doc.Objects.AddBrep(brep, attrs))
    try:
        reply = cr.push([doc.Objects.FindId(i) for i in ids], "trunk", "calflab validation two solids", "Structure", "")
    finally:
        for i in ids:
            doc.Objects.Delete(i, True)
    cr.request("/api/undo", {})
    want = 1000.0 * density + 10.0 * other
    x = 100.0 * 10.0 * other / want  # centre of mass along the line from the box to the rod, weighted by mass
    out["two_solids"] = {"mass_g": reply.get("mass_g"), "solids": reply.get("solids"), "com_world_mm": reply.get("com_world_mm"),
                         "warning": reply.get("warning", ""), "report": cr.push_report(reply, "trunk")}
    assert reply["mass_from_geometry"], "two closed solids were not used for mass: %s" % reply.get("warning")
    assert [s["material"] for s in reply["solids"]] == ["pla", "petg"], "the solids did not keep their own materials"
    assert abs(reply["mass_g"] - want) <= 0.02, "two solids weigh %.2f g, expected %.2f g" % (reply["mass_g"], want)
    assert abs(reply["com_world_mm"][0] - (c.X + x)) <= 0.05, "the centre of mass is not weighted by the solids' masses"

    # a solid tagged with print settings (ADR-054): weighed as a 0.8 mm shell plus the core at 15 %, and marked as an estimate
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.Name = "printed"
    attrs.SetUserString("calflab.material", "pla")
    for key, value in (("infill", "15"), ("perimeters", "2"), ("line_width", "0.4")):
        attrs.SetUserString("calflab.print." + key, value)
    oid = doc.Objects.AddBrep(box, attrs)
    try:
        obj = doc.Objects.FindId(oid)
        assert cr.own_print(obj) == {"infill": "15", "perimeters": "2", "line_width": "0.4"}, "calflab.print.* user text was not read"
        reply = cr.push([obj], "trunk", "calflab validation infill", "Structure", "")
    finally:
        doc.Objects.Delete(oid, True)
    cr.request("/api/undo", {})
    want = (100.0**3 - 98.4**3 + 0.15 * 98.4**3) / 1000.0 * density
    out["infill"] = {"mass_g": reply.get("mass_g"), "infill": reply.get("infill"), "warning": reply.get("warning", ""),
                     "report": cr.push_report(reply, "trunk")}
    assert reply.get("estimate") == "infill", "a solid with print tags was not weighed as printed: %s" % out["infill"]
    assert abs(reply["mass_g"] - want) <= 0.002 * want, "the printed cube weighs %.2f g, expected %.2f g" % (reply["mass_g"], want)
    assert "INFILL ESTIMATE" in out["infill"]["report"][1], "the printout does not mark the mass as an infill estimate"
    return out


def check_model_push(doc):
    """CalflabModelSetup, then a model on the CALFLAB::Model layers pushed whole (ADR-062): the joints
    follow the moved axis lines, the solids give mass, the tagged solid becomes the foot, and a
    pull leaves the model alone."""
    rg = Rhino.Geometry
    first = cr.model_setup()
    layout = first["layout"]
    assert first["added"] and not first["kept"], "CalflabModelSetup added no axis lines: %s" % first
    again = cr.model_setup()
    assert not again["added"] and sorted(again["kept"]) == sorted(first["added"]), "a second CalflabModelSetup added lines again"
    for layer in layout["layers"]:
        assert doc.Layers.FindByFullPath(layer["path"], -1) >= 0, "layer %s was not created" % layer["path"]
    _, lines, solids = cr.collect_model()
    assert len(lines) == len(layout["axes"]) and not solids, "the model layers hold %d lines, %d solids" % (len(lines), len(solids))
    shift = rg.Vector3d(3.0, 0.0, -4.0)
    for obj in lines:  # the researcher moves each line onto the real axis
        doc.Objects.Transform(obj, rg.Transform.Translation(shift), True)
    scene = cr.request("/api/scene")
    density = [m for m in scene["materials"] if m["key"] == "pla"][0]["density_g_cm3"]
    pos = dict((b["id"], b["pos"]) for b in scene["bodies"])
    foot = [f for f in scene["feet"] if f["body"] == "leg.fl.shank"][0]["pos"]

    def add(layer, brep, name, tags):
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.Name = name
        attrs.LayerIndex = doc.Layers.FindByFullPath(layout["root_layer"] + "::" + layer, -1)
        for key, value in tags.items():
            attrs.SetUserString(key, value)
        return doc.Objects.AddBrep(brep, attrs)

    def box(c, x, y, z):
        return rg.Box(rg.Plane(rg.Point3d(c[0], c[1], c[2]), rg.Vector3d.ZAxis),
                      rg.Interval(-x / 2.0, x / 2.0), rg.Interval(-y / 2.0, y / 2.0), rg.Interval(-z / 2.0, z / 2.0)).ToBrep()

    ids = [
        add("trunk", box(pos["trunk"], 100.0, 40.0, 30.0), "check trunk", {"calflab.material": "pla"}),
        add("leg.fl.shank", rg.Sphere(rg.Point3d(foot[0], foot[1], foot[2] + 30.0), 8.0).ToBrep(), "check shank",
            {"calflab.material": "pla", "calflab.id": "left over from a pull"}),
        add("leg.fl.shank", box((foot[0], foot[1], 3.0), 20.0, 14.0, 6.0), "check foot",
            {"calflab.material": "pla", layout["foot_key"]: "yes"}),
    ]
    # detailed parts: a plate with a row of drilled holes and filleted edges, and a part well under a millimetre
    hp = pos["head"]
    plate = box(hp, 30.0, 20.0, 4.0)
    for i in range(5):
        axis = rg.Line(rg.Point3d(hp[0] - 12.0 + 6.0 * i, hp[1], hp[2] - 5.0), rg.Point3d(hp[0] - 12.0 + 6.0 * i, hp[1], hp[2] + 5.0))
        drill = rg.Cylinder(rg.Circle(rg.Plane(axis.From, rg.Vector3d.ZAxis), 1.1), 10.0).ToBrep(True, True)
        cut = rg.Brep.CreateBooleanDifference(plate, drill, 0.001)
        assert cut and len(cut) == 1, "the test plate could not be drilled"
        plate = cut[0]
    filleted = rg.Brep.CreateFilletEdges(plate, list(range(plate.Edges.Count))[:4], [0.6] * 4, [0.6] * 4,
                                         rg.BlendType.Fillet, rg.RailType.RollingBall, 0.001)
    if filleted and len(filleted) == 1 and filleted[0].IsSolid:
        plate = filleted[0]
    assert plate.IsSolid, "the test plate is not a closed polysurface"
    ids.append(add("head", plate, "check drilled plate", {"calflab.material": "pla"}))
    ids.append(add("head", rg.Sphere(rg.Point3d(hp[0], hp[1], hp[2] + 10.0), 0.3).ToBrep(), "check tiny part", {"calflab.material": "pla"}))
    for name in ("check drilled plate", "check tiny part"):
        obj = [o for o in doc.Objects if o.Attributes.Name == name][0]
        v, fc = cr.selection_to_mesh([obj])
        assert fc, "%s: Rhino gave no mesh" % name
    # what a person does: mirror a tagged foot to the other side (the copy keeps calflab.body of its original),
    # and replace an axis line by one drawn and named by hand (no calflab.joint user text)
    other = [f for f in scene["feet"] if f["body"] == "leg.fr.shank"][0]["pos"]
    ids.append(add("leg.fr.shank", box((other[0], other[1], 3.0), 20.0, 14.0, 6.0), "check foot copy",
                   {"calflab.material": "pla", layout["foot_key"]: "yes", "calflab.body": "leg.fl.shank"}))
    old = [o for o in cr.collect_model()[1] if cr.model_joint(o, layout) == "joint.fr.knee"][0]
    a, b = old.Geometry.PointAtStart, old.Geometry.PointAtEnd
    doc.Objects.Delete(old.Id, True)
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.Name = "joint.fr.knee"
    attrs.LayerIndex = doc.Layers.FindByFullPath(layout["joints_layer"], -1)
    doc.Objects.AddLine(rg.Line(b, a), attrs)
    assert not cr.model_setup()["added"], "CalflabModelSetup added a line for a joint that has a hand-drawn, named one"
    out = {"layers": len(layout["layers"]), "axis_lines": len(lines)}
    try:
        summary = cr.model_summary(*cr.collect_model())
        assert "leg.fl.shank: check foot" in summary[-1] and "leg.fr.shank: check foot copy" in summary[-1], summary
        check = cr.push_model(check_only=True)
        assert check["ok"] and not check["stored"], "the check-only push reported: %s" % check["errors"]
        reply = cr.push_model()
        assert reply["ok"] and reply["stored"], "the model was not stored: %s" % reply["errors"]
        assert reply["unprotected"] == 0 and check["unprotected"] == 1, "calflab.id was not removed from the model's solid"
        assert check["relabelled"] == 2 and reply["relabelled"] == 0, "leftover user text was not corrected: %s" % check["relabelled"]
        rows = dict((j["joint"], j) for j in reply["joints"])
        worst = max(abs(j["distance_mm"] - 5.0) for j in rows.values())
        assert len(rows) == len(lines) and worst <= 0.01, "joints are not 5 mm from the pulled calf's: %s" % sorted(
            (j["joint"], j["distance_mm"]) for j in rows.values())
        bodies = dict((b["body"], b) for b in reply["bodies"])
        want = 100.0 * 40.0 * 30.0 / 1000.0 * density
        assert abs(bodies["trunk"]["mass_g"] - want) <= 0.02, "the trunk box weighs %.2f g, expected %.2f g" % (bodies["trunk"]["mass_g"], want)
        assert bodies["leg.fl.shank"]["foot"] and bodies["leg.fl.shank"]["hulls"] == 2, "the tagged solid is not the foot: %s" % bodies["leg.fl.shank"]
        assert bodies["leg.fr.shank"]["foot"], "a mirrored foot on the fr shank layer was not taken as that leg's foot"
        feet = dict((f["geom"], f["lowest_z_mm"]) for f in reply["feet"])
        assert abs(feet["leg.fl.shank.foot"]) <= 0.05, "the foot's lowest point is not where it was modelled: %s" % feet
        s = reply["structure"]
        assert s["free_bodies"] == 1 and s["loose_solids"] == 0 and s["solids"] == 6, "structure: %s" % s
        geometry = cr.request("/api/scene")["geometry"]
        assert geometry["source"] == "rhino_model" and geometry["collision"] == "hulls", "the scene does not say it uses the model"
        cr.pull()
        _, lines_after, solids_after = cr.collect_model()
        assert len(lines_after) == len(lines) and len(solids_after) == 6, "CalflabPull touched the model layers"
        out.update({"joints": len(rows), "joint_distance_error_mm": round(worst, 4), "trunk_mass_g": bodies["trunk"]["mass_g"],
                    "feet": feet, "structure": s, "report": reply["lines"][:3], "label": geometry["label"]})
    finally:
        for oid in ids:
            doc.Objects.Delete(oid, True)
        for obj in cr.collect_model()[1]:
            doc.Objects.Delete(obj.Id, True)
    cr.request("/api/undo", {})
    assert cr.request("/api/scene")["geometry"]["source"] == "parametric", "undo did not bring the parametric calf back"
    cr.pull()
    return out


def finish(report):
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    if os.path.exists(STATE):
        os.remove(STATE)
    print("CALFLAB_RHINO_CHECK " + json.dumps(report))
    if os.environ.get("CALFLAB_RHINO_KEEP_OPEN"):
        return
    Rhino.RhinoDoc.ActiveDoc.Modified = False
    Rhino.RhinoApp.Exit()


# ---------------------------------------------------------------------- pass 1
def pass1():
    import rhinoscriptsyntax as rs

    doc = Rhino.RhinoDoc.ActiveDoc
    rg = Rhino.Geometry
    rep = {"rhino": str(Rhino.RhinoApp.Version)}

    run_command_script("CalflabInstall")
    aliases = {}
    for name in ("CalflabConnect", "CalflabPull", "CalflabPush", "CalflabLiveSync", "CalflabModelSetup", "CalflabTag",
                 "CalflabPushModel"):
        macro = rs.AliasMacro(name) if rs.IsAlias(name) else None
        aliases[name] = bool(macro) and os.path.isfile(macro.split('"')[1])
    rep["install"] = aliases
    assert all(aliases.values()), "CalflabInstall did not register every alias: %s" % aliases

    health = cr.connect()
    rep["connect"] = {"project": health["project"], "revision": health["revision"]}

    summary = cr.pull()
    rep["pull"] = summary
    rep["geometry"] = check_geometry(doc)
    head =[o for o in calflab_objects(doc) if o.Attributes.GetUserString("calflab.body") == TARGET]
    assert head, "CalflabPull created no objects for body %r" % TARGET
    box = bbox_of(head)

    # stand-in sculpt: an ellipsoid shell 8 % larger than the head, pinched towards the muzzle (+X)
    c, d = box.Center, box.Diagonal
    mesh = rg.Mesh.CreateFromSphere(rg.Sphere(rg.Point3d.Origin, 1.0), 24, 16)
    for i in range(mesh.Vertices.Count):
        v = mesh.Vertices[i]
        taper = 1.0 - 0.25 * max(v.X, 0.0)
        mesh.Vertices.SetVertex(i, c.X + v.X * d.X * 0.54, c.Y + v.Y * d.Y * 0.54 * taper, c.Z + v.Z * d.Z * 0.54 * taper)
    mesh.Normals.ComputeNormals()
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.Name = SCULPT_NAME
    layer = doc.Layers.FindByFullPath("Sculpt", -1)
    attrs.LayerIndex = layer if layer >= 0 else doc.Layers.Add("Sculpt", System_color(200, 120, 90))
    oid = doc.Objects.AddMesh(mesh, attrs)
    doc.Objects.UnselectAll()
    doc.Objects.Select(oid)
    doc.Views.Redraw()
    rep["sculpt"] = {"faces": mesh.Faces.Count, "bbox": box_list(mesh.GetBoundingBox(True))}
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(rep, fh)
    print("CALFLAB check: pass 1 done, sculpt selected for CalflabPush")


def System_color(r, g, b):
    import System

    return System.Drawing.Color.FromArgb(r, g, b)


# ---------------------------------------------------------------------- pass 2
def pass2(rep):
    doc = Rhino.RhinoDoc.ActiveDoc
    state = cr.request("/api/state")
    overrides = [o for o in state.get("overrides", []) if o.get("target") == TARGET and o.get("kind") == "geometry"]
    assert overrides, "CalflabPush created no geometry override on %r (prompts not answered?)" % TARGET
    rep["push"] = {"override": overrides[-1].get("id"), "name": overrides[-1].get("name"), "enabled": overrides[-1].get("enabled")}

    summary = cr.pull()
    sculpts = [o for o in doc.Objects if o.Attributes.Name == SCULPT_NAME]
    assert len(sculpts) == 1, "the user's own sculpt object was touched by the second pull"
    pulled = [o for o in calflab_objects(doc)
              if o.Attributes.GetUserString("calflab.body") == TARGET and isinstance(o.Geometry, Rhino.Geometry.Mesh)]
    assert pulled, "the pushed mesh did not come back on the second pull"
    want, got = rep["sculpt"]["bbox"], box_list(bbox_of(pulled))
    err = max(abs(a - b) for a, b in zip(want, got))
    rep["repull"] = {"objects": summary["objects"], "mesh_objects": len(pulled), "bbox_error_mm": round(err, 4)}
    assert err <= TOL_MM, "pushed mesh came back %.3f mm away from where it was modelled" % err

    rep["solid"] = check_solid_push(doc)
    rep["model"] = check_model_push(doc)

    # live sync: on, edit a gene on the server, wait for Rhino to follow while idle
    run_command_script("CalflabLiveSync")
    assert sc.sticky.get("calflab.livesync"), "CalflabLiveSync did not turn on"
    shank = [o for o in calflab_objects(doc) if o.Attributes.GetUserString("calflab.body") == "leg.fl.shank"]
    value = float(cr.request("/api/scene")["genome"]["values"][GENE])
    watch = {
        "t0": time.time(), "edited": False, "value": value, "revision": sc.sticky["calflab.livesync"]["revision"],
        "before": box_list(bbox_of(shank)), "rep": rep, "count": len(calflab_objects(doc)),
    }
    sc.sticky["calflab.check"] = watch

    def on_idle(sender, args):
        w = sc.sticky.get("calflab.check")
        if not w:
            return
        try:
            now = time.time()
            if not w["edited"]:
                if now - w["t0"] < 1.5:
                    return
                w["edited"] = True
                cr.request("/api/commands/set_genes", {"values": {GENE: w["value"] + 20.0}})
                return
            sync = sc.sticky.get("calflab.livesync") or {}
            followed = sync.get("revision") != w["revision"]
            if not followed and now - w["t0"] < SYNC_TIMEOUT_S:
                return
            sc.sticky["calflab.check"] = None
            Rhino.RhinoApp.Idle -= on_idle
            d = Rhino.RhinoDoc.ActiveDoc
            after = box_list(bbox_of([o for o in calflab_objects(d)
                                      if o.Attributes.GetUserString("calflab.body") == "leg.fl.shank"]))
            moved = max(abs(a - b) for a, b in zip(w["before"], after))
            r = w["rep"]
            count = len(calflab_objects(d))
            r["livesync"] = {"followed": followed, "seconds": round(now - w["t0"] - 1.5, 1),
                             "shank_bbox_change_mm": round(moved, 2), "objects": count}
            run_command_script("CalflabLiveSync")
            r["livesync"]["off"] = not sc.sticky.get("calflab.livesync")
            r["geometry_after_sync"] = check_geometry(d)
            cr.request("/api/undo", {})  # the gene edit
            cr.request("/api/undo", {})  # the pushed override
            # a 20 mm longer shank moves its bounding box by a comparable amount, and nothing may go missing
            r["ok"] = bool(followed and 2.0 < moved < 60.0 and count == w["count"] and r["livesync"]["off"])
            if not r["ok"]:
                r["error"] = "live sync did not reproduce the gene edit (see livesync)"
            finish(r)
        except Exception:
            sc.sticky["calflab.check"] = None  # the handler is inert from here on
            w["rep"]["ok"] = False
            w["rep"]["error"] = traceback.format_exc()
            finish(w["rep"])

    Rhino.RhinoApp.Idle += on_idle
    print("CALFLAB check: waiting for live sync...")


def main():
    first = not os.path.exists(STATE)
    rep = {"ok": False}
    try:
        if first:
            pass1()
        else:
            with open(STATE, "r", encoding="utf-8") as fh:
                rep = json.load(fh)
            rep["ok"] = False
            pass2(rep)
    except Exception:
        rep["error"] = traceback.format_exc()
        finish(rep)


main()
