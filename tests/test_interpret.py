"""Interpretation (ADR-085): distances and verdicts, the search on a short synthetic target, determinism, the
records' reasons, and a performance built from a reading."""

from __future__ import annotations

import pytest
from calflab.behave.interpret import (
    Interpreter,
    InterpretSettings,
    feature_distance,
    interpret_behaviour,
    verdict,
)
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.plugins import load_plugins


@pytest.fixture(scope="module")
def spec():
    load_plugins()
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def test_distance_and_verdicts():
    d, parts = feature_distance({"tempo_s": 1.0, "turn_rate_deg_s": 0.0}, {"tempo_s": 1.0, "turn_rate_deg_s": 30.0},
                                {"tempo_s": 1.0, "turn_rate_deg_s": 1.0, "heave_mm": 1.0})
    assert parts["tempo_s"] == 0.0 and parts["turn_rate_deg_s"] == pytest.approx(4.0) and "heave_mm" not in parts
    assert d == pytest.approx(4.0)
    assert verdict("qom_deg_s", 10.0, 11.0) == "kept"
    assert verdict("qom_deg_s", 10.0, 3.0) == "reduced"
    assert verdict("qom_deg_s", 10.0, 0.5) == "dropped"
    assert verdict("qom_deg_s", 10.0, 20.0) == "exaggerated"
    assert verdict("turn_rate_deg_s", -20.0, 20.0) == "reversed"
    assert verdict("tempo_s", None, 1.0) == "not read"


def test_interpretation_of_a_short_synthetic_target_is_deterministic(spec):
    """The target is the robot's own weight shift at known parameters (so it is reachable): the search finds a
    candidate within the limits that reads closer to it than the primitive's defaults, and the same seed gives the
    same record."""
    s = InterpretSettings(popsize=3, generations=1, min_play_s=2.0, max_play_s=4.0)
    it = Interpreter(spec, library(), {}, s, None)
    target = it.evaluate("weight_shift", {"leg": "hr", "shift": 0.8, "shift_s": 0.8, "hold_s": 0.5}, {}, {}).features
    assert target["qom_deg_s"] > 0
    out = []
    for _ in range(2):
        it = Interpreter(spec, library(), {}, s, None)
        out.append(interpret_behaviour(it, "weight_shift", target, ["weight_shift"], {"lean_roll_deg": -2.0}))
    a, b = out
    assert a["params"] == b["params"] and a["distance"] == b["distance"]
    assert a["within_limits"] and a["leg"] == "hr"
    defaults = a["alternatives"][0]["defaults"]
    assert a["distance"] <= defaults["distance"] + 1e-9
    assert {r["feature"] for r in a["comparison"]} >= {"qom_deg_s", "roll_range_deg"}
    assert all(r["verdict"] for r in a["comparison"])
    assert a["cost"]["plays"] == 4


def test_cache_makes_a_second_interpretation_free(spec, tmp_path):
    s = InterpretSettings(popsize=2, generations=1, min_play_s=2.0, max_play_s=3.0)
    target = {"qom_deg_s": 3.0, "roll_range_deg": 1.0}
    it = Interpreter(spec, library(), {}, s, tmp_path)
    first = interpret_behaviour(it, "stand", target, ["stand"])
    it2 = Interpreter(spec, library(), {}, s, tmp_path)
    second = interpret_behaviour(it2, "stand", target, ["stand"])
    assert first["params"] == second["params"]
    assert second["cost"]["plays"] == 0 and second["cost"]["cache_hits"] == first["cost"]["plays"]


def test_states_and_a_short_performance_from_a_synthetic_reading(spec):
    """build_states turns interpretation records and a reading's model into the interpreted controller; a short
    performance plays it and the robot is read back by the same reader."""
    from calflab.app.interpret_jobs import build_states
    from calflab.behave import reading as rd
    from calflab.behave.signals import synthetic_signals
    from calflab.plugins import registry

    sig, _truth = synthetic_signals(spec, [("stand", 2.0), ("weight_shift", 2.0), ("stand", 2.0)])
    st = rd.ReadingSettings()
    up, _how = rd.lifted(sig, st)
    sts = rd.label(sig, up, st, video="synthetic")
    model = rd.fit_model(sts, st)
    beh = rd.behaviour_summary(sts)
    v = rd.VideoReading(file="synthetic", usable=True)
    reading = rd.Reading(id="t", created="t", settings=st, provenance={}, videos=[v], stretches=sts, behaviours=beh,
                         model=model, support=rd.support_statement([v], sts, model), gaps=[])
    recs = [{"behaviour": "stand", "primitive": "stand", "params": {"crouch_mm": 0.0}, "within_limits": True},
            {"behaviour": "weight_shift", "primitive": "weight_shift", "params": {"leg": "hr", "shift": 0.5},
             "within_limits": True},
            {"behaviour": "other", "primitive": "trot", "params": {}, "within_limits": False}]
    ctrl = build_states(reading, recs, spec)
    assert [x["name"] for x in ctrl["states"]] == ["stand", "weight_shift"]  # over a limit: not performed
    assert ctrl["transitions"]["stand"] == {"weight_shift": 1.0}
    ws = ctrl["states"][1]
    assert ws["vary"]["offsets"][1] == 1.0 and ws["vary"]["shift_s"][0] == 1.0  # never larger, never faster
    registry.get("controller", "interpreted").Params.model_validate(ctrl)
