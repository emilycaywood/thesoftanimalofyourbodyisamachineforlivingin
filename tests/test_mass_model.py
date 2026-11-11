"""The feral calf's explicit mass model (R14, ADR-108): library parts, CF tubes from length, headroom."""

from __future__ import annotations

import math

import pytest
from calflab.components import library
from calflab.components.library import parse_component
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.mass import mass_breakdown
from calflab.morphology.feral import HEADROOM_LABEL

LEG_GENES = {"femur": "femur_length", "tibia": "tibia_length", "cannon_rear": "rear_cannon_length",
             "upper": "upper_leg_length", "cannon_front": "front_cannon_length"}


def design(genes: dict | None = None):
    d = genome_definition("feral_calf")
    g = Genome(definition="feral_calf", version=d.version, values=d.complete({**d.defaults(), **(genes or {})}))
    return build_design(g, [], "feral_calf", {}, None)


@pytest.fixture(scope="module")
def old():
    return design()


@pytest.fixture(scope="module")
def new():
    return design({"mass_model": "explicit_v1"})


def _items(spec):
    return {g.id: g for b in spec.bodies for g in b.geoms}


def test_stored_genomes_keep_the_old_mass_model(old):
    gdef = genome_definition("feral_calf")
    assert gdef.gene("mass_model").absent == "as_entered"
    assert gdef.complete({})["mass_model"] == "as_entered"
    assert old.spec.metadata["feral"]["mass_model"] == {"model": "as_entered"}
    assert old.spec.total_mass_g() == pytest.approx(1304.19, abs=0.01)  # ADR-068's total, unchanged
    assert not any(g.mass_source == "headroom" for g in _items(old.spec).values())


@pytest.mark.parametrize("which", ["old", "new"])
def test_the_breakdown_adds_up(which, request):
    spec = request.getfixturevalue(which).spec
    mb = mass_breakdown(spec, library())
    total = spec.total_mass_g()
    assert mb["total_g"] == pytest.approx(total, abs=0.01)
    assert sum(mb["by_source_g"].values()) == pytest.approx(total, abs=0.05)
    assert sum(r["total_g"] for r in mb["bodies"]) == pytest.approx(total, abs=0.05)
    assert sum(i["mass_g"] for r in mb["bodies"] for i in r["items"]) == pytest.approx(total, abs=0.05)
    assert mb["parts_g"] + mb["headroom_g"] == pytest.approx(total, abs=0.01)


def test_cf_tube_mass_from_each_segments_length(new):
    lib = library()
    tube = lib.material("cf_leg_tube_16x12")
    assert (tube.tube_od_mm, tube.tube_id_mm, tube.density_g_cm3, tube.verified) == (16, 12, 1.65, False)
    per_mm = math.pi / 4 * (16 ** 2 - 12 ** 2) * 1.65 / 1000  # g per mm of tube
    assert tube.tube_mass_g(100.0) == pytest.approx(100 * per_mm)
    items = _items(new.spec)
    for k in ("hl", "hr", "fl", "fr"):
        segs = ("femur", "tibia", "cannon") if k[0] == "h" else ("upper", "cannon")
        for seg in segs:
            g = items[f"leg.{k}.{seg}.tube"]
            length = g.size[1]
            assert g.mass_g == pytest.approx(per_mm * length)
            assert g.mass_source == "component" and g.material == "cf_leg_tube_16x12"
            assert g.pos[2] == pytest.approx(-length / 2)  # placed along the segment
    # a longer femur weighs more by exactly the extra length
    longer = _items(design({"mass_model": "explicit_v1", "femur_length": 220}).spec)
    assert longer["leg.hl.femur.tube"].mass_g - items["leg.hl.femur.tube"].mass_g == pytest.approx(20 * per_mm)


def test_cf_tubes_replace_the_tube_estimate(old, new):
    o, n = _items(old.spec), _items(new.spec)
    leg = [i for i in o if i.startswith("leg.") and i.endswith(".tube")]
    assert len(leg) == 10 and {i for i in n if i.startswith("leg.") and i.endswith(".tube")} == set(leg)
    assert all(o[i].mass_source == "tube" and n[i].mass_source == "component" for i in leg)
    added = sum(n[i].mass_g - o[i].mass_g for i in leg)
    assert added == pytest.approx(sum(n[i].mass_g for i in leg) - sum(o[i].mass_g for i in leg))
    assert o["trunk.rail1"].mass_g == n["trunk.rail1"].mass_g  # rails are not leg tubes


def test_horns_axles_servos_and_batteries(new):
    lib = library()
    items = _items(new.spec)
    horns = [g for g in items.values() if g.component == "servo_horn"]
    assert len(horns) == 10 and all(g.mass_g == 14 for g in horns)
    assert {g.id.rsplit(".", 1)[0] for g in horns} == {a.id for a in new.spec.actuators}
    axles = [g for g in items.values() if g.component == "pulley_axle"]
    belted = new.spec.metadata["feral"]["belted"]
    assert sorted(belted) == ["carpus", "hock", "stifle"]
    assert len(axles) == 2 * len(belted) and all(g.mass_g == 24 for g in axles)
    for g in axles:  # at the joint axis: the origin of the driven body
        assert g.pos == (0.0, 0.0, 0.0)
    for a in new.spec.actuators:
        motor = items[f"{a.id}.motor"]
        assert motor.mass_g == lib.actuator(a.component).mass_g and motor.mass_source == "component"
    packs = [g for g in items.values() if g.id.startswith("elec.battery")]
    assert sum(g.mass_g for g in packs) == pytest.approx(270.0)
    missing = {m["item"] for m in new.spec.metadata["missing_masses"]}
    assert "servo_horn_g" not in missing and "bearing_g" in missing  # what is still not entered stays listed
    assert lib.part("pulley_axle").verified is False and lib.part("servo_horn").verified is False


