"""Front and hind legs of their own proportions, and front legs without a
thigh (ADR-056). The lengths used here are test values, not the researcher's
measurements."""

import numpy as np
import pytest
from calflab.app import Lab
from calflab.bridge import armature_plan, rhino_build_list
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.model.xform import quat_rotate
from calflab.plugins import registry
from calflab.sim import SimSettings, compile_mjcf, compute_metrics, run_rollout

NEW = ("front_thigh", "own_leg_lengths", "front_thigh_length", "front_shank_length", "hind_thigh_length", "hind_shank_length")
FRONT, HIND = ("fl", "fr"), ("hl", "hr")


def design(overrides=None, **genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes), overrides)


def hoof_bottoms(spec):
    poses = spec.world_poses()
    return {g.id: poses[b.id][0][2] + quat_rotate(poses[b.id][1], g.pos)[2] - g.size[0]
            for b in spec.bodies for g in b.geoms if g.foot}


def test_the_new_leg_genes_change_nothing_until_they_are_switched_on():
    gdef = genome_definition("calf")
    assert (gdef.gene("front_thigh").default, gdef.gene("front_thigh").absent) == (True, True)
    assert (gdef.gene("own_leg_lengths").default, gdef.gene("own_leg_lengths").absent) == (False, False)
    assert not any(gdef.gene(g).evolvable for g in NEW), "the search space of evolution is unchanged"
    old = {k: v for k, v in gdef.defaults().items() if k not in NEW}
    done = gdef.complete(old)
    assert done["front_thigh"] is True and done["own_leg_lengths"] is False
    base = design().spec
    # the four lengths are not read while the switch is off, whatever they hold
    ignored = design(front_thigh_length=20.0, front_shank_length=400.0, hind_thigh_length=10.0, hind_shank_length=60.0).spec
    assert ignored.model_dump() == base.model_dump()
    # ... and a per-leg override without the switch behaves as it always did: the shorter legs hang short
    short = design([Override(id="o", name="o", target=f"leg.{k}.thigh", param="length", value=100.0) for k in FRONT]).spec
    bottoms = hoof_bottoms(short)
    assert bottoms["leg.hl.hoof"] == pytest.approx(0.0, abs=1e-6) and bottoms["leg.fl.hoof"] > 40


def test_front_and_hind_lengths_of_their_own_keep_every_hoof_on_the_ground():
    d = design(own_leg_lengths=True, front_thigh_length=120.0, front_shank_length=230.0, hind_thigh_length=25.0, hind_shank_length=260.0)
    spec = d.spec
    for k, thigh, shank, gene in (("fl", 120.0, 230.0, "front"), ("hr", 25.0, 260.0, "hind")):
        t, s = d.element_params[f"leg.{k}.thigh"]["length"], d.element_params[f"leg.{k}.shank"]["length"]
        assert (t.value, t.gene, t.min) == (thigh, f"{gene}_thigh_length", 5.0), "Properties and the gumball edit the right gene"
        assert (s.value, s.gene) == (shank, f"{gene}_shank_length")
        assert next(g for g in spec.body(f"leg.{k}.thigh").geoms if g.id.endswith(".tube")).size[1] == thigh
    assert all(abs(z) < 1e-6 for z in hoof_bottoms(spec).values()), "all four hooves stand"
    poses = spec.world_poses()
    drop = poses["trunk"][0][2] - poses["leg.fl.hip"][0][2], poses["trunk"][0][2] - poses["leg.hl.hip"][0][2]
    assert min(drop) == pytest.approx(40.0), "hip drop is that of the longest legs"
    assert max(drop) > 40.0, "the shorter legs' hips sit lower in the trunk"
    # a thigh a few millimetres long is a valid body: it compiles, and its knee motor sits at the hip, not above it
    tiny = design(own_leg_lengths=True, hind_thigh_length=5.0).spec
    assert next(g for g in tiny.body("leg.hl.thigh").geoms if g.id == "act.hl.knee.motor").pos[2] == 0.0
    assert compile_mjcf(tiny, library()).total_mass_kg == pytest.approx(tiny.total_mass_g() / 1000.0)


