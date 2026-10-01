"""Bridge logic (Rhino build list, Blender armature plan, sculpt push) and the
bridge scripts themselves, exercised with fakes where Rhino/Blender are absent."""

import ast

import numpy as np
import pytest
from calflab.app import Lab, LabError
from calflab.bridge import armature_plan, rhino_build_list
from calflab.bridge.sculpt import save_pushed_mesh
from calflab.model.spec import LAYERS
from calflab.paths import repo_root


def test_rhino_build_list_layers_blocks_and_user_text(calf_design):
    rb = rhino_build_list(calf_design, revision=7)
    assert rb["units"] == "mm"
    paths = [layer["path"] for layer in rb["layers"]]
    assert paths == ["CALFLAB"] + [f"CALFLAB::{n}" for n in LAYERS], "layer tree mirrors the CALFLAB layers"
    blocks = {b["name"] for b in rb["blocks"]}
    assert {"calflab.xh540_w270", "calflab.xm430_w350", "calflab.sts3215"} <= blocks
    by_id = {o["id"]: o for o in rb["objects"]}
    knee = by_id["act.fl.knee.motor"]
    assert knee["kind"] == "block" and knee["block"] == "calflab.xh540_w270"
    assert sum(o.get("block") == "calflab.xh540_w270" for o in rb["objects"]) == 8, "repeated components are instances"
    assert knee["user_text"]["calflab.id"] == "act.fl.knee.motor"
    assert knee["user_text"]["calflab.verified"] == "false" and knee["user_text"]["calflab.revision"] == "7"
    shank = by_id["leg.fl.shank.tube"]
    assert shank["kind"] == "primitive" and shank["shape"] == "capsule" and shank["layer"] == "CALFLAB::Structure"
    m = np.array(shank["xform"])
    assert m.shape == (4, 4) and np.allclose(m[:3, :3] @ m[:3, :3].T, np.eye(3), atol=1e-5)
    assert len(by_id) == len(rb["objects"]), "object ids are unique"
    assert {a["id"] for a in rb["annotations"]} == {j.id for j in calf_design.spec.joints}


def test_blender_armature_one_bone_per_joint(calf_design):
    spec = calf_design.spec
    plan = armature_plan(spec)
    bones = {b["name"]: b for b in plan["bones"]}
    assert set(bones) == {"root"} | {j.id for j in spec.joints}, "one bone per joint, named by stable ID"
    assert bones["joint.fl.knee"]["parent"] == "joint.fl.hip_flex"
    assert bones["joint.fl.hip_flex"]["parent"] == "joint.fl.hip_abd"
    assert bones["joint.fl.hip_abd"]["parent"] == "root"
    assert bones["joint.head_pitch"]["parent"] == "joint.neck_pitch"
    knee = bones["joint.fl.knee"]["joint"]
    j = spec.joint("joint.fl.knee")
    assert knee["range_deg"] == [j.range_deg[0] - j.rest_deg, j.range_deg[1] - j.rest_deg]
    assert np.allclose(np.abs(knee["axis_world"]), [0, 1, 0], atol=1e-6)
    for b in plan["bones"]:
        d = np.array(b["tail"]) - np.array(b["head"])
        assert np.linalg.norm(d) > 1.0, b["name"]
        if b["joint"]:
            # a bone must be perpendicular to its joint axis, or Blender cannot
            # hinge it about that axis with a single local rotation
            axis = np.array(b["joint"]["axis_world"])
            assert abs(np.dot(d / np.linalg.norm(d), axis)) < 1e-4, b["name"]
            assert np.linalg.norm(axis) == pytest.approx(1.0, abs=1e-5)
    mesh_bones = {m["id"]: m["bone"] for m in plan["meshes"]}
    assert mesh_bones["leg.fl.shank.tube"] == "joint.fl.knee" and mesh_bones["trunk.shell"] == "root"


