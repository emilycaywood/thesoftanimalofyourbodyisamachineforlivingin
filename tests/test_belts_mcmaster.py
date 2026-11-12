"""R18 (ADR-115/116): the McMaster-Carr belt parts, the only ones offered to the body's belt drives."""

from __future__ import annotations

import pytest
from calflab.mech.belts import (
    BeltCatalog,
    BeltChoice,
    DriveLayout,
    DriveTarget,
    center_distance,
    drive_options,
    evaluate_drive,
    fitting_choices,
)
from calflab.paths import config_dir

MM2, MM3 = "MM-2MGT-6", "MM-3MGT-9"


@pytest.fixture(scope="module")
def catalog() -> BeltCatalog:
    return BeltCatalog.load(config_dir() / "belts")


def layout(**kw: float) -> DriveLayout:
    base = dict(drive="hock", joint_label="hock", segment="tibia", segment_length_mm=239.0, near_limit_mm=28.0,
                far_limit_mm=211.0, servo_length_mm=45.2, servo_width_mm=24.7, output_axis_offset_mm=None,
                target=DriveTarget(kind="C", value=150.0))
    base.update(kw)
    return DriveLayout.model_validate(base)


def test_two_mcmaster_systems_with_the_assumed_breaking_strength_and_no_allowable(catalog: BeltCatalog) -> None:
    s = {x.id: x for x in catalog.systems}
    a, b = s[MM2], s[MM3]
    assert (a.pitch_mm, a.width_mm, b.pitch_mm, b.width_mm) == (2, 6, 3, 9)
    assert (a.breaking_strength_n, b.breaking_strength_n) == (429, 643)
    for x in (a, b):
        assert x.allowable_working_tension_n is None  # not published, never derived
        assert x.guessed == ["breaking_strength_n"]
        assert "researcher's assumption 2026-11-12: 51 lbf per 1/8 in of width" in x.breaking_strength_derivation
        assert not x.verified and not x.purchase_confirmed and x.vendor == "McMaster-Carr" and "2026-11-12" in x.source
    assert [x.id for x in catalog.offered_systems()] == [MM2, MM3]


def test_only_quarter_inch_bore_pulleys_and_closed_belts_with_part_numbers(catalog: BeltCatalog) -> None:
    mm = [p for p in catalog.pulleys if p.vendor == "McMaster-Carr"]
    assert sorted(p.teeth for p in mm if p.pitch_mm == 2) == [60, 72]
    assert sorted(p.teeth for p in mm if p.pitch_mm == 3) == [16, 17, 18, 20, 22, 24, 25, 26, 28, 30, 32, 34, 36, 40,
                                                                44, 45]
    for p in mm:
        assert p.bores_mm == [6.35] and p.mass_g is None and not p.verified and not p.purchase_confirmed
        assert p.part_number and p.part_number in p.source and p.price_usd
        assert p.belt_widths_mm == ([6] if p.pitch_mm == 2 else [9])
        listed = p.listed.get("pitch_diameter_mm")
        assert listed == pytest.approx(p.teeth * p.pitch_mm / 3.141592653589793, abs=0.06)  # listed agrees with ours
    by = {(e.pitch_mm, e.teeth): e for e in catalog.lengths if e.source.startswith("MM-")}
    assert len([k for k in by if k[0] == 2]) == 46 and len([k for k in by if k[0] == 3]) == 42
    assert by[(2, 200)].pitch_length_mm == 400 and by[(2, 200)].part_number == "7947K748"
    assert by[(2, 320)].pitch_length_mm == 640 and by[(2, 320)].part_number == "7947K759"
    assert by[(3, 200)].pitch_length_mm == 600 and by[(3, 200)].part_number == "7947K815"
    assert all(not e.purchase_confirmed and not e.verified and e.mass_g is None for e in by.values())


def test_every_earlier_entry_is_kept_but_marked_not_sourceable(catalog: BeltCatalog) -> None:
    old = [s for s in catalog.systems if s.vendor is None]
    assert old and all(s.not_sourceable for s in old)
    assert all(p.not_sourceable for p in catalog.pairs)
    assert all(p.not_sourceable for p in catalog.pulleys if p.vendor is None)
    assert all(e.not_sourceable for e in catalog.lengths if not e.source.startswith("MM-"))
    assert "sold out" in catalog.pulley("GT2-80T-10").not_sourceable
    assert "unconfirmed" in catalog.length("GT2-2mm-640-C").not_sourceable
    old_choice = BeltChoice(system="GT2-2mm-10mm-generic", pulleys="GT2-40T-10+GT2-60T-10", length="GT2-2mm-444-C")
    problems = catalog.sourcing_problems(old_choice)
    assert any("belt system" in p for p in problems) and any("GT2-40T-10" in p and "sold out" in p for p in problems)
    new = BeltChoice(system=MM3, pulleys="MM-3MGT-30T+MM-3MGT-45T", length="MM-3MGT-600")
    assert catalog.sourcing_problems(new) == []


