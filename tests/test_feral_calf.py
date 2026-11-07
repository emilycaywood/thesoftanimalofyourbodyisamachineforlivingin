"""The final feral calf (ADR-065..069): skeleton, belts in the build, springs, masses, commands, loads."""

from __future__ import annotations

import math
from pathlib import Path

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
        f"belt_{d}_{f}" for d in ("stifle", "hock", "carpus", "shoulder") for f in ("system", "pulleys", "length")}
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


# ---------------------------------------------------------------------- servos per joint pair (ADR-101)
PAIRS = ("hip_abd", "stifle", "hock", "shoulder", "carpus")
FINGERPRINTS = Path(__file__).parent / "data" / "servo_fingerprints_r10.json"
PROJECT = Path(__file__).resolve().parents[1] / "projects" / "robot-calf-final"


def _fp():
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_servo_fingerprints", FINGERPRINTS.parent / "make_servo_fingerprints.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_bodies_are_bit_identical_through_the_pair_genes():
    """The default body and a v1 genome with a non-default ``actuator``: spec, MJCF and masses as built before the
    pair genes (fingerprints written with that code, tests/data/make_servo_fingerprints.py)."""
    import json

    want = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    fp = _fp()
    got = fp.builds(None)
    assert set(got) == {"default", "v1_sts3250"}
    for name, spec in got.items():
        assert fp.fingerprint(spec) == want[name], name
    assert {a.component for a in got["v1_sts3250"].actuators} == {"sts3250_c002"}
    # the same body from v2 genes, all five pairs set
    v2 = design({f"servo_{p}": "sts3250_c002" for p in PAIRS}).spec
    assert fp.fingerprint(v2) == want["v1_sts3250"]


@pytest.mark.skipif(not (PROJECT / "runs" / "20261105-232649-evolve-4237").is_dir(),
                    reason="projects/robot-calf-final (not in git) is only on the researcher's machine")
def test_the_projects_bodies_are_bit_identical_through_the_pair_genes():
    """projects/robot-calf-final: its document (v1 params, unversioned), a baked design and a run candidate."""
    import json

    want = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    fp = _fp()
    got = fp.builds(PROJECT)
    assert got.pop("run_candidate_id") == want["run_candidate_id"]
    for name in ("project_document", "baked_design", "run_candidate"):
        assert fp.fingerprint(got[name]) == want[name], name


def test_a_mixed_body_has_the_right_servo_on_each_joint(default):
    from calflab.model.mass import mass_breakdown

    lib = library()
    new, old = lib.actuator("sts3250_c002"), lib.actuator("sts3215_c018")
    spec = design({"servo_hip_abd": "sts3250_c002", "servo_hock": "sts3250_c002"}).spec
    for a in spec.actuators:
        want = "sts3250_c002" if a.joint.split(".")[-1] in ("hip_abd", "hock") else "sts3215_c018"
        assert a.component == want, a.id
        motor = next(g for b in spec.bodies for g in b.geoms if g.id == f"{a.id}.motor")
        assert motor.component == want and motor.mass_source == "component"
        assert motor.mass_g == (new if want == "sts3250_c002" else old).mass_g
        assert lib.actuator(want).name in (motor.label or "")
    assert spec.total_mass_g() == pytest.approx(default.spec.total_mass_g() + 4 * (new.mass_g - old.mass_g))
    b = mass_breakdown(spec, lib)  # ADR-050: the parts add up to the total
    assert b["total_g"] == pytest.approx(spec.total_mass_g(), abs=0.05)
    assert b["by_source_g"]["component"] == pytest.approx(6 * old.mass_g + 4 * new.mass_g)
    meta = spec.metadata["feral"]
    assert meta["servo"]["component"] == "sts3215_c018" and meta["servo"]["mixed"] is True
    assert {p: s["component"] for p, s in meta["servos"].items()} == {
        "hip_abd": "sts3250_c002", "stifle": "sts3215_c018", "hock": "sts3250_c002", "shoulder": "sts3215_c018",
        "carpus": "sts3215_c018"}
    assert "mixed" not in default.spec.metadata["feral"]["servo"]


