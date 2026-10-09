"""Mass from real geometry and real materials (ADR-050, ADR-051, ADR-052):
pushed solids, a material per part, weighed parts, the breakdown, the scale
gene, and component entries that never take a value silently."""

from __future__ import annotations

import importlib.util
import shutil

import mujoco
import numpy as np
import pytest
import trimesh
import yaml
from calflab.app import Lab, LabError
from calflab.bridge import rhino_build_list
from calflab.bridge.sculpt import save_pushed_mesh
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.model.mass import mass_breakdown
from calflab.model.solid import analyze_mesh, equivalent_box, inertia_matrix
from calflab.model.xform import quat_to_matrix
from calflab.paths import repo_root
from calflab.sim import compile_mjcf


@pytest.fixture()
def lab(tmp_path):
    lab = Lab.open(tmp_path / "p")
    lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
    lab.end_gesture()
    yield lab
    lab.close()


def structure(lab, body="trunk"):
    return next(r for r in lab.scene()["mass"]["breakdown"]["bodies"] if r["body"] == body)["structure"]


def push_box(lab, size=(100.0, 100.0, 100.0), offset=(0.0, 0.0, 0.0), target="trunk", open_top=False, **kw):
    """Push a box centred ``offset`` mm from the body origin (world = standing pose)."""
    box = trimesh.creation.box(size)
    faces = box.faces
    if open_top:
        top = np.isclose(box.triangles[:, :, 2].min(axis=1), size[2] / 2)
        faces = faces[~top]
    origin = np.array(next(b for b in lab.scene()["bodies"] if b["id"] == target)["pos"])
    verts = box.vertices + origin + np.array(offset)
    return save_pushed_mesh(lab, target, verts.tolist(), faces.tolist(), layer="Structure", **kw)


# ---------------------------------------------------------------------- A: pushed solids
def test_a_closed_box_weighs_volume_times_density_and_nothing_is_counted_twice(lab):
    density = library().material("pla").density_g_cm3
    before = lab.scene()["mass"]
    old = structure(lab)
    assert old["source"] == "parametric" and old["material"] == "petg"

    reply = push_box(lab, material="pla", name="box trunk")
    assert reply["mass_from_geometry"] and reply["warning"] == ""
    assert reply["mass_g"] == pytest.approx(1000.0 * density, abs=1e-6)

    new = structure(lab)
    assert new["mass_g"] == pytest.approx(1000.0 * density, abs=1e-6)
    assert (new["source"], new["material"]) == ("geometry", "pla")
    assert new["replaced_g"] == pytest.approx(old["mass_g"]), "the envelope estimate is shown, not counted"
    after = lab.scene()["mass"]
    assert after["total_g"] - before["total_g"] == pytest.approx(new["mass_g"] - old["mass_g"], abs=0.11)
    b = after["breakdown"]
    assert sum(r["total_g"] for r in b["bodies"]) == pytest.approx(b["total_g"], abs=0.5)
    assert sum(b["by_source_g"].values()) == pytest.approx(b["total_g"], abs=0.05)
    assert b["by_source_g"]["geometry"] == pytest.approx(new["mass_g"]) and b["geometry_parts"] == ["trunk"]
    trunk = next(x for x in lab.scene()["bodies"] if x["id"] == "trunk")
    shell = next(g for g in trunk["geoms"] if g["id"] == "trunk.shell")
    assert shell["mass_g"] == 0 and shell["role"] == "collision", "the envelope is only a collision shape now"
    motors = [g for g in trunk["geoms"] if g["layer"] == "Actuators"]
    assert motors and all(g["mass_source"] == "component" and g["mass_g"] > 0 for g in motors)

    # toggling the override off returns the parametric value; every step undoes
    lab.execute("toggle_override", {"id": reply["override"]})
    assert structure(lab) == old and lab.scene()["mass"]["total_g"] == before["total_g"]
    lab.undo()
    assert structure(lab)["source"] == "geometry"
    lab.undo()
    assert structure(lab) == old and lab.state.overrides == []
    lab.redo()
    assert structure(lab)["mass_g"] == pytest.approx(1000.0 * density, abs=1e-6)


def test_centre_of_mass_and_inertia_follow_the_solid_into_the_simulator(lab):
    lib = library()
    plain = compile_mjcf(lab.design().spec, lib)
    push_box(lab, size=(300.0, 40.0, 20.0), offset=(60.0, 0.0, 10.0), material="pla")
    design = lab.design()
    geom = next(g for g in design.spec.body("trunk").geoms if g.shape == "mesh")
    mass = 300 * 40 * 20 / 1000.0 * lib.material("pla").density_g_cm3
    assert geom.mass_g == pytest.approx(mass)
    assert geom.com == pytest.approx((60.0, 0.0, 10.0), abs=1e-3)
    ixx, iyy, izz = geom.inertia[:3]
    assert ixx == pytest.approx(mass * (40**2 + 20**2) / 12, rel=1e-6)
    assert iyy == pytest.approx(mass * (300**2 + 20**2) / 12, rel=1e-6)
    assert izz == pytest.approx(mass * (300**2 + 40**2) / 12, rel=1e-6)

    solid = compile_mjcf(design.spec, lib)
    assert solid.total_mass_kg == pytest.approx(design.spec.total_mass_g() / 1000.0)
    m = mujoco.MjModel.from_xml_string(solid.xml)
    gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, geom.id)
    assert m.geom_type[gid] == mujoco.mjtGeom.mjGEOM_BOX and m.geom_contype[gid] == 0
    assert sorted(m.geom_size[gid] * 2000) == pytest.approx([20.0, 40.0, 300.0], rel=1e-4), "the box with the same inertia"
    assert m.geom_pos[gid] * 1000 == pytest.approx([60.0, 0.0, 10.0], abs=1e-2)
    # the trunk's own mass and centre differ from the envelope version exactly by the swap of shell for solid
    m0 = mujoco.MjModel.from_xml_string(plain.xml)
    tid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk")
    shell_kg = next(g for g in build_design(design.genome).spec.body("trunk").geoms if g.id == "trunk.shell").mass_g / 1000
    assert m.body_mass[tid] - m0.body_mass[tid] == pytest.approx(mass / 1000 - shell_kg, abs=1e-6)
    assert m.body_ipos[tid][0] > m0.body_ipos[tid][0], "a solid placed forward moves the trunk's centre of mass forward"
    assert not np.allclose(m.body_inertia[tid], m0.body_inertia[tid])
    sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "trunk.shell")
    assert m.geom_contype[sid] == 1, "the envelope still collides"


