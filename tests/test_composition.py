"""Composition (ADR-078): clips chosen by affect tags, kinematic modulation, an affect curve, movement features,
and the composition study."""

from __future__ import annotations

import numpy as np
import pytest
from calflab.design import build_design, genome_definition
from calflab.project.motions import AffectTags, MotionClip


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _clip(name, arousal, words, amp=20.0, seconds=1.0, fps=20):
    n = int(seconds * fps)
    v = [amp * np.sin(2 * np.pi * i / n) for i in range(n)]
    return MotionClip(id=name, name=name, fps=fps, joints={"joint.fl.carpus": [max(0.0, x) for x in v],
                                                           "joint.hl.stifle": [0.3 * x for x in v]},
                      affect=AffectTags(arousal=arousal, words=words))


@pytest.fixture()
def library(tmp_path):
    from calflab.project.store import write_json

    d = tmp_path / "motions"
    d.mkdir()
    for c in (_clip("calm-paw", 0.1, ["calm"]), _clip("busy-paw", 0.9, ["agitated", "wary"], amp=35.0),
              _clip("untagged", None, [])):
        if c.id == "untagged":
            c.affect = None
        write_json(d / f"{c.id}.json", c.model_dump(mode="json"))
    return tmp_path


def _play(params, spec, project_dir, seed=0, seconds=30.0):
    from calflab.plugins import load_plugins, registry
    from calflab.plugins.types import ControlInfo, Observation

    load_plugins()
    cls = registry.get("controller", "behaviors")
    resolved = cls.resolve_params({**cls.Params().model_dump(mode="json"), **params}, project_dir)
    c = cls(resolved)
    acts = spec.actuators
    lim = [spec.joint(a.joint).range_deg for a in acts]
    info = ControlInfo(actuator_ids=[a.id for a in acts], joint_ids=[a.joint for a in acts], rest=np.zeros(len(acts)),
                       lo=np.radians([x[0] for x in lim]), hi=np.radians([x[1] for x in lim]), control_dt=0.02)
    c.reset(info, seed)
    n = len(acts)
    out = []
    for k in range(int(seconds / 0.02)):
        out.append(c.act(Observation(t=k * 0.02, q=np.zeros(n), dq=np.zeros(n), trunk_quat=np.array([1.0, 0, 0, 0]),
                                     trunk_gyro=np.zeros(3), foot_contact=np.ones(4))))
    return np.array(out), c.log()["episodes"], resolved, c


TAGGED = [{"name": "idle", "kind": "idle", "weight": 1.0},
          {"name": "paw", "kind": "clip", "select": {"words": []}, "weight": 1.0, "speed": [1.0, 1.0],
           "amplitude": [1.0, 1.0]}]


def test_clips_chosen_by_affect_tags(spec, library):
    _, eps, resolved, _ = _play({"repertoire": [{"name": "wary", "kind": "clip", "select": {"words": ["Wary"]}}]},
                                spec, library, seconds=5)
    assert resolved["pools"] == {"wary": ["busy-paw"]} and set(resolved["clips"]) == {"busy-paw"}
    assert {e["clip"] for e in eps} == {"busy-paw"}
    _, _, resolved, _ = _play({"repertoire": TAGGED}, spec, library, seconds=1)  # any tagged clip; untagged left out
    assert sorted(resolved["pools"]["paw"]) == ["busy-paw", "calm-paw"]
    with pytest.raises(ValueError, match="no clip in the motion library has the tags"):
        _play({"repertoire": [{"name": "x", "kind": "clip", "select": {"arousal": [0.4, 0.6]}}]}, spec, library)


def test_tempo_amplitude_stillness_and_phrasing(spec, library):
    base = {"repertoire": TAGGED, "blend_s": 0.0, "speed_fraction": 0.0}
    _, eps, _, _ = _play(base, spec, library, seed=3)
    _, fast, _, _ = _play({**base, "tempo": 2.0}, spec, library, seed=3)
    clip_eps = [e for e in eps if e["kind"] == "clip"]
    fast_eps = [e for e in fast if e["kind"] == "clip"]
    assert clip_eps and all(e["speed"] == pytest.approx(1.0) for e in clip_eps)
    assert fast_eps and all(e["speed"] == pytest.approx(2.0) for e in fast_eps)
    a1, _, _, c = _play({**base, "repertoire": [TAGGED[1]]}, spec, library, seed=1)
    a2, _, _, _ = _play({**base, "repertoire": [TAGGED[1]], "amplitude": 0.5}, spec, library, seed=1)
    assert np.max(np.abs(a2)) == pytest.approx(0.5 * np.max(np.abs(a1)), rel=0.02)
    _, still, _, _ = _play({**base, "idle_share": 0.9}, spec, library, seed=2, seconds=120)
    _, busy, _, _ = _play({**base, "idle_share": 0.1}, spec, library, seed=2, seconds=120)

    def idle_frac(e):
        return sum(1 for x in e if x["kind"] == "idle") / max(1, len(e))
    assert idle_frac(still) > 0.7 > 0.3 > idle_frac(busy)
    _, ph, _, _ = _play({**base, "pause_prob": 1.0, "repeat_prob": 0.5}, spec, library, seed=4)
    kinds = [e["kind"] for e in ph]
    assert "pause" in kinds and all(kinds[i] != "pause" or kinds[i + 1] != "pause" for i in range(len(kinds) - 1))
    names = [e["name"] for e in ph if e["kind"] != "pause"]
    assert any(a == b for a, b in zip(names, names[1:], strict=False))  # repeats happen
    assert all("composition" in e for e in ph)