def test_a_mixed_body_simulates_as_r9s_in_memory_swap(default):
    """Session R9 swapped servos on an in-memory spec (component and motor mass); the genes give the same model."""
    from calflab.sim import CompileOptions, compile_mjcf

    lib = library()
    new = lib.actuator("sts3250_c002")
    swapped = default.spec.model_copy(deep=True)
    for a in swapped.actuators:
        if a.joint.split(".")[-1] in ("stifle", "carpus"):
            a.component = new.key
            g = next(g for b in swapped.bodies for g in b.geoms if g.id == f"{a.id}.motor")
            g.mass_g, g.component = new.mass_g, new.key
    genes = design({"servo_stifle": new.key, "servo_carpus": new.key}).spec
    assert compile_mjcf(genes, lib, CompileOptions(), 0).xml == compile_mjcf(swapped, lib, CompileOptions(), 0).xml


def test_the_lab_shows_each_joints_servo_and_its_limits():
    from calflab.mech.limits import joint_servos

    lib = library()
    spec = design({"servo_hock": "sts3250_c002"}).spec
    rows = {r["joint"]: r for r in joint_servos(spec, lib)}
    assert len(rows) == 10
    hock, stifle, hip = rows["joint.hl.hock"], rows["joint.hl.stifle"], rows["joint.hl.hip_abd"]
    new, old = lib.actuator("sts3250_c002"), lib.actuator("sts3215_c018")
    assert hock["component"] == new.key and hock["mass_g"] == new.mass_g and stifle["component"] == old.key
    eff = spec.metadata["feral"]["checks"]["belt_efficiency"]
    assert hock["drive"] == "belt" and hock["ratio"] == 2.0
    assert hock["stall_joint_nm"] == pytest.approx(new.stall_torque_nm * 2.0 * eff, abs=1e-4)
    assert hock["rated_joint_nm"] == pytest.approx(new.rated_torque_nm * 2.0 * eff, abs=1e-4)
    assert hock["speed_joint_deg_s"] == pytest.approx(new.no_load_speed_rpm * 6.0 / 2.0, abs=0.01)
    assert hip["drive"] == "direct" and hip["speed_joint_deg_s"] == pytest.approx(old.no_load_speed_rpm * 6.0, abs=0.01)


def test_an_open_v1_document_builds_with_its_own_servo_and_is_upgraded_when_saved(tmp_path):
    import json

    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    f = project.path / "project.calflab.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    node = next(n for n in data["state"]["graph"]["nodes"] if n["type"] == "genome:feral_calf")
    for p in PAIRS:
        node["params"].pop(f"servo_{p}", None)
    node["params"]["actuator"] = "sts3250_c002"  # as a v1 document stored it
    f.write_text(json.dumps(data), encoding="utf-8")
    lab = Lab.open(project.path, create=False)
    try:
        assert {a.component for a in lab.design().spec.actuators} == {"sts3250_c002"}
        rows = lab.scene()["mass"]["servos"]
        assert {r["component"] for r in rows} == {"sts3250_c002"} and len(rows) == 10
        form = lab.genome_form(lab.state.graph)
        assert form is not None and form["values"]["servo_hock"] == "sts3250_c002" and "actuator" not in form["values"]
        lab.execute("set_mass_target", {"mass_g": 1500})  # any edit saves the document
        saved = next(n for n in json.loads(f.read_text(encoding="utf-8"))["state"]["graph"]["nodes"]
                     if n["type"] == "genome:feral_calf")["params"]
        assert "actuator" not in saved and {saved[f"servo_{p}"] for p in PAIRS} == {"sts3250_c002"}
        assert {a.component for a in lab.design().spec.actuators} == {"sts3250_c002"}
    finally:
        lab.close()


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


