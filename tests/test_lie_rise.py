"""lie_rise evolves per body (ADR-107): the primitive's new dims, today's motion bit for bit, determinism."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from calflab.plugins import load_plugins, registry

FINGERPRINT = Path(__file__).parent / "data" / "lie_rise_fingerprint_r13.json"


@pytest.fixture(scope="module", autouse=True)
def _plugins() -> None:
    load_plugins()


def _prim(params: dict | None = None):
    return registry.get("motion_primitive", "lie_rise")(params or {})


def _default_spec():
    from calflab.design import build_design, genome_definition

    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _payload() -> dict:
    from calflab.design import genome_definition
    from calflab.fitness.preset import EvaluationSettings

    g = genome_definition("feral_calf").default_genome()
    return {"genome": g.model_dump(mode="json"), "overrides": [], "generator": "feral_calf", "generator_params": {},
            "compile": {}, "evaluation": EvaluationSettings().model_dump(mode="json")}


# ---------------------------------------------------------------------------------------------- the default
def test_default_reproduces_todays_lie_rise_bit_for_bit() -> None:
    """Fingerprint written from commit 3d7c690 (before ADR-107): controller params, period, every pose and the
    rollout of the default body are identical."""
    from calflab.components import library
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    ref = json.loads(FINGERPRINT.read_text(encoding="utf-8"))
    lib = library()
    spec = _default_spec()
    key, params = _prim().controller(spec, lib)
    assert {"key": key, "params": params} == ref["controller"]
    assert _prim().period_s() == ref["period_s"]
    cm = compile_mjcf(spec, lib, CompileOptions(), 0)
    ro = run_rollout(cm, registry.get("controller", key)(params),
                     SimSettings(duration_s=12.5, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                                 stop_on_fall=False, seed=0), lib)
    h = hashlib.sha1()
    for a in (ro.t, ro.q, ro.dq, ro.torque, ro.body_pos, ro.body_quat):
        h.update(np.ascontiguousarray(a).tobytes())
    assert h.hexdigest() == ref["rollout_sha1"]
    ctrl = registry.get("controller", "feral_motion")({"mode": "lie_rise"})
    poses = [ctrl.pose_at(float(t)) for t in np.arange(0.0, 12.0, 0.01)]
    assert hashlib.sha1(json.dumps([sorted(p.items()) for p in poses]).encode()).hexdigest() == ref["pose_sha1"]


def test_moves_written_out_are_still_classic_and_general_path_agrees() -> None:
    """Every move's time written out as phase_s plays the classic path; the general path, forced, gives the same
    poses to rounding."""
    from calflab.control.feral_motion import (
        FeralMotionController,
        lie_rise_is_classic,
        lie_rise_pose,
    )

    P = FeralMotionController.Params
    written = P(mode="lie_rise", kneel_s=2.0, lie_s=2.0, rise_hind_s=2.0, reach_s=2.0, rise_front_s=2.0)
    assert lie_rise_is_classic(written)
    ctrl = registry.get("controller", "feral_motion")({"mode": "lie_rise"})
    for t in np.arange(0.0, 12.0, 0.05):
        a = ctrl.pose_at(float(t))
        b = lie_rise_pose(written, float(t))
        assert set(a) == set(b)
        assert max((abs(a[k] - b[k]) for k in a), default=0.0) < 1e-9


# ---------------------------------------------------------------------------------------------- contract of the dims
def test_lie_rise_dims_contract() -> None:
    """The new dims: fields of Params, inside the field's bounds, angles inside the joint ranges (less the 2 deg
    clearance); the primitive passes its plugin contract; the controller sends only what differs from today's."""
    import yaml
    from calflab.builtin.primitives import LieRisePrimitive
    from calflab.control.feral_motion import RANGE_CLEARANCE_DEG
    from calflab.paths import repo_root
    from calflab.plugins.contracts import check_plugin

    assert check_plugin(LieRisePrimitive) == []
    names = [d.name for d in LieRisePrimitive.vector_dims()]
    for want in ("kneel_shoulder", "kneel_carpus", "reach_shoulder", "reach_carpus", "kneel_s", "lie_s", "rise_hind_s",
                 "reach_s", "rise_front_s", "front_first", "rock_back_deg", "rock_s", "pause_mid_s", "pause_reach_s"):
        assert want in names
    assert len(names) == len(set(names))
    ranges = yaml.safe_load((repo_root() / "config" / "feral_calf.yaml").read_text(encoding="utf-8"))["joint_ranges_deg"]
    fields = LieRisePrimitive.Params.model_fields
    for d in LieRisePrimitive.vector_dims():
        f = fields[d.name]
        lo = next((m.ge for m in f.metadata if hasattr(m, "ge")), None)
        hi = next((m.le for m in f.metadata if hasattr(m, "le")), None)
        assert lo is not None and hi is not None and lo <= d.lo < d.hi <= hi, d
        joint = d.name.split("_")[-1]
        if joint in ranges:
            jlo, jhi = ranges[joint]
            assert jlo + RANGE_CLEARANCE_DEG <= d.lo and d.hi <= jhi - RANGE_CLEARANCE_DEG, d
    key, params = _prim({"kneel_carpus": 95.0, "pause_mid_s": 0.5}).controller(None, None)
    assert key == "feral_motion"
    assert params == {"mode": "lie_rise", "phase_s": 2.0, "hold_s": 1.5, "kneel_carpus": 95.0, "pause_mid_s": 0.5}


