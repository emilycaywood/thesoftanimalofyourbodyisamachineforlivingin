"""Behaviour diversity on a fixed body (ADR-093): the generator, its chain, one evaluation, a tiny run."""

from __future__ import annotations

import numpy as np
import pytest
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.evolve.diversity import (
    checked_duration,
    controller_params,
    coverage_plan,
    decode,
    evaluate_behaviour,
    layout,
    palette_for,
    reach_probability,
    transition_matrix,
    unpredictability,
)
from calflab.fitness import presets
from calflab.model.genome import Genome
from calflab.plugins import load_plugins, registry


@pytest.fixture(scope="module")
def body():
    load_plugins()
    d = genome_definition("feral_calf")
    genome = {"definition": "feral_calf", "version": d.version, "values": d.complete(d.defaults())}
    return genome, build_design(Genome.model_validate(genome), [], "feral_calf", {}).spec


def test_the_palette_fits_the_body_and_the_vector_decodes(body):
    _g, spec = body
    pal = palette_for(spec)
    assert {n for n, _k, _b in pal} >= {"stand", "shift_hl", "step_hr", "walk", "trot"}
    genes = layout(pal)
    gen = decode(np.full(len(genes), 0.5), pal)
    assert gen["states"]["shift_hl"]["params"]["leg"] == "hl"  # the fixed part stays
    walk = registry.get("motion_primitive", "walk")
    for d in walk.vector_dims():
        assert gen["states"]["walk"]["params"][d.name] == pytest.approx((d.lo + d.hi) / 2, abs=1e-3)
    with pytest.raises(ValueError):
        decode(np.zeros(3), pal)


def test_the_chain_never_repeats_a_state_and_its_rows_sum_to_one(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.random.default_rng(1).uniform(0, 1, len(layout(pal))), pal)
    names, m = transition_matrix(gen)
    assert np.allclose(np.diag(m), 0.0) and np.allclose(m.sum(axis=1), 1.0)
    from calflab.components import library

    ctrl = controller_params(gen, spec, library())
    params = registry.get("controller", "interpreted").Params.model_validate(ctrl)
    assert [s.name for s in params.states] == names


def test_unpredictability_is_one_for_a_uniform_chain_and_lower_when_it_wanders(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.full(len(layout(pal)), 0.5), pal)
    for st in gen["states"].values():
        st["weight"] = 1.0
    gen["sharpness"] = 0.0
    assert unpredictability(gen) == pytest.approx(1.0, abs=1e-6)
    for k, st in enumerate(gen["states"].values()):
        st["place"] = k / (len(gen["states"]) - 1)
    gen["sharpness"] = 8.0
    assert unpredictability(gen) < 0.8


def test_one_generator_played_and_judged(body):
    genome, spec = body
    pal = palette_for(spec)
    preset = presets()["diversity"].model_dump(mode="json")
    preset["evaluation"]["seeds"] = [0]
    out = evaluate_behaviour({"genome": genome, "overrides": [], "generator": "feral_calf", "generator_params": {},
                              "compile": {}, "fitness": preset, "x": [0.5] * len(layout(pal)), "duration_s": 6.0,
                              "margin": 0.2, "descriptors": ["quantity_of_motion", "tempo_regularity"]})
    m = out["metrics"]
    assert m["seeds"][0]["seed"] == 0 and 0.0 <= m["unpredictability"] <= 1.0
    safe = 1.0 if m["within_limits"] else -1.0  # a safe one always outranks an unsafe one
    assert out["fitness"] == pytest.approx(safe + min(1.0, m["safety_margin"]) + 0.5 * m["unpredictability"])
    assert m["within_limits"] == (not out.get("unsafe_reasons"))
    assert set(out["descriptors"]) == {"quantity_of_motion", "tempo_regularity"}
    assert out["controller_params"]["states"]


