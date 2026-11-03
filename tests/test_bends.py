"""Each leg's bend chosen over the window (ADR-083), and frames a recording repeated.

The known-bend footage: the feral calf's own skeleton, with a fore carpus allowed to bend either way (a test-only
range; the robot's own ranges leave no second bend in a side view), seen at a slant. The carpus point is tracked
weakly, so in any one frame the two bends fit about equally, but over the video the weak cue adds up."""

from __future__ import annotations

import itertools
import json
import math

import numpy as np
import pytest
from calflab import units as u
from calflab.behave.keypoints import KeypointTracks
from calflab.behave.lift import (
    N_POSE,
    LiftResult,
    LiftSettings,
    Skeleton,
    _chain,
    _choose_bends,
    _Frame,
    _leg_cost,
    _leg_grid,
    _solve_leg,
    leg_jumps,
    lift,
    lift_clip,
    load_lift_map,
    project,
)
from calflab.behave.timing import RepeatedFrames, repeated_frames, repeated_from_differences, retime
from calflab.design import build_design, genome_definition

FPS = 30.0
CARPUS = 40.0  # the true bend of the fore carpus, deg (the other bend is near -40)


@pytest.fixture(scope="module")
def spec():
    """The feral calf with fore carpi that may bend either way (test only)."""
    s = build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec
    for j in s.joints:
        if j.id in ("joint.fl.carpus", "joint.fr.carpus"):
            j.range_deg = (-130.0, 130.0)
    return s


@pytest.fixture(scope="module")
def weak_carpus():
    """The robot's own joints as landmarks, the carpus point tracked weakly: in one frame the other bend costs about
    2 noise units more (the bends move it about 110 px apart)."""
    m = load_lift_map("feral_calf_3d")
    lms = dict(m.landmarks)
    lms["{S}_carpus"] = lms["{S}_carpus"].model_copy(update={"weight": 0.0015})
    return m.model_copy(update={"name": "weak_carpus", "landmarks": lms})


def _footage(spec, lmap, seconds=3.0, noise_px=3.0, seed=0, carpus_noise_px=0.0):
    """Tracks of a walk seen 25 deg off a side view, with the true pose vectors and globals. ``carpus_noise_px``:
    extra noise on the carpus points (a tracker unsure of them)."""
    sk = Skeleton(spec, lmap)
    n = int(seconds * FPS)
    t = np.arange(n) / FPS
    d = np.zeros((n, sk.n))
    for i, jid in enumerate(sk.free_ids):
        ph = 2 * math.pi * (t + (0.5 if jid.split(".")[1].endswith("r") else 0.0))
        part = jid.split(".")[-1]
        d[:, i] = u.deg_to_rad({"stifle": 10 * np.sin(ph), "hock": 6 * (1 - np.cos(ph)), "shoulder": -12 * np.sin(ph),
                                "carpus": CARPUS + 10 * np.sin(ph)}.get(part, 0.0 * t))
    g = sk.initial_globals()
    g[3] = u.deg_to_rad(8.0)
    x = np.concatenate([np.stack([np.full(n, u.deg_to_rad(25.0)), np.zeros(n), np.zeros(n), np.full(n, math.log(0.5)),
                                  300 + 3.0 * t * FPS, np.full(n, -200.0)], axis=1), d], axis=1)
    rng = np.random.default_rng(seed)
    uv = project(sk, x, g) + rng.normal(0.0, noise_px, (n, len(sk.names), 2))
    for i, name in enumerate(sk.names):
        if name.endswith("_carpus"):
            uv[:, i] += rng.normal(0.0, carpus_noise_px, (n, 2))
    lk = rng.uniform(0.85, 1.0, (n, len(sk.names)))
    tracks = KeypointTracks(fps=FPS, names=list(sk.names), xy=uv, likelihood=lk, source="synthetic",
                            image_size=(900, 400))
    return tracks, sk, x, g


def _mirror_bend(sk, x, g, fr, sigma, leg):
    """The other bend of a leg in one frame (refined from the grid), and its chi-square against the true one's."""
    from scipy.ndimage import minimum_filter

    ji, li = sk.legs[leg]
    mesh, shape = _leg_grid(sk, ji)
    cg = _leg_cost(sk, x, mesh, g, fr, sigma, ji, li, None)
    a0 = x[[N_POSE + j for j in ji]]
    local = (cg.reshape(shape) <= minimum_filter(cg.reshape(shape), size=3, mode="nearest")).reshape(-1)
    far = np.abs(mesh - a0).max(axis=1) > u.deg_to_rad(20.0)
    k = np.where(local & far)[0]
    k = k[np.argmin(cg[k])]
    prior = load_lift_map("feral_calf_3d").prior
    a = _solve_leg(sk, x, mesh[k], g, fr, sigma, ji, li, prior)
    c = _leg_cost(sk, x, np.stack([a, a0]), g, fr, sigma, ji, li, None)
    return a, float(c[0] - c[1])


