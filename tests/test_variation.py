"""Movement that varies within a state (ADR-098): bounded signals, extremes, the controller, the genes."""

from __future__ import annotations

import math

import numpy as np
import pytest
from calflab.components import library
from calflab.control.variation import CORNERS, Signals, extremes_value, posture_basis
from calflab.design import build_design, genome_definition
from calflab.evolve.diversity import (
    WITHIN_GLOBAL,
    WITHIN_STATE,
    controller_params,
    coverage_plan,
    decode,
    layout,
    palette_for,
)
from calflab.model.genome import Genome
from calflab.plugins import ControlInfo, Observation, load_plugins, registry


@pytest.fixture(scope="module")
def body():
    load_plugins()
    d = genome_definition("feral_calf")
    genome = {"definition": "feral_calf", "version": d.version, "values": d.complete(d.defaults())}
    return genome, build_design(Genome.model_validate(genome), [], "feral_calf", {}).spec


def _info(spec, n: int | None = None) -> ControlInfo:
    ids = [a.joint for a in spec.actuators]
    k = len(ids)
    return ControlInfo(actuator_ids=[a.id for a in spec.actuators], joint_ids=ids, rest=np.zeros(k),
                       lo=np.full(k, -2.0), hi=np.full(k, 2.0), control_dt=0.02, speed_limit=None)


def _play(ctrl: dict, spec, seconds: float, seed: int = 0) -> tuple[np.ndarray, list[dict]]:
    c = registry.get("controller", "interpreted")(ctrl)
    info = _info(spec)
    c.reset(info, seed)
    k = len(info.joint_ids)
    out = []
    for i in range(int(seconds / info.control_dt)):
        obs = Observation(t=i * info.control_dt, q=np.zeros(k), dq=np.zeros(k), trunk_quat=np.array([1.0, 0, 0, 0]),
                          trunk_gyro=np.zeros(3), foot_contact=np.ones(4))
        out.append(c.act(obs))
    return np.asarray(out), c.log()["episodes"]


def test_signals_stay_within_their_bounds_and_height_only_crouches():
    s = Signals(3, 0.4)
    for t in np.linspace(0, 60, 601):
        for a in ("lateral", "fore_aft", "head_pitch"):
            assert abs(s.value(a, float(t), 0.6, 0.2)) <= 0.8 + 1e-9
        assert 0.0 <= s.value("height", float(t), 0.6, 0.2) <= 0.8 + 1e-9
    assert s.value("lateral", 1.0, 0.0, 0.0) == 0.0 and s.value("height", 1.0, 0.0, 0.0) == 0.0


def test_the_extremes_reach_every_corner_at_full_drift():
    step = 1.0
    reached = set()
    for k in range(4):
        t = k * step + 0.8  # held after 60 % of the step
        lat, fa = extremes_value("lateral", t, step, 0.7, 0.0), extremes_value("fore_aft", t, step, 0.7, 0.0)
        reached.add((round(lat / 0.7), round(fa / 0.7)))
        assert extremes_value("height", t, step, 0.7, 0.0) == pytest.approx(0.7)
    assert reached == set(CORNERS)
    assert max(abs(extremes_value("lateral", t, step, 0.7, 0.2)) for t in np.linspace(0, 4, 400)) <= 0.9 + 1e-9


def test_the_posture_basis_is_solved_on_the_body(body):
    _g, spec = body
    b = posture_basis(spec)
    assert b["height"] and b["lateral"] and b["fore_aft"]
    # mirror symmetry: the lateral shift moves the left and right hip ab/ad oppositely
    assert b["lateral"]["joint.hl.hip_abd"] == pytest.approx(-b["lateral"]["joint.hr.hip_abd"], abs=1e-3)
    assert b["height"]["joint.hl.stifle"] == pytest.approx(b["height"]["joint.hr.stifle"], abs=1e-3)
    assert not b["head_pitch"] and not b["head_yaw"]  # the feral calf has no neck motors


