"""Clip smoothing (ADR-082): a zero-lag low-pass whose cutoff can come from the video (Winter's residual
analysis), recorded in each clip's provenance; and a 3D map with the hind Knee at the hock, compared with the
tied map side by side."""

from __future__ import annotations

import json

import numpy as np
import pytest
from calflab.behave import inbox
from calflab.behave.lift import LandmarkDef, compare_lifts, lift, load_lift_map
from calflab.behave.smoothing import (
    ClipSmoothing,
    max_cutoff_hz,
    provenance,
    residual_cutoff,
    smooth_clip,
)
from calflab.behave.synthetic import Camera3D, Script3D, synthetic_tracks_3d
from calflab.design import build_design, genome_definition
from calflab.project.motions import MotionClip

FPS = 30.0


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _noisy_walk(seconds=6.0, noise_deg=2.0, seed=0):
    """A 1 Hz, 20 deg swing with a 3 Hz harmonic (a stride is not a sine), plus white jitter, as a tracker gives
    it."""
    t = np.arange(int(seconds * FPS)) / FPS
    true = 20.0 * np.sin(2 * np.pi * 1.0 * t) + 5.0 * np.sin(2 * np.pi * 3.0 * t + 0.4)
    rng = np.random.default_rng(seed)
    raw = true + rng.normal(0.0, noise_deg, t.size)
    clip = MotionClip(name="walk", fps=FPS, joints={"joint.hl.stifle": list(raw), "joint.fl.carpus": list(raw * 0.5)},
                      root_pos=[(float(x), 0.0, 600.0) for x in 100.0 * t + rng.normal(0, 3.0, t.size)],
                      root_quat=[(1.0, 0.0, 0.0, 0.0)] * t.size)
    return clip, true


def _peak(v):
    return float(np.max(np.abs(np.diff(np.asarray(v))))) * FPS


def test_auto_cutoff_brings_peak_speed_back_to_the_motion(spec):
    clip, true = _noisy_walk()
    assert _peak(clip.joints["joint.hl.stifle"]) > 1.5 * _peak(true)  # the jitter, not the swing
    out, info = smooth_clip(clip, ClipSmoothing(method="auto"))
    assert info["applied"] and 3.0 <= info["cutoff_hz"] <= 8.0, info  # keeps the harmonic
    assert abs(info["noise_rms_deg"] - 2.0) < 1.0  # the analysis finds the jitter it was given
    sm = np.asarray(out.joints["joint.hl.stifle"])
    assert abs(_peak(sm) - _peak(true)) < 0.3 * _peak(true)
    raw = np.asarray(clip.joints["joint.hl.stifle"])
    assert np.sqrt(np.mean((sm - true) ** 2)) < 0.8 * np.sqrt(np.mean((raw - true) ** 2))
    lags = range(-5, 6)  # zero lag: the smoothed motion lines up with the true one
    assert max(lags, key=lambda k: float(np.dot(np.roll(sm, k)[10:-10], true[10:-10]))) == 0
    assert sm.min() >= raw.min() and sm.max() <= raw.max()  # no new extremes
    q = np.asarray(out.root_quat)
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0)
    prov = provenance(ClipSmoothing(method="auto"), FPS, info, clip, out)
    assert prov["peak_speed_deg_s"]["joint.hl.stifle"]["smoothed"] < prov["peak_speed_deg_s"]["joint.hl.stifle"]["raw"]
    assert "Winter" in prov["filter"]
    json.dumps(prov)


