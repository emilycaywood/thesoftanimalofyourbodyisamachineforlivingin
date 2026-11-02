"""The final feral calf (ADR-065..069): skeleton, belts in the build, springs, masses, commands, loads."""

from __future__ import annotations

import math

import numpy as np
import pytest
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.mech.springs import side_check, spring_force_n, spring_state
from calflab.model.genome import Genome

STIFLE = {"system": "GT2-2mm-10mm-generic", "pulleys": "30T-60T", "length": "GT2-2mm-444-C"}


def design(genes: dict | None = None, params: dict | None = None, project_dir=None):
    d = genome_definition("feral_calf")
    g = Genome(definition="feral_calf", version=d.version, values=d.complete({**d.defaults(), **(genes or {})}))
    return build_design(g, [], "feral_calf", params or {}, project_dir)


@pytest.fixture(scope="module")
def default():
    return design()


# ---------------------------------------------------------------------- skeleton
def test_standing_geometry_from_the_supplied_dimensions(default):
    spec = default.spec
    meta = spec.metadata["feral"]
    rad = math.radians
    rear = 200 * math.cos(rad(40)) + 245 * math.cos(rad(35)) + 230 * math.cos(rad(10)) + 30
    assert meta["standing_height_mm"] == pytest.approx(rear, abs=0.01) == pytest.approx(610.4, abs=0.1)
    # back level: the front angle is solved so the front hooves stand at the rear hooves' height
    assert (340 + 245) * math.cos(rad(meta["front_angle_deg"])) + 30 == pytest.approx(rear, abs=0.01)  # angle stored to 0.001 deg
    poses = spec.world_poses()
    assert poses["leg.hl.femur"][0][2] == pytest.approx(poses["leg.fl.upper"][0][2])  # hip and shoulder axles level
    assert poses["leg.fl.upper"][0][0] - poses["leg.hl.femur"][0][0] == pytest.approx(550)
    from calflab.mech.statics import default_contacts

    for _body, p in default_contacts(spec, poses):
        assert p[2] == pytest.approx(0.0, abs=1e-6)


def test_ten_servos_and_the_joint_map(default):
    spec = default.spec
    acts = {a.joint: a for a in spec.actuators}
    assert len(acts) == 10 and {a.component for a in acts.values()} == {"sts3215_c018"}
    for k in ("hl", "hr"):
        for j in ("hip_abd", "stifle", "hock"):
            assert f"joint.{k}.{j}" in acts
        assert spec.joint(f"joint.{k}.hip_abd").axis[1] == pytest.approx(0.0)  # fore-aft
    for k in ("fl", "fr"):
        assert f"joint.{k}.shoulder" in acts and f"joint.{k}.carpus" in acts and f"joint.{k}.hip_abd" not in acts
    trans = {t.id: t for t in spec.transmissions}
    belted = {a.joint for a in acts.values() if a.transmission}
    assert belted == {f"joint.{k}.{j}" for k in ("hl", "hr") for j in ("stifle", "hock")} | {"joint.fl.carpus", "joint.fr.carpus"}
    assert all(t.ratio == 2.0 and t.type == "belt" for t in trans.values())


def test_no_belt_crosses_a_joint_it_does_not_drive(default):
    spec = default.spec
    for k in ("hl", "hr"):
        femur = {g.id for g in spec.body(f"leg.{k}.femur").geoms}
        tibia = {g.id for g in spec.body(f"leg.{k}.tibia").geoms}
        cannon = {g.id for g in spec.body(f"leg.{k}.cannon").geoms}
        # driver servo and pulley on the segment above the joint, driven pulley fixed to the one below
        assert {f"act.{k}.stifle.motor", f"belt.{k}.stifle.driver", f"belt.{k}.stifle.span1"} <= femur
        assert f"belt.{k}.stifle.driven" in tibia
        assert {f"act.{k}.hock.motor", f"belt.{k}.hock.driver"} <= tibia and f"belt.{k}.hock.driven" in cannon


def test_carpus_belt_option(default):
    assert "carpus" not in design({"carpus_belt": False}).spec.metadata["feral"]["belted"]
    belted = default  # belted by default since ADR-071
    meta = belted.spec.metadata["feral"]
    assert "carpus" in meta["belted"]
    rep = meta["belt_drives"]["carpus"]
    assert rep["choice"]["length"] == "GT2-2mm-640-C"  # closest offered to the 680 mm target
    assert "act.fl.carpus.motor" in {g.id for g in belted.spec.body("leg.fl.upper").geoms}


def test_belted_range_beyond_180_degrees_is_refused(monkeypatch):
    from calflab.morphology import feral

    cfg = feral.feral_config()
    wide = {**cfg, "joint_ranges_deg": {**cfg["joint_ranges_deg"], "stifle": [-100, 100]}}
    monkeypatch.setattr(feral, "feral_config", lambda: wide)
    with pytest.raises(ValueError, match="at most 180 deg"):
        design()