def test_run_record_names_the_parts_with_geometry_based_mass(lab):
    job = lab.jobs.wait(lab.run_sim().id)
    plain = lab.registry.get_run(job.result["run_id"])
    assert plain.inputs["mass"]["geometry_parts"] == [] and plain.inputs["mass"]["structure"]["trunk"]["source"] == "parametric"
    push_box(lab, material="pla")
    job = lab.jobs.wait(lab.run_sim().id)
    assert job.status == "done", job.error
    rec = lab.registry.get_run(job.result["run_id"])
    assert rec.id != plain.id, "a pushed solid is a different simulation"
    assert rec.inputs["mass"]["geometry_parts"] == ["trunk"]
    assert rec.inputs["mass"]["structure"]["trunk"] == {
        "mass_g": pytest.approx(1240.0), "source": "geometry", "material": "pla", "materials": ["pla"]}
    assert rec.overrides[0]["meta"]["solid"]["closed"] is True, "the run keeps what its mass was computed from"
    assert rec.metrics["speed_mps"] != plain.metrics["speed_mps"]


def test_an_open_solid_warns_and_keeps_the_estimate(lab):
    old = structure(lab)
    total = lab.scene()["mass"]["total_g"]
    logs = []
    lab.bus.subscribe(lambda e: logs.append(e) if e.get("type") == "log" else None)
    reply = push_box(lab, open_top=True, material="pla")
    assert not reply["mass_from_geometry"] and reply["solid"]["closed"] is False
    assert "open (4 naked edges)" in reply["warning"] and "parametric estimate is kept" in reply["warning"]
    assert any(e.get("level") == "warn" and "naked edges" in e.get("message", "") for e in logs)
    st = structure(lab)
    assert st["mass_g"] == old["mass_g"] and st["source"] == "parametric" and "not used for mass" in st["note"]
    scene = lab.scene()
    assert scene["mass"]["total_g"] == total
    assert any("not used for mass" in w for w in scene["warnings"]), "the design carries the warning too"
    assert scene["mass"]["breakdown"]["geometry_parts"] == []


def test_solid_analysis_and_equivalent_box():
    ball = trimesh.creation.icosphere(subdivisions=4, radius=30.0)
    info = analyze_mesh(ball.vertices + [5.0, -2.0, 7.0], ball.faces)
    assert info.closed and info.volume_mm3 == pytest.approx(4 / 3 * np.pi * 30**3, rel=0.01)
    assert info.com_mm == pytest.approx((5.0, -2.0, 7.0), abs=1e-6)
    inside_out = analyze_mesh(ball.vertices, ball.faces[:, ::-1])
    assert inside_out.closed and inside_out.volume_mm3 == pytest.approx(info.volume_mm3)
    two = trimesh.util.concatenate([ball, ball.copy().apply_translation([100, 0, 0])])
    assert analyze_mesh(two.vertices, two.faces).volume_mm3 == pytest.approx(2 * info.volume_mm3)
    assert "fewer than four faces" in analyze_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]).problem
    # unwelded faces (each triangle with its own vertices), as a mesher may deliver them, still count as closed
    soup = ball.vertices[ball.faces].reshape(-1, 3)
    assert analyze_mesh(soup, np.arange(len(soup)).reshape(-1, 3)).closed

    rot = trimesh.transformations.rotation_matrix(0.7, [1.0, 2.0, 0.5])
    part = trimesh.creation.box((80.0, 30.0, 12.0)).apply_transform(rot)
    info = analyze_mesh(part.vertices, part.faces)
    mass = info.volume_mm3 * 0.00124
    tensor = tuple(v * 0.00124 for v in info.inertia_mm5)
    extents, quat = equivalent_box(mass, tensor)
    assert sorted(extents) == pytest.approx([12.0, 30.0, 80.0], rel=1e-6)
    r = quat_to_matrix(quat)
    a, b, c = extents
    principal = np.diag([mass * (b * b + c * c) / 12, mass * (a * a + c * c) / 12, mass * (a * a + b * b) / 12])
    assert r @ principal @ r.T == pytest.approx(inertia_matrix(tensor), rel=1e-6, abs=1e-6)


def test_skin_sculpt_and_structure_solid_can_share_a_body(lab):
    head = next(b for b in lab.scene()["bodies"] if b["id"] == "head")
    skin = sum(g["mass_g"] for g in head["geoms"] if g["layer"] == "Skin")
    tet = np.array(head["pos"]) + np.array([[0, 0, 0], [80, 0, 0], [0, 60, 0], [0, 0, 50]])
    r = save_pushed_mesh(lab, "head", tet.tolist(), [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], layer="Skin")
    assert "changes the look only" in r["note"] and not r["mass_from_geometry"]
    push_box(lab, size=(50.0, 40.0, 30.0), target="head")
    geoms = next(b for b in lab.scene()["bodies"] if b["id"] == "head")["geoms"]
    meshes = {g["layer"]: g for g in geoms if g["shape"] == "mesh"}
    assert set(meshes) == {"Skin", "Structure"}
    assert meshes["Skin"]["mass_g"] == pytest.approx(skin) and meshes["Skin"]["mass_source"] == "parametric"
    assert meshes["Structure"]["mass_g"] == pytest.approx(60.0 * library().material("petg").density_g_cm3)


