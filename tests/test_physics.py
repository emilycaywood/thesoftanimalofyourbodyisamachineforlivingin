"""Clips judged in physics (ADR-084): the torque-speed envelope, the safety margin, planted hooves, the
feasible-version search, and the jobs that expose them."""

from __future__ import annotations

import time

import numpy as np
import pytest
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.project.motions import MotionClip


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _base():
    from calflab.plugins import load_plugins, registry

    load_plugins()
    return registry.get("controller", "behaviors").Params().model_dump(mode="json")


def _clip(name, joints, fps=20.0):
    return MotionClip(id=name, name=name, fps=fps, joints={k: [float(x) for x in v] for k, v in joints.items()})


def _sway(n=30, amp=12.0):
    """A slow sway: the trunk lowered and raised by the hind legs, the front shoulders swinging a little."""
    w = 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / n))
    return {"joint.hl.stifle": amp * w, "joint.hr.stifle": amp * w, "joint.hl.hock": 0.8 * amp * w,
            "joint.hr.hock": 0.8 * amp * w, "joint.fl.shoulder": 0.5 * amp * w, "joint.fr.shoulder": -0.3 * amp * w}


# ---------------------------------------------------------------------- the envelope
def test_envelope_is_stall_at_rest_and_zero_at_no_load():
    from calflab.sim.servo import available_torque, envelope_use

    stall, w0 = np.array([2.0]), np.array([4.0])
    for w, (hi, lo) in [(0.0, (2.0, -2.0)), (2.0, (1.0, -2.0)), (-2.0, (2.0, -1.0)), (4.0, (0.0, -2.0)), (6.0, (0.0, -2.0))]:
        h, low = available_torque(np.array([w]), stall, w0)
        assert (float(h[0]), float(low[0])) == pytest.approx((hi, lo)), w
    # driving at half speed with half stall is on the curve; braking only counts torque
    assert float(envelope_use(np.array([1.0]), np.array([2.0]), stall, w0)[0]) == pytest.approx(1.0)
    assert float(envelope_use(np.array([-1.0]), np.array([2.0]), stall, w0)[0]) == pytest.approx(0.5)