def test_pushed_sculpt_becomes_a_geometry_override(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        head = next(b for b in lab.scene()["bodies"] if b["id"] == "head")
        skin_mass = sum(g["mass_g"] for g in head["geoms"] if g["layer"] == "Skin")
        c = np.array(head["pos"])
        verts = (c + np.array([[0, 0, 0], [80, 0, 0], [0, 60, 0], [0, 0, 50]])).tolist()
        faces = [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]
        r = save_pushed_mesh(lab, "head", verts, faces, name="Sculpted head")
        assert (lab.project.path / r["asset"]).is_file()
        ov = lab.state.overrides[0]
        assert (ov.kind, ov.target, ov.source, ov.name) == ("geometry", "head", "rhino", "Sculpted head")
        head2 = next(b for b in lab.scene()["bodies"] if b["id"] == "head")
        meshes = [g for g in head2["geoms"] if g["shape"] == "mesh"]
        assert len(meshes) == 1 and meshes[0]["mesh"] == r["asset"]
        assert not any(g["id"] == "head.skin" for g in head2["geoms"])
        assert meshes[0]["mass_g"] == pytest.approx(skin_mass), "the sculpt keeps the skin's mass"
        lab.jobs.wait(lab.run_sim().id)  # a sculpted design still simulates
        lab.undo()
        assert any(g["id"] == "head.skin" for g in next(b for b in lab.scene()["bodies"] if b["id"] == "head")["geoms"])
        with pytest.raises(LabError, match="not a body"):
            save_pushed_mesh(lab, "leg.fl.hoof", verts, faces)
    finally:
        lab.close()


BRIDGE_FILES = sorted((repo_root() / "bridges").rglob("*.py"))


@pytest.mark.parametrize("path", BRIDGE_FILES, ids=lambda p: p.name)
def test_bridge_scripts_are_valid_python_and_stdlib_only(path):
    """Bridge scripts run inside Rhino/Blender: they must not import calflab or third-party packages."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed_host = {"Rhino", "rhinoscriptsyntax", "scriptcontext", "System", "bpy", "mathutils", "Grasshopper",
                    "ghpythonlib", "calflab_rhino", "bpy_extras", "bmesh", "calflab_blender",
                    "clr"}  # clr: pythonnet, part of Rhino's Python
    import sys

    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods = [node.module.split(".")[0]]
        for m in mods:
            assert m in allowed_host or m in sys.stdlib_module_names, f"{path.name} imports {m}"


def test_rhino_script_builds_from_a_build_list_with_a_fake_rhino(calf_design):
    """Run the real CalflabPull builder against a recording fake of the Rhino document."""
    import importlib.util

    path = repo_root() / "bridges" / "rhino" / "scripts" / "calflab_rhino.py"
    spec = importlib.util.spec_from_file_location("calflab_rhino_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class FakeDoc(mod.DocAdapter):
        def __init__(self):
            self.layers, self.blocks, self.objects, self.deleted = [], {}, [], 0

        def ensure_layer(self, path, color):
            self.layers.append(path)
            return len(self.layers) - 1

        def ensure_block(self, name, description, geoms):
            self.blocks[name] = geoms

        def delete_objects_with_key(self, key):
            self.deleted += 1

        def add_primitive(self, shape, size, xform, layer, name, color, user_text):
            self.objects.append(("primitive", name, layer, user_text))

        def add_block_instance(self, block, xform, layer, name, user_text):
            self.objects.append(("block", name, layer, user_text))

        def add_mesh_asset(self, asset, xform, layer, name, user_text):
            self.objects.append(("mesh", name, layer, user_text))

        def add_line(self, a, b, layer, name, user_text):
            self.objects.append(("line", name, layer, user_text))

        def redraw(self):
            pass

    doc = FakeDoc()
    rb = rhino_build_list(calf_design, 3)
    summary = mod.build(doc, rb)
    assert doc.layers[0] == "CALFLAB" and "CALFLAB::Skin" in doc.layers
    assert set(doc.blocks) == {b["name"] for b in rb["blocks"]}
    assert summary["objects"] == len(rb["objects"]) and doc.deleted == 1
    kinds = {name: kind for kind, name, _, _ in doc.objects}
    assert kinds["act.fl.knee.motor"] == "block" and kinds["leg.fl.shank.tube"] == "primitive"
    assert all(ut["calflab.id"] == name for _, name, _, ut in doc.objects)
