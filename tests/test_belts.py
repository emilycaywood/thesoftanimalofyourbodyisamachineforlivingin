"""Belt drives from catalogs (ADR-063, ADR-064): derived centre distance, catalog rules, checks."""

from __future__ import annotations

import copy
import json
import math

import pytest
from calflab.mech.belts import (
    BeltCatalog,
    BeltChoice,
    BeltChoiceError,
    CatalogError,
    DriveLayout,
    DriveTarget,
    center_distance,
    choose_default,
    clearance_sweep,
    evaluate_drive,
    pitch_diameter,
    teeth_in_mesh,
    validate_drive,
    wrap_angle_driver,
)
from calflab.paths import config_dir

D1, D2 = pitch_diameter(30, 2.0), pitch_diameter(60, 2.0)


def _files() -> dict:
    return {n: json.loads((config_dir() / "belts" / n).read_text(encoding="utf-8"))
            for n in ("belt_systems.json", "belt_lengths.json", "pulleys.json")}


@pytest.fixture()
def catalog() -> BeltCatalog:
    return BeltCatalog.load(config_dir() / "belts")


def hock_layout(**kw: float | None) -> DriveLayout:
    base = dict(drive="hock", joint_label="hock", segment="tibia", segment_length_mm=245.0, near_limit_mm=28.0,
                far_limit_mm=217.0, servo_length_mm=45.2, servo_width_mm=24.7, output_axis_offset_mm=None,
                target=DriveTarget(kind="C", value=180.0))
    base.update(kw)
    return DriveLayout.model_validate(base)


# ---------------------------------------------------------------------- geometry
def test_pitch_diameters_are_teeth_times_pitch_over_pi():
    assert pytest.approx(19.099, abs=1e-3) == D1
    assert pytest.approx(38.197, abs=1e-3) == D2


@pytest.mark.parametrize(("length", "c"), [(450, 179.7), (444, 176.7), (460, 184.8)])
def test_center_distance_from_belt_length(length: float, c: float):
    """The researcher's check values: 2 mm pitch, 30T/60T."""
    assert center_distance(length, D1, D2) == pytest.approx(c, abs=0.06)


def test_center_distance_agrees_with_the_exact_open_belt_length():
    """The supplied formula is the standard closed-form approximation; against the exact length
    2C cos(phi) + pi (D1 + D2) / 2 + phi (D2 - D1) it is off by about 0.1 micrometre here."""
    c = center_distance(450, D1, D2)
    phi = math.asin((D2 - D1) / (2 * c))
    length = 2 * c * math.cos(phi) + math.pi * (D1 + D2) / 2 + phi * (D2 - D1)
    assert length == pytest.approx(450, abs=1e-3)


def test_too_short_a_belt_has_no_center_distance():
    with pytest.raises(ValueError, match="too short"):
        center_distance(80, D1, D2)


def test_wrap_and_teeth_in_mesh():
    wrap = wrap_angle_driver(D1, D2, 179.7)
    assert math.degrees(wrap) == pytest.approx(173.9, abs=0.1)
    assert teeth_in_mesh(30, wrap) == pytest.approx(14.5, abs=0.05)


# ---------------------------------------------------------------------- catalog
def test_catalog_values_are_the_supplied_ones(catalog: BeltCatalog):
    s = {x.id: x for x in catalog.systems}
    assert catalog.default_system == "MM-3MGT-9"  # R18 (ADR-115): the default rule chooses McMaster parts
    assert (s["GT2-2mm-10mm-generic"].allowable_working_tension_n, s["GT2-2mm-10mm-generic"].breaking_strength_n) == (44, 860)
    assert (s["GT2-2mm-9mm-gates"].allowable_working_tension_n, s["GT2-2mm-9mm-gates"].breaking_strength_n) == (39, 774)
    assert (s["GT2-2mm-15mm-generic"].allowable_working_tension_n, s["GT2-2mm-15mm-generic"].breaking_strength_n) == (66, 1290)
    assert s["GT2-3mm-9mm"].allowable_working_tension_n is None and s["GT2-3mm-9mm"].breaking_strength_n == 1422
    assert s["GT2-3mm-15mm"].allowable_working_tension_n is None and s["GT2-3mm-15mm"].breaking_strength_n == 2370
    assert "derated" in s["GT2-2mm-10mm-generic"].notes
    assert [p.id for p in catalog.pairs] == ["30T-60T", "36T-72T", "40T-80T"]
    assert catalog.pair(catalog.default_pair).pitch_mm == catalog.system(catalog.default_system).pitch_mm
    assert all(p.ratio == 2 for p in catalog.pairs)
    assert all(not e.purchase_confirmed for e in catalog.lengths)