@pytest.mark.parametrize("own", [False, True])
def test_a_front_leg_without_a_thigh_is_hip_then_one_pitch_joint_then_shank(own):
    genes = {"front_thigh": False, "front_hip_flex": True, "front_knee_forward": True, "knee_drive": "belt"}  # the last three: no say
    if own:
        genes |= {"own_leg_lengths": True, "front_shank_length": 310.0, "hind_thigh_length": 24.0, "hind_shank_length": 280.0}
    d = design(**genes)
    spec, full = d.spec, design(knee_drive="belt").spec
    assert {b.id for b in full.bodies} - {b.id for b in spec.bodies} == {"leg.fl.thigh", "leg.fr.thigh"}
    assert {j.id for j in full.joints} - {j.id for j in spec.joints} == {"joint.fl.hip_flex", "joint.fr.hip_flex"}
    assert {a.id for a in full.actuators} - {a.id for a in spec.actuators} == {"act.fl.hip_flex", "act.fr.hip_flex"}
    assert "leg.fl.thigh" not in d.element_params and "leg.hl.thigh" in d.element_params
    lib = library()
    for k in FRONT:
        shank = spec.body(f"leg.{k}.shank")
        assert shank.parent == f"leg.{k}.hip"
        pitch = next(j for j in spec.joints if j.id == f"joint.{k}.knee")
        assert pitch.body == shank.id and pitch.name.startswith("Shoulder pitch") and pitch.axis == (0.0, 1.0, 0.0)
        assert pitch.rest_deg == 0.0 and pitch.range_deg == (-75.0, 75.0), "it hangs straight and swings both ways"
        act = next(a for a in spec.actuators if a.id == f"act.{k}.knee")
        assert act.joint == pitch.id and act.component == d.genome.values["act_knee"] and act.transmission is None
        motor = next(g for g in spec.body(f"leg.{k}.hip").geoms if g.id == f"act.{k}.knee.motor")
        assert motor.mass_g == lib.actuator(act.component).mass_g and motor.mass_source == "component"
        assert not any(g.id.startswith(f"trans.{k}") for b in spec.bodies for g in b.geoms), "no belt without a thigh"
        assert next(r for r in spec.skin_regions if r.id == f"skin.leg.{k}").bodies == [shank.id]
        bus = next(r for r in spec.harness_routes if r.id == f"harness.bus.{k}")
        assert bus.dst == motor.id and bus.via_bodies == []
    assert next(a for a in spec.actuators if a.id == "act.hl.knee").transmission == "trans.hl.knee", "hind legs keep their belt"
    # the hoof is straight below the shoulder pitch axis, on the ground like the hind hooves
    poses = spec.world_poses()
    assert all(abs(z) < 1e-6 for z in hoof_bottoms(spec).values())
    hoof = next(g for g in spec.body("leg.fl.shank").geoms if g.foot)
    tip = np.array(poses["leg.fl.shank"][0]) + quat_rotate(poses["leg.fl.shank"][1], hoof.pos)
    assert tip[:2] == pytest.approx(poses["leg.fl.shank"][0][:2])
    length = d.element_params["leg.fl.shank"]["length"]
    assert length.gene == ("front_shank_length" if own else "shank_length")
    assert poses["leg.fl.shank"][0][2] == pytest.approx(length.value + hoof.size[0]), "pitch axis to ground = shank + hoof radius"
    # mass: the two thigh shells are gone, the two hip-flexion motors are gone, nothing else
    if not own:
        gone = sum(g.mass_g for k in FRONT for g in full.body(f"leg.{k}.thigh").geoms if g.id.endswith((".tube", ".skin", ".belt")))
        gone += 2 * lib.actuator(str(d.genome.values["act_hip_flex"])).mass_g
        assert full.total_mass_g() - spec.total_mass_g() == pytest.approx(gone)