def test_fixed_cutoff_none_and_out_of_band(spec):
    clip, _ = _noisy_walk(seconds=2.0)
    same, info = smooth_clip(clip, ClipSmoothing(method="none"))
    assert not info["applied"] and same.joints == clip.joints
    out, info = smooth_clip(clip, ClipSmoothing(method="lowpass", cutoff_hz=6.0))
    assert info == {"applied": True, "cutoff_hz": 6.0}
    assert _peak(out.joints["joint.hl.stifle"]) < _peak(clip.joints["joint.hl.stifle"])
    too_high = ClipSmoothing(method="lowpass", cutoff_hz=max_cutoff_hz(FPS) + 1.0)
    out, info = smooth_clip(clip, too_high)
    assert not info["applied"] and out.joints == clip.joints
    assert "Not applied" in provenance(too_high, FPS, info)["note"]
    r = residual_cutoff(np.asarray(clip.joints["joint.hl.stifle"])[:, None], FPS, ClipSmoothing(method="auto"))
    assert set(r) == {"cutoff_hz", "noise_rms_deg", "residual_deg"}


def _hock_map():
    """ap10k_3d with the hind Knee at the hock and the hock untied (the map made for robot-calf-final)."""
    m = load_lift_map("ap10k_3d")
    lms = dict(m.landmarks)
    lms["{S}_Knee"] = LandmarkDef(body="leg.h{s}.cannon")
    return m.model_copy(update={"name": "ap10k_3d_hock", "landmarks": lms, "ties": {}})


def test_knee_at_the_hock_untied_recovers_both_hind_angles(spec):
    """Footage of a body whose stifle and hock move differently: the untied map finds both, the tied one cannot."""
    hock = _hock_map()
    tracks, truth = synthetic_tracks_3d(spec, hock, Camera3D(yaw_deg=25.0, elevation_deg=8.0),
                                        Script3D(seconds=1.0, trunk_width=0.35 / (159.0 / 550.0)))
    assert np.std(truth["joints_deg"]["joint.hl.hock"] - truth["joints_deg"]["joint.hl.stifle"]) > 3.0
    untied = lift(tracks, hock, spec)
    tied = lift(tracks, load_lift_map("ap10k_3d"), spec)
    rel = untied.reliable()
    assert rel.mean() > 0.9
    for j in ("joint.hl.stifle", "joint.hl.hock", "joint.hr.stifle", "joint.hr.hock"):
        err = np.asarray(untied.joints_deg[j])[rel] - truth["joints_deg"][j][rel]
        assert np.sqrt(np.mean(err ** 2)) < 3.0, j
    assert tied.joints_deg["joint.hl.hock"] == tied.joints_deg["joint.hl.stifle"]
    cmp = compare_lifts({"ap10k_3d": tied, "ap10k_3d_hock": untied})
    assert cmp["frames"] == tracks.frames
    assert cmp["hind_angles_deg"]["ap10k_3d"]["hock - stifle (l)"]["rms"] == 0.0
    assert cmp["hind_angles_deg"]["ap10k_3d_hock"]["hock - stifle (l)"]["rms"] > 3.0
    # the hind paw is where a tied hock cannot follow
    paws = cmp["landmark_residual_px"]["L_B_Paw"]
    assert paws["ap10k_3d_hock"] < paws["ap10k_3d"]
    assert set(cmp["summary"]["ap10k_3d"]) >= {"reliable_fraction", "ambiguous_fraction", "median_residual_px"}
    json.dumps(cmp)


def test_lifts_are_kept_per_map(tmp_path, spec):
    m = load_lift_map("feral_calf_3d")
    tracks, _ = synthetic_tracks_3d(spec, m, Camera3D(yaw_deg=20.0), Script3D(seconds=0.5))
    res = lift(tracks, m, spec)
    sha = "ab" * 32
    inbox.save_lift(tmp_path, sha, res)
    inbox.save_lift(tmp_path, sha, res.model_copy(update={"map": "other"}))
    assert inbox.lift_maps(tmp_path, sha) == ["feral_calf_3d", "other"]
    assert inbox.load_lift(tmp_path, sha).map == "other"  # the current one is the last
    assert inbox.load_lift(tmp_path, sha, "feral_calf_3d").map == "feral_calf_3d"
    with pytest.raises(FileNotFoundError):
        inbox.load_lift(tmp_path, sha, "nope")
