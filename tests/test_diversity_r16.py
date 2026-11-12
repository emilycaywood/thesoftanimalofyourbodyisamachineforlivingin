"""R16 (ADR-112): outcome_motion version 2, the free outcome, MAP-Elites on one body, the r16 compare manifest."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest
from calflab.control.feral_motion import smooth
from calflab.control.outcome import OutcomeMotionController, from_feral_trot, from_feral_walk
from calflab.evolve import qd
from calflab.fitness.outcomes import CLASSES, FreeTask, classify, held_min


def _ctrl(**kw: float) -> OutcomeMotionController:
    return OutcomeMotionController(kw)  # type: ignore[arg-type]


def test_version_2_defaults_play_version_1() -> None:
    """With the new numbers at their defaults: the ramp is version 1's, no side offset, no pause in the keyframes."""
    c = _ctrl(**from_feral_trot(cycle_s=0.4, stride=2.0))
    for t in (0.0, 0.3, 0.9, 1.5, 4.0):
        assert c.envelope(t) == pytest.approx(smooth(t / 1.5))
        assert c.side_at(t) == {}
    k = _ctrl(p1_s=2.0, p1_stifle=10.0, p2_s=3.0, p2_hock=20.0)
    assert [d for _p, d in k.keyframes()] == [2.0, 3.0]
    # version 1's sweep factor was (1 - side x turn); stride 1 keeps it
    a = _ctrl(**from_feral_trot(), turn=0.4).rhythm_at(1.0, 0.4)
    b = _ctrl(**from_feral_trot(), turn=0.4, stride=1.0).rhythm_at(1.0, 0.4)
    assert a == b


def test_pauses_side_offsets_and_bouts() -> None:
    k = _ctrl(p1_s=2.0, p1_stifle=10.0, p1_hold_s=1.5, p2_s=3.0, p2_hock=20.0)
    assert [d for _p, d in k.keyframes()] == [2.0, 1.5, 3.0]
    assert k.posture_at(3.0)["hl.stifle"] == pytest.approx(10.0)  # still at keyframe 1 during its pause
    s = _ctrl(side_abd=6.0, side_s=1.0, side_from_s=2.0)
    assert s.side_at(1.0) == {}
    off = s.side_at(5.0)
    assert off["hl.hip_abd"] == pytest.approx(6.0) and off["hr.hip_abd"] == pytest.approx(-6.0)
    g = _ctrl(**from_feral_trot(ramp_s=0.0), bout_s=2.0, pause_s=1.0)
    assert g.envelope(1.0) == pytest.approx(1.0)
    assert g.envelope(2.5) == 0.0 and not any(g.rhythm_at(2.5, 0.0).values())
    late = _ctrl(**from_feral_trot(), gait_from_s=5.0)
    assert late.envelope(4.9) == 0.0 and late.envelope(8.0) == pytest.approx(1.0)


def test_turning_on_the_spot_sweeps_the_sides_opposite() -> None:
    c = _ctrl(**from_feral_walk(cycle_s=2.0, stride=0.0, turn=1.0), ramp_s=0.0)
    p = _ctrl(**from_feral_walk(cycle_s=2.0), ramp_s=0.0)
    t = 1.4  # both hind legs in stance (no lift): the left sweeps against the plain walk, the right with it
    a, b = c.rhythm_at(t, 1.0), p.rhythm_at(t, 0.0)
    assert a["hl.hock"] == pytest.approx(-b["hl.hock"]) and abs(b["hl.hock"]) > 0.1
    assert a["hr.hock"] == pytest.approx(b["hr.hock"])


def test_classes_and_held_levels() -> None:
    task = FreeTask()
    assert classify(0.45, 0.0, "stand", task) == "down"
    assert classify(0.7, 0.3, "trot", task) == "kneel"
    assert classify(0.95, 0.0, "pace", task) == "pace"
    assert classify(0.95, 0.0, "other", task) == "irregular"
    assert classify(0.8, 0.0, "stand", task) == "crouch"
    assert classify(0.95, 0.0, "stand", task) == "stand"
    x = np.ones(200)
    x[50:52] = 0.2  # a dip, not a level held for 1 s
    assert held_min(x, 0.02, 1.0) > 0.9
    x[100:160] = 0.4
    assert held_min(x, 0.02, 1.0) == pytest.approx(0.4)
    assert set(CLASSES) >= {"down", "stand", "trot", "walk", "pace", "bound"}


