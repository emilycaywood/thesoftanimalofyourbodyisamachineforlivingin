"""A switch per neck and head joint (ADR-055): a prototype without neck or
head motors carries neither the joints nor the motors' mass."""

import itertools

import numpy as np
import pytest
from calflab.bridge import armature_plan, rhino_build_list
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.plugins import registry
from calflab.sim import SimSettings, compile_mjcf, compute_metrics, run_rollout

SWITCHES = {"has_neck_yaw": "neck_yaw", "has_neck_pitch": "neck_pitch", "has_head_pitch": "head_pitch"}


def design(**genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes))


def test_all_three_motors_stay_the_default_and_old_genomes_keep_them():
    gdef = genome_definition("calf")
    for gene in SWITCHES:
        g = gdef.gene(gene)
        assert g.default is True and g.absent is True and not g.evolvable and g.group == "Neck and head"
    old = {k: v for k, v in gdef.defaults().items() if k not in SWITCHES}
    assert all(gdef.complete(old)[gene] is True for gene in SWITCHES)


@pytest.mark.parametrize("off", [c for n in (1, 2, 3) for c in itertools.combinations(SWITCHES, n)])
def test_each_switch_drops_its_own_joint_and_motor_and_nothing_else(off):
    full = design().spec
    less = design(**dict.fromkeys(off, False)).spec
    names = {SWITCHES[g] for g in off}
    assert {j.id for j in full.joints} - {j.id for j in less.joints} == {f"joint.{n}" for n in names}
    assert {a.id for a in full.actuators} - {a.id for a in less.actuators} == {f"act.{n}" for n in names}
    assert {a.joint for a in less.actuators} == {j.id for j in less.joints}
    geoms = {g.id for b in less.bodies for g in b.geoms}
    assert not any(f"act.{n}.motor" in geoms for n in names)
    assert {b.id for b in less.bodies} == {b.id for b in full.bodies}, "part IDs do not change"
    motor = library().actuator("sts3215").mass_g
    assert full.total_mass_g() - less.total_mass_g() == pytest.approx(len(off) * motor)
    # the fixed parts stay where the motors held them in the standing pose
    p_less, p_full = less.world_poses(), full.world_poses()
    for b in less.bodies:
        assert np.allclose(p_less[b.id][0], p_full[b.id][0], atol=1e-9) and np.allclose(p_less[b.id][1], p_full[b.id][1], atol=1e-9)
    assert set(next(r for r in less.skin_regions if r.id == "skin.neck").joints) == {
        f"joint.{n}" for n in SWITCHES.values() if n not in names}
    # the neck bus ends at the furthest motor that is left; with none there is no bus
    bus = [r for r in less.harness_routes if r.id == "harness.bus.neck"]
    left = [n for n in ("head_pitch", "neck_pitch", "neck_yaw") if n not in names]
    assert [r.dst for r in bus] == ([f"act.{left[0]}.motor"] if left else [])


def test_a_calf_without_neck_or_head_motors_compiles_simulates_and_reaches_the_bridges():
    d = design(**dict.fromkeys(SWITCHES, False))
    lib = library()
    cm = compile_mjcf(d.spec, lib)
    assert len(cm.actuator_joint) == len(d.spec.actuators) == 15 and "joint.neck_yaw" not in cm.joint_ids
    assert cm.total_mass_kg == pytest.approx(d.spec.total_mass_g() / 1000.0)
    m = compute_metrics(run_rollout(cm, registry.get("controller", "cpg")({}), SimSettings(duration_s=3.0), lib))
    assert len(m["by_actuator"]) == 15 and not m["fell"]
    plan = armature_plan(d.spec)
    bones = {b["name"] for b in plan["bones"]}
    assert not bones & {"joint.neck_yaw", "joint.neck_pitch", "joint.head_pitch"}
    assert {m["id"] for m in plan["meshes"]} >= {"neck.tube", "head.shell"}, "the fixed neck and head are still drawn"
    rb = rhino_build_list(d)
    ids = {o["id"] for o in rb["objects"]}
    assert {"neck.tube", "head.shell"} <= ids and not any(i.startswith(("act.neck", "act.head")) for i in ids)
    assert {a["id"] for a in rb["annotations"]} == {j.id for j in d.spec.joints}
    # the tail and ear switches still work beside them: legs only
    legs = design(**dict.fromkeys(SWITCHES, False), has_tail=False, has_ears=False).spec
    assert len(legs.actuators) == 12 and all(a.id.split(".")[1] in ("fl", "fr", "hl", "hr") for a in legs.actuators)
