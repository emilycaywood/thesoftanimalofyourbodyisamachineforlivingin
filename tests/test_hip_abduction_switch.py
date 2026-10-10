"""Hip abduction can be left out per pair of legs (ADR-057), the model settings
for a small body (ADR-058) and the proportion study (ADR-059). Lengths and
ranges used here are test values, not the researcher's measurements."""

import numpy as np
import pytest
from calflab.app import Lab
from calflab.bridge import armature_plan, rhino_build_list
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.evolve.study import (
    ProportionStudySettings,
    design_real,
    sample_unit,
    spearman,
    study_dimensions,
    summarize,
    variant_genes,
)
from calflab.model.genome import Genome
from calflab.model.mass import mass_breakdown
from calflab.plugins import registry
from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout
from calflab.wiring import power_budget

FRONT, HIND = ("fl", "fr"), ("hl", "hr")
#: the simplified prototype: two joints per leg, no neck, head, tail or ear motors
TWO_JOINT = {
    "scale": 0.337, "front_hip_abd": False, "hind_hip_abd": False, "front_knee_forward": True, "hind_knee_forward": False,
    "has_neck_yaw": False, "has_neck_pitch": False, "has_head_pitch": False, "has_tail": False, "has_ears": False,
    "act_hip_flex": "scs0009", "act_knee": "scs0009", "battery": "lipo_2s_1100",
}


def design(overrides=None, **genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes), overrides)


def test_the_switches_change_nothing_until_they_are_switched_off():
    gdef = genome_definition("calf")
    for gene in ("front_hip_abd", "hind_hip_abd"):
        assert (gdef.gene(gene).default, gdef.gene(gene).absent, gdef.gene(gene).evolvable) == (True, True, False)
    old = {k: v for k, v in gdef.defaults().items() if k not in ("front_hip_abd", "hind_hip_abd")}
    assert gdef.complete(old)["front_hip_abd"] is True and gdef.complete(old)["hind_hip_abd"] is True
    base = design().spec
    assert len(base.joints) == 18 and len(base.actuators) == 18
    assert base.model_dump() == build_design(Genome(definition="calf", version=gdef.version, values=old)).spec.model_dump()


@pytest.mark.parametrize(("front", "hind"), [(False, True), (True, False), (False, False)])
def test_a_pair_without_abduction_is_hip_pitch_then_knee(front, hind):
    spec = design(front_hip_abd=front, hind_hip_abd=hind).spec
    full = design().spec
    for legs, on in ((FRONT, front), (HIND, hind)):
        for k in legs:
            ids = [j.id for j in spec.joints if f".{k}." in j.id]
            acts = [a.id for a in spec.actuators if f".{k}." in a.id]
            motors = [g.id for b in spec.bodies for g in b.geoms if g.id.startswith(f"act.{k}.")]
            if on:
                assert ids == [f"joint.{k}.hip_abd", f"joint.{k}.hip_flex", f"joint.{k}.knee"]
                assert f"act.{k}.hip_abd.motor" in motors
            else:
                assert ids == [f"joint.{k}.hip_flex", f"joint.{k}.knee"], "hip pitch, then knee"
                assert acts == [f"act.{k}.hip_flex", f"act.{k}.knee"]
                assert sorted(motors) == [f"act.{k}.hip_flex.motor", f"act.{k}.knee.motor"]
            # the bodies keep their IDs and places either way: solids are pushed onto the same parts
            for part in ("hip", "thigh", "shank"):
                assert spec.body(f"leg.{k}.{part}").pos == full.body(f"leg.{k}.{part}").pos
            assert spec.body(f"leg.{k}.hip").parent == "trunk" and spec.body(f"leg.{k}.thigh").parent == f"leg.{k}.hip"
    removed = 2 * (not front) + 2 * (not hind)
    assert len(spec.joints) == 18 - removed
    one = library().actuator("xm430_w350").mass_g
    assert spec.total_mass_g() == pytest.approx(full.total_mass_g() - removed * one)