def test_moves_order_rock_pauses_and_period() -> None:
    from calflab.control.feral_motion import FeralMotionController
    from calflab.evolve.lie_rise import controller_params, length_s, moves

    hind = moves({"rock_back_deg": 10.0, "rock_s": 0.5, "pause_mid_s": 0.3, "pause_reach_s": 0.4, "kneel_s": 1.0})
    assert [m[0] for m in hind] == ["kneel", "lie", "hold", "rise hind", "pause", "rock back", "reach",
                                    "pause on hooves", "rise front"]
    assert hind[0][2] == 1.0 and hind[-1][2] == pytest.approx(length_s({"rock_back_deg": 10.0, "rock_s": 0.5,
                                                                         "pause_mid_s": 0.3, "pause_reach_s": 0.4,
                                                                         "kneel_s": 1.0}))
    front = moves({"front_first": 0.8})
    assert [m[0] for m in front] == ["kneel", "lie", "hold", "reach", "rise front", "rise hind"]
    # the rock folds the hind legs further, clipped inside their range (80 deg less 2)
    ctrl = registry.get("controller", "feral_motion")
    p = FeralMotionController.Params.model_validate(controller_params({"front_first": 0.8, "rock_back_deg": 20.0}))
    from calflab.control.feral_motion import lie_rise_pose

    t_reach = moves({"front_first": 0.8, "rock_back_deg": 20.0})[4][1]  # start of the reach = end of the rock
    pose = lie_rise_pose(p, t_reach, {"hl.stifle": (-30.0, 80.0), "hr.stifle": (-30.0, 80.0)})
    assert pose["hl.stifle"] == pytest.approx(78.0)
    assert pose["hl.hock"] == pytest.approx(95.0)  # no range given for the hock here: not clipped
    assert ctrl is not None


# ---------------------------------------------------------------------------------------------- determinism
def test_lie_rise_play_is_deterministic() -> None:
    """The same version on the same body and seed gives the same record."""
    from calflab.evolve.lie_rise import play_seed

    pay = _payload()
    v = {"kneel_s": 0.9, "lie_s": 0.9, "hold_s": 0.0, "rise_hind_s": 0.9, "reach_s": 0.9, "rise_front_s": 0.9,
         "pause_mid_s": 0.2}
    a = play_seed(pay, v, 1, 0.2, 0.2)
    b = play_seed(pay, v, 1, 0.2, 0.2)
    for k in ("margin", "within", "fell", "moves", "excess", "joints"):
        assert a[k] == b[k], k


def test_lie_rise_search_is_deterministic_whatever_the_play_order() -> None:
    """The CMA-ES loop with a synthetic play (a smooth function of the params): the same history twice, and with
    the plays handed out in another order, as workers would."""
    from calflab.evolve.lie_rise import LieRiseSearch, optimise

    def fake(job):
        p = job["params"]
        m = 0.3 - abs(p["kneel_carpus"] - 90.0) / 50.0 - 0.01 * job["seed"] - 0.05 * p.get("front_first", 0.0)
        return {"margin": m, "within": m >= 0, "fell": False, "excess": max(0.0, -m), "cached": False}

    def in_order(_fn, jobs):
        return [fake(j) for j in jobs]

    def backwards(_fn, jobs):
        return list(reversed([fake(j) for j in reversed(jobs)]))

    s = LieRiseSearch(popsize=6, generations=4)
    r1 = optimise(_payload(), [0, 1, 2], 0.2, s, map_fn=in_order)
    r2 = optimise(_payload(), [0, 1, 2], 0.2, s, map_fn=backwards)
    assert r1["history"] == r2["history"]
    assert r1["best"]["params"] == r2["best"]["params"]
    assert len(r1["history"]) == 1 + 6 * 4
    assert r1["best"]["worst"] >= r1["start"]["worst"]  # the search keeps today's if nothing beats it


@pytest.mark.slow
def test_lie_rise_real_search_is_deterministic() -> None:
    """A tiny real search (plays in physics) gives the same history twice, plays in another order."""
    from calflab.evolve.lie_rise import LieRiseSearch, optimise

    pay = _payload()
    s = LieRiseSearch(popsize=4, generations=1, settle_s=0.2,
                      starts=[{"kneel_s": 0.9, "lie_s": 0.9, "rise_hind_s": 0.9, "reach_s": 0.9, "rise_front_s": 0.9,
                               "hold_s": 0.0}])

    def backwards(fn, jobs):  # plays in reverse order, results returned in order
        return list(reversed([fn(j) for j in reversed(jobs)]))

    r1 = optimise(pay, [0], 0.2, s)
    r2 = optimise(pay, [0], 0.2, s, map_fn=backwards)
    assert r1["history"] == r2["history"]
    assert r1["best"]["params"] == r2["best"]["params"]
    assert len(r1["history"]) == 2 + 4