def test_one_vendor_per_drive_is_checked_only_for_a_vendor_system(catalog: BeltCatalog) -> None:
    lay = layout()
    mixed = BeltChoice(system=MM2, pulleys="GT2-60T-10+GT2-60T-10", length="MM-2MGT-400")
    rep = evaluate_drive(catalog, lay, mixed)
    assert not rep.ok and any(c.id == "vendor" and c.status == "fail" for c in rep.checks)
    old = BeltChoice(system="GT2-2mm-10mm-generic", pulleys="GT2-40T-10+GT2-60T-10", length="GT2-2mm-400-C")
    assert "vendor" not in {c.id for c in evaluate_drive(catalog, lay, old).checks}  # earlier bodies unchanged
    ok = evaluate_drive(catalog, lay, BeltChoice(system=MM3, pulleys="MM-3MGT-30T+MM-3MGT-45T", length="MM-3MGT-375"))
    assert {c.id: c.status for c in ok.checks}["vendor"] == "pass"


def test_fitting_choices_are_mcmaster_only_pass_every_check_and_derive_c(catalog: BeltCatalog) -> None:
    lay = layout()
    ok, fails = fitting_choices(catalog, lay)
    assert ok and fails
    assert {r.choice.system for r in ok} <= {MM2, MM3}
    for r in ok[:: max(1, len(ok) // 50)]:
        assert r.ok
        e = catalog.length(r.choice.length)
        assert r.c_mm == pytest.approx(center_distance(e.pitch_length_mm, r.d1_mm, r.d2_mm))
    ratios = {round(r.ratio, 4) for r in ok}
    assert 1.5 in ratios and 1.0 in ratios and 1.2 in ratios


def test_the_belts_panel_offers_only_mcmaster_parts(catalog: BeltCatalog) -> None:
    lay = layout()
    old = drive_options(catalog, lay, BeltChoice(system="GT2-2mm-10mm-generic", pulleys="GT2-40T-10+GT2-60T-10",
                                                 length="GT2-2mm-400-C"))
    usable = {s["id"] for s in old["systems"] if s["usable"]}
    assert usable == {MM2, MM3}
    assert all("not sourceable" in s["why_not"] for s in old["systems"] if s["id"] not in usable)
    new = drive_options(catalog, lay, BeltChoice(system=MM3, pulleys="MM-3MGT-30T+MM-3MGT-45T", length="MM-3MGT-375"))
    pairs = {p["id"] for p in new["pairs"] if p["usable"]}
    assert "MM-3MGT-30T+MM-3MGT-45T" in pairs and len(pairs) == 16 * 16
    lengths = {x["id"]: x for x in new["lengths"]}
    assert lengths["MM-3MGT-375"]["part_number"] == "7947K789"  # 125 teeth


def test_the_search_space_offers_only_sourceable_parts() -> None:
    from calflab.design import build_design, genome_definition
    from calflab.evolve.hardware import HardwareSettings, baseline_of
    from calflab.evolve.production import ProductionSettings, ProductionSpace
    from calflab.mech.belts import catalog_files
    from calflab.model.genome import Genome

    gdef = genome_definition("feral_calf")
    gp = {"belt_catalog": catalog_files(None)}
    cat = BeltCatalog.from_dict(gp["belt_catalog"])
    base = gdef.complete(dict(gdef.default_genome().values))

    def build(v):  # type: ignore[no-untyped-def]
        return build_design(Genome(definition="feral_calf", version=gdef.version, values=v), [], "feral_calf", gp)

    start = build(base)
    pr = ProductionSettings(sourceable_only=True, carpus_drive=True, springs=None).model_dump(mode="json")
    hw = HardwareSettings(servo_budget={"sts3250_c002": 6}, drives=["stifle", "hock", "carpus"], production=pr)
    hw.baseline = baseline_of(start.spec, base)
    space = ProductionSpace(gdef, hw, cat, base, start.spec, build)
    assert [s.id for s in space.systems] == [MM2, MM3]
    assert all(p.vendor == "McMaster-Carr" for v in space.pulleys.values() for p in v)
    assert "carpus_belt" in space.names
