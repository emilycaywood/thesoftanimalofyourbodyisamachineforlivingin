"""Behaviors from reference footage (ADR-073): keypoints -> clips -> stochastic behaviors; and the trot (ADR-074)."""

from __future__ import annotations

import numpy as np
import pytest
from behave_fixtures import dlc_csv, paw_angles
from calflab.behave.feasibility import clip_report
from calflab.behave.keypoints import clean, parse_tracks
from calflab.behave.retarget import RetargetMap, load_map, retarget
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.project.motions import MotionClip


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


@pytest.fixture(scope="module")
def paw(spec):
    tracks = parse_tracks(dlc_csv(spec), 30.0, source="synthetic.csv")
    return retarget(tracks, load_map("feral_calf_side"), "paw", robot_height_mm=spec.root.pos[2])


# ---------------------------------------------------------------------- keypoints
def test_the_three_csv_layouts_read_the_same():
    long = "frame,keypoint,x,y,likelihood\n0,a,1,2,0.9\n0,b,3,4,0.9\n1,a,5,6,0.9\n1,b,7,8,0.8\n"
    wide = "frame,a_x,a_y,b_x,b_y\n0,1,2,3,4\n1,5,6,7,8\n"
    dlc = ("scorer,s,s,s,s,s,s\nbodyparts,a,a,a,b,b,b\ncoords,x,y,likelihood,x,y,likelihood\n"
           "0,1,2,0.9,3,4,0.9\n1,5,6,0.9,7,8,0.8\n")
    tracks = [parse_tracks(t, 25.0) for t in (long, wide, dlc)]
    for t in tracks:
        assert t.names == ["a", "b"] and t.frames == 2
        assert np.allclose(t.xy[1, 1], (7.0, -8.0))  # image y points down: flipped
    assert tracks[0].likelihood[1, 1] == pytest.approx(0.8)
    with pytest.raises(ValueError, match="Cannot tell the format"):
        parse_tracks("just,some\n1,2\n", 30.0)


def test_cleaning_fills_short_gaps_and_leaves_long_ones():
    xy = np.zeros((30, 1, 2))
    xy[:, 0, 0] = np.arange(30.0)
    lk = np.ones((30, 1))
    lk[5:7] = 0.1  # 2 frames
    lk[15:28] = 0.1  # 13 frames
    from calflab.behave.keypoints import KeypointTracks

    out, missing = clean(KeypointTracks(fps=30, names=["a"], xy=xy, likelihood=lk), max_gap_frames=10, smooth_frames=1)
    assert out.xy[6, 0, 0] == pytest.approx(6.0)
    assert np.isnan(out.xy[20, 0, 0]) and missing["a"] == pytest.approx(13 / 30)


# ---------------------------------------------------------------------- retargeting
def test_retargeting_gives_back_the_angles_the_footage_was_posed_with(paw):
    for j, tol in (("joint.fl.shoulder", 1.0), ("joint.hl.stifle", 1.0), ("joint.hl.hock", 1.0), ("joint.fl.carpus", 3.0)):
        want = np.array([paw_angles(f / 30.0)[j] for f in range(paw.frames)])
        assert np.max(np.abs(np.array(paw.joints[j]) - want)) < tol, j
    assert paw.joints["joint.fr.carpus"] == paw.joints["joint.fl.carpus"]  # far side copies the near one
    assert "joint.hl.hip_abd" not in paw.joints  # a side view cannot see ab/adduction
    assert paw.source == "footage" and paw.meta["footage"] == "synthetic.csv"


def test_half_cycle_far_side_needs_a_period(spec):
    tracks = parse_tracks(dlc_csv(spec, seconds=2.0), 30.0)
    m = load_map("feral_calf_side").model_copy(update={"far_side": "half_cycle"})
    with pytest.raises(ValueError, match="period_s"):
        retarget(tracks, m, "x")
    clip = retarget(tracks, m.model_copy(update={"period_s": 2.0}), "x")
    assert np.allclose(clip.joints["joint.hr.stifle"], np.roll(clip.joints["joint.hl.stifle"], 30))


def test_a_map_naming_landmarks_the_file_lacks_omits_those_joints(spec):
    tracks = parse_tracks(dlc_csv(spec, seconds=1.0), 30.0)
    m = RetargetMap(name="t", joints={"hl.stifle": {"flexion": ["hip", "stifle", "hock"]},
                                      "fl.carpus": {"flexion": ["elbow", "carpus", "fore_fetlock"]}})
    clip = retarget(tracks, m, "t")
    assert "joint.hl.stifle" in clip.joints and "joint.fl.carpus" not in clip.joints
    assert "fl.carpus" in clip.meta["retarget"]["omitted"]