# ---------------------------------------------------------------------- B: material per part
def test_b_material_of_a_parametric_part_is_an_override(lab):
    lib = library()
    petg, pla = lib.material("petg").density_g_cm3, lib.material("pla").density_g_cm3
    old = structure(lab, "leg.fl.shank")
    other = structure(lab, "leg.fr.shank")
    res = lab.execute("set_part_material", {"target": "leg.fl.shank", "material": "pla"})["result"]
    assert res["on"] == "part"
    ov = lab.state.overrides[0]
    assert (ov.kind, ov.target, ov.material) == ("material", "leg.fl.shank", "pla")
    new = structure(lab, "leg.fl.shank")
    assert new["material"] == "pla" and new["mass_g"] == pytest.approx(old["mass_g"] * pla / petg, abs=0.02)
    assert structure(lab, "leg.fr.shank") == other, "only that part changes"
    el = lab.scene()["elements"]["leg.fl.shank"]
    assert el["structure"]["material"] == "pla" and el["structure"]["source"] == "parametric"
    keys = {m["key"]: m for m in lab.scene()["materials"]}
    assert {"petg", "pla"} <= set(keys) and keys["petg"]["default"] and not keys["pla"]["verified"]
    bom = {line["key"]: line for line in lab.analysis("bom")["lines"] if "structure" in line["name"]}
    assert bom["pla"]["mass_g"] == pytest.approx(new["mass_g"], abs=0.1) and bom["petg"]["mass_g"] > 0

    lab.execute("set_part_material", {"target": "leg.fl.shank", "material": ""})
    assert lab.state.overrides == [] and structure(lab, "leg.fl.shank") == old
    lab.undo()
    assert structure(lab, "leg.fl.shank")["material"] == "pla"
    lab.undo()
    assert structure(lab, "leg.fl.shank") == old

    with pytest.raises(LabError, match="not a structure material.*petg, pla"):
        lab.execute("set_part_material", {"target": "trunk", "material": "cast_silicone"})
    with pytest.raises(LabError, match="not a part of this design"):
        lab.execute("set_part_material", {"target": "wing", "material": "pla"})


def test_b_material_of_a_pushed_solid_belongs_to_the_solid(lab):
    lib = library()
    old = structure(lab)
    reply = push_box(lab)  # no material named: the part's material
    assert structure(lab)["material"] == "petg"
    assert structure(lab)["mass_g"] == pytest.approx(1000 * lib.material("petg").density_g_cm3)
    res = lab.execute("set_part_material", {"target": "trunk", "material": "pla"})["result"]
    assert res == {"override": reply["override"], "on": "solid"}
    assert len(lab.state.overrides) == 1 and lab.state.overrides[0].meta["material"] == "pla"
    assert structure(lab)["mass_g"] == pytest.approx(1000 * lib.material("pla").density_g_cm3)
    lab.execute("toggle_override", {"id": reply["override"]})
    assert structure(lab) == old, "with the solid off, the parametric part is as it was"
    with pytest.raises(LabError, match="not a structure material"):
        push_box(lab, material="unobtainium")


# ---------------------------------------------------------------------- G: several solids, each with its own material
def box_part(lab, size, offset=(0.0, 0.0, 0.0), material="", name="", target="trunk", open_top=False):
    """One solid of a several-solid push, as the Rhino bridge sends it (ADR-053)."""
    box = trimesh.creation.box(size)
    faces = box.faces
    if open_top:
        faces = faces[~np.isclose(box.triangles[:, :, 2].min(axis=1), size[2] / 2)]
    origin = np.array(next(b for b in lab.scene()["bodies"] if b["id"] == target)["pos"])
    return {"name": name, "material": material, "vertices": (box.vertices + origin + np.array(offset)).tolist(),
            "faces": faces.tolist(), "host": {"closed": not open_top, "volume_mm3": float(np.prod(size))}}


def push_parts(lab, parts, target="trunk", **kw):
    return save_pushed_mesh(lab, target, [], [], layer="Structure", parts=parts, **kw)