def test_grid_cells_and_descriptor() -> None:
    g = qd.Grid()
    assert g.size() == 9 * 7 * 5
    assert g.cell({"class": "trot", "speed": 544.0, "turn": 0.1}) == "trot|5|2"
    assert g.cell({"class": "stand", "speed": 0.0, "turn": -12.0}) == "stand|1|0"
    assert g.cell({"class": None, "speed": 0.0, "turn": 0.0}) is None
    assert g.label("trot|5|2") == "trot, brisk, straight"
    e = {"seeds": [{"outcome": {"d_class": "walk", "d_speed_mm_s": 10.0, "d_turn_deg_s": 1.0}},
                   {"outcome": {"d_class": "trot", "d_speed_mm_s": 20.0, "d_turn_deg_s": 2.0}},
                   {"outcome": {"d_class": "trot", "d_speed_mm_s": 30.0, "d_turn_deg_s": 3.0}}]}
    d = qd.descriptor(e)
    assert d == {"class": "trot", "speed": 20.0, "turn": 2.0, "agree": 0.67}


def test_parameters_snap_and_keep_defaults() -> None:
    sp = qd.free_space()
    base = qd.defaults()
    x = qd.to_x({}, sp.dims, base)
    p = qd.from_x(x, sp.dims)
    assert p["gait_amp"] == 0.0 and p["p2_s"] == 0.0 and p["side_s"] == 0.0 and p["bout_s"] == 0.0
    assert p["stride"] == pytest.approx(1.0) and p["cycle_s"] == pytest.approx(0.6)  # defaults, not the range ends
    t = qd.from_x(qd.to_x(from_feral_trot(cycle_s=0.4, stride=2.0), sp.dims, base), sp.dims)
    assert t["gait_amp"] == pytest.approx(1.0) and t["phase_fl"] == pytest.approx(0.5)


def test_mutation_is_deterministic_and_bounded() -> None:
    sp = qd.free_space()
    s = qd.QDSettings()
    a, b = np.full(len(sp.dims), 0.5), np.full(len(sp.dims), 0.9)
    r1, r2 = np.random.default_rng(3), np.random.default_rng(3)
    for _ in range(20):
        c1, o1 = qd.mutate(r1, a, b, sp.dims, s)
        c2, o2 = qd.mutate(r2, a, b, sp.dims, s)
        assert o1 == o2 and np.array_equal(c1, c2)
        assert c1.min() >= 0.0 and c1.max() <= 1.0


def _fake_map(fn, jobs):  # noqa: ANN001, ANN202 - a stand-in for the process pool: no simulation
    out = []
    for j in jobs:
        p = j["params"]
        amp = float(p.get("gait_amp", 0.0))
        safe = float(p.get("p1_stifle", 0.0)) < 40.0
        speed = 600.0 * amp * float(p.get("stride", 1.0))
        turn = 20.0 * float(p.get("turn", 0.0))
        cls = "stand" if amp == 0.0 else ("trot" if abs(float(p.get("phase_fl", 0.5)) - 0.5) < 0.2 else "irregular")
        o = {"d_class": cls, "d_speed_mm_s": speed, "d_turn_deg_s": turn, "score": -abs(amp) / 4 - 0.05,
             "gates": {"not_tipped": safe}, "holds": safe}
        out.append({"within": True, "margin": 0.5, "closest": None, "violations": [], "joints": {},
                    "complete": True, "sim_fell": False, "outcome": o, "length_s": 16.0, "binding": None,
                    "holds": safe, "wall_s": 0.0, "rank": 0.0, "cached": False})
    return out


def test_map_elites_fills_cells_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("calflab.evolve.outcomes.body_key", lambda payload: "fake")
    sp = qd.free_space()
    s = qd.QDSettings(iterations=4, batch=10, seed=1)
    starts = [{}, from_feral_trot(cycle_s=0.4, stride=2.0)]
    r1 = qd.run({}, sp, qd.Grid(), s, starts, 0.2, _fake_map, None)
    r2 = qd.run({}, sp, qd.Grid(), s, starts, 0.2, _fake_map, None)
    assert r1["cells"] >= 2 and sorted(r1["archive"]) == sorted(r2["archive"])
    assert "stand|1|2" in r1["archive"] and r1["tried"]["stand"]["held"] >= 1
    assert json.dumps(r1, default=float)  # JSON-able
    assert all(math.isfinite(h["wall_s"]) for h in r1["history"])