# ---------------------------------------------------------------------- the body
def test_clip_report_says_what_the_body_can_play(paw, spec):
    r = clip_report(paw, spec, library())
    assert r["verdict"] in ("too_fast", "clamped_and_too_fast") and 0 < r["playable_speed"] < 1
    row = next(x for x in r["joints"] if x["joint"] == "joint.fl.carpus")
    assert row["speed_limit_deg_s"] == pytest.approx(270.27 / 2, abs=0.1)  # belted 2:1
    held = next(x for x in r["joints"] if x["joint"] == "joint.hl.hip_abd")
    assert held["in_clip"] is False
    slow = MotionClip(name="slow", fps=paw.fps / 3, joints=paw.joints)  # three times slower
    assert clip_report(slow, spec, library())["max_speed_ratio"] < r["max_speed_ratio"]


def test_preview_poses_the_body_and_clamps_to_ranges(paw, spec):
    from calflab.behave.preview import preview_rollout

    big = MotionClip(name="big", fps=30, joints={"joint.fl.carpus": [0.0, 500.0]})
    r = preview_rollout(big, spec)
    i = r.joint_ids.index("joint.fl.carpus")
    assert np.degrees(r.q[1, i]) == pytest.approx(spec.joint("joint.fl.carpus").range_deg[1], abs=1e-3)
    rp = preview_rollout(paw, spec)
    assert rp.n_frames == paw.frames and rp.meta["kinematic_preview"]


# ---------------------------------------------------------------------- stochastic behaviors
def _info(spec):
    from calflab.plugins.types import ControlInfo

    acts = spec.actuators
    lim = [spec.joint(a.joint).range_deg for a in acts]
    return ControlInfo(actuator_ids=[a.id for a in acts], joint_ids=[a.joint for a in acts], rest=np.zeros(len(acts)),
                       lo=np.radians([x[0] for x in lim]), hi=np.radians([x[1] for x in lim]), control_dt=0.02)


def _play(params, spec, seed, seconds=30.0):
    from calflab.plugins import load_plugins, registry
    from calflab.plugins.types import Observation

    load_plugins()
    c = registry.get("controller", "behaviors")(params)
    c.reset(_info(spec), seed)  # type: ignore[attr-defined]
    n = len(spec.actuators)
    out = []
    for k in range(int(seconds / 0.02)):
        obs = Observation(t=k * 0.02, q=np.zeros(n), dq=np.zeros(n), trunk_quat=np.array([1.0, 0, 0, 0]),
                          trunk_gyro=np.zeros(3), foot_contact=np.ones(4))
        out.append(c.act(obs))  # type: ignore[attr-defined]
    return np.array(out), c.log()["episodes"]  # type: ignore[attr-defined]


def test_behaviors_are_random_but_seeded(spec):
    a, ea = _play({}, spec, 1)
    b, eb = _play({}, spec, 1)
    c, ec = _play({}, spec, 2)
    assert np.array_equal(a, b) and ea == eb
    assert [e["name"] for e in ea] != [e["name"] for e in ec] or not np.array_equal(a, c)


def test_clips_play_with_variation_mirroring_and_transitions(paw, spec):
    params = {
        "repertoire": [
            {"name": "paw", "kind": "clip", "clip": "paw", "speed": [0.5, 0.7], "amplitude": [0.5, 0.5], "mirror": True},
            {"name": "rest", "kind": "idle", "duration_s": [1.0, 1.0]},
        ],
        "transitions": {"paw": {"rest": 1.0}, "rest": {"paw": 1.0}},
        "start": "paw",
        "clips": {"paw": {"fps": paw.fps, "joints": paw.joints}},
        "speed_fraction": 0.0,
        "blend_s": 0.0,
    }
    out, eps = _play(params, spec, 0, seconds=20.0)
    names = [e["name"] for e in eps]
    assert names[:4] == ["paw", "rest", "paw", "rest"]  # the transition table alternates them
    assert all(0.5 <= e["speed"] <= 0.7 for e in eps if e["name"] == "paw")
    assert any(e["mirror"] for e in eps if e["name"] == "paw") and any(not e["mirror"] for e in eps if e["name"] == "paw")
    # amplitude 0.5: the carpus never goes past half the clip's largest flexion
    i = [a.joint for a in spec.actuators].index("joint.fl.carpus")
    assert np.degrees(out[:, i].max()) <= 0.5 * max(paw.joints["joint.fl.carpus"]) + 1e-6


def test_a_clip_the_library_lacks_is_refused(tmp_path):
    from calflab.control.behaviors import BehaviorsController

    with pytest.raises(ValueError, match="not in the project's motion library"):
        BehaviorsController.resolve_params({"repertoire": [{"name": "x", "kind": "clip", "clip": "nope"}]}, tmp_path)


