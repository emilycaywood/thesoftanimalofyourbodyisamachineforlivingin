"""Printed mass of an infilled solid (ADR-054): print tags, the shell and the
core, and the estimate through the push, the breakdown, Rhino and the run record."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest
import trimesh
from calflab.app import Lab, LabError
from calflab.bridge import rhino_build_list
from calflab.bridge.sculpt import save_pushed_mesh
from calflab.components import library
from calflab.model.infill import measure_core, parse_print_tags, printed_solid
from calflab.model.solid import analyze_mesh
from calflab.paths import repo_root

#: the researcher's print settings (2026-10-08): 15 % infill, 2 perimeters of 0.4 mm
TAGS = {"infill": "15", "perimeters": "2", "line_width": "0.4"}
WALL = 0.8


@pytest.fixture()
def lab(tmp_path):
    lab = Lab.open(tmp_path / "p")
    lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
    lab.end_gesture()
    yield lab
    lab.close()


def structure(lab, body="trunk"):
    return next(r for r in lab.scene()["mass"]["breakdown"]["bodies"] if r["body"] == body)["structure"]


def part(lab, mesh, offset=(0.0, 0.0, 0.0), material="pla", name="", tags=None, target="trunk"):
    """One solid as the Rhino bridge sends it, with its calflab.print.* user text."""
    origin = np.array(next(b for b in lab.scene()["bodies"] if b["id"] == target)["pos"])
    out = {"name": name, "material": material, "vertices": (mesh.vertices + origin + np.array(offset)).tolist(),
           "faces": mesh.faces.tolist(), "host": {"closed": True, "volume_mm3": float(mesh.volume)}}
    if tags is not None:
        out["print"] = dict(tags)
    return out


def push(lab, parts, **kw):
    return save_pushed_mesh(lab, "trunk", [], [], layer="Structure", parts=parts, **kw)


def box(*size):
    return trimesh.creation.box(size)


# ---------------------------------------------------------------------- tags
def test_print_tags_are_read_as_written_and_nothing_is_assumed():
    assert parse_print_tags({}) is None and parse_print_tags(None) is None, "no print tags: a fully dense solid"
    s = parse_print_tags({"calflab.print.infill": "15 %", "calflab.print.perimeters": "2", "calflab.print.line_width": "0,4 mm"})
    assert (s.infill_pct, s.perimeters, s.line_width_mm, s.fraction) == (15.0, 2, 0.4, 0.15)
    assert s.wall_mm == pytest.approx(0.8) and s.ignored == []
    s = parse_print_tags({**TAGS, "top_layers": "3", "layer_height": "0.2"})
    assert s.ignored == ["calflab.print.layer_height", "calflab.print.top_layers"], "known to be there, not used"
    assert parse_print_tags({"layer_height": "0.2"}) is None, "none of the three tags: dense"
    with pytest.raises(ValueError, match=r"not calflab.print.perimeters, calflab.print.line_width.*no value is assumed"):
        parse_print_tags({"infill": "15"})
    with pytest.raises(ValueError, match="looks like a fraction"):
        parse_print_tags({**TAGS, "infill": "0.15"})
    with pytest.raises(ValueError, match="between 0 and 100"):
        parse_print_tags({**TAGS, "infill": "150"})
    with pytest.raises(ValueError, match="whole number, 1 or more"):
        parse_print_tags({**TAGS, "perimeters": "0"})
    with pytest.raises(ValueError, match="whole number, 1 or more"):
        parse_print_tags({**TAGS, "perimeters": "2.5"})
    with pytest.raises(ValueError, match="more than 0"):
        parse_print_tags({**TAGS, "line_width": "0"})
    with pytest.raises(ValueError, match="calflab.print.line_width = 'wide' is not a number"):
        parse_print_tags({**TAGS, "line_width": "wide"})


# ---------------------------------------------------------------------- the core
def test_the_core_of_a_box_is_the_box_one_wall_smaller_all_round():
    mesh = box(40.0, 30.0, 20.0).apply_translation((5.0, -3.0, 2.0))
    core = measure_core(mesh.vertices, mesh.faces, WALL)
    a, b, c = 40 - 2 * WALL, 30 - 2 * WALL, 20 - 2 * WALL
    shell = 40 * 30 * 20 - a * b * c
    assert 40 * 30 * 20 - core.volume_mm3 == pytest.approx(shell, rel=0.005), "the shell volume, checked by hand"
    assert core.com_mm == pytest.approx((5.0, -3.0, 2.0), abs=1e-3)
    assert core.inertia_mm5[:3] == pytest.approx(
        (a * b * c * (b * b + c * c) / 12, a * b * c * (a * a + c * c) / 12, a * b * c * (a * a + b * b) / 12), rel=0.005)
    # turned and moved, the same solid has the same core: the grid does not favour the axes
    turned = mesh.copy().apply_transform(trimesh.transformations.rotation_matrix(0.6, (1.0, 2.0, 3.0)))
    assert measure_core(turned.vertices, turned.faces, WALL).volume_mm3 == pytest.approx(core.volume_mm3, rel=0.002)
    # a coarser grid (a solid too large for the fine one) still measures a flat wall
    coarse = measure_core(mesh.vertices, mesh.faces, WALL, max_cells=20_000)
    assert coarse.pitch_mm > WALL and coarse.volume_mm3 == pytest.approx(a * b * c, rel=0.01)


def test_thin_features_have_no_core_and_the_core_never_exceeds_the_solid():
    for mesh in (box(80.0, 40.0, 1.5), box(80.0, 40.0, 1.6), trimesh.creation.cylinder(radius=0.7, height=50.0)):
        core = measure_core(mesh.vertices, mesh.faces, WALL)
        assert core.volume_mm3 == 0.0, "thinner than two walls: all shell"
        solid = analyze_mesh(mesh.vertices, mesh.faces)
        assert printed_solid(solid, core, 0.15)[0] == solid.volume_mm3, "it counts as fully dense, never less than nothing"
    # just thicker than two walls: a thin sliver of core, not a negative one
    plate = box(80.0, 40.0, 2.0)
    core = measure_core(plate.vertices, plate.faces, WALL)
    assert core.volume_mm3 == pytest.approx(78.4 * 38.4 * 0.4, rel=0.03)
    # a thick block with a thin fin (one object, two shells): the fin has no core, the block has
    both = trimesh.util.concatenate([box(40.0, 40.0, 40.0), box(40.0, 40.0, 1.5).apply_translation((100.0, 0.0, 0.0))])
    core = measure_core(both.vertices, both.faces, WALL)
    assert core.volume_mm3 == pytest.approx(38.4**3, rel=0.005) and core.com_mm == pytest.approx((0.0, 0.0, 0.0), abs=1e-3)
    solid = analyze_mesh(both.vertices, both.faces)
    for fraction in (0.0, 0.15, 0.5, 1.0):
        volume, com, inertia = printed_solid(solid, core, fraction)
        assert fraction * solid.volume_mm3 - 1e-6 <= volume <= solid.volume_mm3, "between all infill and fully dense"
        assert min(np.linalg.eigvalsh(np.array([[inertia[0], inertia[3], inertia[4]], [inertia[3], inertia[1], inertia[5]],
                                                [inertia[4], inertia[5], inertia[2]]]))) > 0
    assert printed_solid(solid, core, 1.0) == (solid.volume_mm3, solid.com_mm, solid.inertia_mm5), "100 % is the dense solid"
    # the centre of mass moves towards the fin, which keeps all its mass while the block loses most of its own
    block, fin = 40.0**3 - 0.85 * 38.4**3, 40.0 * 40.0 * 1.5
    volume, com, _ = printed_solid(solid, core, 0.15)
    assert volume == pytest.approx(block + fin, rel=0.002)
    assert com[0] == pytest.approx(100.0 * fin / (block + fin), rel=0.002) and com[0] > 3 * solid.com_mm[0]
    # a closed void inside the solid has walls of its own
    hollow = trimesh.util.concatenate([box(30.0, 30.0, 30.0), box(10.0, 10.0, 10.0)])
    hollow.faces[12:] = hollow.faces[12:, ::-1]
    core = measure_core(hollow.vertices, hollow.faces, WALL)
    assert core.volume_mm3 == pytest.approx(28.4**3 - 11.6**3, rel=0.005)


# ---------------------------------------------------------------------- the researcher's checks
def test_a_100_mm_pla_cube_at_15_percent_lies_between_all_infill_and_dense(tmp_path):
    """The 100 mm PLA cube that used to print "1000.0 cm3 of pla = 1240.0 g", now tagged 15 % infill,
    2 perimeters x 0.4 mm: shell 100^3 - 98.4^3 = 47 236 mm3 at full density, core 98.4^3 at 15 %."""
    from calflab_server.app import create_app
    from fastapi.testclient import TestClient

    path = repo_root() / "bridges" / "rhino" / "scripts" / "calflab_rhino.py"
    spec = importlib.util.spec_from_file_location("calflab_rhino_infill_test", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    density = library().material("pla").density_g_cm3
    core, shell = 98.4**3, 100.0**3 - 98.4**3
    expected = (shell + 0.15 * core) / 1000.0 * density
    lab = Lab.open(tmp_path / "p")
    try:
        lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
        lab.end_gesture()
        old = structure(lab)
        with TestClient(create_app(lab, watch_plugins=False)) as client:
            body = {"target": "trunk", "layer": "Structure", "name": "cube", "material": "",
                    "parts": [part(lab, box(100.0, 100.0, 100.0), name="cube", tags={**TAGS, "top_layers": "3"})]}
            reply = client.post("/api/bridge/rhino/push", json=body).json()
            assert reply["mass_from_geometry"] and reply["warning"] == "" and reply["estimate"] == "infill"
            assert 0.15 * 1000.0 * density < reply["mass_g"] < 1000.0 * density
            assert reply["mass_g"] == pytest.approx(expected, rel=0.001)  # 235.8 g with pla at 1.24 g/cm3
            info = reply["infill"]
            assert (info["infill_pct"], info["perimeters"], info["line_width_mm"], info["wall_mm"]) == (15.0, 2, 0.4, 0.8)
            assert info["volume_mm3"] == pytest.approx(1.0e6) and info["dense_g"] == pytest.approx(1000.0 * density)
            assert info["shell_volume_mm3"] == pytest.approx(shell, rel=0.002)
            assert info["shell_volume_mm3"] + info["core_volume_mm3"] == pytest.approx(1.0e6)
            lines = script.push_report(reply, "trunk")
            assert f"trunk structure mass is now {reply['mass_g']:.1f} g, an INFILL ESTIMATE (1000.0 cm3 outer volume of pla" in lines[1]
            assert lines[2].startswith("CALFLAB:   infill estimate: 15 % infill, 2 perimeters x 0.4 mm = 0.8 mm wall; shell 47.2 cm3 "
                                       "at full density + core 952.8 cm3 at 15 %; fully dense it would be ")
            assert any(line.startswith("CALFLAB: Infill estimate, not a weighed mass") for line in lines)
            assert any("calflab.print.top_layers is not used" in line for line in lines)

            # incomplete tags refuse the push; nothing is assumed and nothing changes
            bad = {**body, "parts": [{**body["parts"][0], "print": {"infill": "15"}}]}
            res = client.post("/api/bridge/rhino/push", json=bad)
            assert res.status_code == 400 and "Solid 'cube': it has print tags but not calflab.print.perimeters" in res.json()["error"]
            assert "Nothing was pushed" in res.json()["error"]

        st = structure(lab)
        assert (st["source"], st["material"]) == ("infill", "pla") and st["source_label"].startswith("Pushed solid, infill estimate")
        assert st["estimate_note"].startswith("Infill estimate, not a weighed mass") and st["replaced_g"] == pytest.approx(old["mass_g"])
        assert st["solids"][0]["infill"]["label"] == info["label"] and st["com_mm"] == pytest.approx([0.0, 0.0, 0.0], abs=0.01)
        b = lab.scene()["mass"]["breakdown"]
        assert b["by_source_g"]["infill"] == pytest.approx(st["mass_g"]) and b["by_source_g"]["geometry"] == 0
        assert b["geometry_parts"] == ["trunk"] and b["infill_parts"] == ["trunk"]
        assert sum(b["by_source_g"].values()) == pytest.approx(b["total_g"], abs=0.05)

        # inertia: the dense cube minus 85 % of its core, not a dense cube scaled down
        geom = next(g for g in lab.design().spec.body("trunk").geoms if g.shape == "mesh")
        ixx = density / 1000.0 * (1.0e6 * 2 * 100.0**2 / 12 - 0.85 * core * 2 * 98.4**2 / 12)
        assert geom.inertia[0] == pytest.approx(ixx, rel=0.002)
        assert geom.inertia[0] > 1.1 * geom.mass_g * 2 * 100.0**2 / 12, "more of the mass sits in the walls"

        # pulled into Rhino the solid carries its print tags, so pushing it back keeps the estimate
        text = next(o for o in rhino_build_list(lab.design())["objects"] if o["kind"] == "mesh")["user_text"]
        assert (text["calflab.print.infill"], text["calflab.print.perimeters"], text["calflab.print.line_width"]) == ("15", "2", "0.4")
        assert text["calflab.mass_source"] == "infill"

        # the run record keeps the print settings and the estimated mass of the solid
        job = lab.jobs.wait(lab.run_sim().id)
        assert job.status == "done", job.error
        rec = lab.registry.get_run(job.result["run_id"]).inputs["mass"]
        assert rec["infill_parts"] == ["trunk"] and rec["structure"]["trunk"]["source"] == "infill"
        solid = rec["structure"]["trunk"]["solids"][0]
        assert solid["mass_g"] == pytest.approx(expected, rel=0.001) and solid["material"] == "pla"
        assert (solid["infill"]["infill_pct"], solid["infill"]["perimeters"], solid["infill"]["line_width_mm"]) == (15.0, 2, 0.4)

        # another material in Properties: the density changes, the infill estimate stays on top of it
        lab.execute("set_part_material", {"target": "trunk", "material": "petg"})
        assert structure(lab)["mass_g"] == pytest.approx(reply["mass_g"] * library().material("petg").density_g_cm3 / density, abs=0.02)
        assert structure(lab)["source"] == "infill"
        lab.undo()
        # a weighed mass still wins, and the estimate stays visible beside it
        lab.execute("set_measured_mass", {"target": "trunk", "mass_g": 251.0})
        st = structure(lab)
        assert (st["mass_g"], st["source"], st["estimate_note"]) == (251.0, "measured", "")
        assert st["computed_g"] == pytest.approx(expected, rel=0.001)
        lab.undo()
        lab.undo()
        assert structure(lab) == old
        lab.redo()
        assert structure(lab)["source"] == "infill"
    finally:
        lab.close()


def test_100_percent_infill_weighs_exactly_what_an_untagged_solid_does(lab):
    mesh = box(40.0, 30.0, 20.0)
    plain = push(lab, [part(lab, mesh, offset=(10.0, 0.0, 0.0))])
    dense = next(g for g in lab.design().spec.body("trunk").geoms if g.shape == "mesh")
    assert structure(lab)["source"] == "geometry" and "infill" not in plain and "estimate" not in plain
    lab.undo()
    full = push(lab, [part(lab, mesh, offset=(10.0, 0.0, 0.0), tags={**TAGS, "infill": "100"})])
    geom = next(g for g in lab.design().spec.body("trunk").geoms if g.shape == "mesh")
    assert full["mass_g"] == plain["mass_g"] == pytest.approx(24.0 * library().material("pla").density_g_cm3)
    assert (geom.mass_g, geom.com, geom.inertia) == (dense.mass_g, dense.com, dense.inertia)
    assert structure(lab)["source"] == "infill", "it still says it was weighed as a print"


def test_untagged_solids_and_mixed_bodies_are_weighed_as_before(lab):
    lib = library()
    pla, steel = lib.material("pla").density_g_cm3, lib.material("stainless_304").density_g_cm3
    body, rod = box(40.0, 40.0, 40.0), box(3.0, 3.0, 100.0)
    printed = (40.0**3 - 0.85 * 38.4**3) / 1000.0 * pla
    reply = push(lab, [
        part(lab, body, name="body", tags=TAGS),
        part(lab, rod, offset=(60.0, 0.0, 0.0), material="stainless_304", name="rod"),
    ])
    assert reply["mass_from_geometry"] and reply["warning"] == "" and "note" not in reply
    rows = reply["solids"]
    assert rows[0]["mass_g"] == pytest.approx(printed, rel=0.002) and rows[0]["infill"]["infill_pct"] == 15.0
    assert rows[1]["mass_g"] == pytest.approx(0.9 * steel, abs=0.01) and rows[1]["infill"] is None, "the rod is fully dense"
    st = structure(lab)
    assert (st["source"], st["materials"]) == ("infill", ["pla", "stainless_304"])
    x = 60.0 * 0.9 * steel / (printed + 0.9 * steel)
    assert st["com_mm"] == pytest.approx([x, 0.0, 0.0], abs=0.05), "the steel rod pulls harder on a lighter body"
    b = lab.scene()["mass"]["breakdown"]
    assert b["by_source_g"]["infill"] == pytest.approx(rows[0]["mass_g"], abs=0.01)
    assert b["by_source_g"]["geometry"] == pytest.approx(0.9 * steel, abs=0.01)

    path = repo_root() / "bridges" / "rhino" / "scripts" / "calflab_rhino.py"
    spec = importlib.util.spec_from_file_location("calflab_rhino_infill_mixed_test", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    lines = script.push_report(reply, "trunk")
    assert "an INFILL ESTIMATE (64.9 cm3 outer volume of pla + stainless_304" in lines[1]
    assert lines[2] == f"CALFLAB:   solid 1 (body): 64.0 cm3 of pla = {rows[0]['mass_g']:.1f} g (infill estimate)"
    assert lines[3].startswith("CALFLAB:     infill estimate: 15 % infill, 2 perimeters x 0.4 mm = 0.8 mm wall; shell ")
    assert lines[4] == f"CALFLAB:   solid 2 (rod): 0.9 cm3 of stainless_304 = {rows[1]['mass_g']:.1f} g"

    # the all-or-nothing rule is unchanged: one open solid keeps the whole part on its estimate
    lab.undo()
    open_rod = part(lab, rod, offset=(60.0, 0.0, 0.0), material="stainless_304", name="rod")
    open_rod["faces"] = open_rod["faces"][:-2]
    reply = push(lab, [part(lab, body, name="body", tags=TAGS), open_rod])
    assert not reply["mass_from_geometry"] and "rod: it is open" in reply["warning"] and structure(lab)["source"] == "parametric"
    lab.undo()
    # a thin plate tagged for infill counts as fully dense and says why
    reply = push(lab, [part(lab, box(60.0, 40.0, 1.5), tags=TAGS)])
    assert reply["mass_g"] == pytest.approx(3.6 * pla, abs=0.01)
    assert "no core (nowhere thicker than two walls), so all 3.6 cm3 count at full density" in reply["infill"]["label"]
    # a bad tag on one solid of several refuses the whole push
    with pytest.raises(LabError, match=r"Solid 'body': calflab.print.infill = 'lots' is not a number.*Nothing was pushed"):
        push(lab, [part(lab, body, name="body", tags={**TAGS, "infill": "lots"}), part(lab, rod, offset=(60.0, 0.0, 0.0))])
    # on Skin the tags mean nothing: look only, as before
    reply = save_pushed_mesh(lab, "trunk", [], [], layer="Skin", parts=[part(lab, body, tags={"infill": "15"})])
    assert "changes the look only" in reply["note"]