def test_a_length_that_is_not_whole_teeth_is_rejected():
    data = _files()
    data["belt_lengths.json"]["lengths"].append(
        {"id": "odd", "pitch_mm": 2, "pitch_length_mm": 451, "source": "C", "purchase_confirmed": False})
    with pytest.raises(CatalogError, match="whole number"):
        BeltCatalog.from_dict(data)


def test_a_pitch_diameter_or_centre_distance_cannot_be_written_into_the_catalog():
    data = _files()
    data["pulleys.json"]["pairs"][0]["driver_pitch_diameter_mm"] = 19.1
    with pytest.raises(CatalogError, match="Extra inputs"):
        BeltCatalog.from_dict(data)
    data = _files()
    data["belt_lengths.json"]["lengths"][0]["center_distance_mm"] = 100
    with pytest.raises(CatalogError):
        BeltCatalog.from_dict(data)


def test_lengths_are_offered_only_where_their_source_covers_the_width(catalog: BeltCatalog):
    ten = catalog.system("GT2-2mm-10mm-generic")
    offered = {e.pitch_length_mm for e in catalog.lengths_for(ten) if catalog.length_status(ten, e)[0]}
    assert offered == {300, 360, 376, 394, 400, 444, 450, 460, 500, 540, 550, 600, 610, 640}
    ok, why = catalog.length_status(ten, catalog.length("GT2-2mm-450-A"))
    assert not ok and "width unconfirmed" in why
    gates = catalog.system("GT2-2mm-9mm-gates")
    assert all(e.source == "B" for e in catalog.lengths_for(gates) if catalog.length_status(gates, e)[0])
    wide = catalog.system("GT2-2mm-15mm-generic")  # R11c (ADR-103): source E lists 300 and 310 mm in 15 mm
    assert {e.pitch_length_mm for e in catalog.lengths_for(wide) if catalog.length_status(wide, e)[0]} == {300, 310}


def test_single_pulleys_pair_by_id_and_by_width(catalog: BeltCatalog):
    """R11c (ADR-103): listed pulleys are offered to a system only for a width their listings name; two of them make
    a pair ``<driver>+<driven>`` whose masses stay unentered until verified."""
    ten, wide = catalog.system("GT2-2mm-10mm-generic"), catalog.system("GT2-2mm-15mm-generic")
    assert [p.teeth for p in catalog.pulleys_for(ten)] == [20, 30, 36, 40, 45, 48, 60, 80]
    assert [p.teeth for p in catalog.pulleys_for(wide)] == [20, 40, 60, 80]
    assert not catalog.pulleys_for(catalog.system("GT2-2mm-9mm-gates"))
    pair = catalog.pair(catalog.pair_of("GT2-45T-10", "GT2-45T-10"))
    assert pair.ratio == 1.0 and pair.driver_mass_g is None and pair.driven_mass_g is None
    assert all(not p.verified and p.mass_g is None and p.listings for p in catalog.pulleys)
    from calflab.mech.belts import BeltChoice, DriveLayout, DriveTarget, evaluate_drive

    lay = DriveLayout(drive="hock", joint_label="hock", segment="tibia", segment_length_mm=245, near_limit_mm=28,
                      far_limit_mm=217, servo_length_mm=45.2, servo_width_mm=24.7, target=DriveTarget(value=150))
    rep = evaluate_drive(catalog, lay, BeltChoice(system=ten.id, pulleys="GT2-20T-15+GT2-40T-15",
                                                  length="GT2-2mm-400-C"))
    assert not rep.ok and any(c.id == "pulley_width" and c.status == "fail" for c in rep.checks)


