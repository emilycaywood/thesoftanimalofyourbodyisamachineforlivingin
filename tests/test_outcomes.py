"""Behaviours from their outcome (ADR-110): the controller family, the scene and probes, the measures and their
gates (each cheat named in the study fails its gate), the preset, the search's ranking."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from calflab.plugins import load_plugins, registry


@pytest.fixture(scope="module", autouse=True)
def _plugins() -> None:
    load_plugins()


def _payload() -> dict:
    from calflab.design import genome_definition
    from calflab.fitness.preset import EvaluationSettings

    g = genome_definition("feral_calf").default_genome()
    return {"genome": g.model_dump(mode="json"), "overrides": [], "generator": "feral_calf", "generator_params": {},
            "compile": {}, "evaluation": EvaluationSettings().model_dump(mode="json")}


def _ctrl(params: dict | None = None):
    from calflab.plugins import ControlInfo

    c = registry.get("controller", "outcome_motion")(params or {})
    ids = ["joint.hl.hip_abd", "joint.hl.stifle", "joint.hl.hock", "joint.hr.hip_abd", "joint.hr.stifle",
           "joint.hr.hock", "joint.fl.shoulder", "joint.fl.carpus", "joint.fr.shoulder", "joint.fr.carpus"]
    c.reset(ControlInfo(actuator_ids=[i.replace("joint", "act") for i in ids], joint_ids=ids, rest=np.zeros(10),
                        lo=np.full(10, -3.0), hi=np.full(10, 3.0), control_dt=0.02, speed_limit=None))
    return c


# ---------------------------------------------------------------------------------------------- controller
def test_the_rhythm_plays_feral_motions_trot_as_a_warm_start() -> None:
    """from_feral_trot gives the same joint offsets as feral_motion's trot (the trot primitive's mapping)."""
    from calflab.control.outcome import from_feral_trot

    fm = registry.get("controller", "feral_motion")({"mode": "trot", "trot_cycle_s": 0.5, "trot_sweep_scale": 1.5,
                                                     "trot_lift_scale": 0.6})
    oc = _ctrl(from_feral_trot(cycle_s=0.5, stride=1.5, lift=0.6))
    for t in np.linspace(0.0, 4.0, 81):
        a, b = fm.pose_at(float(t)), oc.rhythm_at(float(t), 0.0)
        for k, v in a.items():
            if k.endswith("hip_abd"):
                continue
            assert b[k] == pytest.approx(v, abs=1e-9), (t, k)


def test_keyframes_hold_then_rise_back_to_standing() -> None:
    c = _ctrl({"p1_stifle": 40.0, "p1_s": 2.0, "p2_stifle": 70.0, "p2_carpus": 100.0, "p2_s": 3.0, "hold_s": 1.0,
               "rise_scale": 2.0})
    assert c.length_s() == pytest.approx(2 + 3 + 1 + 6 + 4)
    assert c.posture_at(2.0)["hl.stifle"] == pytest.approx(40.0)
    assert c.posture_at(5.5)["fr.carpus"] == pytest.approx(100.0)
    assert c.posture_at(12.0)["hl.stifle"] == pytest.approx(40.0)  # back at keyframe 1 after the first reverse move
    assert c.posture_at(99.0) == {}  # standing
    still = _ctrl({"p1_stifle": 10.0, "p1_s": 1.0})
    assert still.posture_at(50.0)["hr.stifle"] == pytest.approx(10.0)


def test_controller_dims_and_default_space_bounds() -> None:
    from calflab.control.outcome import OutcomeMotionController
    from calflab.evolve.outcomes import default_spaces

    fields = OutcomeMotionController.Params.model_fields
    for space in default_spaces().values():
        for name, lo, hi in space.dims:
            assert name in fields and lo < hi
        for name in space.fixed:
            assert name in fields


# ---------------------------------------------------------------------------------------------- scene and probes
def test_suckling_scene_measures_a_backward_force_on_the_pressing_head() -> None:
    """The head pressed into the block: the probe sees the block push the head back (-x), nothing else touches it."""
    from calflab.evolve.outcomes import default_spaces, play_seed

    space = default_spaces()["suckle"].model_copy(update={"search_s": 6.0, "task": {"press_from_s": 3.0}})
    rec = play_seed(_payload(), space, {"p1_s": 1.0, "p2_s": 1.0, "p2_shoulder": 12.0}, 0, 0.2)
    o = rec["outcome"]
    assert o["contact_frac"] > 0.5 and o["push_mean_n"] > 0.2
    assert o["other_peak_n"] == 0.0
    assert set(o["gates"]) == {"pressing", "steady", "no_slip", "not_propped", "not_leaning_down", "head_only",
                               "upright"}


def test_with_scene_leaves_a_model_without_probes_unchanged() -> None:
    from calflab.components import library
    from calflab.design import build_design, genome_definition
    from calflab.sim import compile_mjcf
    from calflab.sim.scene import Block, collision_geoms, with_scene

    spec = build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec
    cm = compile_mjcf(spec, library())
    assert cm.probes == []
    assert "head.mass" not in collision_geoms(cm)
    s = with_scene(cm, [Block(id="b", center_mm=(900.0, 0.0, 700.0))], ["head.mass"],
                   [{"id": "p", "geoms": ["head.mass"], "other": ["b"]}])
    assert "head.mass" in collision_geoms(s) and 'name="b"' in s.xml and s.probes[0]["id"] == "p"
    with pytest.raises(KeyError):
        with_scene(cm, [], ["no.such.geom"])


# ---------------------------------------------------------------------------------------------- measures: cheats
def _fake(z: np.ndarray, tilt_deg: np.ndarray | None = None, body_floor: np.ndarray | None = None,
          x: np.ndarray | None = None, feet: int = 4):
    """A rollout stub: trunk heights z (m) at 50 Hz from t = 0, standing height 0.6 m, 2 kg."""
    n = len(z)
    t = np.arange(n) * 0.02
    ang = np.radians(tilt_deg if tilt_deg is not None else np.zeros(n))
    q = np.zeros((n, 1, 4))
    q[:, 0, 0], q[:, 0, 2] = np.cos(ang / 2), np.sin(ang / 2)
    pos = np.zeros((n, 1, 3))
    pos[:, 0, 2] = z
    if x is not None:
        pos[:, 0, 0] = x
    pf = None
    if body_floor is not None:
        pf = np.zeros((n, 1, 3))
        pf[:, 0, 2] = body_floor
    ro = SimpleNamespace(t=t, body_ids=["trunk"], body_quat=q, body_pos=pos, impacts=[],
                         meta={"total_mass_kg": 2.0, "root_height": 0.6}, probe_ids=["body_floor"] if pf is not None
                         else [], probe_force=pf, foot_force=np.full((n, feet), 5.0),
                         foot_geoms=[f"leg.{k}.cannon.hoof" for k in ("hl", "hr", "fl", "fr")][:feet])
    spec = SimpleNamespace(root=SimpleNamespace(id="trunk"))
    return ro, spec


def test_a_crouch_does_not_count_as_lying_down() -> None:
    from calflab.fitness.outcomes import LieTask, measure_lie

    z = np.concatenate([np.linspace(0.6, 0.36, 300), np.full(300, 0.36)])  # 0.6 of standing
    ro, spec = _fake(z)
    assert not measure_lie(ro, spec, LieTask())["gates"]["lay_down"]
    z = np.concatenate([np.linspace(0.6, 0.27, 300), np.full(300, 0.27)])  # 0.45 of standing, slowly
    ro, spec = _fake(z, body_floor=np.where(z < 0.28, 19.6, 0.0))
    o = measure_lie(ro, spec, LieTask())
    assert o["holds"], o
    ro, spec = _fake(z, body_floor=np.zeros(len(z)))  # low enough, but held up on folded legs: a crouch
    assert not measure_lie(ro, spec, LieTask())["gates"]["resting"]


def test_a_drop_or_a_roll_onto_the_side_does_not_count_as_lying_under_control() -> None:
    from calflab.fitness.outcomes import LieTask, measure_lie

    z = np.concatenate([np.full(50, 0.6), np.full(5, 0.27), np.full(300, 0.27)])  # a drop
    ro, spec = _fake(z, body_floor=np.concatenate([np.zeros(52), np.full(3, 120.0), np.full(300, 19.6)]))
    g = measure_lie(ro, spec, LieTask())["gates"]
    assert not g["slow_descent"] and not g["soft_landing"]
    z = np.concatenate([np.linspace(0.6, 0.27, 300), np.full(300, 0.27)])
    ro, spec = _fake(z, tilt_deg=np.concatenate([np.zeros(300), np.full(300, 80.0)]))  # tipped onto its side
    assert not measure_lie(ro, spec, LieTask())["gates"]["not_tipped"]


def test_a_crouch_or_kneeling_does_not_count_as_standing() -> None:
    from calflab.fitness.outcomes import StandTask, measure_stand

    ro, spec = _fake(np.full(600, 0.45), body_floor=np.zeros(600))
    ro.actuator_ids = []
    spec.actuators, spec.transmissions, spec.metadata = [], [], {}
    assert not measure_stand(ro, spec, StandTask())["gates"]["standing"]
    ro, spec = _fake(np.full(600, 0.58), body_floor=np.full(600, 5.0))  # resting on the carpi
    ro.actuator_ids = []
    spec.actuators, spec.transmissions, spec.metadata = [], [], {}
    assert not measure_stand(ro, spec, StandTask())["gates"]["hooves_only"]


def test_support_margin_inside_and_outside() -> None:
    from calflab.fitness.outcomes import support_margin

    feet = np.array([[-0.25, 0.2], [-0.25, -0.2], [0.3, 0.18], [0.3, -0.18]])
    assert support_margin(np.array([0.0, 0.0]), feet) > 0.15
    assert support_margin(np.array([0.35, 0.0]), feet) < 0  # ahead of the front hooves: propped by the block
    assert support_margin(np.array([0.0, 0.0]), feet[:2]) == -np.inf


def test_footfall_labels_trot_walk_and_pace() -> None:
    from calflab.fitness.outcomes import footfall

    def ro_for(phases: dict[str, float], duty: float = 0.6, period: float = 0.5):
        t = np.arange(0, 10, 0.02)
        names = ["hl", "hr", "fl", "fr"]
        ff = np.stack([(((t / period) - phases[n]) % 1.0 >= 1 - duty) * 10.0 for n in names], 1)
        return SimpleNamespace(t=t, foot_force=ff, foot_geoms=[f"leg.{n}.cannon.hoof" for n in names])

    assert footfall(ro_for({"hl": 0, "fr": 0.05, "hr": 0.5, "fl": 0.55}), None, 1.0)["label"] == "trot"
    assert footfall(ro_for({"hl": 0, "fl": 0.25, "hr": 0.5, "fr": 0.75}), None, 1.0)["label"] == "walk"
    assert footfall(ro_for({"hl": 0, "fl": 0.0, "hr": 0.5, "fr": 0.5}), None, 1.0)["label"] == "pace"


# ---------------------------------------------------------------------------------------------- preset and rank
def test_preset_terms_and_settings() -> None:
    from calflab.evolve.outcomes import settings_from_preset
    from calflab.fitness.preset import preset

    s = settings_from_preset("outcomes_r15")
    assert s.mass_model == "explicit_v2" and s.margin == 0.2
    assert s.space("suckle").task["press_from_s"] == 6.0
    assert s.space("suckle").task["max_slip_mm"] == 30.0 and s.space("suckle").judge_s == 16.0  # variant A
    p = preset("outcomes_r15")
    out = {"suckle": {"holds": True, "within": True, "score": -0.15}, "trot": {"holds": False, "score": 900.0},
           "stand": {"holds": True, "within": True, "score": -0.05}, "lie": {}}
    r = p.evaluate({"outcome": out})
    assert r["terms"]["outcome_suckle"]["value"] == pytest.approx(-0.3)
    assert r["terms"]["outcome_trot"]["value"] == -1.0  # a fast trot that does not hold earns nothing
    assert r["terms"]["outcome_stand"]["value"] == pytest.approx(-0.1)
    assert r["terms"]["outcome_lie"]["value"] == -1.0


def test_rank_puts_a_failed_gate_below_any_held_version() -> None:
    from calflab.evolve.outcomes import rank

    held = {"outcome": {"score": 120.0, "gates": {"a": True}}, "margin": 0.05, "complete": True}
    fast_cheat = {"outcome": {"score": 400.0, "gates": {"a": False}}, "margin": 0.05, "complete": True}
    over = {"outcome": {"score": 400.0, "gates": {"a": True}}, "margin": -1.5, "complete": True, "within": False,
            "joints": {"fl.carpus": {"torque": 3.0, "speed": 0.5}}}
    assert rank("trot", held) > rank("trot", fast_cheat)
    assert rank("trot", fast_cheat) == pytest.approx(0.5 - 2.0)
    assert rank("trot", over) == pytest.approx(0.5 - 2.0 - 1.5 - 0.1 * 2.0)  # over a limit = a failed gate
    assert rank("trot", over) < rank("trot", held)
    fell = {**held, "complete": False}
    assert rank("trot", fell) < rank("trot", held) - 4.9


def test_slip_is_net_travel_not_jitter() -> None:
    from calflab.fitness.outcomes import slip_mm, slip_net_mm

    rng = np.random.default_rng(0)
    hp = np.zeros((400, 1, 3))
    hp[:, 0, :2] = rng.normal(0.0, 0.0003, (400, 2))  # 0.3 mm contact jitter
    load = np.ones((400, 1), bool)
    assert slip_mm(hp, load)[0] > 50.0  # the summed path grows with time
    assert slip_net_mm(hp, load)[0] < 2.0
    hp[:, 0, 0] += np.linspace(0.0, 0.015, 400)  # a real 15 mm slide
    assert slip_net_mm(hp, load)[0] > 14.0
