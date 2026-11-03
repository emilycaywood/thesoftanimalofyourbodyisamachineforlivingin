"""The 3D lift (ADR-080): the robot's own skeleton and a camera fitted to 2D keypoints from one camera.

Synthetic footage is the robot's own forward kinematics seen from a camera at a known yaw and elevation,
with hip ab/adduction, a slow turn, noise and dropped points (``synthetic_tracks_3d``). Tolerances, on the
frames the lift calls reliable: joint angles within 2.5 deg RMS (hip ab/adduction too, where the
view shows it), heading within 1.5 deg RMS, camera elevation within 1.5 deg, segment ratios within 3 %.
Frames turned more than 75 deg from a side view (toward head-on or tail-on) must be unreliable.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pytest
from calflab.behave import inbox
from calflab.behave.lift import Skeleton, cut_lift, lift, lift_clip, load_lift_map
from calflab.behave.synthetic import Camera3D, Script3D, synthetic_tracks_3d
from calflab.design import build_design, genome_definition


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _rms(res, truth, joints):
    rel = res.reliable()
    return {j: float(np.sqrt(np.mean((np.asarray(res.joints_deg[j]) - truth["joints_deg"][j])[rel] ** 2)))
            for j in joints}


def _heading_rms(res, truth):
    e = (np.asarray(res.heading_deg) - truth["heading_deg"] + 180.0) % 360.0 - 180.0
    return float(np.sqrt(np.mean(e[res.reliable()] ** 2)))


def test_the_skeleton_is_the_robots_forward_kinematics(spec):
    m = load_lift_map("feral_calf_3d")
    sk = Skeleton(spec, m)
    rng = np.random.default_rng(1)
    d = rng.uniform(sk.free_lo, sk.free_hi)
    pts = sk.points(d[None], sk.initial_globals())[0]
    full = sk.full_angles(d[None])[0]
    angles = {j: float(np.rad2deg(full[k])) for k, j in enumerate(sk.joint_ids)}
    poses = spec.world_poses(angles, root_pos=(0.0, 0.0, 0.0))
    for name, body in (("L_hip", "leg.hl.femur"), ("R_stifle", "leg.hr.tibia"), ("L_hock", "leg.hl.cannon"),
                       ("R_carpus", "leg.fr.cannon")):
        assert np.allclose(pts[sk.names.index(name)], poses[body][0], atol=1e-6)


def test_lift_recovers_angles_heading_and_camera_at_30_deg(spec):
    m = load_lift_map("feral_calf_3d")
    tracks, truth = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=30.0, elevation_deg=10.0),
                                        Script3D(seconds=1.0, turn_deg=20.0))
    res = lift(tracks, m, spec)
    assert res.summary["reliable_fraction"] >= 0.9
    errs = _rms(res, truth, truth["free_ids"])
    assert max(errs.values()) < 2.0, errs
    assert _heading_rms(res, truth) < 1.5
    assert abs(res.camera["elevation_deg"] - 10.0) < 1.5
    assert all(h == 1 for h in res.hypothesis)  # labels as tracked, the near side more confident
    json.loads(res.model_dump_json())  # stored as JSON


@pytest.mark.slow
def test_lift_from_four_camera_yaws_with_turning_abduction_and_proportions(spec):
    m = load_lift_map("feral_calf_3d")
    abd = ["joint.hl.hip_abd", "joint.hr.hip_abd"]
    for yaw in (0.0, 30.0, 45.0, 60.0):
        script = Script3D(seconds=3.0, turn_deg=35.0, abduction_deg=8.0, trunk_length=1.15, trunk_width=1.2,
                          front_leg=0.9, seed=int(yaw))
        tracks, truth = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=yaw, elevation_deg=10.0), script)
        t0 = time.perf_counter()
        res = lift(tracks, m, spec)
        took = time.perf_counter() - t0
        sagittal = [j for j in truth["free_ids"] if j not in abd]
        errs = _rms(res, truth, sagittal)
        assert max(errs.values()) < 2.5, (yaw, errs)
        abd_err = _rms(res, truth, abd)
        assert max(abd_err.values()) < 2.5, (yaw, abd_err)
        assert _heading_rms(res, truth) < 1.5, yaw
        assert abs(res.camera["elevation_deg"] - 10.0) < 1.5, yaw
        p = res.proportions
        assert abs(p["trunk_length"] - 1.15) < 0.035 and abs(p["front_leg"] - 0.9) < 0.03, (yaw, p)
        # near head-on frames are unreliable; frames well inside the limit are not
        vy = np.abs(truth["view_yaw_deg"])
        st = np.asarray(res.state)
        assert np.all(st[vy > 75.0] == "unreliable"), yaw
        if np.any(vy < 60.0):
            assert np.mean(st[vy < 60.0] != "unreliable") > 0.9, yaw
        assert took < 60.0, took


def test_tracker_labels_swapped_is_the_depth_flip(spec):
    """The tracker calls the near side R: the lift takes the mirror pose (labels exchanged) and keeps the heading."""
    m = load_lift_map("ap10k_3d")
    # a calf as wide as the prior says (0.35 of its length; the robot is 159 / 550 = 0.29): AP-10K's few points
    # do not pin the width, so the lift takes the prior
    tracks, truth = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=28.0, elevation_deg=8.0),
                                        Script3D(seconds=1.0, trunk_width=0.35 / (159.0 / 550.0)))
    left = [i for i, n in enumerate(tracks.names) if n.startswith("L_")]
    right = [i for i, n in enumerate(tracks.names) if n.startswith("R_")]
    xy, lk = tracks.xy.copy(), tracks.likelihood.copy()
    xy[:, left], xy[:, right] = tracks.xy[:, right], tracks.xy[:, left]
    lk[:, left], lk[:, right] = tracks.likelihood[:, right], tracks.likelihood[:, left]
    res = lift(tracks.model_copy(update={"xy": xy, "likelihood": lk}), m, spec)
    assert np.mean(np.asarray(res.hypothesis) == -1) > 0.95
    assert _heading_rms(res, truth) < 1.5
    # the AP-10K map keeps ap10k_side's assumption: the hock follows the stifle
    assert res.joints_deg["joint.hl.hock"] == res.joints_deg["joint.hl.stifle"]


def test_a_level_side_view_cannot_see_abduction_or_width(spec):
    m = load_lift_map("feral_calf_3d")
    tracks, truth = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=0.0, elevation_deg=0.0),
                                        Script3D(seconds=1.5, turn_deg=0.0))
    res = lift(tracks, m, spec)
    assert res.proportions["width_source"] == "prior"
    assert res.summary["unobservable_fraction"]["joint.hl.hip_abd"] > 0.8
    errs = _rms(res, truth, ["joint.hl.stifle", "joint.fl.carpus", "joint.fr.shoulder"])
    assert max(errs.values()) < 2.0, errs


def test_lift_clip_turns_and_tracks_the_far_legs(spec):
    m = load_lift_map("feral_calf_3d")
    tracks, truth = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=20.0), Script3D(seconds=1.0, turn_deg=30.0))
    res = lift(tracks, m, spec)
    full = lift_clip(res, spec, None, "walk")
    assert "robot's own standing pose" in full.meta["reference"]
    clip = cut_lift(full, 0, res.frames, "walk")
    assert set(clip.meta["legs"].values()) == {"tracked"}
    assert abs(clip.meta["turn_deg"] - 30.0) < 2.0
    w, x, y, z = clip.root_quat[-1]
    assert abs(np.rad2deg(2 * np.arctan2(z, w)) - 30.0) < 3.0  # the robot turns as the animal did
    assert clip.root_pos[0][:2] == (0.0, 0.0)
    assert clip.joints["joint.hr.hip_abd"] != clip.joints["joint.hl.hip_abd"]  # far legs are not copies
    copied = cut_lift(full, 0, res.frames, "walk", far_side="copy")
    near = "l" if clip.meta["near_side"] == "left" else "r"
    far = "r" if near == "l" else "l"
    assert copied.joints[f"joint.f{far}.carpus"] == copied.joints[f"joint.f{near}.carpus"]


# ---------------------------------------------------------------------- through the inbox
@pytest.fixture()
def lab(tmp_path):
    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    lab = Lab.open(project.path, create=False)
    yield lab
    lab.close()


def _wait(lab, timeout=180.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        jobs = [j for j in lab.jobs.list() if j["kind"] == "footage"]
        if jobs and all(j["status"] in ("done", "failed", "cancelled") for j in jobs):
            return jobs
        time.sleep(0.05)
    raise TimeoutError


def _drop_csv_video(lab, spec, name, camera, script):
    """A blank AVI with the synthetic 3D keypoints beside it as a CSV (tracker ``csv``)."""
    from calflab.behave.video import write_avi

    m = load_lift_map("feral_calf_3d")
    tracks, truth = synthetic_tracks_3d(spec, m, camera, script)
    d = inbox.videos_dir(lab.project.path)
    write_avi(d / name, np.zeros((tracks.frames, 36, 64), dtype=np.uint8), tracks.fps,
              np.array([[0, 0, 0]], dtype=np.uint8))
    head = ["frame"] + [f"{n}_{c}" for n in tracks.names for c in ("x", "y", "likelihood")]
    rows = [",".join(head)]
    for f in range(tracks.frames):
        vals = [str(f)]
        for k in range(len(tracks.names)):
            x, y = tracks.xy[f, k]
            vals += ["" if np.isnan(x) else f"{x:.3f}", "" if np.isnan(y) else f"{-y:.3f}",
                     f"{tracks.likelihood[f, k]:.3f}"]
        rows.append(",".join(vals))
    (d / name).with_suffix(".csv").write_bytes(("\n".join(rows) + "\n").encode())
    return truth


def test_new_projects_lift_in_3d_and_older_ones_stay_2d(lab, tmp_path):
    from calflab.app.footage import load_settings

    assert load_settings(lab.project.path).mode == "3d"
    assert load_settings(lab.project.path).smoothing.method == "auto"  # ADR-082
    old = tmp_path / "old"
    (old / "footage").mkdir(parents=True)
    (old / "footage" / "inbox.json").write_bytes(b"{}")
    assert load_settings(old).mode == "2d"  # processed videos before the lift existed
    assert load_settings(old).smoothing.method == "none"  # clips of an older project are cut as before
    (old / "footage" / "settings.json").write_bytes(json.dumps({"tracker": "csv", "map": "feral_calf_side"}).encode())
    assert load_settings(old).mode == "2d"
    assert load_settings(old).smoothing.method == "none"


def test_a_video_through_the_inbox_in_3d(lab, spec):
    from calflab.app.footage import (
        FootageError,
        FootageSettings,
        candidate_clip,
        compare_lift_maps,
        footage_lift,
        footage_view,
        preview_candidate,
        save_settings,
    )

    save_settings(lab.project.path, FootageSettings(tracker="csv", mode="3d", map_3d="feral_calf_3d"))
    script = Script3D(seconds=2.5, turn_deg=25.0, period_s=0.8)
    _drop_csv_video(lab, spec, "turning.avi", Camera3D(yaw_deg=35.0, elevation_deg=8.0), script)
    lab.footage.poll()
    lab.footage.poll()
    jobs = _wait(lab)
    assert jobs[0]["status"] == "done", jobs
    rec = inbox.load(lab.project.path)["turning.avi"]
    assert rec.status == "needs_review" and rec.mode == "3d", rec.reason
    assert rec.lift["summary"]["reliable_fraction"] > 0.9
    assert "too oblique" not in rec.view["verdict"]
    assert rec.candidates and all(c.reliable_fraction is not None for c in rec.candidates)
    strip = footage_lift(lab, "turning.avi")
    assert len(strip["state"]) == len(strip["view_yaw_deg"]) == strip["frames"]
    assert 25.0 < float(np.median(strip["view_yaw_deg"])) < 60.0
    c = max(rec.candidates, key=lambda c: c.end - c.start)
    clip = candidate_clip(lab, "turning.avi", c.id)
    assert clip.meta["mode"] == "3d" and clip.meta["video_sha256"] == rec.sha256
    assert "joint.hl.hip_abd" in clip.joints and clip.root_quat
    out = preview_candidate(lab, "turning.avi", c.id)
    assert out["motion"]["turn_deg"] is not None
    rows = {r["joint"]: r for r in out["report"]["joints"]}
    assert rows["joint.hl.hip_abd"]["in_clip"] and "peak_speed_deg_s" in rows["joint.hl.hip_abd"]
    # clip smoothing (ADR-082): on by default, chosen from the video, recorded with the clip
    sm = clip.meta["smoothing"]
    assert sm["method"] == "auto" and sm["applied"] and sm["cutoff_hz"] > 0
    assert set(sm["peak_speed_deg_s"]) == set(clip.joints)
    assert out["smoothing"]["cutoff_hz"] == sm["cutoff_hz"]
    lab.execute("set_footage_settings", {"tracker": "csv", "map": "feral_calf_side", "clip_smoothing": "none"})
    view = footage_view(lab)["settings"]
    assert view["clip_smoothing"] == "none" and view["map_3d"] == "feral_calf_3d" and view["mode"] == "3d"
    raw = candidate_clip(lab, "turning.avi", c.id)
    assert not raw.meta["smoothing"]["applied"]
    assert max(sm["peak_speed_deg_s"][j]["raw"] for j in clip.joints) == pytest.approx(
        max(float(np.max(np.abs(np.diff(raw.joints[j])))) * raw.fps for j in raw.joints), abs=0.2)
    assert strip["maps"] == ["feral_calf_3d"]
    with pytest.raises(FootageError, match="another map"):
        compare_lift_maps(lab, "turning.avi")


def test_frames_come_from_an_open_reader_and_a_cache(tmp_path, spec):
    from calflab.app.footage import FrameCache
    from calflab.behave.synthetic import Stretch, SyntheticScript, write_synthetic_video

    path = tmp_path / "v.avi"
    write_synthetic_video(spec, path, SyntheticScript(stretches=[Stretch(kind="walk", seconds=2.0)]))
    cache = FrameCache(frames=100, ahead=10)
    data, media = cache.get(path, 0, 320)
    assert data and media.startswith("image/")
    end = time.monotonic() + 10.0
    while not cache.cached(path, 10, 320) and time.monotonic() < end:  # read ahead on a thread
        time.sleep(0.01)
    assert cache.cached(path, 10, 320)
    assert cache.get(path, 5, 320)[0] == cache.get(path, 5, 320)[0]
    cache.close()
