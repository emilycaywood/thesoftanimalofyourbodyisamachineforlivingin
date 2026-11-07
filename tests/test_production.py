"""R11c (ADR-103): the bounded production space of map_elites_hardware."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from calflab.plugins import load_plugins


@pytest.fixture(scope="module")
def setup() -> dict[str, Any]:
    load_plugins()
    from calflab.components import library
    from calflab.design import build_design, genome_definition
    from calflab.evolve.hardware import HardwareSettings, baseline_of
    from calflab.evolve.production import ProductionSettings, ProductionSpace
    from calflab.mech.belts import BeltCatalog, catalog_files
    from calflab.model.genome import Genome

    gdef = genome_definition("feral_calf")
    gp = {"belt_catalog": catalog_files(None)}
    cat = BeltCatalog.from_dict(gp["belt_catalog"])
    base = gdef.complete(dict(gdef.default_genome().values))

    def build(v: dict[str, Any]) -> Any:
        return build_design(Genome(definition="feral_calf", version=gdef.version, values=v), [], "feral_calf", gp)

    start = build(base)
    hw = HardwareSettings(servo_budget={"sts3250_c002": 6}, servo_denominator=4,
                          drives=["stifle", "hock", "carpus", "shoulder"],
                          cost_weights={"servos": 1.0, "pulley_sizes": 0.25, "what_if": 0.5, "mass_kg": 1.0,
                                        "spring_sites": 0.25},
                          production=ProductionSettings().model_dump(mode="json"))
    hw.baseline = baseline_of(start.spec, base)
    space = ProductionSpace(gdef, hw, cat, base, start.spec, build)
    return {"space": space, "base": base, "start": start, "hw": hw, "build": build, "lib": library(), "cat": cat}


def test_the_starting_body_comes_back_unchanged(setup: dict[str, Any]) -> None:
    s = setup
    v, d, why, _ = s["space"].realise(s["space"].encode(s["base"]), s["base"])
    assert not why and d is not None
    assert {k: x for k, x in v.items() if s["base"][k] != x} == {}
    assert d.spec.model_dump_json() == s["start"].spec.model_dump_json()


def test_every_dimension_is_discrete_and_lengths_are_feasible_by_construction(setup: dict[str, Any]) -> None:
    s = setup
    rng = np.random.default_rng(3)
    accepted = 0
    for _ in range(25):
        x = s["space"].encode(s["base"])
        x = np.where(rng.random(len(x)) < 0.3, rng.random(len(x)), x)
        v, d, why, extra = s["space"].realise(x, s["base"])
        v2, _d2, why2, _ = s["space"].realise(x, s["base"])
        assert v == v2 and why == why2  # the same vector is the same body
        if d is None or why:
            assert why  # every rejection says why
            continue
        accepted += 1
        drives = d.spec.metadata["feral"]["belt_drives"]
        assert all(r["ok"] for r in drives.values()), drives  # a decoded length never fails a belt check
        for gid, grid in s["space"].geo.items():
            assert v[gid] in grid
    assert accepted > 0


def test_ratios_outside_the_tolerance_are_rejected_with_the_reason(setup: dict[str, Any]) -> None:
    s = setup
    sp = s["space"]
    x = sp.encode({**s["base"], "femur_length": sp.geo["femur_length"][-1], "tibia_length": sp.geo["tibia_length"][0]})
    _v, d, why, _ = sp.realise(x, s["base"])
    assert d is None and any(r.startswith("ratio tibia/femur") for r in why)


def test_budget_of_six_new_servos_and_the_cost_index(setup: dict[str, Any]) -> None:
    from calflab.evolve.hardware import budget_reasons, hardware_costs

    s = setup
    new = "sts3250_c002"
    six = {**s["base"], "servo_hip_abd": new, "servo_hock": new, "servo_carpus": new}
    assert not budget_reasons(six, s["hw"])
    assert budget_reasons({**six, "servo_shoulder": new}, s["hw"])  # 8 > 6: rejected, never repaired
    v, d, why, _ = s["space"].realise(s["space"].encode({**six, "spring_carpus": True}), s["base"])
    assert d is not None and not why
    c = hardware_costs(d.spec, v, s["hw"], s["lib"])
    assert c["servo_denominator"] == 4 and c["spring_sites_added"] == ["carpus"]
    added_kg = max(0.0, (c["mass_g"] - s["hw"].baseline["mass_g"]) / 1000.0)
    assert c["cost_index"] == pytest.approx(6 / 4 + 0.25 + added_kg, abs=2e-4)


def test_a_spring_anchor_off_its_segment_is_rejected(setup: dict[str, Any]) -> None:
    from calflab.evolve.production import SpringSpace, spring_checks

    s = setup
    v = {**s["base"], "spring_hock": True, "spring_hock_upper_along": float(s["base"]["tibia_length"])}
    d = s["build"](v)
    why, rep = spring_checks(d.spec, v, SpringSpace())
    assert any("hock spring: upper anchor" in r for r in why)
    assert rep["hock"]["max_extension_mm"] > 0


def test_belted_shoulder_and_carpus_spring_are_off_for_stored_genomes() -> None:
    from calflab.design import genome_definition

    gdef = genome_definition("feral_calf")
    done = gdef.complete({})
    assert done["shoulder_belt"] is False and done["spring_carpus"] is False