def test_chain_finds_the_best_path_and_true_margins():
    rng = np.random.default_rng(3)
    for _ in range(20):
        ks = [int(k) for k in rng.integers(1, 4, size=6)]
        unary = [rng.uniform(0, 5, k) for k in ks]
        pair = [np.zeros((1, ks[0]))] + [rng.uniform(0, 5, (ks[t - 1], ks[t])) for t in range(1, len(ks))]
        path, margin = _chain(unary, pair)

        def cost(p, unary=unary, pair=pair):
            return sum(unary[t][p[t]] for t in range(len(p))) + sum(pair[t][p[t - 1], p[t]] for t in range(1, len(p)))

        paths = list(itertools.product(*[range(k) for k in ks]))
        best = min(paths, key=cost)
        assert math.isclose(cost(tuple(path)), cost(best))
        for t, k in enumerate(ks):
            if k == 1:
                assert margin[t] == np.inf
                continue
            through = [min(cost(p) for p in paths if p[t] == s) for s in range(k)]
            assert math.isclose(margin[t], min(c for s, c in enumerate(through) if s != path[t]) - cost(best),
                                abs_tol=1e-9)


def test_window_puts_back_a_bend_the_frames_lost(spec, weak_carpus):
    """Frames where a frame-by-frame choice took the other bend (a single frame, and a short stretch) are put back
    in the true bend, and nothing else changes."""
    tracks, sk, x, g = _footage(spec, weak_carpus)
    frames = [_Frame(tracks.xy[f], tracks.likelihood[f] * sk.weight) for f in range(tracks.frames)]
    sigma = 3.0
    cols = [N_POSE + j for j in sk.legs["fl"][0]]
    wrong = [12, 40, 41, 42, 43]
    X = x.copy()
    for f in wrong:
        a, extra = _mirror_bend(sk, x[f], g, frames[f], sigma, "fl")
        assert u.rad_to_deg(np.abs(a - x[f, cols]).max()) > 40.0  # a real second bend ...
        assert extra < 4.0  # ... that fits about as well in the frame alone
        X[f, cols] = a
    step = np.concatenate([np.full(3, u.deg_to_rad(150.0) / FPS), [1.0 / FPS],
                           np.where(sk.is_abd, u.deg_to_rad(60.0), u.deg_to_rad(300.0)) / FPS])
    out, bends = _choose_bends(sk, X, g, frames, sigma, step, weak_carpus.prior, LiftSettings())
    assert sorted(np.where(bends["fl"]["changed"])[0].tolist()) == wrong
    assert u.rad_to_deg(np.abs(out[wrong][:, cols] - x[wrong][:, cols]).max()) < 6.0
    for leg in ("hl", "hr", "fr"):
        assert not bends[leg]["changed"].any()
    assert np.all(bends["fl"]["second"][wrong])  # every one of them had a second bend in the frame alone
    assert np.nanmin(bends["fl"]["margin"]) >= 0.0