def test_r16_manifest(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    from calflab.app import diversity_compare as dc

    def rec(key: str, group: str, speed: float, holds: bool, run: str | None) -> dict:
        return {"key": key, "group": group, "source": "pilot", "descriptor": {"class": group, "speed": speed,
                                                                              "turn": 0.0, "agree": 1.0},
                "outcome": {"height_mean": 0.98, "height_low": 0.95, "gait": group, "effort_mean": 0.1,
                            "effort_max": 0.2, "worst": "hl.hip_abd", "gates": {"not_tipped": True}},
                "holds": holds, "within": holds, "same_cell": True, "binding": {"joint": "hl.stifle",
                                                                                "limit": "torque", "use": 1.3},
                "margin": 0.3 if holds else -0.3, "judged_s": 30.0, "run": run}

    f = tmp_path / "d.json"
    f.write_text(json.dumps({"mass_g": 2073.9, "shown": [rec("a", "trot", 540.0, True, "r1"),
                                                           rec("b", "stand", 0.0, True, "r2"),
                                                           rec("c", "trot", 300.0, False, None)]}), encoding="utf-8")
    monkeypatch.setitem(dc.DIVERSITY_SETS, "t", dc.DiversityCompareSet(key="t", title="T", study=str(f), body="b",
                                                                       views=3))
    monkeypatch.setattr(dc, "repo_root", lambda: tmp_path.parent)
    m = dc.diversity_manifest(None, "t")
    assert m["per_cell"] and [b["key"] for b in m["bodies"]] == ["v1", "v2", "v3"]
    assert [g["key"] for g in m["groups"]] == ["stand", "trot"]
    assert m["default_cells"][:2] == ["b", "a"]  # each group's fastest that holds first
    trot = m["groups"][1]["items"]
    assert [i["key"] for i in trot] == ["c", "a"]  # slowest first
    assert trot[1]["cells"][0]["seeds"][0]["badge"] == "within"
    assert trot[0]["cells"][0]["seeds"][0]["badge"] == "over" and trot[0]["cells"][0]["empty"]
    assert "trots forward" in trot[1]["cells"][0]["playing"]
    assert m["stored"] == 2 and m["missing"] == 1


def test_names() -> None:
    from calflab.app.diversity_compare import name

    assert name({"class": "trot", "speed": 2.0, "turn": 8.0}, {}) == "trots on the spot, turning left"
    assert name({"class": "walk", "speed": -40.0, "turn": 0.0}, {}) == "walks backward"
    assert name({"class": "stand", "speed": 0.0, "turn": 0.0}, {}) == "stands"
    assert name({"class": "down", "speed": 0.0, "turn": 0.0}, {"height_mean": 0.9}) == "goes down (and gets up again)"


def test_confirmation_and_the_posture_emitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("calflab.evolve.outcomes.body_key", lambda payload: "fake")
    sp = qd.free_space()
    s = qd.QDSettings(iterations=3, batch=10, seed=2, confirm=True, p_posture=0.5)
    seen: list[dict] = []

    def checkpoint(r: dict) -> None:
        seen.append(r)

    r = qd.run({}, sp, qd.Grid(), s, [{}, from_feral_trot(cycle_s=0.4, stride=2.0)], 0.2, _fake_map, None,
               checkpoint=checkpoint)
    assert len(seen) == 3 and seen[-1]["cells"] == r["cells"]
    assert all("judged" in e and e["judged"]["same_cell"] for e in r["archive"].values())
    assert r["tried"]["stand"]["confirmed"] >= 1
    x = np.full(len(sp.dims), 0.6)
    child, op = qd.posture_child(np.random.default_rng(0), x, sp.dims, s)
    names = [n for n, _lo, _hi in sp.dims]
    assert op == "posture" and child[names.index("gait_amp")] == 0.0
    rhythm = [i for i, n in enumerate(names) if qd.block_of(n) == "rhythm" and n != "gait_amp"]
    assert np.allclose(child[rhythm], 0.6)