def test_hock_default_avoids_the_stifle_belt_through_the_range(default):
    drives = default.spec.metadata["feral"]["belt_drives"]
    assert drives["stifle"]["choice"] == STIFLE and drives["stifle"]["ok"]
    hock = drives["hock"]
    assert hock["choice"]["length"] == "GT2-2mm-400-C" and hock["ok"]
    near_target = design({"belt_hock_length": "GT2-2mm-450-C"})
    rep = near_target.spec.metadata["feral"]["belt_drives"]["hock"]
    sweep = next(c for c in rep["checks"] if c["id"] == "stifle_belt_clearance")
    assert sweep["status"] == "fail" and "78 deg of flexion" in sweep["detail"]
    assert not near_target.spec.metadata["feral"]["belts_ok"]
    assert any("rejected" in w for w in near_target.warnings)


def test_no_gene_or_parameter_sets_a_belt_distance():
    gdef = genome_definition("feral_calf")
    for g in gdef.genes:
        if g.id.startswith("belt_"):  # a belt is catalog ids only: never a number, never evolved (ADR-070)
            assert g.type == "enum" and g.open and not g.evolvable and g.hidden, g.id
        else:
            assert not any(word in g.id for word in ("center", "centre", "servo_pos")), g.id
    assert {g.id for g in gdef.genes if g.id.startswith("belt_")} == {
        f"belt_{d}_{f}" for d in ("stifle", "hock", "carpus") for f in ("system", "pulleys", "length")}
    from calflab.morphology.feral import FeralCalfGenerator

    for name, f in FeralCalfGenerator.Params.model_fields.items():
        assert f.annotation is not float or not any(word in name for word in ("center", "centre", "c_mm", "servo")), name


# ---------------------------------------------------------------------- springs
def test_springs_pull_only():
    assert spring_force_n(50.0, 0.4, 64.5) == 0.0
    assert spring_force_n(114.5, 0.4, 64.5) == pytest.approx(20.0)
    st = spring_state((0, 0, 100), (0, 0, 0), (25, 0, 50), (0, 1, 0), 0.4, 50.0)
    assert st.force_n == pytest.approx(20.0) and st.arm_mm == pytest.approx(25.0)
    assert abs(st.torque_nm) == pytest.approx(0.5)
    slack = spring_state((0, 0, 40), (0, 0, 0), (25, 0, 20), (0, 1, 0), 0.4, 50.0)
    assert slack.slack and slack.force_n == 0.0 and slack.torque_nm == 0.0


def test_default_springs_at_standing_and_their_side(default):
    from calflab.mech.loads import static_spring_report

    rows = {r["spring"]: r for r in static_spring_report(default.spec)}
    st, hk, sh = rows["spring.hl.stifle"], rows["spring.hl.hock"], rows["spring.fl.shoulder"]
    assert st["force_n"] == pytest.approx(20, abs=0.5) and st["arm_mm"] == pytest.approx(25, abs=1.5)
    assert hk["force_n"] == pytest.approx(8, abs=0.5) and hk["arm_mm"] == pytest.approx(25, abs=1.5)
    assert sh["force_n"] == pytest.approx(8, abs=0.5) and sh["arm_mm"] == pytest.approx(25, abs=1.5)
    assert st["side"] == "resists" and hk["side"] == "resists"


def test_side_check_warns_when_the_spring_helps_the_fold():
    assert side_check(0.3, -0.2)[0] == "resists"
    verdict, note = side_check(0.3, 0.2)
    assert verdict == "helps_collapse" and "WARNING" in note
    assert side_check(0.3, 0.0)[0] == "slack"


def test_spring_genes_are_sliders_and_evolvable():
    gdef = genome_definition("feral_calf")
    for f in ("k", "free_length", "upper_along", "upper_normal", "lower_along", "lower_normal"):
        g = gdef.gene(f"spring_stifle_{f}")
        assert g.type == "float" and g.evolvable and g.provisional


# ---------------------------------------------------------------------- mass
def test_mass_adds_up_and_missing_parts_are_listed(default):
    from calflab.model.mass import mass_breakdown

    spec = default.spec
    b = mass_breakdown(spec, library())
    assert b["total_g"] == pytest.approx(spec.total_mass_g(), abs=0.05)
    assert b["by_source_g"]["component"] == pytest.approx(10 * 55)
    assert b["by_source_g"]["specified"] == pytest.approx(2 * 135 + 150)  # batteries + head and neck
    tube = math.pi / 4 * (15**2 - 12**2) * 1.55 / 1000  # g per mm of 15 x 12 CF tube
    legs = 2 * (200 + 245 + 230 + 340 + 245) * tube
    rails = 2 * math.pi / 4 * 8**2 * 550 * 1.55 / 1000
    assert b["by_source_g"]["tube"] == pytest.approx(legs + rails, abs=0.01)
    missing = {m["item"]: m["qty"] for m in b["missing"]}
    # six belted joints: a 30T and a 60T pulley each; collars on the hock and carpus servos
    assert missing["servo_horn_g"] == 10 and missing["pulley_30t"] == 6 and missing["clamp_collar_g"] == 4
    assert missing["hip_block_g"] == 1