def test_g_a_pla_box_and_a_steel_rod_pushed_together_are_each_weighed_with_their_own_material(tmp_path):
    """The researcher's two-box check: a 100 x 100 x 100 mm box tagged pla and a 10 x 10 x 100 mm box tagged
    stainless_304, pushed onto trunk Structure in one CalflabPush. Densities are read from the library."""
    from calflab_server.app import create_app
    from fastapi.testclient import TestClient

    path = repo_root() / "bridges" / "rhino" / "scripts" / "calflab_rhino.py"
    spec = importlib.util.spec_from_file_location("calflab_rhino_solids_test", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    lib = library()
    pla, steel = lib.material("pla").density_g_cm3, lib.material("stainless_304").density_g_cm3
    m_box, m_rod = 1000.0 * pla, 10.0 * steel
    lab = Lab.open(tmp_path / "p")
    try:
        lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
        lab.end_gesture()
        old, total = structure(lab), lab.scene()["mass"]["total_g"]
        origin = np.array(next(b for b in lab.scene()["bodies"] if b["id"] == "trunk")["pos"])
        with TestClient(create_app(lab, watch_plugins=False)) as client:
            body = {"target": "trunk", "layer": "Structure", "name": "trunk chassis", "material": "", "parts": [
                box_part(lab, (100.0, 100.0, 100.0), material="pla", name="body"),
                box_part(lab, (10.0, 10.0, 100.0), offset=(100.0, 0.0, 0.0), material="stainless_304", name="rod"),
            ]}
            reply = client.post("/api/bridge/rhino/push", json=body).json()
        assert reply["mass_from_geometry"] and reply["warning"] == ""
        assert reply["mass_g"] == pytest.approx(m_box + m_rod, abs=0.01)
        assert [(s["name"], s["material"], s["volume_mm3"]) for s in reply["solids"]] == [
            ("body", "pla", pytest.approx(1.0e6)), ("rod", "stainless_304", pytest.approx(1.0e4))]
        assert [s["mass_g"] for s in reply["solids"]] == pytest.approx([m_box, m_rod], abs=0.01)
        lines = script.push_report(reply, "trunk")
        assert f"trunk structure mass is now {m_box + m_rod:.1f} g (1010.0 cm3 of pla + stainless_304" in lines[1]
        assert f"solid 1 (body): 1000.0 cm3 of pla = {m_box:.1f} g" in lines[2]
        assert f"solid 2 (rod): 10.0 cm3 of stainless_304 = {m_rod:.1f} g" in lines[3]

        # centre of mass: between the two boxes, weighted by their masses, not at the centre of their combined volume
        x = 100.0 * m_rod / (m_box + m_rod)
        assert x > 3 * (100.0 * 10.0 / 1010.0), "steel pulls it well past the volume centroid (0.99 mm)"
        st = structure(lab)
        assert st["com_mm"] == pytest.approx([x, 0.0, 0.0], abs=0.01)
        assert reply["com_world_mm"] == pytest.approx((origin + [x, 0.0, 0.0]).tolist(), abs=0.02)
        assert "structure centre of mass is at" in lines[4]
        assert (st["source"], st["material"], st["materials"]) == ("geometry", None, ["pla", "stainless_304"])
        assert st["material_label"] == "pla + stainless_304" and st["replaced_g"] == pytest.approx(old["mass_g"])
        assert [(s["material"], s["mass_g"]) for s in st["solids"]] == [
            ("pla", pytest.approx(m_box, abs=0.01)), ("stainless_304", pytest.approx(m_rod, abs=0.01))]
        el = lab.scene()["elements"]["trunk"]["structure"]
        assert el["material"] is None and el["material_label"] == "pla + stainless_304", "no default material is shown for a mixed part"
        b = lab.scene()["mass"]["breakdown"]
        assert sum(b["by_source_g"].values()) == pytest.approx(b["total_g"], abs=0.05) and b["geometry_parts"] == ["trunk"]
        assert lab.scene()["mass"]["total_g"] == pytest.approx(total + m_box + m_rod - old["mass_g"], abs=0.11)

        # each solid is its own mass geom with its own density; the simulator composes them
        design = lab.design()
        box, rod = (g for g in design.spec.body("trunk").geoms if g.shape == "mesh")
        assert (box.material, rod.material) == ("pla", "stainless_304") and box.mesh != rod.mesh
        assert rod.mass_center() == pytest.approx((100.0, 0.0, 0.0), abs=1e-3)
        assert rod.inertia[0] == pytest.approx(m_rod * (10**2 + 100**2) / 12, rel=1e-6)
        assert box.inertia[2] == pytest.approx(m_box * (100**2 + 100**2) / 12, rel=1e-6)
        model = compile_mjcf(design.spec, lib)
        assert model.total_mass_kg == pytest.approx(design.spec.total_mass_g() / 1000.0)
        m = mujoco.MjModel.from_xml_string(model.xml)
        for g, extents in ((box, [100.0, 100.0, 100.0]), (rod, [10.0, 10.0, 100.0])):
            gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, g.id)
            assert m.geom_type[gid] == mujoco.mjtGeom.mjGEOM_BOX and m.geom_contype[gid] == 0
            assert sorted(m.geom_size[gid] * 2000) == pytest.approx(extents, rel=1e-4)
        bom = {line["key"]: line for line in lab.analysis("bom")["lines"] if "structure" in line["name"]}
        assert bom["stainless_304"]["mass_g"] == pytest.approx(m_rod, abs=0.1) and bom["pla"]["mass_g"] == pytest.approx(m_box, abs=0.1)

        # pulled back into Rhino, each solid is its own object and keeps its material
        pulled = [o for o in rhino_build_list(design)["objects"] if o["kind"] == "mesh"]
        assert [o["user_text"]["calflab.material"] for o in pulled] == ["pla", "stainless_304"]

        # the run record names the materials of the part
        job = lab.jobs.wait(lab.run_sim().id)
        assert job.status == "done", job.error
        rec = lab.registry.get_run(job.result["run_id"]).inputs["mass"]["structure"]["trunk"]
        assert rec["materials"] == ["pla", "stainless_304"] and rec["source"] == "geometry" and rec["material"] is None
        assert [(s["material"], s["mass_g"]) for s in rec["solids"]] == [
            ("pla", pytest.approx(m_box, abs=0.01)), ("stainless_304", pytest.approx(m_rod, abs=0.01))]

        # a weighed mass on top: the value wins, the solids keep their proportions and the centre of mass stays
        lab.execute("set_measured_mass", {"target": "trunk", "mass_g": 1500.0})
        st = structure(lab)
        assert (st["mass_g"], st["source"]) == (1500.0, "measured") and st["computed_g"] == pytest.approx(m_box + m_rod, abs=0.01)
        assert st["com_mm"] == pytest.approx([x, 0.0, 0.0], abs=0.01) and st["materials"] == ["pla", "stainless_304"]
        lab.execute("set_measured_mass", {"target": "trunk", "mass_g": 0})

        # the material list in Properties cannot flatten a mixed part
        with pytest.raises(LabError, match=r"own materials \(pla \+ stainless_304\).*calflab.material"):
            lab.execute("set_part_material", {"target": "trunk", "material": "petg"})

        # switching the override off returns the parametric part; undo and redo work as for one solid
        lab.execute("toggle_override", {"id": reply["override"]})
        assert structure(lab) == old and lab.scene()["mass"]["total_g"] == total
        lab.undo()
        assert structure(lab)["mass_g"] == pytest.approx(m_box + m_rod, abs=0.01)
        lab.undo()  # removing the weighed mass
        lab.undo()  # setting it
        lab.undo()  # the push
        assert structure(lab) == old and [o for o in lab.state.overrides if o.kind == "geometry"] == []
        lab.redo()
        assert structure(lab)["materials"] == ["pla", "stainless_304"]
    finally:
        lab.close()


