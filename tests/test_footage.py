"""The video inbox (ADR-076) and pose trackers (ADR-077): video files -> tracks -> candidates -> clips."""

from __future__ import annotations

import os
import time

import numpy as np
import pytest
from calflab.behave import inbox
from calflab.behave.synthetic import Stretch, SyntheticScript, render, write_synthetic_video
from calflab.behave.video import AviReader, open_video, write_avi
from calflab.design import build_design, genome_definition


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


@pytest.fixture()
def lab(tmp_path):
    from calflab.app import Lab
    from calflab.app.footage import FootageSettings, save_settings
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    lab = Lab.open(project.path, create=False)
    save_settings(lab.project.path, FootageSettings(tracker="synthetic", map="feral_calf_side"))
    yield lab
    lab.close()


def _wait(lab, kind="footage", timeout=120.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        jobs = [j for j in lab.jobs.list() if j["kind"] == kind]
        if jobs and all(j["status"] in ("done", "failed", "cancelled") for j in jobs):
            return jobs[0]
        time.sleep(0.05)
    raise TimeoutError


def _drop(lab, spec, name="calf.avi", script=None):
    path = inbox.videos_dir(lab.project.path) / name
    return path, write_synthetic_video(spec, path, script)


# ---------------------------------------------------------------------- video files
def test_avi_frames_and_frame_rate_come_from_the_file(tmp_path):
    pal = np.array([[255, 255, 255], [200, 0, 0]])
    frames = np.zeros((7, 30, 41), dtype=np.uint8)
    frames[4, 10:20, 5:9] = 1
    path = write_avi(tmp_path / "t.avi", frames, 23.976, pal)
    r = AviReader(path)
    assert r.info.fps == pytest.approx(23.976) and r.info.frames == 7 and (r.info.width, r.info.height) == (41, 30)
    assert tuple(r.frame(4)[12, 6]) == (200, 0, 0) and tuple(r.frame(3)[12, 6]) == (255, 255, 255)
    with open_video(path) as v:  # OpenCV when installed, else the built-in reader: the same frames
        assert v.info.fps == pytest.approx(23.976, abs=1e-3)
        assert np.array_equal(v.frame(4), r.frame(4))


# ---------------------------------------------------------------------- inbox
def test_synthetic_video_through_the_inbox_to_accepted_clips(lab, spec):
    _, truth = _drop(lab, spec)
    lab.footage.poll()  # first sight: waiting until its size is stable
    assert inbox.load(lab.project.path)["calf.avi"].status == "waiting"
    assert lab.footage.poll()["started"] == "calf.avi"
    assert _wait(lab)["status"] == "done"
    rec = inbox.load(lab.project.path)["calf.avi"]
    assert rec.status == "needs_review" and len(rec.sha256) == 64
    assert rec.info["fps"] == pytest.approx(20.0) and rec.tracker["tracker"] == "synthetic"
    assert rec.near_side["near_side"] == "left"  # it faces left: its left side is toward the camera
    kinds = [c.kind for c in rec.candidates]
    assert kinds == ["idle", "gait", "idle"]
    gait = rec.candidates[1]
    assert gait.period_s == pytest.approx(1.2, abs=0.06) and gait.far_side == "half_cycle"
    out = lab.execute("accept_candidate", {"file": "calf.avi", "candidate": gait.id, "name": "walk",
                                           "valence": 0.2, "arousal": 0.5, "words": "steady"})["result"]
    clip = lab.motions.get(out["clip"])
    a, b = clip.meta["frame_range"]
    for j in ("joint.hl.stifle", "joint.hl.hock", "joint.fl.shoulder", "joint.fl.carpus"):
        want = np.array([truth["angles"][f][j] for f in range(a, b)])
        assert np.max(np.abs(np.array(clip.joints[j]) - want)) < 1.5, j
    # the far legs half a period behind, and the provenance of the clip
    half = int(round(0.6 * 20))
    assert np.allclose(clip.joints["joint.hr.stifle"], np.roll(clip.joints["joint.hl.stifle"], half))
    assert clip.meta["video_sha256"] == rec.sha256 and clip.meta["tracker"]["model"] == "colour-markers"
    assert clip.meta["map"]["name"] == "feral_calf_side" and clip.meta["cleaning"]["smooth_frames"] == 3
    assert clip.affect is not None and clip.affect.words == ["steady"] and clip.affect.arousal == 0.5
    lab.execute("reject_candidate", {"file": "calf.avi", "candidate": "c1"})
    lab.execute("accept_candidate", {"file": "calf.avi", "candidate": "c3", "start": rec.candidates[2].start + 5})
    rec = inbox.load(lab.project.path)["calf.avi"]
    assert rec.status == "ready" and rec.candidates[2].trim is not None
    view = lab.analysis("behave")["inbox"]
    assert view["videos"][0]["file"] == "calf.avi" and any(t["key"] == "rtmpose_ap10k" for t in view["trackers"])


def test_the_watcher_processes_a_file_once_and_again_when_it_changes(lab, spec):
    path, _ = _drop(lab, spec, script=SyntheticScript(stretches=[Stretch(kind="stand", seconds=1.5)]))
    lab.footage.poll()
    lab.footage.poll()
    _wait(lab)
    sha = inbox.load(lab.project.path)["calf.avi"].sha256
    assert lab.footage.poll()["started"] is None  # nothing new
    os.utime(path, None)  # touched, same content: hashed again, not processed again
    assert lab.footage.poll()["queued"] == []
    n_jobs = len(lab.jobs.list())
    write_synthetic_video(spec, path, SyntheticScript(stretches=[Stretch(kind="stand", seconds=2.0)]))
    out = lab.footage.poll()
    assert out["queued"] == ["calf.avi"] and out["started"] == "calf.avi"
    _wait(lab)
    rec = inbox.load(lab.project.path)["calf.avi"]
    assert rec.sha256 != sha and rec.status == "needs_review" and len(lab.jobs.list()) == n_jobs + 1
    path.unlink()
    lab.footage.poll()
    assert inbox.load(lab.project.path)["calf.avi"].status == "missing"


def test_a_failing_tracker_marks_the_video_failed_and_retry_queues_it(lab, spec):
    from calflab.app.footage import FootageSettings, save_settings

    save_settings(lab.project.path, FootageSettings(tracker="csv", map="feral_calf_side"))
    _drop(lab, spec, script=SyntheticScript(stretches=[Stretch(kind="stand", seconds=1.0)]))
    lab.footage.poll()
    lab.footage.poll()
    _wait(lab)
    rec = inbox.load(lab.project.path)["calf.avi"]
    assert rec.status == "failed" and "No CSV beside calf.avi" in rec.reason
    save_settings(lab.project.path, FootageSettings(tracker="synthetic", map="feral_calf_side"))
    assert lab.execute("retry_video", {"file": "calf.avi"})["result"]["started"] == "calf.avi"
    _wait(lab)
    assert inbox.load(lab.project.path)["calf.avi"].status == "needs_review"


def test_frames_and_points_for_the_review(lab, spec):
    from calflab.app.footage import frame_image, frame_points

    _, truth = _drop(lab, spec, script=SyntheticScript(stretches=[Stretch(kind="walk", seconds=3.0)]))
    lab.footage.poll()
    lab.footage.poll()
    _wait(lab)
    data, media = frame_image(lab, "calf.avi", 5)
    assert media in ("image/jpeg", "image/png") and len(data) > 100
    pts = frame_points(lab, "calf.avi", 10, 12)
    assert len(pts["frames"]) == 2 and pts["image_size"] == [400, 180] or pts["image_size"] == (400, 180)
    k = pts["names"].index("hock")
    x, y, conf = pts["frames"][0][k]
    assert (x, y) == pytest.approx(tuple(truth["points_px"][10, k]), abs=0.6) and conf == 1.0  # image pixels, y down
    assert "hip" in pts["used"] and ["hip", "stifle"] in pts["links"]


# ---------------------------------------------------------------------- segmentation, side, view
def test_segmentation_finds_a_known_walk_and_pause(spec):
    from calflab.behave.clips import near_angles, settle_side
    from calflab.behave.keypoints import parse_tracks
    from calflab.behave.retarget import load_map
    from calflab.behave.segment import segment

    script = SyntheticScript(stretches=[Stretch(kind="walk", seconds=4.8, period_s=0.8), Stretch(kind="stand", seconds=2.5),
                                        Stretch(kind="walk", seconds=3.0, period_s=1.0)], fps=25)
    _, truth = render(spec, script)
    pts = truth["points_px"]
    rows = ["frame," + ",".join(f"{n}_x,{n}_y" for n in truth["names"])]
    for f in range(pts.shape[0]):
        rows.append(f"{f}," + ",".join(f"{pts[f, k, 0]:.3f},{pts[f, k, 1]:.3f}" for k in range(len(truth["names"]))))
    tracks = parse_tracks("\n".join(rows), 25.0)
    m, _ = settle_side(tracks, load_map("feral_calf_side").model_copy(update={"near_side": "auto"}))
    full = near_angles(tracks, m, None, 610.0)
    out = segment(tracks, "hip", "withers", {k: np.asarray(v) for k, v in full.joints.items()})["candidates"]
    assert [c["kind"] for c in out] == ["gait", "idle", "gait"]
    walk, pause, walk2 = out
    assert walk["period_s"] == pytest.approx(0.8, abs=0.08) and walk2["period_s"] == pytest.approx(1.0, abs=0.08)
    stretches = truth["stretches"]
    assert abs(pause["start"] - stretches[1]["start"]) <= 0.25 * 25 and abs(pause["end"] - stretches[1]["end"]) <= 0.25 * 25
    assert walk["trunk_bl_s"] > 0.1 and pause["trunk_bl_s"] < 0.02


def test_near_side_follows_the_facing_and_the_ap10k_map_mirrors(spec):
    from calflab.behave.keypoints import KeypointTracks
    from calflab.behave.retarget import for_side, load_map
    from calflab.behave.view import detect_near_side, view_report

    m = load_map("ap10k_side")
    r = for_side(m, "right")
    assert set(r.joints) == {"hr.stifle", "hr.hock", "fr.shoulder", "fr.carpus"}
    assert r.joints["hr.stifle"].flexion == ["R_Hip", "R_Knee", "R_B_Paw"] and r.trunk[0] == ["R_Hip", "Root of tail"]
    # an animal facing right whose right side is tracked more confidently; hips 20 px apart in a 200 px trunk
    names = ["L_Hip", "R_Hip", "L_Shoulder", "R_Shoulder"]
    n = 10
    xy = np.zeros((n, 4, 2))
    xy[:, :, 0] = [100, 120, 300, 320]
    lk = np.tile([0.4, 0.9, 0.4, 0.9], (n, 1))
    t = KeypointTracks(fps=10, names=names, xy=xy, likelihood=lk)
    side = detect_near_side(t, m)
    assert side["near_side"] == "right" and side["by_confidence"] == "right" and side["agree"] is True
    v = view_report(t, m)
    assert v["median_yaw_deg"] == pytest.approx(np.degrees(np.arctan(0.1 / 0.35)), abs=0.2)
    assert v["verdict"] == "side view OK"
    xy[:, :, 0] = [100, 200, 300, 400]  # hips 100 px apart: turned toward the camera
    assert view_report(KeypointTracks(fps=10, names=names, xy=xy, likelihood=lk), m)["verdict"] == "too oblique"


# ---------------------------------------------------------------------- trackers
def test_tracker_plugins_honour_their_contract():
    from calflab.plugins import load_plugins, registry
    from calflab.plugins.contracts import check_plugin

    load_plugins()
    for key in ("csv", "synthetic", "rtmpose_ap10k"):
        assert check_plugin(registry.get("pose_tracker", key)) == [], key
    ok, why = registry.get("pose_tracker", "rtmpose_ap10k")().available()
    assert ok or "extra" in why or "download" in why


def test_new_plugin_template_for_a_pose_tracker(tmp_path):
    from calflab.plugins.templates import render

    src, test = render("pose_tracker", "my_tracker")
    assert "class MyTracker(PoseTracker)" in src and "registry.get(\"pose_tracker\", \"my_tracker\")" in test
    compile(src, "my_tracker.py", "exec")


@pytest.mark.slow
def test_rtmpose_tracks_a_video_when_installed(tmp_path, spec):
    from calflab.plugins import load_plugins, registry

    load_plugins()
    tracker = registry.get("pose_tracker", "rtmpose_ap10k")({"device": "cpu"})
    ok, why = tracker.available()
    if not ok:
        pytest.skip(why)
    path = tmp_path / "calf.avi"
    write_synthetic_video(spec, path, SyntheticScript(stretches=[Stretch(kind="walk", seconds=1.0)]))
    t = tracker.track(path)
    assert t.names[:5] == ["L_Eye", "R_Eye", "Nose", "Neck", "Root of tail"] and t.frames == 20
    assert t.model["files"]["yolox_s.onnx"] and t.model["device"] == "cpu"
