"""Servo mounts can be rotated so the limb below comes off at an angle (ADR-060).
Angles used here are test values, not the researcher's."""

import math

import pytest
from calflab.bridge import armature_plan, rhino_build_list
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.model.xform import quat_rotate
from calflab.plugins import registry
from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout

GENES = ("front_leg_splay", "hind_leg_splay", "front_leg_toe", "hind_leg_toe")
TWO_JOINT = {
    "scale": 0.337, "front_hip_abd": False, "hind_hip_abd": False, "has_neck_yaw": False, "has_neck_pitch": False,
    "has_head_pitch": False, "has_tail": False, "has_ears": False, "act_hip_flex": "scs0009", "act_knee": "scs0009",
    "battery": "lipo_2s_1100",
}


def design(overrides=None, **genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes), overrides)


def hooves(spec):
    """Hoof id -> (centre in world mm, radius)."""
    poses = spec.world_poses()
    out = {}
    for b in spec.bodies:
        for g in b.geoms:
            if g.foot:
                r = quat_rotate(poses[b.id][1], g.pos)
                out[g.id] = (tuple(poses[b.id][0][i] + r[i] for i in range(3)), g.size[0])
    return out


def test_the_mount_genes_are_zero_and_change_nothing():
    gdef = genome_definition("calf")
    for g in GENES:
        assert (gdef.gene(g).default, gdef.gene(g).absent, gdef.gene(g).evolvable, gdef.gene(g).unit) == (0, 0, False, "deg")
    old = {k: v for k, v in gdef.defaults().items() if k not in GENES}
    a = build_design(Genome(definition="calf", version=gdef.version, values=old))
    b = design()
    assert a.spec.model_dump() == b.spec.model_dump()
    hip = b.element_params["leg.fl.hip"]
    assert (hip["mount_roll"].gene, hip["mount_yaw"].gene) == ("front_leg_splay", "front_leg_toe")
    assert b.element_params["leg.hr.hip"]["mount_roll"].gene == "hind_leg_splay"
    assert b.element_params["leg.fl.thigh"]["mount_roll"].value == 0.0 and b.element_params["leg.fl.shank"]["mount_yaw"].unit == "deg"


def test_splay_leans_the_legs_out_and_keeps_every_hoof_on_the_ground():
    base, splayed = design().spec, design(front_leg_splay=20.0, hind_leg_splay=10.0).spec
    h0, h1 = hooves(base), hooves(splayed)
    for hid, (pos, radius) in h1.items():
        assert pos[2] - radius == pytest.approx(0.0, abs=1e-6), f"{hid} stands"
    # mirrored: both sides move outward, the front pair (20 deg) further than the hind (10 deg)
    out = {k: abs(h1[f"leg.{k}.hoof"][0][1]) - abs(h0[f"leg.{k}.hoof"][0][1]) for k in ("fl", "fr", "hl", "hr")}
    assert out["fl"] == pytest.approx(out["fr"]) and out["hl"] == pytest.approx(out["hr"])
    assert out["fl"] > out["hl"] > 10.0
    assert h1["leg.fl.hoof"][0][1] > 0 > h1["leg.fr.hoof"][0][1]
    assert splayed.body("trunk").pos[2] < base.body("trunk").pos[2], "leaning legs reach less far down"
    # the hip-pitch axis leans with the mount; the servo box drawn in the hip turns with the body
    poses = splayed.world_poses()
    axis = quat_rotate(poses["leg.fl.thigh"][1], splayed.joint("joint.fl.hip_flex").axis)
    assert math.degrees(math.atan2(axis[2], axis[1])) == pytest.approx(20.0, abs=1e-6)
    assert splayed.body("leg.fl.hip").quat != base.body("leg.fl.hip").quat
    assert splayed.total_mass_g() == pytest.approx(base.total_mass_g())


def test_toe_out_turns_the_swing_plane_and_is_mirrored():
    spec = design(front_leg_toe=15.0).spec
    poses = spec.world_poses()
    for k, sign in (("fl", 1.0), ("fr", -1.0)):
        # a leg that would swing along +X now swings along a direction turned outward
        fwd = quat_rotate(poses[f"leg.{k}.hip"][1], (1.0, 0.0, 0.0))
        assert math.degrees(math.atan2(fwd[1], fwd[0])) == pytest.approx(sign * 15.0, abs=1e-6)
    assert spec.body("leg.hl.hip").quat == design().spec.body("leg.hl.hip").quat, "the hind pair has its own gene"
    assert all(abs(p[2] - r) < 1e-6 for p, r in hooves(spec).values())


def test_one_servo_can_be_rotated_by_an_override_on_its_part():
    ov = [Override(id="o1", name="knee mount", target="leg.hl.shank", param="mount_roll", value=12.0)]
    d = design(ov)
    spec, base = d.spec, design().spec
    assert spec.body("leg.hl.shank").quat != base.body("leg.hl.shank").quat
    assert spec.body("leg.hr.shank").quat == base.body("leg.hr.shank").quat, "only the overridden part turns"
    h = hooves(spec)
    assert all(abs(p[2] - r) < 1e-6 for p, r in h.values()), "the other legs' hips come down with it"
    assert h["leg.hl.hoof"][0][1] > hooves(base)["leg.hl.hoof"][0][1] + 5.0
    thigh = design([Override(id="o2", name="t", target="leg.fl.thigh", param="mount_yaw", value=-8.0)]).spec
    assert thigh.body("leg.fl.thigh").quat != base.body("leg.fl.thigh").quat


def test_rotated_mounts_work_on_the_other_leg_layouts_and_in_the_simulator():
    lib = library()
    # a fixed thigh strut keeps its standing angle under the mount; a thighless leg turns at the shank's parent
    strut = design(front_hip_flex=False, front_knee_forward=False, front_leg_splay=15.0).spec
    assert all(abs(p[2] - r) < 1e-6 for p, r in hooves(strut).values())
    thighless = design(front_thigh=False, front_leg_splay=15.0, front_leg_toe=10.0).spec
    assert all(abs(p[2] - r) < 1e-6 for p, r in hooves(thighless).values())
    d = design(**TWO_JOINT, front_leg_splay=15.0, hind_leg_splay=15.0)
    cm = compile_mjcf(d.spec, lib, CompileOptions(include_skin=False))
    m = compute_metrics(run_rollout(cm, registry.get("controller", "cpg")({"gait": "trot"}), SimSettings(duration_s=4.0), lib))
    assert not m["fell"] and m["joint_limit_violation"] == 0.0
    bones = {b["name"] for b in armature_plan(d.spec)["bones"]}
    assert bones >= {"joint.fl.hip_flex", "joint.fl.knee"}
    assert {a["id"] for a in rhino_build_list(d)["annotations"]} == {j.id for j in d.spec.joints}