def test_g_solids_without_their_own_material_take_the_one_named_at_the_push(lab):
    lib = library()
    petg, pla = lib.material("petg").density_g_cm3, lib.material("pla").density_g_cm3
    parts = [box_part(lab, (100.0, 100.0, 100.0), material="pla"), box_part(lab, (20.0, 20.0, 50.0), offset=(0.0, 100.0, 0.0))]
    reply = push_parts(lab, parts, material="petg")
    assert [(s["name"], s["material"]) for s in reply["solids"]] == [("solid 1", "pla"), ("solid 2", "petg")]
    assert reply["mass_g"] == pytest.approx(1000.0 * pla + 20.0 * petg, abs=0.01)
    lab.undo()
    reply = push_parts(lab, parts)  # nothing named: the part's material
    assert reply["solids"][1]["material"] == "petg" and reply["materials"] == ["petg", "pla"]
    lab.undo()
    # two solids of one material are one material; Properties may then change it for the whole part
    reply = push_parts(lab, [{**p, "material": ""} for p in parts], material="pla")
    assert structure(lab)["material"] == "pla" and reply["mass_g"] == pytest.approx(1020.0 * pla, abs=0.01)
    lab.execute("set_part_material", {"target": "trunk", "material": "petg"})
    assert structure(lab)["mass_g"] == pytest.approx(1020.0 * petg, abs=0.01)
    with pytest.raises(LabError, match="not a structure material"):
        push_parts(lab, [{**parts[0], "material": "unobtainium"}, parts[1]])
    # one object alone is exactly a plain push; a second push replaces the first
    reply = push_parts(lab, [parts[0]])
    assert "solids" not in reply and structure(lab)["mass_g"] == pytest.approx(1000.0 * pla)
    assert len([o for o in lab.state.overrides if o.kind == "geometry"]) == 1
    # on Skin the objects are joined, as before: look only
    reply = save_pushed_mesh(lab, "trunk", [], [], layer="Skin", parts=parts)
    assert reply["faces"] == 24 and "changes the look only" in reply["note"]


def test_g_one_open_solid_keeps_the_whole_part_on_its_estimate(lab):
    old = structure(lab)
    reply = push_parts(lab, [
        box_part(lab, (100.0, 100.0, 100.0), material="pla", name="body"),
        box_part(lab, (10.0, 10.0, 100.0), offset=(100.0, 0.0, 0.0), material="petg", name="rod", open_top=True),
    ])
    assert not reply["mass_from_geometry"] and "solids" not in reply
    assert "The solids pushed onto trunk are not used for mass: rod: it is open (4 naked edges)" in reply["warning"]
    assert "parametric estimate is kept" in reply["warning"]
    st = structure(lab)
    assert st["mass_g"] == old["mass_g"] and st["source"] == "parametric" and st["solids"] == []
    assert lab.scene()["mass"]["breakdown"]["geometry_parts"] == []


# ---------------------------------------------------------------------- F: measured mass
def test_f_measured_mass_is_preferred_and_both_values_are_shown(lab):
    old = structure(lab, "leg.hl.thigh")
    total = lab.scene()["mass"]["total_g"]
    thigh = next(b for b in lab.scene()["bodies"] if b["id"] == "leg.hl.thigh")
    motor = sum(g["mass_g"] for g in thigh["geoms"] if g["layer"] == "Actuators")
    lab.execute("set_measured_mass", {"target": "leg.hl.thigh", "mass_g": 41.5})
    st = structure(lab, "leg.hl.thigh")
    assert st["mass_g"] == 41.5 and st["source"] == "measured" and st["computed_g"] == pytest.approx(old["mass_g"])
    assert lab.scene()["mass"]["total_g"] == pytest.approx(total + 41.5 - old["mass_g"], abs=0.11)
    thigh = next(b for b in lab.scene()["bodies"] if b["id"] == "leg.hl.thigh")
    assert sum(g["mass_g"] for g in thigh["geoms"] if g["layer"] == "Actuators") == motor, "motors are not part of the weighed print"
    assert lab.scene()["mass"]["breakdown"]["measured_parts"] == ["leg.hl.thigh"]
    lab.execute("set_measured_mass", {"target": "leg.hl.thigh", "mass_g": 44.0})
    assert len(lab.state.overrides) == 1 and structure(lab, "leg.hl.thigh")["mass_g"] == 44.0
    lab.execute("set_measured_mass", {"target": "leg.hl.thigh", "mass_g": 0})
    assert lab.state.overrides == [] and structure(lab, "leg.hl.thigh") == old
    with pytest.raises(LabError, match="no printed structure"):
        lab.execute("set_measured_mass", {"target": "tail", "mass_g": 5})

    # on a pushed solid: the weighed value wins, the geometry still shapes centre of mass and inertia
    push_box(lab, size=(200.0, 50.0, 50.0), offset=(40.0, 0.0, 0.0), material="pla")
    computed = structure(lab)["mass_g"]
    lab.execute("set_measured_mass", {"target": "trunk", "mass_g": 310.0})
    st = structure(lab)
    assert (st["mass_g"], st["source"]) == (310.0, "measured") and st["computed_g"] == pytest.approx(computed)
    geom = next(g for g in lab.design().spec.body("trunk").geoms if g.shape == "mesh")
    assert geom.com == pytest.approx((40.0, 0.0, 0.0), abs=1e-3)
    assert geom.inertia[0] == pytest.approx(310.0 * (50**2 + 50**2) / 12, rel=1e-6)


# ---------------------------------------------------------------------- E: breakdown
def test_e_breakdown_accounts_for_every_gram(calf_design):
    lib = library()
    b = mass_breakdown(calf_design.spec, lib)
    assert b["total_g"] == pytest.approx(calf_design.spec.total_mass_g(), abs=0.01)
    items = [i for r in b["bodies"] for i in r["items"]]
    assert sum(i["mass_g"] for i in items) == pytest.approx(b["total_g"], abs=0.5)
    assert len({i["id"] for i in items}) == len(items), "no item twice"
    assert b["by_source_g"]["geometry"] == 0 and b["by_source_g"]["measured"] == 0
    comp = sum(lib.get(g.component).mass_g for bd in calf_design.spec.bodies for g in bd.geoms if g.component)
    assert b["by_source_g"]["component"] == pytest.approx(comp)
    assert b["unverified_g"] == pytest.approx(b["total_g"], abs=13 * 4 + 1), "all but the belts rest on unverified entries"
    by_id = {i["id"]: i for i in items}
    assert by_id["act.fl.knee.motor"]["source"] == "component" and by_id["act.fl.knee.motor"]["verified"] is False
    assert by_id["trunk.shell"]["source"] == "parametric" and by_id["trunk.shell"]["material"] == "petg"
    assert by_id["leg.fl.hoof"]["material"] == "cast_silicone"
    trunk = next(r for r in b["bodies"] if r["body"] == "trunk")
    assert trunk["structure"]["mass_g"] == by_id["trunk.shell"]["mass_g"], "motors and boards are not structure"
    assert {n["component"] for n in b["not_counted"]} == {"fsr_foot", "cap_touch_zone"}, "sensors the model gives no body"


