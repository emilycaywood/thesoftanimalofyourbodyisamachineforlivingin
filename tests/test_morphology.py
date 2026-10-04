"""Reference calf: spec validity, defaults from the brief, overrides."""

import pytest
from calflab.components import library
from calflab.config import default
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.model.spec import LAYERS, RobotSpec


def test_dof_matches_brief(calf_design):
    spec = calf_design.spec
    leg = [j for j in spec.joints if j.group == "leg"]
    neck = [j for j in spec.joints if j.group == "neck"]
    cosmetic = [j for j in spec.joints if j.cosmetic]
    assert len(leg) == 12 and len(neck) == 3 and len(cosmetic) == 3
    assert len(spec.actuators) == 18
    assert {a.joint for a in spec.actuators} == {j.id for j in spec.joints}


def test_stable_ids_and_layers(calf_design):
    spec = calf_design.spec
    ids = spec.element_ids()
    assert len(ids) == len(set(ids))
    for expected in ("trunk", "leg.fl.shank", "joint.hr.knee", "act.fl.knee", "leg.fl.hoof", "sensor.imu"):
        assert expected in ids
    for b in spec.bodies:
        for g in b.geoms:
            assert g.layer in LAYERS
    assert RobotSpec.model_validate_json(spec.model_dump_json()) == spec


def test_proportions_and_mass_budget(calf_design):
    spec = calf_design.spec
    poses = spec.world_poses()
    top = max(poses[b.id][0][2] for b in spec.bodies)
    assert 500 < top < 700, "standing height should be near the 610 mm target"
    assert spec.total_mass_g() <= default("targets.max_mass_g")
    assert spec.mass_by_layer()["Skin"] > 0
    com = spec.center_of_mass()
    assert abs(com[1]) < 1.0, "the calf is left-right symmetric"


def test_hooves_touch_the_ground(calf_design):
    spec = calf_design.spec
    poses = spec.world_poses()
    from calflab.model.xform import quat_rotate

    for b in spec.bodies:
        for g in b.geoms:
            if g.foot:
                p, q = poses[b.id]
                z = p[2] + quat_rotate(q, g.pos)[2] - g.size[0]
                assert z == pytest.approx(0.0, abs=0.5)


def test_components_are_unverified_with_sources():
    for c in library().all():
        assert c.source, f"{c.key} has no source"
        assert c.verified is False, f"{c.key}: only the researcher may mark specs verified"


def test_override_changes_one_segment_only():
    g = genome_definition("calf").default_genome()
    base = build_design(g)
    ov = Override(id="ov1", name="long shank", target="leg.fl.shank", param="length", value=200.0)
    d = build_design(g, [ov])
    pv = d.element_params["leg.fl.shank"]["length"]
    assert pv.value == 200.0 and pv.parametric == 170.0 and pv.override == "ov1" and pv.gene == "shank_length"
    assert d.element_params["leg.fr.shank"]["length"].override is None
    assert d.genome.values["shank_length"] == base.genome.values["shank_length"], "overrides never touch genes"
    hoof = next(x for x in d.spec.body("leg.fl.shank").geoms if x.foot)
    assert hoof.pos[2] == -200.0
    assert next(x for x in d.spec.body("leg.fr.shank").geoms if x.foot).pos[2] == -170.0


def test_disabled_and_dangling_overrides():
    g = genome_definition("calf").default_genome()
    off = Override(id="a", name="off", target="leg.fl.shank", param="length", value=200.0, enabled=False)
    gone = Override(id="b", name="gone", target="no.such.part", param="length", value=1.0)
    d = build_design(g, [off, gone])
    assert d.element_params["leg.fl.shank"]["length"].override is None
    assert any("no.such.part" in w for w in d.warnings)


def test_optional_parts_follow_genes():
    gdef = genome_definition("calf")
    v = gdef.defaults() | {"has_tail": False, "has_ears": False, "knee_drive": "belt"}
    spec = build_design(Genome(definition="calf", version=gdef.version, values=v)).spec
    ids = spec.element_ids()
    assert "tail" not in ids and "ear.l" not in ids
    assert len(spec.transmissions) == 4 and all(t.type == "belt" for t in spec.transmissions)
    assert len([j for j in spec.joints if j.group == "leg"]) == 12


def test_knee_direction_genes_flip_only_their_pair():
    gdef = genome_definition("calf")
    def knees(**genes):
        v = gdef.defaults() | {"front_knee_forward": False} | genes
        spec = build_design(Genome(definition="calf", version=gdef.version, values=v)).spec
        return {k: spec.joint(f"joint.{k}.knee") for k in ("fl", "fr", "hl", "hr")}, spec

    base, _ = knees()
    front, spec = knees(front_knee_forward=True)
    for k in ("fl", "fr"):
        assert front[k].rest_deg == pytest.approx(-base[k].rest_deg) and front[k].rest_deg > 0
        assert front[k].range_deg == (-base[k].range_deg[1], -base[k].range_deg[0])
        hip = spec.joint(f"joint.{k}.hip_flex")
        assert hip.rest_deg < 0, "the thigh swings forward so the hoof stays under the hip"
    for k in ("hl", "hr"):
        assert front[k].rest_deg == base[k].rest_deg and front[k].range_deg == base[k].range_deg
    hind, _ = knees(hind_knee_forward=True)
    assert hind["fl"].rest_deg == base["fl"].rest_deg and hind["hl"].rest_deg == -base["hl"].rest_deg
    # hooves still reach the ground with the front knees flipped
    from calflab.model.xform import quat_rotate

    poses = spec.world_poses()
    for b in spec.bodies:
        for g in b.geoms:
            if g.foot:
                p, q = poses[b.id]
                assert p[2] + quat_rotate(q, g.pos)[2] - g.size[0] == pytest.approx(0.0, abs=0.5)