@pytest.mark.slow
def test_lift_over_the_window_finds_the_known_bend(spec, weak_carpus):
    """End to end on footage whose carpus bend is known, the tracker misleading for the first half second (the
    carpus point where the other bend would put it). Frame by frame every frame is ambiguous (the two bends fit
    within the noise); over the window the weak cue of the later frames outvotes the start, the true bend is held
    on every reliable frame and no frame is left ambiguous. (Frame by frame also holds it here, from its straight-leg
    start, which is nearer the true bend: the frames the window puts back are in the test above.) The proportions
    are the robot's (the footage is of the robot): fitted, a straighter carpus with a shorter fore leg reaches the
    same hoof, which is another question than the bend."""
    tracks, sk, x, g = _footage(spec, weak_carpus, seconds=2.0, carpus_noise_px=20.0)
    i_c = sk.names.index("L_carpus")
    cols = [N_POSE + j for j in sk.legs["fl"][0]]
    for f in range(15):  # half a second; the 45 frames after it say otherwise
        fr = _Frame(tracks.xy[f], tracks.likelihood[f] * sk.weight)
        xm = x[f].copy()
        xm[cols], _ = _mirror_bend(sk, x[f], g, fr, 3.0, "fl")
        tracks.xy[f, i_c] = project(sk, xm[None], g)[0, i_c]
    truth = u.rad_to_deg(x[:, N_POSE + sk.free_ids.index("joint.fl.carpus")])
    frame = lift(tracks, weak_carpus, spec, LiftSettings(bend_choice="frame", fit_proportions=False))
    window = lift(tracks, weak_carpus, spec, LiftSettings(bend_choice="window", fit_proportions=False))
    rel = window.reliable()
    assert rel.mean() > 0.7  # the misleading frames fit badly: unreliable, and still in the true bend
    off = np.abs(np.asarray(window.joints_deg["joint.fl.carpus"]) - truth) > 20.0
    assert not off.any()
    legs = window.summary["legs"]["fl"]
    assert legs["ambiguous_fraction"] == 0.0
    assert legs["second_bend_fraction"] > 0.5  # one frame alone cannot tell
    assert frame.summary["legs"]["fl"]["ambiguous_fraction"] > 0.5
    margin = np.array([np.nan if v is None else v for v in window.bend_margin["fl"]])
    assert np.nanmin(margin[:15]) >= LiftSettings().bend_margin  # the misleading start is outvoted
    assert window.settings["bend_choice"] == "window"
    assert leg_jumps(window)["fl"]["jumps"] == 0
    LiftResult.model_validate_json(window.model_dump_json())  # stored and read back


# ---------------------------------------------------------------------- frames the recording repeated
def test_repeated_frames_from_the_images(tmp_path):
    """A 15 fps motion written at 30 fps (every image twice, a third time once) is found; a still stretch is not
    a repeat."""
    from calflab.behave.video import write_avi

    rng = np.random.default_rng(0)
    src = [rng.integers(0, 255, (60, 80), dtype=np.uint8) for _ in range(12)]
    frames = []
    for i, im in enumerate(src):
        frames += [im, im] if i != 5 else [im, im, im]
    still = frames[-1]
    frames += [still] * 8  # a still scene: a long run, kept
    pal = np.stack([np.arange(256)] * 3, axis=1).astype(np.uint8)
    path = write_avi(tmp_path / "stutter.avi", np.stack(frames), 30.0, pal)
    rep = repeated_frames(path)
    expected = np.zeros(len(frames), dtype=bool)
    i = 0
    for k in range(12):
        n = 3 if k == 5 else 2
        expected[i + 1:i + n] = True
        i += n
    expected[i - 1:] = False  # the last image's own repeat joins the still run (9 identical frames)
    assert rep.tolist() == expected.tolist()
    assert not repeated_from_differences(np.zeros(5)).any()
    assert repeated_from_differences(np.array([10.0, 0.1, 10.0]), RepeatedFrames(rel_threshold=0.0)).sum() == 0


def test_retimed_clip_halves_the_stutter(spec):
    """A steady joint motion recorded with every frame twice: per frame it is nothing then a double step; re-timed,
    the steps are even and the peak speed is the motion's own."""
    m = load_lift_map("feral_calf_3d")
    tracks, sk, x, g = _footage(spec, m, seconds=1.0)
    res = lift(tracks, m, spec)
    true = np.asarray(res.joints_deg["joint.hl.stifle"])
    stutter = true.copy()
    rep = np.zeros(res.frames, dtype=bool)
    rep[1::2] = True
    stutter[1::2] = stutter[0:-1:2][: stutter[1::2].size]  # the recorder shows the previous image again
    res = res.model_copy(update={"joints_deg": {**res.joints_deg, "joint.hl.stifle": list(stutter)},
                                 "repeated": rep.tolist()})
    raw = np.asarray(lift_clip(res, spec, None).joints["joint.hl.stifle"])
    even = np.asarray(lift_clip(res, spec, None, retime=True).joints["joint.hl.stifle"])
    peak = lambda v: float(np.max(np.abs(np.diff(v[:-1]))))  # noqa: E731
    assert peak(raw) > 1.6 * peak(even)
    assert np.abs(even[:-1] - true[:-1]).max() < 0.25 * np.ptp(true)
    clip = lift_clip(res, spec, None, retime=True)
    assert sum(clip.meta["lift"]["retimed"]) == int(rep.sum())
    assert retime(np.array([0.0, 0.0, 2.0, 2.0, 4.0]), np.array([0, 1, 0, 1, 0], dtype=bool)).tolist() == \
        [0.0, 1.0, 2.0, 3.0, 4.0]
    json.dumps(clip.meta["lift"]["retimed"])