def test_torque_speed_servo_holds_joint_speed_to_no_load(spec):
    """A clip that asks for a fast shoulder swing: with the torque-speed servo no joint drives faster than its
    servo's no-load speed (at the joint); with torque alone the shoulder goes well past it."""
    from calflab import units as u
    from calflab.behave import physics

    n = 24
    sw = np.where((np.arange(n) // 4) % 2 == 0, 35.0, -35.0)  # a square wave: as fast as the servo can go
    clip = _clip("fast", {"joint.fl.shoulder": sw, "joint.fr.shoulder": -sw}, fps=20.0)
    s = physics.PhysicsSettings(command_speed_fraction=0.0, lead_in_s=0.4, return_s=0.4, hold_s=0.0)
    peak = {}
    for model in ("torque", "torque_speed"):
        doc = {"servo_model": model}
        ro, timing, _ = physics.play(clip, spec, library(), _base(), doc, s)
        if model == "torque":  # play() always uses the torque-speed servo; compile the comparison by hand
            from calflab.plugins import registry
            from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

            pb, timing = physics.playback_clip(clip, spec, s)
            cm = compile_mjcf(spec, library(), CompileOptions(torque_derating=1.0, servo_model="torque"))
            ctrl = registry.get("controller", "behaviors")(physics.controller_params(_base(), pb, s))
            ro = run_rollout(cm, ctrl, SimSettings(duration_s=timing["end_t"], settle_s=0.4, stop_on_fall=True), library())
        m = (ro.t >= timing["clip_t0"]) & (ro.t < timing["clip_t1"])
        if ro.meta.get("fell"):
            m &= ro.t < float(ro.meta["fall_time"]) - 0.1
        k = ro.actuator_ids.index("act.fl.shoulder")
        lim = float(ro.meta["speed_limit"][k])
        peak[model] = float(np.max(np.abs(ro.dq[m, k]))) / lim
    assert peak["torque_speed"] <= 1.02, peak
    assert peak["torque"] > 1.2, peak
    assert u.rad_to_deg(lim) == pytest.approx(270.27, rel=0.01)  # 45.045 rpm at the shoulder (direct drive)


def test_torque_model_default_is_unchanged(spec):
    """The default servo model is torque only, and the explicit setting gives the same rollout bit for bit."""
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    assert CompileOptions().servo_model == "torque"
    out = []
    for opts in (CompileOptions(), CompileOptions(servo_model="torque")):
        cm = compile_mjcf(spec, library(), opts, 0)
        r = run_rollout(cm, registry.get("controller", "feral_motion")(), SimSettings(duration_s=1.0, seed=2), library())
        out.append(r)
    assert np.array_equal(out[0].body_pos, out[1].body_pos)
    assert np.array_equal(out[0].torque, out[1].torque)
    assert "servo_model" not in out[0].meta or out[0].meta["servo_model"] == "torque"


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["trot", "walk"])
def test_own_gaits_stand_under_both_servo_models(spec, mode):
    """The body's own gaits balance by timing on two or three hooves, under the torque and the torque-speed servo:
    falling slowed clips (ADR-084) are not a limit of the body."""
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout

    load_plugins()
    for model in ("torque", "torque_speed"):
        cm = compile_mjcf(spec, library(), CompileOptions(torque_derating=1.0, servo_model=model), 0)
        ctrl = registry.get("controller", "feral_motion")({"mode": mode})
        r = run_rollout(cm, ctrl, SimSettings(duration_s=10.0, seed=0), library())
        assert not compute_metrics(r)["fell"], (mode, model)
        down = (r.foot_force[r.t >= 0] > 1.0).sum(axis=1)
        assert float(np.mean(down < 3)) > 0.3, (mode, model)  # it really is on fewer than three hooves often


# ---------------------------------------------------------------------- the margin
def test_safety_margin_scales_every_limit(spec):
    from calflab.behave import physics
    from calflab.evolve.safety import SafetyPolicy, safety_report

    clip = _clip("sway", _sway())
    ro, _timing, _ = physics.play(clip, spec, library(), _base(), {}, physics.PhysicsSettings(margin=0.0))
    plain = {c["key"]: c for c in safety_report(ro, spec, library(), SafetyPolicy(margin=0.0))["constraints"]}
    kept = {c["key"]: c for c in safety_report(ro, spec, library(), SafetyPolicy(margin=0.2))["constraints"]}
    # instantaneous limits: value / limit, the limit x (1 - margin)
    for key in ("stall", "joint_speed", "envelope"):
        assert kept[key]["limit"] == pytest.approx(0.8 * plain[key]["limit"]), key
        assert kept[key]["value"] == pytest.approx(plain[key]["value"]), key
    assert kept["belt_breaking"]["limit"] == pytest.approx(0.8 * plain["belt_breaking"]["limit"])
    # sustained limits: the threshold falls, so the share of the window above it can only grow
    for key in ("servo_sustained", "belt_sustained"):
        assert kept[key]["limit"] == pytest.approx(plain[key]["limit"])
        assert kept[key]["value"] >= plain[key]["value"] - 1e-9, key
    assert kept["fall"]["limit"] == plain["fall"]["limit"]  # a fall is not scaled
    assert SafetyPolicy().margin == 0.0  # earlier runs are judged as before


# ---------------------------------------------------------------------- planting
def test_plant_keeps_supporting_hooves_and_centre_of_mass(spec):
    """Synthetic poses that lift the left fore hoof while the body sways: after planting, every hoof that
    supports in two frames moves by less than 3 mm between them, at least three hooves support, and the centre of
    mass is inside the support polygon, all checked with the body's own kinematics from the solved trunk."""
    from calflab.behave import stance

    n = 30
    w = 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / n))
    lift = np.where((np.arange(n) >= 10) & (np.arange(n) < 20), 1.0, 0.0)
    joints = {"joint.fl.shoulder": 15 * w, "joint.fl.carpus": 70 * lift, "joint.fr.shoulder": 10 * w,
              "joint.hl.stifle": 10 * w, "joint.hr.stifle": -8 * w, "joint.hl.hip_abd": 6 * w,
              "joint.hl.hock": 8 * w}
    clip = _clip("lift", joints)
    planted, info = stance.plant(clip, spec, library(), stance.StanceSettings(min_support=3))
    assert info["applied"] and planted is not clip and clip.joints["joint.fl.carpus"][15] == pytest.approx(70.0)
    assert info["support"][15][2] == "."  # the left fore hoof swings while lifted
    assert all(s.count("X") >= 3 for s in info["support"])
    assert planted.meta["stance_paths"]["lead_in"] and planted.meta["stance_paths"]["return"]
    ids = [a.joint for a in spec.actuators if a.joint in planted.joints]
    kin = stance._Kinematics(spec, library(), ids)
    rest = spec.rest_angles()
    from calflab import units as u

    prev = None
    for f in range(n):
        q = np.array([u.deg_to_rad(rest[j] + planted.joints[j][f]) for j in ids])
        tp = np.array(info["trunk_pose"][f])
        h, com = kin.pose(tp[:3], tp[3:], q)
        down = [k for k in range(4) if info["support"][f][k] == "X"]
        assert all(abs(h[k, 2]) < 0.003 for k in down), (f, h[:, 2])
        assert all(h[k, 2] > -0.003 for k in range(4))
        poly = stance._hull(h[down, :2])
        assert stance.outside(com[:2], poly, 0.0) < 0.001, f
        if prev is not None:
            for k in down:
                if info["support"][f - 1][k] == "X":
                    assert np.linalg.norm(h[k, :2] - prev[k, :2]) < 0.003, (f, k)
        prev = h
    assert max(info["slip_after_mm"].values()) < 3.0
    assert info["com_outside_after_fraction"] == 0.0