def test_unknown_stall_current_is_reported_not_guessed():
    c = library().actuator("sts3215_c018")
    assert c.stall_current_a is None and "stall_current_a" in c.unknown and c.torque_constant_nm_per_a is None
    assert (c.stall_torque_nm, c.rated_torque_nm, c.mass_g, c.encoder_steps_per_rev, c.gear_ratio) == (2.94, 0.98, 55, 4096, 345)
    assert c.no_load_speed_rpm == pytest.approx(10 / 0.222, abs=0.01) and not c.verified


# ---------------------------------------------------------------------- simulation and loads
def test_quiet_standing_with_springs_is_deterministic(default):
    from calflab.mech.compare import run_scenario

    a, _, _ = run_scenario(default.spec, library(), "stand")
    b, _, _ = run_scenario(default.spec, library(), "stand")
    assert np.array_equal(a.body_pos, b.body_pos) and np.array_equal(a.spring_force, b.spring_force)
    i = a.spring_ids.index("spring.hl.stifle")
    assert a.spring_force[-1, i] == pytest.approx(20, abs=1.0)
    assert not a.meta["fell"]


def test_load_analysis_columns_and_belt_tension(default):
    from calflab.mech.compare import run_scenario
    from calflab.mech.loads import analyse, frames_csv, summary_csv, windowed_fraction

    meta = default.spec.metadata["feral"]
    r, _, cycle = run_scenario(default.spec, library(), "stand")
    res = analyse(r, default.spec, library(), cycle, meta["checks"], meta["belt_drives"])
    row = next(s for s in res["summary"] if s["joint"] == "joint.hl.stifle")
    d1 = meta["belt_drives"]["stifle"]["d1_mm"]
    assert row["belt_tension_peak_n"] == pytest.approx(row["servo_torque_peak_nm"] / (d1 / 2000), rel=1e-9)
    assert row["servo_torque_peak_nm"] == pytest.approx(row["joint_torque_peak_nm"] / 2.0)
    assert row["allowable_n"] == 44 and row["breaking_n"] == 860
    head = frames_csv(res).splitlines()[0].split(",")
    assert {"hl.stifle.joint_nm", "hl.stifle.servo_nm", "hl.stifle.spring_nm", "hl.stifle.belt_n",
            "hl.stifle.pct_rated", "hl.stifle.pct_stall"} <= set(head)
    assert summary_csv(res).splitlines()[0].startswith("joint,drive,servo")
    t = np.arange(0, 10, 0.1)
    assert windowed_fraction(t < 1.0, t, 4.0) == pytest.approx(0.25, abs=0.03)


def test_set_belt_drive_validates_and_undoes(tmp_path):
    from calflab.app import Lab
    from calflab.app.lab import LabError
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    assert (project.path / "catalog" / "belt_lengths.json").is_file()
    lab = Lab.open(project.path, create=False)
    try:
        def belts() -> dict:
            return {k: v for k, v in lab.state.graph.node("genome").params.items() if k.startswith("belt_")}

        start = belts()
        assert start["belt_stifle_length"] == "GT2-2mm-444-C" and start["belt_hock_length"] == "GT2-2mm-400-C"
        with pytest.raises(LabError, match="rejected"):
            lab.execute("set_belt_drive", {"drive": "hock", "length": "GT2-2mm-450-C"})
        with pytest.raises(LabError, match="width unconfirmed"):
            lab.execute("set_belt_drive", {"drive": "hock", "length": "GT2-2mm-396-A"})
        with pytest.raises(LabError, match="set_belt_drive"):
            lab.execute("set_node_params", {"node": "morphology", "params": {"auto_belts": True}})
        with pytest.raises(LabError, match="set_belt_drive"):
            lab.execute("set_genes", {"values": {"belt_hock_length": "GT2-2mm-394-C"}})
        assert belts() == start  # nothing changed
        out = lab.execute("set_belt_drive", {"drive": "hock", "length": "GT2-2mm-394-C"})["result"]
        assert out["c_mm"] == pytest.approx(151.7, abs=0.1)
        out = lab.execute("set_belt_drive", {"drive": "stifle", "system": "GT2-2mm-9mm-gates"})["result"]
        assert out["choice"]["length"].endswith("-B") and "re-chosen" in out["note"]
        lab.undo()
        lab.undo()
        assert belts() == start
        panel = lab.analysis("belt_drives")
        hock_opts = {o["id"]: o for o in panel["drives"]["hock"]["options"]["lengths"]}
        assert not hock_opts["GT2-2mm-450-A"]["selectable"] and "width unconfirmed" in hock_opts["GT2-2mm-450-A"]["reason"]
        assert not hock_opts["GT2-2mm-450-C"]["ok"]
        assert any(p["where"].startswith("gene rail_spacing") for p in panel["provisional"])
    finally:
        lab.close()


@pytest.mark.slow
def test_walk_and_lie_rise_keep_the_body_upright(default):
    from calflab.mech.compare import run_scenario

    for mode in ("walk", "lie_rise"):
        r, _, _ = run_scenario(default.spec, library(), mode)
        trunk = r.body_ids.index("trunk")
        assert not r.meta["fell"], mode
        assert r.body_pos[-1, trunk, 2] == pytest.approx(0.61, abs=0.01), mode