def test_without_variation_the_layout_and_controller_are_as_before(body):
    _g, spec = body
    pal = palette_for(spec)
    assert len(layout(pal, True)) == len(layout(pal)) + len(WITHIN_GLOBAL) + len(pal) * len(WITHIN_STATE)
    x = np.full(len(layout(pal)), 0.5)
    ctrl = controller_params(decode(x, pal), spec, library(), 0.2, cap=True)
    assert "variation" not in ctrl and all("within" not in s for s in ctrl["states"])


def test_zero_variation_plays_the_same_targets(body):
    _g, spec = body
    pal = palette_for(spec)
    x0 = np.full(len(layout(pal)), 0.5)
    plain = controller_params(decode(x0, pal), spec, library(), 0.2, cap=True)
    x1 = np.concatenate([x0, np.zeros(len(layout(pal, True)) - len(x0))])
    x1[len(x0) + 2] = 0.0  # drift_hz at its low end (any value; no drift)
    varied = controller_params(decode(x1, pal, True), spec, library(), 0.2, cap=True)
    assert varied["variation"]["basis"]
    a, ea = _play(plain, spec, 20.0)
    b, eb = _play(varied, spec, 20.0)
    assert [e["name"] for e in ea] == [e["name"] for e in eb]
    assert np.allclose(a, b, atol=1e-6)


def test_variation_changes_the_movement_and_one_shots_keep_the_cap(body):
    _g, spec = body
    pal = palette_for(spec)
    x = np.random.default_rng(4).uniform(0, 1, len(layout(pal, True)))
    gen = decode(x, pal, True)
    ctrl = controller_params(gen, spec, library(), 0.2, cap=True)
    targets, eps = _play(ctrl, spec, 40.0)
    assert np.isfinite(targets).all()
    caps = {s["name"]: (s["duration"]["max_s"], s["one_shot"], s["period_s"], s["offset_s"]) for s in ctrl["states"]}
    for e in eps:
        cap, one_shot, period, offset = caps[e["name"]]
        if one_shot:  # whole cycles at their own tempo: within the cap, unless one slow cycle is longer
            rate_lo = math.exp(-gen["states"][e["name"]]["within"]["tempo"])
            assert e["planned_s"] <= max(cap, offset + period / rate_lo) + 1e-6
        else:
            assert e["planned_s"] <= cap + 1e-6
    assert all("blend_s" in e for e in eps)


def test_coverage_plays_the_extremes(body):
    _g, spec = body
    pal = palette_for(spec)
    gen = decode(np.full(len(layout(pal, True)), 0.5), pal, True)
    ctrl = controller_params(gen, spec, library(), 0.2, cap=True)
    plays = coverage_plan(gen, ctrl, {}, 3, 60.0, 0.05, 6.0, force_all=True)
    assert plays
    for pl in plays:
        v = pl["controller"]["variation"]
        st = {s["name"]: s for s in pl["controller"]["states"]}[pl["state"]]
        assert v["mode"] == "extremes" and v["extremes_state"] == pl["state"]
        assert 4 * v["step_s"] <= math.exp(st["duration"]["log_mean"]) + 1e-3  # all four corners within the state
    assert ctrl["variation"]["mode"] == "draw"  # the seeds draw


def test_variation_amount_is_zero_without_genes_and_grows_with_them(body):
    from calflab.evolve.diversity import variation_amount

    _g, spec = body
    pal = palette_for(spec)
    n0, n1 = len(layout(pal)), len(layout(pal, True))
    assert variation_amount(decode(np.full(n0, 0.5), pal)) == 0.0
    low = variation_amount(decode(np.concatenate([np.full(n0, 0.5), np.full(n1 - n0, 0.1)]), pal, True))
    high = variation_amount(decode(np.concatenate([np.full(n0, 0.5), np.full(n1 - n0, 0.6)]), pal, True))
    assert 0.0 < low < high <= 1.0