def test_the_two_joint_prototype_has_eight_motors_and_no_abduction_mass():
    d = design(**TWO_JOINT)
    spec = d.spec
    assert [a.id for a in spec.actuators] == [f"act.{k}.{j}" for k in (*FRONT, *HIND) for j in ("hip_flex", "knee")]
    assert {a.component for a in spec.actuators} == {"scs0009"}
    # front knees point forward (hip angle negative, knee positive), hind knees backward
    rest = spec.rest_angles()
    assert rest["joint.fl.hip_flex"] < 0 < rest["joint.fl.knee"] and rest["joint.hl.knee"] < 0 < rest["joint.hl.hip_flex"]
    b = mass_breakdown(spec, library())
    assert b["total_g"] == pytest.approx(spec.total_mass_g(), abs=0.2)
    items = [i["id"] for r in b["bodies"] for i in r["items"]]
    assert not any("hip_abd" in i for i in items) and sum(i.endswith(".motor") for i in items) == 8
    comps = {g.component for body in spec.bodies for g in body.geoms if g.component}
    assert "mg996r" not in comps and "xm430_w350" not in comps and "lipo_2s_1100" in comps
    # every exporter-facing view accepts a hip that is fixed to the trunk
    bones = {bone["name"]: bone for bone in armature_plan(spec)["bones"]}
    assert "joint.fl.hip_abd" not in bones and bones["joint.fl.knee"]["parent"] == "joint.fl.hip_flex"
    assert bones["joint.fl.hip_flex"]["parent"] == "root"
    rb = rhino_build_list(d)
    assert {a["id"] for a in rb["annotations"]} == {j.id for j in spec.joints}
    assert "leg.fl.hip.block" in {o["id"] for o in rb["objects"]}
    assert [r.id for r in spec.harness_routes if r.id.startswith("harness.bus.")] == [f"harness.bus.{k}" for k in (*FRONT, *HIND)]


def test_the_existing_leg_settings_still_work_without_abduction():
    own = design(**TWO_JOINT, own_leg_lengths=True, front_thigh_length=90.0, front_shank_length=200.0,
                 hind_thigh_length=60.0, hind_shank_length=150.0)
    poses = own.spec.world_poses()
    from calflab.model.xform import quat_rotate

    bottoms = [poses[b.id][0][2] + quat_rotate(poses[b.id][1], g.pos)[2] - g.size[0]
               for b in own.spec.bodies for g in b.geoms if g.foot]
    assert all(abs(z) < 1e-6 for z in bottoms), "all four hooves stand"
    assert own.element_params["leg.fl.thigh"]["length"].value == pytest.approx(90.0 * 0.337)
    flipped = design(**(TWO_JOINT | {"front_knee_forward": False, "hind_knee_forward": True})).spec.rest_angles()
    assert flipped["joint.fl.knee"] < 0 < flipped["joint.hl.knee"]
    thighless = design(**TWO_JOINT, front_thigh=False).spec
    assert [j.id for j in thighless.joints if ".fl." in j.id] == ["joint.fl.knee"], "no thigh and no abduction: one pitch joint"
    assert len(thighless.actuators) == 6
    # front hip flexion off as well leaves only the knee; the leg still builds and compiles
    knee_only = design(**TWO_JOINT, front_hip_flex=False).spec
    assert [a.id for a in knee_only.actuators if ".fl." in a.id] == ["act.fl.knee"]
    assert compile_mjcf(knee_only, library()).total_mass_kg == pytest.approx(knee_only.total_mass_g() / 1000.0)


@pytest.mark.parametrize("gait", ["walk", "trot", "bound"])
def test_the_two_joint_body_simulates_without_collapsing_or_hitting_limits(gait):
    spec = design(**TWO_JOINT).spec
    cm = compile_mjcf(spec, library(), CompileOptions(include_skin=False))
    assert len(cm.actuator_ids) == 8 and len(cm.actuator_speed_limit) == 8
    r = run_rollout(cm, registry.get("controller", "cpg")({"gait": gait}), SimSettings(duration_s=4.0), library())
    m = compute_metrics(r)
    assert not m["fell"] and m["joint_limit_violation"] == 0.0
    assert np.min(r.body_pos[:, 0, 2]) > 0.9 * cm.root_height, "the trunk does not sink"
    row = m["by_actuator"]["act.fl.knee"]
    assert row["speed_limit_deg_s"] == pytest.approx(library().actuator("scs0009").no_load_speed_rpm * 6.0)
    assert row["speed_margin"] == pytest.approx(1.0 - row["speed_peak_deg_s"] / row["speed_limit_deg_s"])
    assert 0.0 <= row["torque_saturated"] <= 1.0
    assert m["speed_margin_min"] == pytest.approx(min(a["speed_margin"] for a in m["by_actuator"].values()))


def test_the_small_body_model_settings_are_off_by_default_and_do_what_they_say():
    spec = design(**TWO_JOINT).spec
    lib = library()
    assert (CompileOptions().joint_loss_scale, CompileOptions().armature_scale) == (1.0, 1.0)
    base = compile_mjcf(spec, lib)
    assert compile_mjcf(spec, lib, CompileOptions(joint_loss_scale=1.0, armature_scale=1.0)).xml == base.xml
    import xml.etree.ElementTree as ET

    def joint(cm, jid="joint.fl.knee"):
        return next(j for j in ET.fromstring(cm.xml).iter("joint") if j.get("name") == jid)

    no_skin = compile_mjcf(spec, lib, CompileOptions(include_skin=False))
    scaled = compile_mjcf(spec, lib, CompileOptions(include_skin=False, joint_loss_scale=0.1, armature_scale=0.5))
    assert float(joint(scaled).get("damping")) == pytest.approx(0.1 * float(joint(no_skin).get("damping")))
    assert float(joint(scaled).get("frictionloss")) == pytest.approx(0.1 * float(joint(no_skin).get("frictionloss")))
    assert float(joint(scaled).get("armature")) == pytest.approx(0.5 * lib.actuator("scs0009").armature_kgm2)