def test_a_belted_shoulder_gets_its_axle():
    d = design({"mass_model": "explicit_v1", "shoulder_belt": True})
    axles = [g for b in d.spec.bodies for g in b.geoms if g.component == "pulley_axle"]
    assert len(axles) == 8
    assert {g.id for g in axles} >= {"belt.fl.shoulder.axle", "belt.fr.shoulder.axle"}


def test_the_headroom_is_labelled_provisional_and_is_not_a_part(new):
    spec = new.spec
    head = [g for b in spec.bodies for g in b.geoms if g.mass_source == "headroom"]
    assert len(head) == 1
    g = head[0]
    assert g.id == "trunk.headroom" and g.mass_g == 300 and g.label == HEADROOM_LABEL == "headroom (PROVISIONAL)"
    assert g.component is None and g.material is None and g.layer == "Annotations" and g.role == "visual"
    # at the trunk's centre of mass before it was added
    trunk = spec.body("trunk")
    rest = [x for x in trunk.geoms if x.id != g.id and x.mass_g > 0]
    m = sum(x.mass_g for x in rest)
    for i in range(3):
        assert g.pos[i] == pytest.approx(sum(x.mass_g * x.mass_center()[i] for x in rest) / m)
    mb = mass_breakdown(spec, library())
    assert mb["headroom_g"] == 300 and mb["parts_g"] == pytest.approx(spec.total_mass_g() - 300)
    assert "PROVISIONAL" in mb["source_labels"]["headroom"]
    (item,) = mb["headroom_items"]
    assert item["provisional"] is True and item["verified"] is None
    assert not any(i["provisional"] for r in mb["bodies"] for i in r["items"] if i["id"] != "trunk.headroom")
    assert spec.metadata["feral"]["mass_model"]["headroom_g"] == 300


def test_new_total(old, new):
    lib = library()
    # +24 g x 6 axles, +14 g x 10 horns, +300 g headroom, and the leg tubes' difference
    o, n = _items(old.spec), _items(new.spec)
    tubes = sum(n[i].mass_g - o[i].mass_g for i in o if i.startswith("leg.") and i.endswith(".tube"))
    expect = old.spec.total_mass_g() + 6 * lib.part("pulley_axle").mass_g + 10 * lib.part("servo_horn").mass_g + 300 + tubes
    assert new.spec.total_mass_g() == pytest.approx(expect)
    assert new.spec.total_mass_g() == pytest.approx(2005.46, abs=0.01)


def test_a_part_needs_its_mass():
    from calflab.components.library import IncompleteComponent

    with pytest.raises(IncompleteComponent):
        parse_component({"key": "x", "kind": "part", "name": "x", "mass_g": None, "source": "test"})
    p = parse_component({"key": "x", "kind": "part", "name": "x", "mass_g": 3, "source": "test"})
    assert p.kind == "part" and p.mass_g == 3
    # a material that is not a tube does not list the tube fields as unknown
    assert "tube_od_mm" not in library().material("petg").unknown


def test_the_hardware_presets_build_with_the_explicit_model():
    import yaml
    from calflab.evolve.hardware import HardwareSettings
    from calflab.fitness.preset import FitnessPreset
    from calflab.paths import config_dir

    for name, version in (("hardware_r11c", 3), ("hardware_r13", 3), ("hardware_r14", 2)):
        p = FitnessPreset.model_validate(yaml.safe_load((config_dir() / "fitness" / f"{name}.yaml").read_text()))
        assert p.version == version
        assert HardwareSettings.model_validate(p.evaluation.hardware).mass_model == "explicit_v2"  # ADR-109
    assert HardwareSettings().mass_model is None  # a stored v1 run's settings: each genome's own model


def test_explicit_v2_carries_the_flywoo_pack_in_place_of_the_two_packs(new):
    """ADR-109: one library pack on the centre line at the packs' place; everything else as explicit_v1."""
    lib = library()
    pack = lib.battery("flywoo_p45b_3s1p_4500")
    assert (pack.mass_g, pack.voltage_v, pack.capacity_mah, pack.verified) == (224.3, 11.1, 4500, False)
    v2 = design({"mass_model": "explicit_v2"}).spec
    items = _items(v2)
    packs = [g for g in items.values() if g.id.startswith("elec.battery")]
    assert len(packs) == 1
    (g,) = packs
    assert g.component == pack.key and g.mass_source == "component" and g.mass_g == pytest.approx(224.3)
    old_packs = [x for x in _items(new.spec).values() if x.id.startswith("elec.battery")]
    assert g.pos[1] == 0.0 and g.pos[0] == old_packs[0].pos[0] and g.pos[2] == old_packs[0].pos[2]
    assert v2.total_mass_g() == pytest.approx(new.spec.total_mass_g() - 270 + 224.3, abs=0.2)  # headroom moves a little
    mb = mass_breakdown(v2, library())
    assert mb["total_g"] == pytest.approx(v2.total_mass_g(), abs=0.01) and mb["headroom_g"] == 300
    assert v2.metadata["feral"]["mass_model"]["battery"] == pack.key
    from calflab.wiring.budget import bill_of_materials

    assert any(line["key"] == pack.key and line["qty"] == 1 for line in bill_of_materials(v2, lib)["lines"])