def test_mass_target_can_be_set_per_project(lab):
    assert lab.scene()["mass"]["target_g"] == 7000 and lab.scene()["mass"]["target_source"] == "default"
    lab.execute("set_mass_target", {"mass_g": 800})
    m = lab.scene()["mass"]
    assert m["target_g"] == 800 and m["target_source"] == "project" and m["over_budget"]
    lab.undo()
    assert lab.scene()["mass"]["target_g"] == 7000


# ---------------------------------------------------------------------- D: scale
def test_d_a_200_mm_calf_builds_without_range_errors(lab):
    full = lab.scene()
    res = lab.execute("set_genes", {"values": {"scale": 0.33}})
    assert res["result"]["genes"]["scale"] == 0.33
    small = lab.scene()
    assert small["warnings"] == []
    assert small["extents"]["height_mm"] == pytest.approx(200, abs=5)
    assert small["extents"]["target_height_mm"] == pytest.approx(610 * 0.33, abs=0.1)
    assert small["extents"]["height_mm"] / full["extents"]["height_mm"] == pytest.approx(0.33, abs=0.005)
    design = lab.design()
    pv = design.element_params["leg.fl.thigh"]["length"]
    assert pv.value == pytest.approx(170 * 0.33) and pv.scale == 0.33 and pv.min == pytest.approx(100 * 0.33)
    assert design.genome.values["thigh_length"] == 170, "length genes stay written at full size"
    assert design.element_params["neck"]["angle"].value == 50, "angles do not scale"
    feet = [f["pos"][2] - f["radius"] for f in small["feet"]]
    assert feet == pytest.approx([0.0] * 4, abs=1e-6), "hooves on the ground"
    wall = design.genome.values["wall_thickness"]
    shell = next(g for g in design.spec.body("trunk").geoms if g.id == "trunk.shell")
    assert shell.mass_g == pytest.approx(shell.area_mm2() * wall * 1.27 / 1000), "the wall is not scaled"
    b = small["mass"]["breakdown"]
    assert b["by_source_g"]["component"] == full["mass"]["breakdown"]["by_source_g"]["component"], "components do not shrink"

    # a typed override is in real millimetres and internalizes back to the full-size gene
    lab.execute("add_override", {"target": "leg.fl.shank", "param": "length", "value": 70.0})
    assert lab.design().element_params["leg.fl.shank"]["length"].value == 70.0
    lab.execute("internalize_override", {"id": lab.state.overrides[0].id})
    assert lab.state.graph.role("genome").params["shank_length"] == pytest.approx(70.0 / 0.33)

    job = lab.jobs.wait(lab.run_sim().id)
    assert job.status == "done", job.error
    assert job.result["metrics"]["speed_mps"] is not None
    assert rhino_build_list(lab.design())["objects"], "the small calf pulls into Rhino"


def test_d_form_shows_and_takes_real_millimetres(lab):
    """Lengths are stored at full size and shown as they measure on the body (ADR-052)."""
    form = lab.graph_view()["genome_form"]
    fields = {f["name"]: f for f in form["schema"]["fields"]}
    assert form["values"]["thigh_length"] == 170 and form["scaled"] == []
    assert (fields["thigh_length"]["min"], fields["thigh_length"]["max"]) == (100, 260)

    lab.execute("set_genes", {"values": {"scale": 0.33}, "real": True})
    form = lab.graph_view()["genome_form"]
    fields = {f["name"]: f for f in form["schema"]["fields"]}
    assert form["values"]["thigh_length"] == pytest.approx(56.1) and form["values"]["scale"] == 0.33
    assert fields["thigh_length"]["min"] == pytest.approx(33.0) and fields["thigh_length"]["max"] == pytest.approx(85.8)
    assert fields["thigh_length"]["default"] == pytest.approx(56.1)
    assert form["values"]["neck_angle"] == 50 and fields["neck_angle"]["max"] == 80, "angles are not scaled"
    assert form["values"]["wall_thickness"] == 2.0 and fields["wall_thickness"]["min"] == 1.0, "nor is the printed wall"
    assert "thigh_length" in form["scaled"] and "wall_thickness" not in form["scaled"]
    assert lab.scene()["genome_real"]["thigh_length"] == pytest.approx(56.1)

    # typing 60 in the slider is a 60 mm thigh; the stored gene is its full-size equivalent
    res = lab.execute("set_genes", {"values": {"thigh_length": 60.0}, "real": True})["result"]
    assert res["real"]["thigh_length"] == pytest.approx(60.0)
    assert res["genes"]["thigh_length"] == pytest.approx(60.0 / 0.33)
    assert lab.design().element_params["leg.fl.thigh"]["length"].value == pytest.approx(60.0)
    assert lab.graph_view()["genome_form"]["values"]["thigh_length"] == pytest.approx(60.0)
    # beyond the (scaled) range it stops at the range, as before
    res = lab.execute("set_genes", {"values": {"thigh_length": 500.0}, "real": True})["result"]
    assert res["real"]["thigh_length"] == pytest.approx(85.8)
    # unscaled genes pass straight through; without real=true values are stored ones, as scripts send them
    lab.execute("set_genes", {"values": {"wall_thickness": 1.2, "knee_bend": 35}, "real": True})
    assert lab.state.graph.role("genome").params["wall_thickness"] == 1.2
    lab.execute("set_genes", {"values": {"shank_length": 200}})
    assert lab.graph_view()["genome_form"]["values"]["shank_length"] == pytest.approx(66.0)
    # a new scale and a length in one edit: the length is real at the new scale
    lab.execute("set_genes", {"values": {"scale": 0.5, "trunk_length": 200.0}, "real": True})
    params = lab.state.graph.role("genome").params
    assert params["scale"] == 0.5 and params["trunk_length"] == pytest.approx(400.0)
    # changing only the scale keeps the proportions: every real length follows
    assert lab.graph_view()["genome_form"]["values"]["shank_length"] == pytest.approx(100.0)
    lab.execute("reset_genes")
    assert lab.graph_view()["genome_form"]["values"]["thigh_length"] == 170


