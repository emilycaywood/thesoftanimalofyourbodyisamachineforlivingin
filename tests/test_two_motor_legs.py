"""Two-motor front legs (abduction + elbow), the gait that drives them, and
gait tuning for a fixed body."""

import numpy as np
import pytest
from calflab.app import Lab, LabError
from calflab.bridge import armature_plan, rhino_build_list
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.evolve.gait import GaitTuneSettings, speed_caps, speed_excess
from calflab.model.genome import Genome
from calflab.model.xform import quat_rotate
from calflab.plugins import registry
from calflab.sim import SimSettings, compile_mjcf, compute_metrics, run_rollout


def _cpg():
    return registry.get("controller", "cpg")


def design(**genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes))


def test_three_motors_stay_the_default_and_old_genomes_keep_them():
    gdef = genome_definition("calf")
    g = gdef.gene("front_hip_flex")
    assert g.default is True and g.absent is True and not g.evolvable
    old = {k: v for k, v in gdef.defaults().items() if k != "front_hip_flex"}
    assert gdef.complete(old)["front_hip_flex"] is True


@pytest.mark.parametrize("knee_forward", [False, True])
def test_two_motor_front_legs_drop_only_the_front_hip_flexion(knee_forward):
    three = design(front_knee_forward=knee_forward).spec
    two = design(front_hip_flex=False, front_knee_forward=knee_forward).spec
    gone = {"joint.fl.hip_flex", "joint.fr.hip_flex"}
    assert {j.id for j in three.joints} - {j.id for j in two.joints} == gone
    assert {a.id for a in three.actuators} - {a.id for a in two.actuators} == {"act.fl.hip_flex", "act.fr.hip_flex"}
    assert len(two.actuators) == 16 and {a.joint for a in two.actuators} == {j.id for j in two.joints}
    assert {b.id for b in two.bodies} == {b.id for b in three.bodies}, "part IDs do not change"
    motor = library().actuator("xh540_w270").mass_g
    assert three.total_mass_g() - two.total_mass_g() == pytest.approx(2 * motor)
    # the fixed thigh sits exactly where the motor used to hold it: same standing pose, hooves on the ground
    p2, p3 = two.world_poses(), three.world_poses()
    for b in two.bodies:
        assert np.allclose(p2[b.id][0], p3[b.id][0], atol=1e-6), b.id
        for g in b.geoms:
            if g.foot:
                assert p2[b.id][0][2] + quat_rotate(p2[b.id][1], g.pos)[2] - g.size[0] == pytest.approx(0.0, abs=0.5)
    assert all("hip_flex" not in j for r in two.skin_regions if r.id in ("skin.leg.fl", "skin.leg.fr") for j in r.joints)
    assert "joint.hl.hip_flex" in next(r for r in two.skin_regions if r.id == "skin.leg.hl").joints


def test_two_motor_body_compiles_simulates_and_reaches_the_bridges():
    d = design(front_hip_flex=False, front_knee_forward=False)
    cm = compile_mjcf(d.spec, library())
    assert len(cm.actuator_joint) == 16 and "joint.fl.hip_flex" not in cm.joint_ids
    m = compute_metrics(run_rollout(cm, _cpg()({"gait": "walk"}), SimSettings(duration_s=3.0), library()))
    assert len(m["by_actuator"]) == 16 and not m["fell"]
    lying = run_rollout(cm, _cpg()({}), SimSettings(duration_s=1.0, start_pose="lying"), library())
    assert lying.n_frames > 0
    plan = armature_plan(d.spec)
    bones = {b["name"]: b for b in plan["bones"]}
    assert "joint.fl.hip_flex" not in bones and bones["joint.fl.knee"]["parent"] == "joint.fl.hip_abd"
    assert bones["joint.hl.knee"]["parent"] == "joint.hl.hip_flex"
    meshes = {m["id"]: m["bone"] for m in plan["meshes"]}
    assert meshes["leg.fl.thigh.tube"] == "joint.fl.hip_abd", "the fixed thigh moves with the hip"
    rb = rhino_build_list(d)
    ids = {o["id"] for o in rb["objects"]}
    assert "act.fl.hip_flex.motor" not in ids and "act.hl.hip_flex.motor" in ids and "leg.fl.thigh.tube" in ids
    assert {a["id"] for a in rb["annotations"]} == {j.id for j in d.spec.joints}