def test_the_power_budget_says_when_motor_and_battery_voltages_differ():
    lib = library()
    small = power_budget(design(**TWO_JOINT).spec, lib, None)
    assert small["bus_voltage_v"] == pytest.approx(7.4)
    assert small["voltage_mismatch"] == [{"component": "scs0009", "name": lib.actuator("scs0009").name, "rated_v": 6.0, "bus_v": 7.4}]
    assert "6 V" in small["voltage_note"] and "7.4 V" in small["voltage_note"] and "nothing is converted" in small["voltage_note"]
    default = power_budget(design().spec, lib, None)
    assert default["voltage_mismatch"] == [] and default["voltage_note"] is None


def test_study_ranges_are_real_millimetres_fitted_into_the_sliders():
    gdef = genome_definition("calf")
    genes = gdef.defaults() | TWO_JOINT
    cfg = ProportionStudySettings(thigh_min=20, thigh_max=100, shank_min=20, shank_max=100, trunk_length_min=100, trunk_length_max=250)
    dims = {d["key"]: d for d in study_dimensions(gdef, genes, cfg)}
    assert list(dims) == ["thigh", "shank", "trunk_length"], "a range of 0 to 0 is not varied"
    assert (dims["thigh"]["min"], dims["thigh"]["max"], dims["thigh"]["clamped"]) == (20.0, 100.0, False)
    assert dims["thigh"]["genes"] == ["front_thigh_length", "hind_thigh_length"]
    # the trunk slider ends at 560 mm full size: 188.7 mm at this scale, and the study says so
    assert dims["trunk_length"]["max"] == pytest.approx(560 * 0.337, abs=0.01) and "188.7" in dims["trunk_length"]["note"]
    real = {"thigh": 30.0, "shank": 80.0, "trunk_length": 150.0}
    v = variant_genes(gdef, genes, list(dims.values()), real)
    assert v["own_leg_lengths"] is True
    assert gdef.real_values(v)["front_thigh_length"] == pytest.approx(30.0) and gdef.real_values(v)["hind_shank_length"] == pytest.approx(80.0)
    assert gdef.real_values(v)["trunk_length"] == pytest.approx(150.0)
    # the design as it is, in the same terms; switching the own-length genes on by itself changes nothing
    now = design_real(gdef, genes, list(dims.values()))
    assert now == {"thigh": pytest.approx(170 * 0.337, abs=0.01), "shank": pytest.approx(170 * 0.337, abs=0.01), "trunk_length": pytest.approx(420 * 0.337, abs=0.01)}
    same = variant_genes(gdef, genes, list(dims.values()), now)
    a = build_design(Genome(definition="calf", version=gdef.version, values=same)).spec
    b = build_design(Genome(definition="calf", version=gdef.version, values=genes)).spec
    assert a.total_mass_g() == pytest.approx(b.total_mass_g(), rel=1e-4) and a.standing_height_mm() == pytest.approx(b.standing_height_mm(), abs=0.05)
    split = study_dimensions(gdef, genes, cfg.model_copy(update={"front_hind_differ": True}))
    assert [d["key"] for d in split][:4] == ["front_thigh", "hind_thigh", "front_shank", "hind_shank"]
    no_thigh = study_dimensions(gdef, genes | {"front_thigh": False}, cfg)
    assert no_thigh[0]["genes"] == ["hind_thigh_length"]
    u = sample_unit(8, 3, np.random.default_rng(1))
    assert u.shape == (8, 3) and all(sorted((u[:, j] * 8).astype(int)) == list(range(8)) for j in range(3)), "one body per stratum"


def test_study_summary_marks_the_bodies_no_other_beats():
    def body(i, speed, margin, works=True, x=0.0):
        return {"id": i, "baseline": False, "real": {"shank": x},
                "gaits": {"trot": {"works": works, "metrics": {"speed_mps": speed, "torque_margin_min": margin, "stability": 0.9}}}}

    bodies = [body("a", 0.30, 0.10), body("b", 0.20, 0.40), body("c", 0.15, 0.30), body("d", 0.50, 0.50, works=False),
              {"id": "e", "error": "boom", "gaits": {}}]
    s = summarize(bodies, [], ["trot"])
    assert s["gaits"]["trot"] == {"tried": 4, "working": 3, "front": ["a", "b"], "fastest": "a", "trends": []}
    assert s["works_in_all"] == ["a", "b", "c"]
    assert spearman([1, 2, 3], [1, 2, 3]) is None, "too few bodies to call it a trend"
    many = [body(f"m{i}", 0.1 + 0.01 * i, 0.5 - 0.01 * i, x=float(i)) for i in range(12)]
    t = summarize(many, [{"key": "shank", "label": "Shank length"}], ["trot"])["gaits"]["trot"]["trends"]
    assert {(r["outcome"], r["rho"]) for r in t} == {("speed_mps", 1.0), ("torque_margin_min", -1.0)}
    assert "More shank length: more speed" in t[0]["text"] or "More shank length: less torque margin" in t[0]["text"]