def test_imitation_scores_joint_tracking():
    from calflab.plugins import load_plugins, registry

    load_plugins()
    term = registry.get("fitness_term", "imitation")({"scale_deg": 10.0})
    assert not term.stub
    assert term.evaluate({"tracking_rms_deg": 0.0}, {}) == pytest.approx(1.0)  # type: ignore[attr-defined]
    assert term.evaluate({"tracking_rms_deg": 10.0}, {}) == pytest.approx(np.exp(-1.0))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------- the lab
def test_footage_to_simulated_behaviors_in_a_project(tmp_path, spec):
    from calflab.app import Lab
    from calflab.app.lab import LabError
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    (project.path / "footage").mkdir(exist_ok=True)
    (project.path / "footage" / "paw.csv").write_text(dlc_csv(spec), encoding="utf-8")
    lab = Lab.open(project.path, create=False)
    try:
        with pytest.raises(LabError, match="No file"):
            lab.execute("import_footage", {"file": "missing.csv"})
        out = lab.execute("import_footage", {"file": "paw.csv", "fps": 30})["result"]
        assert out["clip"] == "paw" and out["body"]["verdict"] in ("too_fast", "clamped_and_too_fast")
        view = lab.analysis("behave")
        assert [c["id"] for c in view["clips"]] == ["paw"] and view["footage"] == ["paw.csv"]
        assert any(m["name"] == "feral_calf_side" for m in view["maps"])
        prev = lab.execute("preview_clip", {"clip": "paw"})["result"]
        assert lab.registry.get_run(prev["run_id"]).kind == "clip"
        lab.execute("set_controller", {"key": "behaviors", "params": {"repertoire": [
            {"name": "paw", "kind": "clip", "clip": "paw", "speed": [0.5, 0.6]},
            {"name": "stand", "kind": "idle", "duration_s": [1.0, 2.0]}]}})
        assert lab.state.graph.role("controller").type == "controller:behaviors"
        sim = lab.state.graph.role("simulation").id
        lab.execute("set_node_params", {"node": sim, "params": {"duration_s": 6.0}})
        job = lab.jobs.wait(lab.run_sim().id, timeout=300)
        assert job.status == "done", getattr(job, "error", None)
        r = lab.load_rollout(job.result["run_id"])
        assert [e["name"] for e in r.meta["controller_log"]["episodes"]]
        assert lab.registry.get_run(job.result["run_id"]).metrics["tracking_rms_deg"] >= 0
        lab.undo()
        assert lab.state.graph.role("controller").type == "controller:behaviors"  # undid the duration only
        lab.undo()
        assert lab.state.graph.role("controller").type == "controller:feral_motion"
    finally:
        lab.close()


# ---------------------------------------------------------------------- the trot (ADR-074)
def test_trot_moves_diagonal_pairs_together_within_servo_speed(spec):
    from calflab.mech.compare import run_scenario
    from calflab.sim.metrics import compute_metrics

    r, used, cycle = run_scenario(spec, library(), "trot")
    m = compute_metrics(r)
    assert not m["fell"] and m["speed_mps"] > 0.15 and cycle == used["trot_cycle_s"]
    assert m["speed_margin_min"] > 0  # commanded speed stays under the servos' (rate limit)


# ---------------------------------------------------------------------- choosing the controller (ADR-075)
def test_switching_controllers_keeps_each_ones_settings(tmp_path):
    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    lab = Lab.open(project.path, create=False)
    try:
        ctrl = lab.state.graph.role("controller")
        lab.execute("set_node_params", {"node": ctrl.id, "params": {"mode": "trot", "trot_cycle_s": 0.7}})
        lab.execute("set_controller", {"key": "behaviors"})
        node = lab.state.graph.role("controller")
        assert node.type == "controller:behaviors"
        lab.execute("set_node_params", {"node": node.id, "params": {"blend_s": 1.2}})
        lab.execute("set_controller", {"key": "feral_motion"})
        node = lab.state.graph.role("controller")
        assert node.params["mode"] == "trot" and node.params["trot_cycle_s"] == 0.7  # as it was left
        lab.execute("set_controller", {"key": "behaviors"})
        assert lab.state.graph.role("controller").params["blend_s"] == 1.2
        lab.undo()
        assert lab.state.graph.role("controller").type == "controller:feral_motion"
        choices = {c["key"]: c["fits"] for c in lab.graph_view()["controllers"]}
        assert choices["feral_motion"] and choices["behaviors"] and not choices["cpg"]  # the CPG drives the old calf
    finally:
        lab.close()