# ---------------------------------------------------------------------- turned-out legs (ADR-072)
def test_turned_out_legs_are_mount_angles_with_hooves_grounded_and_belts_unchanged(default):
    from calflab.mech.statics import default_contacts
    from calflab.model.xform import quat_mul, quat_rotate

    out = design({"hind_leg_toe": 10, "front_leg_toe": 10, "hind_leg_splay": 8, "front_leg_splay": 8}).spec
    for _body, p in default_contacts(out, out.world_poses()):
        assert p[2] == pytest.approx(0.0, abs=1e-6)
    base_feet = {b: p for b, p in default_contacts(default.spec, default.spec.world_poses())}
    for b, p in default_contacts(out, out.world_poses()):
        assert abs(p[1]) > abs(base_feet[b][1]) + 50  # 8 deg of splay puts every hoof well outward
    # the hip ab/ad axis turns with its mount: 10 deg of toe-out, mirrored left and right
    poses = out.world_poses()
    for k, sign in (("hl", 1), ("hr", -1)):
        j = out.joint(f"joint.{k}.hip_abd")
        ax = quat_rotate(quat_mul(poses["trunk"][1], out.body(j.body).quat), j.axis)
        assert ax[0] == pytest.approx(sign * math.cos(math.radians(10)), abs=1e-6)
        assert ax[1] == pytest.approx(math.sin(math.radians(10)), abs=1e-6)
    # no servo holds the angle: the joints, ranges and actuators are the same, and so are the belts
    assert [(j.id, j.range_deg) for j in out.joints] == [(j.id, j.range_deg) for j in default.spec.joints]
    assert {d: r["c_mm"] for d, r in out.metadata["feral"]["belt_drives"].items()} == {
        d: r["c_mm"] for d, r in default.spec.metadata["feral"]["belt_drives"].items()}
    assert out.metadata["feral"]["belts_ok"]


def test_legs_straight_by_default():
    gdef = genome_definition("feral_calf")
    for gid in ("hind_leg_toe", "hind_leg_splay", "front_leg_toe", "front_leg_splay"):
        g = gdef.gene(gid)
        assert g.default == 0
        # the splays evolve since session R step 3 (ADR-090); toe-out stays fixed
        assert g.evolvable == gid.endswith("_splay")


# ---------------------------------------------------------------------- wider blocks, hip springs (ADR-089)
def test_wider_blocks_move_the_legs_out_and_keep_the_hooves_grounded(default):
    from calflab.mech.statics import default_contacts

    base = default.spec.metadata["feral"]
    assert base["hip_block_width_mm"] == base["chest_block_width_mm"] == pytest.approx(140)  # rails 100 + 2 x 20
    wide = design({"hip_block_widen": 60, "chest_block_widen": 45})
    meta = wide.spec.metadata["feral"]
    assert meta["hip_block_width_mm"] == pytest.approx(260) and meta["chest_block_width_mm"] == pytest.approx(230)
    assert meta["leg_y_mm"] == pytest.approx(base["leg_y_mm"] + 60)
    assert meta["front_leg_y_mm"] == pytest.approx(base["front_leg_y_mm"] + 45)
    poses = wide.spec.world_poses()
    assert poses["leg.hl.femur"][0][1] == pytest.approx(-poses["leg.hr.femur"][0][1]) == pytest.approx(meta["leg_y_mm"])
    for _body, p in default_contacts(wide.spec, poses):
        assert p[2] == pytest.approx(0.0, abs=1e-6)
    assert meta["standing_height_mm"] == base["standing_height_mm"] and meta["belts_ok"]
    # the blocks' masses are not entered: widening changes no mass (an entered one would be kept and flagged)
    assert wide.spec.total_mass_g() == pytest.approx(default.spec.total_mass_g())


def test_hip_springs_are_off_by_default_and_pull_a_splayed_leg_in(default):
    assert not any(s.joint.endswith("hip_abd") for s in default.spec.springs)
    from calflab.mech.loads import static_spring_report

    splayed = design({"spring_hip_abd": True, "hind_leg_splay": 12.0})
    rows = {r["spring"]: r for r in static_spring_report(splayed.spec)}
    for k in ("hl", "hr"):
        r = rows[f"spring.{k}.hip_abd"]
        assert r["force_n"] > 0 and r["side"] == "resists", r  # against the weight's abduction
        assert r["servo_with_nm"] < r["servo_without_nm"]
    assert splayed.spec.metadata["feral"]["springs"]["hip_abd"]["enabled"]
    gdef = genome_definition("feral_calf")
    assert gdef.gene("spring_hip_abd_k").evolvable and gdef.gene("spring_hip_abd").absent is False
