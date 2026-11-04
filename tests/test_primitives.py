"""Motion primitives (ADR-085): contracts, poses that balance by construction, controllers, safe switching."""

from __future__ import annotations

import numpy as np
import pytest
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.plugins import load_plugins, registry
from calflab.plugins.contracts import check_plugin

KEYS = ("stand", "weight_shift", "step", "walk", "turn", "trot", "lie_rise")


@pytest.fixture(scope="module")
def spec():
    load_plugins()
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


@pytest.mark.parametrize("key", KEYS)
def test_primitive_contract(spec, key):
    cls = registry.get("motion_primitive", key)
    assert check_plugin(cls) == []
    prim = cls()
    for a, b in prim.safe_phases():
        assert 0.0 <= a <= b <= 1.0
    assert prim.period_s() > 0 and prim.warmup_s() >= 0


def test_new_plugin_template_passes_its_contract(tmp_path):
    from calflab.plugins.templates import render

    src, test = render("motion_primitive", "sway_in_place")
    ns: dict = {}
    exec(compile(src.replace("@register\n", ""), "sway_in_place.py", "exec"), ns)  # noqa: S102 - our own template
    assert check_plugin(ns["SwayInPlace"]) == []
    assert "check_plugin" in test


def test_weight_shift_pose_keeps_hooves_and_moves_the_centre_of_mass_inside_the_tripod(spec):
    from calflab.behave.shift_design import design_pose

    stand = design_pose(spec, library(), "hr", 0.0)
    shifted = design_pose(spec, library(), "hr", 0.8)
    assert shifted["hoof_slip_mm"] < 1.0
    assert shifted["com_inside_tripod_mm"] > stand["com_inside_tripod_mm"] + 25.0
    assert shifted["com_shift_mm"] == pytest.approx(shifted["com_target_shift_mm"], abs=2.0)
    crouch = design_pose(spec, library(), None, 0.0, crouch_mm=30.0)
    assert crouch["trunk_drop_mm"] == pytest.approx(30.0, abs=2.0) and crouch["hoof_slip_mm"] < 1.0


def test_weight_shift_controller_timeline():
    from calflab.control.weight_shift import WeightShiftController

    c = WeightShiftController({"offsets": {"joint.hl.stifle": 10.0}, "lift": {"joint.hr.stifle": 20.0},
                               "shift_s": 1.0, "hold_s": 1.0, "back_s": 1.0, "lift_share": 0.6})
    assert c.pose_at(0.0)["joint.hl.stifle"] == pytest.approx(0.0)
    mid = c.pose_at(1.5)
    assert mid["joint.hl.stifle"] == pytest.approx(10.0) and mid["joint.hr.stifle"] == pytest.approx(20.0)
    assert c.pose_at(1.05).get("joint.hr.stifle", 0.0) == pytest.approx(0.0)  # the hoof waits for the shift
    assert c.pose_at(3.0)["joint.hl.stifle"] == pytest.approx(0.0, abs=1e-9)


def test_feral_walk_and_trot_unchanged_by_default():
    """stride 1 and turn 0 multiply by exactly 1.0: every earlier rollout is the same."""
    from calflab.control.feral_motion import FeralMotionController

    for mode in ("walk", "trot"):
        a = FeralMotionController({"mode": mode})
        b = FeralMotionController({"mode": mode, "stride": 1.0, "turn": 0.0})
        for t in np.linspace(0, 6, 61):
            assert a.pose_at(float(t)) == b.pose_at(float(t))
    turn = FeralMotionController({"mode": "walk", "stride": 0.0, "turn": 1.0})
    p = turn.pose_at(3.0)
    assert p["hl.stifle"] == pytest.approx(-p["hr.stifle"], abs=1e-9) or p["hl.stifle"] != p["hr.stifle"]


def test_interpreted_controller_switches_only_at_safe_phases(spec):
    """Two states with short durations: every switch out of the walk happens with every hoof down (a safe
    phase), and the episodes are logged."""
    from calflab.behave.physics import compile_params
    from calflab.control.interpreted import InterpretedController
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    walk = registry.get("motion_primitive", "walk")({"cycle_s": 2.0})
    stand = registry.get("motion_primitive", "stand")()
    states = []
    for name, prim in (("walk", walk), ("stand", stand)):
        key, params = prim.controller(spec, library())
        states.append({"name": name, "primitive": prim.key, "controller": {"key": key, "params": params},
                       "period_s": prim.period_s(), "offset_s": prim.phase_offset_s(),
                       "safe": [list(x) for x in prim.safe_phases()], "one_shot": prim.one_shot,
                       "duration": {"log_mean": float(np.log(2.2)), "log_sd": 0.01, "min_s": 2.0, "max_s": 3.0}})
    params = {"states": states, "transitions": {"walk": {"stand": 1.0}, "stand": {"walk": 1.0}}, "start": "walk"}
    cm = compile_mjcf(spec, library(), CompileOptions.model_validate(compile_params({})), 0)
    ro = run_rollout(cm, InterpretedController(params), SimSettings(duration_s=9.0, seed=0, stop_on_fall=True), library())
    eps = ro.meta["controller_log"]["episodes"]
    assert [e["name"] for e in eps][:3] == ["walk", "stand", "walk"]
    first_walk = eps[0]
    local = first_walk["t1"] - first_walk["t0"]
    ph = ((local - 1.5) / 2.0) % 1.0
    assert any(a - 0.02 <= ph <= b + 0.02 for a, b in walk.safe_phases()), ph
    assert not first_walk.get("unsafe_switch")
    # the run is reproducible
    ro2 = run_rollout(cm, InterpretedController(params), SimSettings(duration_s=9.0, seed=0, stop_on_fall=True), library())
    assert np.array_equal(ro.q, ro2.q)