def test_a_thighless_short_thighed_small_calf_simulates_and_reaches_the_bridges():
    genes = {"scale": 0.337, "own_leg_lengths": True, "front_thigh": False, "front_shank_length": 310.0,
             "hind_thigh_length": 24.0, "hind_shank_length": 280.0, "has_tail": False, "has_ears": False,
             "has_neck_yaw": False, "has_neck_pitch": False, "has_head_pitch": False}
    d = design(**genes)
    lib = library()
    cm = compile_mjcf(d.spec, lib)
    assert len(cm.actuator_joint) == 10 and "leg.fl.thigh" not in cm.xml
    cpg = registry.get("controller", "cpg")
    ids = [a.joint for a in d.spec.actuators]
    assert {"elbow_amplitude", "swing_abduction", "hip_amplitude"} <= set(cpg.relevant_dims(ids)), "front legs step as two-motor legs"
    ro = run_rollout(cm, cpg({}), SimSettings(duration_s=4.0), lib)
    m = compute_metrics(ro)
    assert not m["fell"] and m["joint_limit_violation"] == 0 and len(m["by_actuator"]) == 10
    trunk = ro.body_pos[:, ro.body_ids.index("trunk"), 2] * 1000.0
    stand = d.spec.world_poses()["trunk"][0][2]
    assert np.isfinite(ro.body_pos).all() and trunk.min() > 0.85 * stand, "the legs neither collapse nor sink into the ground"
    lying = run_rollout(cm, cpg({}), SimSettings(duration_s=1.0, start_pose="lying"), lib)
    assert lying.n_frames > 0
    plan = armature_plan(d.spec)
    bones = {b["name"]: b["parent"] for b in plan["bones"]}
    assert bones["joint.fl.knee"] == "joint.fl.hip_abd" and bones["joint.hl.knee"] == "joint.hl.hip_flex"
    rb = rhino_build_list(d)
    ids = {o["id"] for o in rb["objects"]}
    assert "leg.fl.shank.tube" in ids and "leg.hl.thigh.tube" in ids and not any(i.startswith("leg.fl.thigh") for i in ids)
    assert {a["id"] for a in rb["annotations"]} == {j.id for j in d.spec.joints}


def test_the_form_shows_the_new_lengths_in_real_millimetres_and_old_overrides_only_warn(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        lab.execute("add_override", {"target": "leg.fl.thigh", "param": "length", "value": 150.0})
        lab.execute("set_genes", {"values": {"scale": 0.337, "own_leg_lengths": True, "front_thigh": False}})
        res = lab.execute("set_genes", {"values": {"hind_thigh_length": 8.0, "hind_shank_length": 95.0, "front_shank_length": 105.0},
                                        "real": True})["result"]
        assert res["real"]["hind_thigh_length"] == pytest.approx(8.0) and res["genes"]["hind_thigh_length"] == pytest.approx(8.0 / 0.337)
        fields = {f["name"]: f for f in lab.graph_view()["genome_form"]["schema"]["fields"]}
        assert [fields[g]["label"] for g in NEW] == [
            "Front legs have a thigh", "Front and hind legs have their own lengths", "Front thigh length", "Front shank length",
            "Hind thigh length", "Hind shank length"]
        assert all(fields[g]["group"] == "Legs" for g in NEW)
        assert (fields["hind_thigh_length"]["min"], fields["hind_thigh_length"]["max"]) == (pytest.approx(1.685), pytest.approx(101.1))
        assert (fields["front_shank_length"]["min"], fields["front_shank_length"]["max"]) == (pytest.approx(10.11), pytest.approx(151.65))
        scene = lab.scene()
        assert "leg.fl.thigh" not in scene["elements"] and "leg.fl.shank" in scene["elements"]
        assert any("leg.fl.thigh.length" in w for w in scene["warnings"]), "an override on the removed thigh is reported, not fatal"
        rows = {r["body"] for r in scene["mass"]["breakdown"]["bodies"]}
        assert "leg.fl.thigh" not in rows and {"leg.fl.hip", "leg.fl.shank", "leg.hl.thigh"} <= rows
        lab.undo()
        lab.undo()
        assert "leg.fl.thigh" in lab.scene()["elements"]
    finally:
        lab.close()
