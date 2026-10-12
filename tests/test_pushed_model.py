"""A whole modelled robot pushed from Rhino (ADR-062): joints from axis lines,
mass and collision from solids, one override, recorded with the run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from calflab.app import Lab
from calflab.bridge.rhino_model import model_layout, save_pushed_model
from calflab.components import library
from calflab.model.pushed_model import support_hull
from calflab.sim.mjcf import CompileOptions, compile_mjcf

TWO_JOINT = {"front_hip_abd": False, "hind_hip_abd": False, "scale": 0.337, "has_neck_yaw": False,
             "has_neck_pitch": False, "has_head_pitch": False, "has_tail": False, "has_ears": False}
PRINT = {"infill": "20", "perimeters": "5", "line_width": "0.4"}


def box(centre: Any, size: Any) -> tuple[list[list[float]], list[list[int]]]:
    import trimesh

    m = trimesh.creation.box(extents=size)
    m.apply_translation(centre)
    return m.vertices.tolist(), m.faces.tolist()


def solid(body: str, centre: Any, size: Any, material: str = "pla", **kw: Any) -> dict[str, Any]:
    v, f = box(centre, size)
    return {"body": body, "name": kw.pop("name", f"{body} box"), "material": material, "vertices": v, "faces": f,
            "host": {"closed": True, "volume_mm3": float(np.prod(size))}, **kw}


@pytest.fixture
def lab(tmp_path: Path) -> Any:
    lab = Lab.open(tmp_path / "proj")
    lab.execute("set_genes", {"values": TWO_JOINT})
    yield lab
    lab.close()


def payload(lab: Any, shift: tuple[float, float, float] = (3.0, 0.0, -4.0)) -> dict[str, Any]:
    """Every axis line moved by ``shift``; a trunk box, and per leg a thigh box,
    a shank box and a foot box under the (moved) knee."""
    layout = model_layout(lab.design())
    poses = lab.design().spec.world_poses()
    joints = [{"id": a["id"], "from": [a["from"][k] + shift[k] for k in range(3)], "to": [a["to"][k] + shift[k] for k in range(3)]}
              for a in layout["axes"]]
    solids = [solid("trunk", poses["trunk"][0], (120.0, 40.0, 30.0), print=PRINT)]
    for k in ("fl", "fr", "hl", "hr"):
        knee = np.asarray(poses[f"leg.{k}.shank"][0]) + np.asarray(shift)
        hip = np.asarray(poses[f"leg.{k}.thigh"][0]) + np.asarray(shift)
        solids.append(solid(f"leg.{k}.thigh", (hip + knee) / 2.0, (8.0, 8.0, 20.0)))
        solids.append(solid(f"leg.{k}.shank", knee + (0.0, 0.0, -15.0), (8.0, 8.0, 20.0)))
        solids.append(solid(f"leg.{k}.shank", knee + (0.0, 0.0, -32.0), (14.0, 10.0, 6.0), foot=True, name=f"{k} foot"))
        solids.append(solid(f"leg.{k}.shank", knee + (0.0, 0.0, -15.0), (2.0, 2.0, 2.0), material="stainless_304", name=f"{k} pin"))
    return {"file": "prototype.3dm", "name": "Rhino model", "joints": joints, "solids": solids}


def test_support_hull_keeps_the_lowest_point_and_is_small() -> None:
    import trimesh

    ball = trimesh.creation.icosphere(subdivisions=4, radius=10.0)
    hull = np.asarray(support_hull(ball.vertices, 32, keep=((0.0, 0.0, -1.0),)))
    assert 4 <= len(hull) <= 32
    assert hull[:, 2].min() == pytest.approx(ball.vertices[:, 2].min(), abs=1e-3)
    assert support_hull([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]]) == []  # flat: no volume


def test_joints_move_to_the_axis_lines_and_are_reported_against_the_parametric_ones(lab: Any) -> None:
    before = {j["id"]: j["world_pos"] for j in lab.scene()["joints"]}
    r = save_pushed_model(lab, payload(lab))
    assert r["ok"] and r["stored"], r["errors"]
    after = {j["id"]: j["world_pos"] for j in lab.scene()["joints"]}
    for jid, p in before.items():
        assert after[jid] == pytest.approx([p[0] + 3.0, p[1], p[2] - 4.0], abs=0.01), jid
    rows = {row["joint"]: row for row in r["joints"]}
    assert len(rows) == 8
    for row in rows.values():
        assert row["source"] == "model"
        assert row["delta_mm"] == pytest.approx([3.0, 0.0, -4.0], abs=0.01)
        assert row["distance_mm"] == pytest.approx(5.0, abs=0.01)
        assert row["axis_angle_deg"] == pytest.approx(0.0, abs=0.01)
    assert any("moved 5.0 mm" in line for line in r["lines"])


def test_a_tilted_axis_line_tilts_the_joint_and_points_the_parametric_way(lab: Any) -> None:
    p = payload(lab, shift=(0.0, 0.0, 0.0))
    knee = next(j for j in p["joints"] if j["id"] == "joint.fl.knee")
    mid = (np.asarray(knee["from"]) + np.asarray(knee["to"])) / 2.0
    d = np.array([0.0, np.cos(np.radians(10.0)), np.sin(np.radians(10.0))])
    knee["from"], knee["to"] = (mid + d * 20).tolist(), (mid - d * 20).tolist()  # drawn the other way round
    r = save_pushed_model(lab, p)
    row = next(row for row in r["joints"] if row["joint"] == "joint.fl.knee")
    assert row["axis_angle_deg"] == pytest.approx(10.0, abs=0.01)
    assert row["distance_mm"] == pytest.approx(0.0, abs=0.01)
    world = next(j for j in lab.scene()["joints"] if j["id"] == "joint.fl.knee")["world_axis"]
    assert world == pytest.approx(d.tolist(), abs=1e-4)


def test_solids_give_mass_and_hulls_replace_the_envelope_and_the_hoof(lab: Any) -> None:
    lib = library()
    r = save_pushed_model(lab, payload(lab))
    spec = lab.design().spec
    shank = spec.body("leg.fl.shank")
    assert [g.id for g in shank.geoms if g.foot] == ["leg.fl.shank.foot"]  # the hoof sphere is gone
    assert not any(g.layer == "Structure" and g.shape != "mesh" and g.component is None for g in shank.geoms)
    hulls = [g for g in shank.geoms if g.hull]
    assert len(hulls) == 3 and all(g.role == "collision" and g.mass_g == 0 for g in hulls)
    pla, steel = lib.get("pla").density_g_cm3, lib.get("stainless_304").density_g_cm3
    expected = (8 * 8 * 20 + 14 * 10 * 6) / 1000.0 * pla + 8 / 1000.0 * steel
    row = next(b for b in r["bodies"] if b["body"] == "leg.fl.shank")
    assert row["mass_g"] == pytest.approx(expected, abs=0.02)
    assert row["materials"] == ["pla", "stainless_304"] and row["collision"] == "hulls" and row["foot"]
    trunk = next(b for b in r["bodies"] if b["body"] == "trunk")
    assert trunk["source"] == "infill" and trunk["mass_g"] < 120 * 40 * 30 / 1000.0 * pla
    assert {h["id"] for h in r["hooves_removed"]} == {f"leg.{k}.hoof" for k in ("fl", "fr", "hl", "hr")}
    # the breakdown still adds up
    assert r["mass"]["total_g"] == pytest.approx(spec.total_mass_g(), abs=0.01)
    assert r["structure"] == {"free_bodies": 1, "hinges": 8, "dof": 14, "rigid_bodies": len(spec.bodies),
                              "modelled_bodies": 9, "solids": 17, "loose_solids": 0}


def test_the_simulator_collides_the_hulls_and_each_body_is_one_rigid_piece(lab: Any) -> None:
    import mujoco

    save_pushed_model(lab, payload(lab))
    spec = lab.design().spec
    cm = compile_mjcf(spec, library(), CompileOptions(include_skin=False))
    assert cm.foot_geoms == [f"leg.{k}.shank.foot" for k in ("fl", "fr", "hl", "hr")]
    model = mujoco.MjModel.from_xml_string(cm.xml)
    assert model.nv == 6 + 8 and model.njnt == 1 + 8  # one free body and eight hinges: no solid moves on its own
    assert model.nmesh == sum(1 for b in spec.bodies for g in b.geoms if g.hull)
    colliding = {model.geom(i).name for i in range(model.ngeom) if model.geom_contype[i] and model.geom(i).name != "floor"}
    assert colliding == {g.id for b in spec.bodies for g in b.geoms if g.role in ("collision", "both")}
    assert not any(n.endswith((".tube", ".hoof", ".shell")) for n in colliding if n.startswith("leg."))
    assert float(model.body_mass.sum()) == pytest.approx(cm.total_mass_kg, abs=1e-5)  # the hulls add no mass
    # it starts with its own lowest foot point 2 mm above the floor, and stands on its feet
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    for _ in range(500):
        mujoco.mj_step(model, data)
    floor = model.geom("floor").id
    touching = {model.geom(int(c.geom1 if c.geom2 == floor else c.geom2)).name for c in data.contact[: data.ncon]}
    assert touching <= set(cm.foot_geoms) and len(touching) >= 3
    assert data.qpos[2] == pytest.approx(cm.root_height, abs=0.004)


def test_run_json_says_which_geometry_was_used(lab: Any) -> None:
    lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
    first = lab.jobs.wait(lab.run_sim().id).result
    rec = lab.registry.get_run(first["run_id"])
    assert rec.inputs["geometry"]["source"] == "parametric" and rec.inputs["geometry"]["collision"] == "envelope"
    r = save_pushed_model(lab, payload(lab))
    job = lab.jobs.wait(lab.run_sim().id)
    assert job.status == "done", job.error
    second = job.result
    assert second["run_id"] != first["run_id"] and not second["cached"]  # F5 after a push is a new run
    geo = lab.registry.get_run(second["run_id"]).inputs["geometry"]
    assert geo["source"] == "rhino_model" and geo["file"] == "prototype.3dm" and geo["override"] == r["override"]
    assert geo["collision"] == "hulls" and len(geo["joints"]) == 8 and geo["max_joint_distance_mm"] == pytest.approx(5.0, abs=0.01)
    assert geo["bodies"]["leg.fl.shank"]["solids"] == 3 and len(geo["bodies"]["leg.fl.shank"]["meshes"][0]["sha256"]) == 64
    assert geo["feet"] == [f"leg.{k}.shank.foot" for k in ("fl", "fr", "hl", "hr")]


def test_switching_the_model_off_and_undo_bring_the_parametric_calf_back(lab: Any) -> None:
    before = lab.design().spec.model_dump(mode="json")
    r = save_pushed_model(lab, payload(lab))
    assert lab.design().spec.model_dump(mode="json") != before
    lab.execute("toggle_override", {"id": r["override"], "enabled": False})
    assert lab.design().spec.model_dump(mode="json") == before
    lab.execute("toggle_override", {"id": r["override"], "enabled": True})
    again = save_pushed_model(lab, payload(lab))  # a second push replaces the first: still one model
    assert [o.id for o in lab.state.overrides if o.kind == "model"] == [again["override"]]
    lab.undo()
    lab.undo()
    lab.undo()
    lab.undo()
    assert lab.design().spec.model_dump(mode="json") == before
    assert lab.state.graph.role("genome").params["scale"] == 0.337  # the genome was never touched


def test_a_bad_model_is_refused_whole_with_every_problem_listed(lab: Any) -> None:
    p = payload(lab)
    v, f = box((0, 0, 0), (5, 5, 5))
    p["solids"].append({"body": "leg.fl.shank", "name": "open lid", "material": "pla", "vertices": v, "faces": f[:-2]})
    p["solids"].append(solid("my_tail", (0, 0, 0), (5, 5, 5), name="stray"))
    p["solids"].append(solid("head", (0, 0, 0), (5, 5, 5), material="unobtainium", name="nose"))
    p["solids"].append(solid("head", (0, 0, 0), (5, 5, 5), name="half tagged", print={"infill": "20"}))
    p["joints"].append({"id": "joint.fl.wrist", "from": [0, 0, 0], "to": [0, 1, 0]})
    r = save_pushed_model(lab, p)
    assert not r["ok"] and not r["stored"] and len(r["errors"]) == 5
    assert r["structure"]["loose_solids"] == 1
    assert r["lines"][0].startswith("NOT PUSHED")
    assert not [o for o in lab.state.overrides if o.kind == "model"]
    assert not (lab.project.path / "assets" / "model").exists()


def test_check_only_reports_and_stores_nothing(lab: Any) -> None:
    r = save_pushed_model(lab, payload(lab), check_only=True)
    assert r["ok"] and not r["stored"] and len(r["joints"]) == 8
    assert not lab.state.overrides and not (lab.project.path / "assets" / "model").exists()


def test_parts_without_solids_or_lines_stay_parametric_and_are_named(lab: Any) -> None:
    p = payload(lab)
    p["joints"] = [j for j in p["joints"] if j["id"] != "joint.hr.knee"]
    p["solids"] = [s for s in p["solids"] if not s.get("foot") or s["body"] != "leg.hr.shank"]
    r = save_pushed_model(lab, p)
    assert r["ok"]
    text = " ".join(r["warnings"])
    assert "No axis line for joint.hr.knee" in text and "head" in text and "leg.hr.shank" in text
    spec = lab.design().spec
    assert [g.id for g in spec.body("leg.hr.shank").geoms if g.foot] == ["leg.hr.hoof"]
    assert next(row for row in r["joints"] if row["joint"] == "joint.hr.knee")["source"] == "parametric"