def test_cpg_steps_a_two_motor_leg_with_elbow_and_abduction():
    from calflab.plugins import ControlInfo, Observation

    ids = ["joint.fl.hip_abd", "joint.fl.knee", "joint.hl.hip_abd", "joint.hl.hip_flex", "joint.hl.knee"]
    n = len(ids)
    info = ControlInfo(actuator_ids=[i.replace("joint", "act") for i in ids], joint_ids=ids, rest=np.zeros(n),
                       lo=-np.ones(n) * 3, hi=np.ones(n) * 3, control_dt=0.02)
    c = _cpg()({"gait": "walk", "frequency": 1.0, "swing_fraction": 0.5, "ramp": 0.0, "elbow_amplitude": 20, "elbow_offset": 4,
             "swing_abduction": 10, "hip_amplitude": 8, "hip_offset": -3, "crouch": 0})
    c.reset(info)

    def at(t):
        q = c.act(Observation(t=t, q=np.zeros(n), dq=np.zeros(n), trunk_quat=np.array([1.0, 0, 0, 0]),
                              trunk_gyro=np.zeros(3), foot_contact=np.zeros(4)))
        return np.degrees(q)

    fl_abd, fl_knee, hl_abd, hl_hip, _ = 0, 1, 2, 3, 4
    # front left (phase 0): stance for the first half stride, the elbow sweeps from -a to +a about its offset
    assert at(0.0)[fl_knee] == pytest.approx(4 - 20) and at(0.25)[fl_knee] == pytest.approx(4.0)
    assert at(0.0)[fl_abd] == pytest.approx(0.0), "no lift in stance"
    # swing: it returns forward while the leg swings outward (left leg: positive abduction), peaking mid-swing
    assert at(0.75)[fl_abd] == pytest.approx(10.0) and at(0.75)[fl_knee] == pytest.approx(4.0, abs=1e-6)
    # the three-motor hind leg is driven as before and its abduction is left alone
    assert at(0.0)[hl_abd] == 0.0 and abs(at(0.1)[hl_hip] + 3) <= 8.0 + 1e-9

    peaks = _cpg().peak_joint_speeds(c.params.model_dump(), ids)
    assert peaks["joint.fl.knee"] == pytest.approx(max(2 * 20 / 0.5, np.pi * 20 / 0.5))
    assert peaks["joint.fl.hip_abd"] == pytest.approx(np.pi * 10 / 0.5)
    assert peaks["joint.hl.hip_flex"] == pytest.approx(max(2 * 8 / 0.5, np.pi * 8 / 0.5))
    assert set(_cpg().relevant_dims(ids)) == {d.name for d in _cpg().vector_dims()}
    assert "elbow_amplitude" not in _cpg().relevant_dims([i for i in ids if ".hl." in i])


def test_speed_caps_come_from_the_recorded_motor_speeds(calf_design):
    caps = speed_caps(calf_design.spec, library(), 0.5)
    lib = library()
    assert caps["joint.fl.knee"] == pytest.approx(lib.actuator("xh540_w270").no_load_speed_rpm * 6 * 0.5)
    assert caps["joint.fl.hip_abd"] == pytest.approx(lib.actuator("xm430_w350").no_load_speed_rpm * 6 * 0.5)
    assert speed_excess({"joint.fl.knee": caps["joint.fl.knee"] * 1.2}, caps) == pytest.approx(0.2)
    assert speed_excess({"joint.fl.knee": 1.0}, caps) < 0
    default_peaks = _cpg().peak_joint_speeds({}, [a.joint for a in calf_design.spec.actuators])
    assert speed_excess(default_peaks, speed_caps(calf_design.spec, library(), GaitTuneSettings().speed_fraction)) <= 0.0


def test_tune_gait_finds_a_gait_for_the_body_and_is_undoable(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        lab.execute("set_genes", {"values": {"front_hip_flex": False, "front_knee_forward": False}})
        for part, mm in (("leg.fl.thigh", 100), ("leg.fr.thigh", 100), ("leg.fl.shank", 236), ("leg.fr.shank", 236)):
            lab.execute("add_override", {"target": part, "param": "length", "value": mm})
        before = dict(lab.state.graph.role("controller").params)
        genes = dict(lab.state.graph.role("genome").params)
        out = lab.execute("tune_gait", {"iterations": 4, "popsize": 6, "duration_s": 3, "gaits": ["walk"], "seed": 3},
                          )["result"]
        job = lab.jobs.wait(out["job"], timeout=600)
        assert job.status == "done", job.error
        r = job.result
        after = lab.state.graph.role("controller").params
        assert r["applied"] and after == _cpg().Params.model_validate(r["params"]).model_dump(mode="json") and after != before
        assert after["gait"] == "walk" and r["after"]["speed_excess"] == 0 and not r["after"]["metrics"]["fell"]
        assert r["after"]["fitness"] >= r["before"]["fitness"] or r["before"]["speed_excess"] > 0
        assert max(r["after"]["peak_speed_deg_s"].values()) <= max(r["speed_caps_deg_s"].values())
        assert lab.state.graph.role("genome").params == genes and len(lab.state.overrides) == 4, "the body is not touched"
        rec = lab.registry.get_run(r["run_id"])
        assert rec.kind == "tune" and rec.controller["params"] == r["params"] and len(rec.overrides) == 4
        assert lab.registry.check() == []
        lab.undo()
        assert lab.state.graph.role("controller").params == before
        with pytest.raises(LabError, match="invalid parameters"):
            lab.tune_gait({"iterations": 0})
    finally:
        lab.close()
