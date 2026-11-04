"""Behaviour diversity on a fixed body (ADR-093): the generator, its chain, one evaluation, a tiny run."""

from __future__ import annotations

import numpy as np
import pytest
from calflab.design import build_design, genome_definition
from calflab.evolve.diversity import (
    controller_params,
    decode,
    evaluate_behaviour,
    layout,
    palette_for,
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


def test_the_optimizer_is_registered_with_movement_axes():
    load_plugins()
    cls = registry.get("optimizer", "map_elites_behaviour")
    p = cls.Params()
    assert p.descriptor_x == "quantity_of_motion" and p.descriptor_y == "tempo_regularity" and p.margin == 0.2
    for key in ("tempo_regularity", "stillness_ratio", "unpredictability"):
        assert registry.get("behavior_descriptor", key)().describe_candidate(None, {}, {}) == 0.0