def test_reach_grows_with_the_performance_and_rare_states_are_unlikely(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.full(len(layout(pal)), 0.5), pal)
    gen["states"]["step_hr"]["weight"] = 0.0  # floored at 1e-3: reachable, but rarely
    short, long = reach_probability(gen, 10.0), reach_probability(gen, 600.0)
    assert all(0.0 <= v <= 1.0 for v in short.values())
    assert all(long[n] >= short[n] for n in short)
    assert short["step_hr"] < 0.05 < short["stand"]


def test_coverage_forces_each_likely_unplayed_state_along_a_real_path(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.full(len(layout(pal)), 0.5), pal)
    gen["states"]["trot"]["weight"] = 0.0  # unlikely in a minute: not checked
    ctrl = controller_params(gen, spec, library(), 0.2)
    reach = reach_probability(gen, 60.0)
    plays = coverage_plan(gen, ctrl, {"stand": 3}, 3, 60.0, 0.05, 6.0)
    forced = {pl["state"] for pl in plays}
    assert forced == {n for n in gen["states"] if reach[n] >= 0.05} - {"stand"}  # stand was played on every seed
    assert "trot" not in forced
    assert [pl["reach"] for pl in plays] == sorted((pl["reach"] for pl in plays), reverse=True)  # likeliest first
    for pl in plays:
        c = pl["controller"]
        states = {st["name"]: st for st in c["states"]}
        assert states[pl["state"]]["duration"]["log_sd"] == 0.0 and pl["duration_s"] > 6.0
        if pl["from"] == "start":
            assert c["start"] == pl["state"]
        else:
            assert c["start"] == pl["from"] and c["transitions"][pl["from"]] == {pl["state"]: 1.0}
            assert reach[pl["from"]] >= 0.05  # the path goes through a state the chain really plays
    assert all(st["duration"]["log_sd"] == 0.4 for st in ctrl["states"])


def test_capped_durations_never_exceed_what_coverage_checks(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.full(len(layout(pal)), 0.5), pal)
    free = controller_params(gen, spec, library(), 0.2)
    capped = controller_params(gen, spec, library(), 0.2, cap=True)
    for f, c in zip(free["states"], capped["states"], strict=True):
        assert f["duration"]["max_s"] == 15.0  # off: as before (old runs replay the same)
        assert c["duration"]["max_s"] == pytest.approx(checked_duration(c["duration"]["log_mean"]), abs=1e-3)
        assert c["duration"]["max_s"] < 15.0 and c["duration"]["log_mean"] == f["duration"]["log_mean"]
    # with the cap, a state played on every seed is still forced: a typical length says nothing about the cap
    reach = reach_probability(gen, 60.0)
    likely = {n for n in gen["states"] if reach[n] >= 0.05}
    all_done = dict.fromkeys(gen["states"], 3)
    assert {pl["state"] for pl in coverage_plan(gen, capped, all_done, 3, 60.0, 0.05, 6.0, force_all=True)} == likely
    assert coverage_plan(gen, capped, all_done, 3, 60.0, 0.05, 6.0) == []
    for pl in coverage_plan(gen, capped, {}, 3, 60.0, 0.05, 6.0, force_all=True):  # forced at exactly the cap
        st = {x["name"]: x for x in pl["controller"]["states"]}[pl["state"]]
        assert np.exp(st["duration"]["log_mean"]) == pytest.approx(st["duration"]["max_s"], rel=1e-3)


def test_the_optimizer_is_registered_with_movement_axes():
    load_plugins()
    cls = registry.get("optimizer", "map_elites_behaviour")
    p = cls.Params()
    assert p.descriptor_x == "quantity_of_motion" and p.descriptor_y == "tempo_regularity" and p.margin == 0.2
    assert p.coverage is False and p.performance_s == 60.0  # off by default: old runs replay as they were
    assert p.cap_durations is False
    for key in ("tempo_regularity", "stillness_ratio", "unpredictability"):
        assert registry.get("behavior_descriptor", key)().describe_candidate(None, {}, {}) == 0.0