# ---------------------------------------------------------------------- the search
def test_adapt_one_round_records_every_step(spec):
    """One round of the search on a short clip: the raw and planted starting points and one remedy, every step
    with its operations, and the clip itself untouched."""
    from calflab.behave import adapt, physics

    raw = _clip("brisk", {k: 3.0 * v for k, v in _sway(n=10, amp=14.0).items()}, fps=20.0)
    before = raw.model_dump()
    s = physics.PhysicsSettings(margin=0.2, lead_in_s=0.4, return_s=0.4, hold_s=0.0)

    def play(c):
        ro, timing, _ = physics.play(c, spec, library(), _base(), {}, s)
        return ro, physics.report(ro, c, spec, library(), timing, 0.2)

    st = adapt.AdaptSettings(max_rounds=1, give_back_rounds=0, max_slowdown=2.0)
    res = adapt.adapt(raw, spec, library(), play, st)
    assert raw.model_dump() == before
    assert [x["round"] for x in res["steps"]][:2] == [0, 0]
    assert all("operations" in x for x in res["steps"])
    assert "planted" in res["steps"][1]["operations"]
    assert res["adapted"]["clip"].meta["stance"]["settings"]["min_support"] in (3, 4)


@pytest.mark.slow
def test_adapt_finds_a_version_within_the_limits(spec):
    from calflab.behave import adapt, physics

    raw = _clip("brisk", {k: 3.0 * v for k, v in _sway(n=16, amp=14.0).items()}, fps=20.0)
    s = physics.PhysicsSettings(margin=0.2, lead_in_s=0.6, return_s=0.6, hold_s=0.2)

    def play(c):
        ro, timing, _ = physics.play(c, spec, library(), _base(), {}, s)
        return ro, physics.report(ro, c, spec, library(), timing, 0.2)

    t0 = time.perf_counter()
    res = adapt.adapt(raw, spec, library(), play, adapt.AdaptSettings(max_rounds=8, give_back_rounds=1))
    assert raw.joints["joint.hl.stifle"][8] == pytest.approx(3.0 * _sway(n=16, amp=14.0)["joint.hl.stifle"][8])
    assert all("operations" in st and "badness" in st for st in res["steps"])
    assert res["steps"][1]["operations"].count("planted") == 1  # the kinematic start is planted
    best = res["adapted"]
    assert best["badness"] <= res["raw"]["badness"]
    if res["feasible"]:
        assert best["report"]["within_limits"] and not best["report"]["fell"]
    clip = best["clip"]
    assert clip.meta["adapted_operations"]["plant"] is True and "stance" in clip.meta
    assert 0.0 < best["character"]["score"] <= 1.0
    assert time.perf_counter() - t0 < 120


