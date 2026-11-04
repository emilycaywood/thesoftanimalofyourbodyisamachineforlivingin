"""Vigour within limits (ADR-090): the suite preset, kept shares, cost, archive axes, one tiny evaluation."""

from __future__ import annotations

import math

import pytest
from calflab.design import genome_definition
from calflab.evolve.vigour import (
    SuiteMotion,
    SuiteSettings,
    kept_share,
    prepare_targets,
    suite_plays,
)
from calflab.fitness import presets
from calflab.plugins import load_plugins, registry


def test_the_preset_has_a_suite_of_walk_trot_and_the_read_behaviours():
    p = presets()["vigour"]
    assert p.evaluation is not None and p.evaluation.seeds == [0, 1, 2] and p.evaluation.randomize
    suite = SuiteSettings.model_validate(p.evaluation.suite)
    assert [(m.name, m.kind) for m in suite.motions] == [("walk", "gait"), ("trot", "gait"), ("stand", "read"),
                                                         ("step", "read"), ("other", "read")]
    assert suite.margin == 0.2 and suite.targets is None  # targets are measured when a run starts


def test_kept_share_of_a_gait_is_its_speed_against_the_reference():
    m = SuiteMotion(name="walk", kind="gait", primitive="walk")
    t = {"ref_speed_mm_s": 100.0}
    assert kept_share(m, t, {"speed_mm_s": 50.0}) == pytest.approx(0.5)
    assert kept_share(m, t, {"speed_mm_s": 180.0}) == 1.0
    assert kept_share(m, t, {}) == 0.0


def test_kept_share_of_a_read_behaviour_is_its_features_matched():
    m = SuiteMotion(name="step", kind="read")
    t = {"calf": {"step_rate_hz": 1.0, "qom_deg_s": 20.0}, "weights": {"step_rate_hz": 1.0, "qom_deg_s": 1.0}}
    assert kept_share(m, t, {"step_rate_hz": 1.0, "qom_deg_s": 20.0}) == pytest.approx(1.0)
    half = kept_share(m, t, {"step_rate_hz": 1.0, "qom_deg_s": 40.0})  # one of two features at 2x
    d = math.log((40.0 + 0.5) / (20.0 + 0.5))
    assert half == pytest.approx((1.0 + math.exp(-d * d)) / 2.0)
    assert kept_share(m, t, {"step_rate_hz": 1.0}) == pytest.approx(0.5)  # a feature not measured keeps nothing


def test_plays_per_body_bound_the_cost():
    load_plugins()
    suite = SuiteSettings(motions=[SuiteMotion(name="trot", kind="gait", primitive="trot")], verify=2)
    per = suite_plays(suite, popsize=4, generations=2, seeds=3)
    assert per["search_plays"] == 1 + 4 * 2 and per["verify_plays_max"] == 2 * 3
    assert per["plays_max"] == 15 and per["simulated_s_max"] > 15 * 4.0  # every play at least min_play_s


def test_archive_axes_read_the_suite_record():
    load_plugins()
    metrics = {"vigour": {"kept": 0.4, "worst_margin": -2.5}, "hoof_half_width_mm": {"hind": 150.0, "front": 120.0}}
    assert registry.get("behavior_descriptor", "vigour_kept")().describe_candidate(None, metrics, {}) == 0.4
    assert registry.get("behavior_descriptor", "worst_margin")().describe_candidate(None, metrics, {}) == -1.0  # clipped
    assert registry.get("behavior_descriptor", "hoof_width")().describe_candidate(None, metrics, {}) == 150.0


def test_block_widths_and_splays_evolve_but_belts_do_not():
    gdef = genome_definition("feral_calf")
    ev = {g.id for g in gdef.evolvable(None)}
    assert {"hip_block_widen", "chest_block_widen", "hind_leg_splay", "front_leg_splay", "spring_hip_abd_k"} <= ev
    assert not any(g.startswith("belt_") for g in ev) and "spring_hip_abd" not in ev


def test_one_body_scored_on_a_one_gait_suite(tmp_path):
    """Tiny budget: the trot's defaults (no search), verified on one seed; fitness and record are consistent."""
    from calflab.components import library
    from calflab.evolve.tasks import evaluate_candidate

    load_plugins()
    d = genome_definition("feral_calf")
    genome = {"definition": "feral_calf", "version": d.version, "values": d.complete(d.defaults())}
    from calflab.design import build_design
    from calflab.model.genome import Genome

    spec = build_design(Genome.model_validate(genome), [], "feral_calf", {}).spec
    suite = SuiteSettings(motions=[SuiteMotion(name="trot", kind="gait", primitive="trot")], generations=0, verify=1)
    suite.targets = prepare_targets(suite, spec, library(), {}, None, tmp_path)
    assert suite.targets["trot"]["ref_speed_mm_s"] > 0
    suite.cache_dir = str(tmp_path)
    preset = presets()["vigour"].model_dump(mode="json")
    preset["evaluation"].update({"seeds": [0], "suite": suite.model_dump(mode="json")})
    out = evaluate_candidate({"genome": genome, "overrides": [], "generator": "feral_calf", "generator_params": {},
                              "compile": {}, "sim": {}, "controller": {"key": "feral_motion", "params": {}},
                              "fitness": preset, "descriptors": ["vigour_kept", "worst_margin"],
                              "inner": {"iterations": 0, "popsize": 4}})
    rec = out["metrics"]["vigour"]["motions"]["trot"]
    assert rec["searched"] == 1 and out["evals"] >= 0
    shortfall = min(1.0, max(0.0, -out["metrics"]["vigour"]["worst_margin"]))
    assert out["fitness"] == pytest.approx(out["metrics"]["vigour"]["kept"] - shortfall)
    assert out["descriptors"]["vigour_kept"] == pytest.approx(out["metrics"]["vigour"]["kept"])
    if rec["feasible"]:
        assert rec["kept"] > 0 and all(s["within"] for s in rec["seeds"])
    else:
        assert rec["kept"] == 0.0