# ---------------------------------------------------------------------- C: new components
@pytest.fixture()
def own_config(tmp_path, monkeypatch):
    """A private copy of config/ so tests can add components without touching the repo's."""
    shutil.copytree(repo_root() / "config", tmp_path / "repo" / "config")
    monkeypatch.setenv("CALFLAB_REPO", str(tmp_path / "repo"))
    return tmp_path / "repo" / "config" / "components"


SERVO = {
    "mass_g": 20.0, "dims_mm": [23.0, 12.0, 27.0], "stall_torque_nm": 0.9, "stall_current_a": 1.2,
    "no_load_speed_rpm": 60.0, "voltage_v": 7.4, "cost_usd": 12.0,
}  # made-up numbers for a test fixture, not a real part


def test_c_a_blank_entry_is_incomplete_until_its_values_are_entered(own_config):
    from calflab.components.template import add_component
    from calflab.wiring import component_audit

    path, required = add_component("actuator", "test_servo", "Test servo")
    assert path.name == "actuators.yaml"
    assert set(required) == {"mass_g", "stall_torque_nm", "stall_current_a", "no_load_speed_rpm", "voltage_v"}
    entry = next(e for e in yaml.safe_load(path.read_text(encoding="utf-8")) if e["key"] == "test_servo")
    assert entry["verified"] is False and entry["guessed"] == []
    assert all(entry[f] is None for f in required), "nothing is filled in for the researcher"
    lib = library()
    assert not lib.has("test_servo") and set(lib.incomplete["test_servo"]["missing"]) == set(required)
    with pytest.raises(KeyError, match="incomplete: enter .*stall_torque_nm"):
        lib.get("test_servo")
    assert "test_servo" not in genome_definition("calf").gene("act_knee").choices
    spec = build_design(genome_definition("calf").default_genome()).spec
    rep = component_audit(spec, lib, None)
    assert [c["key"] for c in rep["incomplete"]] == ["test_servo"]
    with pytest.raises(ValueError, match="already exists"):
        add_component("actuator", "test_servo")
    with pytest.raises(ValueError, match="not a valid key"):
        add_component("actuator", "Test Servo")
    for kind in ("sensor", "board", "battery", "material"):
        add_component(kind, f"blank_{kind}")
    assert {"blank_sensor", "blank_board", "blank_battery", "blank_material"} <= set(library().incomplete)


def test_c_a_new_servo_is_selectable_and_every_result_uses_its_numbers(own_config, tmp_path):
    from calflab.evolve.gait import speed_caps
    from calflab.wiring import bill_of_materials, component_audit, torque_margins

    path = own_config / "actuators.yaml"
    entry = {"key": "test_servo", "kind": "actuator", "name": "Test servo", **SERVO,
             "armature_kgm2": 0.0002, "guessed": ["armature_kgm2"], "source": "test fixture", "verified": False}
    path.write_text(path.read_text(encoding="utf-8") + "\n" + yaml.safe_dump([entry]), encoding="utf-8")
    lib = library()
    servo = lib.actuator("test_servo")
    assert servo.guessed == ["armature_kgm2"]
    assert set(servo.defaulted) == {"gear_ratio", "idle_current_a", "winding_resistance_ohm", "r_thermal_k_per_w",
                                    "c_thermal_j_per_k", "max_temp_c"}, "values not entered are named, not hidden"
    gdef = genome_definition("calf")
    for gene in ("act_hip_abd", "act_hip_flex", "act_knee", "act_small"):
        assert "test_servo" in gdef.gene(gene).choices

    lab = Lab.open(tmp_path / "p")
    try:
        before = lab.scene()["mass"]["total_g"]
        lab.execute("set_genes", {"values": {"act_knee": "test_servo"}})
        design = lab.design()
        assert lab.scene()["mass"]["total_g"] == pytest.approx(before - 4 * (165 - 20.0), abs=0.11)
        bom = {line["key"]: line for line in bill_of_materials(design.spec, lib)["lines"]}
        assert bom["test_servo"]["qty"] == 4 and bom["test_servo"]["mass_g"] == 80.0 and not bom["test_servo"]["verified"]
        knee = next(r for r in torque_margins(design.spec, lib, None) if r["joint"] == "joint.fl.knee")
        assert knee["component"] == "test_servo" and knee["stall_nm"] == 0.9
        assert knee["available_nm"] == pytest.approx(0.9 * 0.6)
        caps = speed_caps(design.spec, lib, 0.67)
        assert caps["joint.fl.knee"] == pytest.approx(60.0 * 6.0 * 0.67), "its no-load speed is the gait speed cap"
        assert caps["joint.fl.hip_flex"] == pytest.approx(30.0 * 6.0 * 0.67)
        model = compile_mjcf(design.spec, lib)
        i = model.actuator_ids.index("act.fl.knee")
        assert model.actuator_component[i] == "test_servo" and model.actuator_stall[i] == 0.9
        rep = component_audit(design.spec, lib, None)
        row = next(c for c in rep["components"] if c["key"] == "test_servo")
        assert row["in_design"] and row["verified"] is False and row["qty"] == 4
        assert row["guessed"] == ["armature_kgm2"] and "gear_ratio" in row["defaulted"]
        assert "test_servo" in next(r for r in rep["results"] if r["key"] == "mass")["depends_on_unverified"]
        card = lab.scene()["elements"]["act.fl.knee"]["component"]
        assert card["guessed"] == ["armature_kgm2"] and "max_temp_c" in card["defaulted"]
    finally:
        lab.close()