def test_operations_are_applied_in_order(spec):
    from calflab.behave import adapt

    raw = _clip("c", {"joint.hl.stifle": [0.0, 40.0, 80.0, 40.0], "joint.hr.stifle": [0.0] * 4})
    ops = adapt.Operations(time_scale=2.0, amplitude={"joint.hl.stifle": 0.5}, range_margin_deg=5.0)
    out = adapt.apply(raw, ops, spec)
    lo, hi = spec.joint("joint.hl.stifle").range_deg
    r = spec.rest_angles()["joint.hl.stifle"]
    assert out.fps == pytest.approx(raw.fps / 2)
    assert out.joints["joint.hl.stifle"][1] == pytest.approx(min(20.0, hi - r - 5.0))
    assert max(out.joints["joint.hl.stifle"]) <= hi - r - 5.0 + 1e-9
    assert raw.joints["joint.hl.stifle"] == [0.0, 40.0, 80.0, 40.0]
    assert "planted" in adapt.Operations(plant=True).describe()
    with pytest.raises(ValueError):
        adapt.apply(raw, adapt.Operations(plant=True), spec)  # planting needs the library


# ---------------------------------------------------------------------- jobs and runs
@pytest.fixture()
def lab(tmp_path):
    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    lab = Lab.open(project.path, create=False)
    yield lab
    lab.close()


def _wait(lab, job_id, timeout=240.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        j = next(j for j in lab.jobs.list() if j["id"] == job_id)
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@pytest.mark.slow
def test_play_and_adapt_jobs_leave_runs_and_a_new_clip(lab):
    clip = lab.motions.save(_clip("sway", _sway(n=20)))
    original = lab.motions.get(clip.id).model_dump()
    r = lab.execute("play_in_physics", {"clip": clip.id, "margin": 0.2})["result"]
    j = _wait(lab, r["job"])
    assert j["status"] == "done", j
    view = lab.execute("physics_report", {"run": j["result"]["run_id"]})["result"]
    assert view["kind"] == "physics" and view["report"]["joints"] and view["report"]["constraints"]
    assert view["basis"]["servos"]["sts3215_c018"]["missing"] == ["stall_current_a"]
    assert view["basis"]["servos"]["sts3215_c018"]["armature_default"] is True
    rec = lab.registry.get_run(j["result"]["run_id"])
    assert rec.kind == "physics" and rec.git_hash is not None and "rollout" in rec.artifacts
    assert lab.rollout_payload(rec.id)["t"]

    r = lab.execute("adapt_clip", {"clip": clip.id, "margin": 0.2, "settings": {"max_rounds": 2, "give_back_rounds": 0}})["result"]
    j = _wait(lab, r["job"])
    assert j["status"] == "done", j
    view = lab.execute("physics_report", {"run": r["run_id"]})["result"]
    assert view["kind"] == "adapt" and view["compare"]["raw"] and view["compare"]["adapted"]
    assert view["saved_clip"] == f"{clip.id}-feasible"
    new = lab.motions.get(view["saved_clip"])
    assert new.meta["adapted_from"] == clip.id and new.meta["adapted_operations"]["plant"] is True
    assert "stance" in new.meta and new.meta["margin"] == 0.2
    assert lab.motions.get(clip.id).model_dump() == original  # never changed
    raw_run = lab.registry.get_run(view["raw_run"])
    assert raw_run.kind == "physics" and raw_run.parent == r["run_id"]
    from calflab.app.lab import LabError

    with pytest.raises(LabError):
        lab.execute("keep_adapted_clip", {"run": r["run_id"]})  # already saved