def test_lowpass_smooths_commands(spec, library):
    base = {"repertoire": [TAGGED[1]], "speed_fraction": 0.0, "blend_s": 0.0}
    raw, _, _, _ = _play(base, spec, library, seconds=6)
    smooth, _, _, _ = _play({**base, "lowpass_hz": 1.0}, spec, library, seconds=6)

    def jerk(a):
        return float(np.sqrt(np.mean(np.diff(a, n=3, axis=0) ** 2)))
    assert jerk(smooth) < 0.5 * jerk(raw)


def test_affect_curve_moves_parameters_and_steers_tagged_clips(spec, library):
    curve = [{"t_s": 0, "label": "calm", "tempo": 0.5, "target_arousal": 0.1},
             {"t_s": 60, "label": "agitated", "tempo": 1.5, "target_arousal": 0.9}]
    params = {"repertoire": [{**TAGGED[1], "weight": 1.0}], "affect_curve": curve, "target_width": 0.2}
    _, eps, _, c = _play(params, spec, library, seconds=120)
    m = c.mod(30.0)
    assert m["tempo"] == pytest.approx(1.0) and m["target_arousal"] == pytest.approx(0.5) and m["label"] == "calm"
    early = [e["clip"] for e in eps if e["kind"] == "clip" and e["t0"] < 20]
    late = [e["clip"] for e in eps if e["kind"] == "clip" and e["t0"] > 70]
    assert early.count("calm-paw") > early.count("busy-paw") and late.count("busy-paw") > late.count("calm-paw")
    a, ea, _, _ = _play(params, spec, library, seed=7, seconds=20)
    b, eb, _, _ = _play(params, spec, library, seed=7, seconds=20)
    assert np.array_equal(a, b) and ea == eb  # seeded


def test_movement_features_of_a_known_motion(spec):
    from calflab.behave.descriptors import movement_features
    from calflab.behave.preview import preview_rollout

    fps, period = 50.0, 0.8
    n = int(4 * fps)
    clip = MotionClip(name="w", fps=fps, joints={"joint.fl.carpus": [20 + 20 * np.sin(2 * np.pi * i / (period * fps)) for i in range(n)]},
                      root_pos=[(i * 2.0, 0.0, spec.root.pos[2] * 0.9) for i in range(n)])
    r = preview_rollout(clip, spec)
    r.meta["actuator_joint"] = [a.joint for a in spec.actuators]
    f = movement_features(r, spec)
    assert f["tempo_s"] == pytest.approx(period / 2, abs=0.05)  # |speed| repeats twice a cycle
    assert f["tempo_regularity"] > 0.8 and f["approach_mm"] == pytest.approx((n - 1) * 2.0, rel=0.02)
    assert f["postural_height"] == pytest.approx(0.9, abs=0.01) and f["openness"] == pytest.approx(1.0, abs=0.01)
    still = preview_rollout(MotionClip(name="s", fps=fps, joints={"joint.fl.carpus": [0.0] * n}), spec)
    still.meta["actuator_joint"] = r.meta["actuator_joint"]
    fs = movement_features(still, spec)
    assert fs["stillness_ratio"] == 1.0 and f["stillness_ratio"] < 0.3
    assert "not emotions" in f["note"]


def test_composition_study_tabulates_features_tracking_and_safety(tmp_path, spec, library):
    import shutil

    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    shutil.copytree(library / "motions", project.path / "motions", dirs_exist_ok=True)
    lab = Lab.open(project.path, create=False)
    try:
        lab.execute("set_controller", {"key": "behaviors", "params": {"repertoire": TAGGED}})
        r = lab.execute("run_composition_study", {"compositions": [
            {"name": "busy", "params": {"idle_share": 0.0}}, {"name": "still", "params": {"idle_share": 1.0}}],
            "seeds": [0], "duration_s": 4.0})["result"]
        job = lab.jobs.wait(r["job"], 300)
        assert job.status == "done", job.error
        import json

        study = json.loads((project.path / "runs" / r["run_id"] / "composition_study.json").read_text(encoding="utf-8"))
        busy, still = study["rows"]
        assert busy["ok"] == still["ok"] == 1
        assert still["features"]["stillness_ratio"]["mean"] > busy["features"]["stillness_ratio"]["mean"]
        assert busy["clip_tracking_deg"] and not still["clip_tracking_deg"]
        keys = [c["key"] for c in study["runs"][0]["safety"]["constraints"]]
        assert {"servo_sustained", "stall", "belt_sustained", "belt_breaking", "joint_speed", "joint_limit"} <= set(keys)
        assert (project.path / "runs" / r["run_id"] / "composition_study.csv").is_file()
        assert lab.registry.get_run(r["run_id"]).kind == "composition"
    finally:
        lab.close()