def test_c_battery_gene_and_new_material(own_config, tmp_path):
    from calflab.wiring import power_budget

    elec = own_config / "electronics.yaml"
    pack = {"key": "test_pack", "kind": "battery", "name": "Test 2S pack", "mass_g": 60.0, "dims_mm": [60.0, 30.0, 15.0],
            "voltage_v": 7.4, "capacity_mah": 1000, "max_current_a": 20, "source": "test fixture", "verified": False}
    elec.write_text(elec.read_text(encoding="utf-8") + "\n" + yaml.safe_dump([pack]), encoding="utf-8")
    mats = own_config / "materials.yaml"
    mat = {"key": "test_pla", "kind": "material", "role": "structure", "name": "Test PLA", "density_g_cm3": 1.1,
           "source": "test fixture", "verified": False}
    mats.write_text(mats.read_text(encoding="utf-8") + "\n" + yaml.safe_dump([mat]), encoding="utf-8")
    lib = library()
    assert lib.material("test_pla").defaulted == ["cost_usd_per_kg"]
    assert genome_definition("calf").gene("battery").choices == ["lipo_3s_5000", "test_pack"]
    lab = Lab.open(tmp_path / "p")
    try:
        before = lab.scene()["mass"]["total_g"]
        assert power_budget(lab.design().spec, lib, None)["bus_voltage_v"] == 11.1
        lab.execute("set_genes", {"values": {"battery": "test_pack"}})
        assert lab.scene()["mass"]["total_g"] == pytest.approx(before - 400 + 60, abs=0.11)
        pb = power_budget(lab.design().spec, lib, None)
        assert pb["bus_voltage_v"] == 7.4 and pb["battery"]["name"] == "Test 2S pack"
        reply = push_box(lab, material="test_pla")
        assert reply["mass_g"] == pytest.approx(1100.0)
        assert "test_pla" in {m["key"] for m in lab.scene()["materials"]}
    finally:
        lab.close()


def test_incomplete_and_bad_guess_lists_are_rejected():
    from calflab.components.library import IncompleteComponent, parse_component

    base = {"key": "x", "kind": "actuator", "name": "X", "source": "test", **SERVO}
    assert parse_component(base).guessed == []
    with pytest.raises(IncompleteComponent) as exc:
        parse_component({**base, "mass_g": None})
    assert exc.value.missing == ["mass_g"], "a missing mass is not 0 g"
    with pytest.raises(ValueError, match="'guessed' names"):
        parse_component({**base, "guessed": ["torque"]})


# ---------------------------------------------------------------------- Rhino
def test_pull_writes_material_and_mass_and_skips_the_envelope(lab):
    push_box(lab, material="pla")
    objects = {o["id"]: o for o in rhino_build_list(lab.design())["objects"]}
    assert "trunk.shell" not in objects, "the collision envelope is not drawn in Rhino"
    solid = next(o for o in objects.values() if o["kind"] == "mesh")
    assert solid["user_text"]["calflab.material"] == "pla"
    assert solid["user_text"]["calflab.mass_g"] == "1240.00" and solid["user_text"]["calflab.mass_source"] == "geometry"
    shank = objects["leg.fl.shank.tube"]["user_text"]
    assert shank["calflab.material"] == "petg" and shank["calflab.mass_source"] == "parametric"
    assert float(shank["calflab.mass_g"]) > 0
    motor = objects["act.fl.knee.motor"]["user_text"]
    assert motor["calflab.mass_source"] == "component" and "calflab.material" not in motor


def test_push_over_http_takes_a_material_and_reports_the_mass(tmp_path):
    from calflab_server.app import create_app
    from fastapi.testclient import TestClient

    path = repo_root() / "bridges" / "rhino" / "scripts" / "calflab_rhino.py"
    spec = importlib.util.spec_from_file_location("calflab_rhino_mass_test", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    lab = Lab.open(tmp_path / "p")
    try:
        with TestClient(create_app(lab, watch_plugins=False)) as client:
            assert [m["key"] for m in client.get("/api/bridge/rhino/materials").json()["materials"]][:2] == ["petg", "pla"]
            box = trimesh.creation.box((100.0, 100.0, 100.0))
            origin = np.array(next(b for b in lab.scene()["bodies"] if b["id"] == "trunk")["pos"])
            body = {"target": "trunk", "layer": "Structure", "name": "box", "material": "pla",
                    "vertices": (box.vertices + origin).tolist(), "faces": box.faces.tolist(),
                    "host": {"closed": True, "volume_mm3": 1.0e6}}
            reply = client.post("/api/bridge/rhino/push", json=body).json()
            assert reply["mass_from_geometry"] and reply["mass_g"] == 1240.0 and reply["volume_error"] == 0.0
            lines = script.push_report(reply, "trunk")
            assert "trunk structure mass is now 1240.0 g (1000.0 cm3 of pla" in lines[1]

            # a curved solid meshes a little small: the sender's exact volume is used when the two agree
            ball = trimesh.creation.icosphere(subdivisions=3, radius=40.0)
            exact = 4 / 3 * np.pi * 40.0**3
            curved = {**body, "vertices": (ball.vertices + origin).tolist(), "faces": ball.faces.tolist(),
                      "host": {"closed": True, "volume_mm3": exact}}
            reply = client.post("/api/bridge/rhino/push", json=curved).json()
            assert -0.02 < reply["volume_error"] < 0 and reply["solid"]["volume_source"] == "host"
            assert reply["mass_g"] == pytest.approx(exact / 1000 * 1.24, abs=0.01) and reply["warning"] == ""
            assert "Rhino's exact one" in script.push_report(reply, "trunk")[2]
            geom = next(g for g in lab.design().spec.body("trunk").geoms if g.shape == "mesh")
            assert geom.inertia[0] == pytest.approx(0.4 * geom.mass_g * 40.0**2, rel=0.02), "inertia scaled with the volume"
            # ... and not when they disagree about what the object is
            curved["host"] = {"closed": True, "volume_mm3": exact * 2}
            reply = client.post("/api/bridge/rhino/push", json=curved).json()
            assert reply["solid"]["volume_source"] == "mesh" and "different volume" in reply["warning"]
            assert reply["mass_g"] == pytest.approx(ball.volume / 1000 * 1.24, abs=0.01)

            body["faces"] = box.faces[:-2].tolist()
            reply = client.post("/api/bridge/rhino/push", json=body).json()
            assert not reply["mass_from_geometry"]
            assert "Rhino reports the object as closed" in reply["warning"]
            assert any(line.startswith("CALFLAB WARNING: The solid pushed onto trunk is not used for mass")
                       for line in script.push_report(reply, "trunk"))
            bad = client.post("/api/bridge/rhino/push", json={**body, "material": "steel"})
            assert bad.status_code == 400 and "not a structure material" in bad.json()["error"]
    finally:
        lab.close()