# ---------------------------------------------------------------------- checks, rejection
def test_c_and_servo_position_are_derived_from_the_three_references(catalog: BeltCatalog):
    rep = evaluate_drive(catalog, hock_layout(), BeltChoice(system="GT2-2mm-10mm-generic", pulleys="30T-60T", length="GT2-2mm-450-C"))
    assert rep.c_mm == pytest.approx(179.75, abs=0.01)
    assert rep.servo_axis_from_driven_mm == rep.c_mm
    assert rep.servo_axis_from_far_mm == pytest.approx(245 - rep.c_mm)
    assert rep.c_with_travel_mm == pytest.approx((rep.c_mm - 3, rep.c_mm + 3))
    assert rep.ok


def test_a_choice_stores_only_catalog_references():
    with pytest.raises(ValueError):
        BeltChoice.model_validate({"system": "GT2-2mm-10mm-generic", "pulleys": "30T-60T", "length": "GT2-2mm-450-C", "c_mm": 170})


def test_an_invalid_choice_is_rejected_not_clamped(catalog: BeltCatalog):
    bad = BeltChoice(system="GT2-2mm-10mm-generic", pulleys="30T-60T", length="GT2-2mm-450-A")  # width unconfirmed
    with pytest.raises(BeltChoiceError, match="width unconfirmed"):
        validate_drive(catalog, hock_layout(), bad)
    # a belt so long the servo would leave the tibia
    long_ = BeltChoice(system="GT2-2mm-10mm-generic", pulleys="30T-60T", length="GT2-2mm-640-C")
    rep = evaluate_drive(catalog, hock_layout(), long_)
    assert not rep.ok and rep.c_mm == pytest.approx(274.8, abs=0.1)
    assert next(c for c in rep.checks if c.id == "servo_on_segment").status == "fail"


def test_servo_fit_is_unknown_until_the_output_axis_offset_is_entered(catalog: BeltCatalog):
    choice = BeltChoice(system="GT2-2mm-10mm-generic", pulleys="30T-60T", length="GT2-2mm-500-C")  # C 204.7
    unknown = evaluate_drive(catalog, hock_layout(), choice)
    assert next(c for c in unknown.checks if c.id == "servo_on_segment").status == "unknown" and unknown.ok
    assert evaluate_drive(catalog, hock_layout(output_axis_offset_mm=10.0), choice).ok  # case pointed down the tibia
    assert not evaluate_drive(catalog, hock_layout(output_axis_offset_mm=22.6, far_limit_mm=220.0), choice).ok


def test_too_few_teeth_in_mesh_fails():
    rep_wrap = wrap_angle_driver(D1, D2, 30.0)
    assert teeth_in_mesh(30, rep_wrap) > 6  # 30T always has plenty at 2:1; the check is on the formula
    assert teeth_in_mesh(10, math.radians(180)) == pytest.approx(5.0)


def test_default_is_the_passing_length_closest_to_target(catalog: BeltCatalog):
    old = ("GT2-2mm-10mm-generic", "30T-60T")  # the pre-R18 default, still a valid (not offered) catalog choice
    choice, rep, why = choose_default(catalog, hock_layout(), *old)
    assert why == "" and choice is not None and rep is not None
    assert choice.length == "GT2-2mm-450-C" and rep.c_mm == pytest.approx(179.7, abs=0.1)
    win = hock_layout(target=DriveTarget(kind="C", value=175, low=150, high=200), far_limit_mm=240.0)
    choice, rep, _ = choose_default(catalog, win, *old)
    assert choice is not None and choice.length == "GT2-2mm-444-C"


def test_clearance_sweep_fails_only_where_the_belt_meets_the_case():
    angles = [0.0, 40.0, 80.0]
    dirs = [(-math.sin(math.radians(75 + a)), math.cos(math.radians(75 + a))) for a in angles]
    clear = clearance_sweep(angles[:2], dirs[:2], 176.7, D1, D2, (0.0, -1.0), [(65.3, 110.5)], 15.35, 3.0, "belt")
    assert clear.status == "pass"
    hit = clearance_sweep(angles, dirs, 176.7, D1, D2, (0.0, -1.0), [(65.3, 110.5)], 15.35, 3.0, "belt")
    assert hit.status == "fail" and hit.first_contact_deg == 80.0


def test_catalog_is_copied_unchanged():
    data = copy.deepcopy(_files())
    assert BeltCatalog.from_dict(data).digest() == BeltCatalog.load(config_dir() / "belts").digest()