def test_proportion_study_runs_records_and_can_be_adopted(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        lab.backend_key = "inline"
        lab.execute("set_genes", {"values": TWO_JOINT})
        model = lab.state.graph.role("model").id
        lab.execute("set_node_params", {"node": model, "params": {"include_skin": False}})
        with pytest.raises(Exception, match="Nothing to vary"):
            lab.execute("run_study", {})
        genes_before = dict(lab.state.graph.role("genome").params)
        out = lab.execute("run_study", {"thigh_min": 30, "thigh_max": 90, "shank_min": 30, "shank_max": 90, "height_min": 100,
                                        "height_max": 250, "bodies": 2, "gaits": ["trot", "bound"], "iterations": 1, "popsize": 4,
                                        "duration_s": 2.0})["result"]
        job = lab.jobs.wait(out["job"], timeout=600)
        assert job.status == "done", job.error
        assert dict(lab.state.graph.role("genome").params) == genes_before, "a study does not edit the document"
        run = lab.registry.get_run(out["run_id"])
        assert run.kind == "study" and run.inputs["compile"]["include_skin"] is False and run.metrics["bodies"] == 3
        assert any("scs0009" in n and "armature_kgm2" in n for n in run.inputs["notes"]), "defaulted servo values are named"
        assert any("6 V" in n and "7.4 V" in n for n in run.inputs["notes"])
        view = lab.study_view(out["run_id"])
        assert [b["id"] for b in view["bodies"]] == ["b00", "b01", "b02"] and view["bodies"][0]["baseline"]
        for b in view["bodies"]:
            assert 100 <= b["height_mm"] <= 250 and set(b["gaits"]) == {"trot", "bound"}
            g = b["gaits"]["trot"]
            assert len(g["joints"]) == 8 and {"torque_peak_nm", "torque_limit_nm", "torque_margin", "torque_saturated",
                                               "speed_peak_deg_s", "speed_limit_deg_s", "speed_margin"} <= set(g["joints"][0])
            assert g["battery"]["max_current_a"] == pytest.approx(38.5) and g["battery"]["peak_current_a"] > 0
            assert isinstance(g["works"], bool) and (g["works"] or g["flags"])
        b1 = view["bodies"][1]
        assert 30 <= b1["real"]["thigh"] <= 90 and b1["genes_real"]["front_thigh_length"] == pytest.approx(b1["real"]["thigh"], abs=0.01)
        # replay one body without touching the document, then adopt it (undoable)
        sim = lab.jobs.wait(lab.execute("simulate_study_body", {"run": out["run_id"], "body": "b01", "gait": "trot"})["result"]["job"], timeout=300)
        assert sim.status == "done", sim.error
        assert dict(lab.state.graph.role("genome").params) == genes_before
        lab.execute("adopt_study_body", {"run": out["run_id"], "body": "b01", "gait": "trot"})
        form = lab.genome_form(lab.state.graph)
        assert form["values"]["front_thigh_length"] == pytest.approx(b1["real"]["thigh"], abs=0.01) and form["values"]["own_leg_lengths"] is True
        assert lab.state.graph.role("controller").params["frequency"] == pytest.approx(b1["gaits"]["trot"]["controller"]["params"]["frequency"])
        lab.undo()
        assert dict(lab.state.graph.role("genome").params) == genes_before
        with pytest.raises(Exception, match="no body"):
            lab.execute("adopt_study_body", {"run": out["run_id"], "body": "zz"})
    finally:
        lab.close()


def test_tune_gait_runs_on_the_two_joint_body(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        lab.backend_key = "inline"
        lab.execute("set_genes", {"values": TWO_JOINT})
        out = lab.execute("tune_gait", {"iterations": 2, "popsize": 4, "duration_s": 2, "gaits": ["trot"], "seed": 2})["result"]
        job = lab.jobs.wait(out["job"], timeout=600)
        assert job.status == "done", job.error
        caps = job.result["speed_caps_deg_s"]
        assert set(caps) == {f"joint.{k}.{j}" for k in (*FRONT, *HIND) for j in ("hip_flex", "knee")}
        assert not job.result["after"]["metrics"]["fell"]
    finally:
        lab.close()
