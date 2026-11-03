"""From a long video to candidate clips (ADR-076).

Three per-frame signals, all from the cleaned tracks and the retargeted
angles of the whole video:

* **trunk motion**: speed of the trunk's midpoint (between the rear and front
  trunk landmarks) in body lengths per second (the hip-shoulder distance is
  the length), so the camera's scale does not matter;
* **limb activity**: the mean absolute rate of change of the retargeted joint
  angles (deg/s);
* **periodicity**: in a moving stretch, the autocorrelation of the joint
  angles; its first peak gives the period, its height how regular it is.

A frame is *still* when both trunk motion and limb activity are under their
thresholds, otherwise *moving*. Runs shorter than ``min_run_s`` are merged
into their neighbours. A still run is an ``idle`` candidate; a moving run
whose angles repeat (peak correlation >= ``min_periodicity``) is a ``gait``
with its period, trimmed to whole cycles, and suggests ``far_side:
half_cycle`` (the far legs half a period behind); any other moving run is
``other``. A camera that follows the animal hides trunk motion, so gaits are
recognised by their periodic limbs, not by travel.

Thresholds are settings, stored with every candidate. They are first guesses
tested on synthetic footage (ADR-076): check the cuts on your own videos.

Units: frames, s, deg, deg/s, body lengths/s.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.behave.keypoints import KeypointTracks


class SegmentSettings(BaseModel):
    smooth_s: float = 0.5  # moving-average window of the signals
    still_trunk_bl_s: float = 0.05  # trunk motion under this (body lengths/s) ...
    still_activity_deg_s: float = 8.0  # ... and limb activity under this = still
    min_run_s: float = 0.6  # shorter runs join their neighbours
    min_idle_s: float = 1.0
    min_other_s: float = 0.6
    min_periodicity: float = 0.4  # autocorrelation peak for a gait
    period_range_s: tuple[float, float] = (0.3, 3.0)
    min_cycles: float = 2.0  # a gait candidate holds at least this many cycles
    max_turned_fraction: float = 0.5  # more of the stretch turned from the camera than this = flagged


def _smooth(v: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or v.size == 0:
        return v
    pad = np.pad(v, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, np.ones(n) / n, "valid")


def signals(tracks: KeypointTracks, rear: str | None, front: str | None, joints: dict[str, np.ndarray],
            settings: SegmentSettings, window: int | None = None) -> dict[str, np.ndarray]:
    """Per-frame trunk motion (body lengths/s), limb activity (deg/s) and the body length (px), smoothed over
    ``window`` frames (default ``settings.smooth_s``)."""
    fps = tracks.fps
    n = tracks.frames
    w = window if window is not None else max(1, int(round(settings.smooth_s * fps)))
    trunk = np.zeros(n)
    body_px = float("nan")
    if rear and front:
        r, f = tracks.point(rear), tracks.point(front)
        mid = (r + f) / 2.0
        body_px = float(np.nanmedian(np.hypot(*(f - r).T)))
        if body_px > 0 and n > 1:
            v = np.hypot(*np.gradient(mid, axis=0).T) * fps / body_px
            trunk = _smooth(np.nan_to_num(v), w)
    act = np.zeros(n)
    if joints and n > 1:
        rates = [np.abs(np.gradient(np.asarray(a, dtype=float))) * fps for a in joints.values()]
        act = _smooth(np.nan_to_num(np.mean(rates, axis=0)), w)
    return {"trunk_bl_s": trunk, "activity_deg_s": act, "body_px": np.array([body_px])}


def periodicity(joints: dict[str, np.ndarray], start: int, end: int, fps: float,
                period_range_s: tuple[float, float]) -> tuple[float | None, float]:
    """(period s or None, peak autocorrelation) of the angles in [start, end)."""
    if not joints or end - start < 4:
        return None, 0.0
    x = np.array([np.asarray(a, dtype=float)[start:end] for a in joints.values()])
    x = x - x.mean(axis=1, keepdims=True)
    energy = np.sum(x * x)
    if energy <= 1e-9:
        return None, 0.0
    n = x.shape[1]
    lo, hi = int(round(period_range_s[0] * fps)), min(int(round(period_range_s[1] * fps)), n // 2)
    if hi <= lo:
        return None, 0.0
    ac = np.array([np.sum(x[:, : n - k] * x[:, k:]) / energy * n / (n - k) for k in range(hi + 1)])
    best_k, best = None, 0.0
    for k in range(max(lo, 1), hi):  # the first local maximum in range
        if ac[k] >= ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > best:
            best_k, best = k, float(ac[k])
            break
    return (best_k / fps if best_k else None), best


def _runs(labels: np.ndarray) -> list[list[int]]:
    out: list[list[int]] = []
    for i, v in enumerate(labels):
        if out and labels[out[-1][0]] == v:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return out


def segment(tracks: KeypointTracks, rear: str | None, front: str | None, joints: dict[str, np.ndarray],
            settings: SegmentSettings | None = None, turned: list[bool] | None = None) -> dict[str, Any]:
    """Candidate clips of the video: [{start, end, kind, period_s, far_side, ...}] and the signals."""
    s = settings or SegmentSettings()
    fps = tracks.fps
    sig = signals(tracks, rear, front, joints, s)
    trunk, act = sig["trunk_bl_s"], sig["activity_deg_s"]
    moving = (trunk >= s.still_trunk_bl_s) | (act >= s.still_activity_deg_s)
    labels = moving.astype(int)
    min_run = max(1, int(round(s.min_run_s * fps)))
    changed = True
    while changed:  # merge short runs into the longer neighbour
        changed = False
        runs = _runs(labels)
        if len(runs) <= 1:
            break
        for k, (a, b) in enumerate(runs):
            if b - a < min_run:
                left = runs[k - 1] if k > 0 else None
                right = runs[k + 1] if k + 1 < len(runs) else None
                nb = max((r for r in (left, right) if r), key=lambda r: r[1] - r[0])
                labels[a:b] = labels[nb[0]]
                changed = True
                break
    # the smoothing widens moving stretches by half a window each side: give back the edge frames that are still
    fine = signals(tracks, rear, front, joints, s, window=3)
    still_fine = (fine["trunk_bl_s"] < s.still_trunk_bl_s) & (fine["activity_deg_s"] < s.still_activity_deg_s)
    half = max(1, int(round(s.smooth_s * fps / 2)))
    for a, b in _runs(labels):
        if labels[a] != 1:
            continue
        a2, b2 = a, b
        while a2 < min(b, a + half) and still_fine[a2] and a > 0:
            a2 += 1
        while b2 > max(a2, b - half) and still_fine[b2 - 1] and b < len(labels):
            b2 -= 1
        if a2 > a:
            labels[a:a2] = 0
        if b2 < b:
            labels[b2:b] = 0
    cands: list[dict[str, Any]] = []
    for a, b in _runs(labels):
        seconds = (b - a) / fps
        row: dict[str, Any] = {"start": a, "end": b, "seconds": round(seconds, 3),
                               "trunk_bl_s": round(float(np.mean(trunk[a:b])), 4),
                               "activity_deg_s": round(float(np.mean(act[a:b])), 2)}
        if labels[a] == 0:
            if seconds < s.min_idle_s:
                continue
            row.update(kind="idle", period_s=None, far_side="copy", periodicity=0.0)
        else:
            period, peak = periodicity(joints, a, b, fps, s.period_range_s)
            if period is not None and peak >= s.min_periodicity and seconds >= s.min_cycles * period:
                cycles = int(seconds / period)
                b2 = a + int(round(cycles * period * fps))  # whole cycles, so the clip loops cleanly
                row.update(kind="gait", end=b2, seconds=round((b2 - a) / fps, 3), period_s=round(period, 3),
                           cycles=cycles, far_side="half_cycle", periodicity=round(peak, 3))
            else:
                if seconds < s.min_other_s:
                    continue
                row.update(kind="other", period_s=None, far_side="copy", periodicity=round(peak, 3))
        if turned is not None:
            frac = float(np.mean(turned[row["start"]:row["end"]])) if row["end"] > row["start"] else 0.0
            row["turned_fraction"] = round(frac, 3)
            row["view_ok"] = frac <= s.max_turned_fraction
        cands.append(row)
    return {"candidates": cands, "settings": s.model_dump(mode="json"),
            "signals": {"trunk_bl_s": [round(float(v), 4) for v in trunk],
                        "activity_deg_s": [round(float(v), 2) for v in act]},
            "body_px": None if np.isnan(sig["body_px"][0]) else round(float(sig["body_px"][0]), 1)}
