"""Smoothing a clip cut from footage, so its speeds are the animal's, not the tracker's (ADR-082).

A pose tracker's points jitter from frame to frame by a few pixels. Through the
2D retarget or the 3D lift that jitter becomes joint angles that change by a
few degrees between frames, which at 30 fps reads as hundreds of deg/s: the
body report's peak speeds (and so the playable speed) were the tracker's, not
the calf's.

**The filter**: a Butterworth low-pass (order 2) run forward and backward
(``scipy.signal.sosfiltfilt``), so nothing lags: a peak stays on its frame.
Running it twice squares its response, so the design frequency is raised by
Winter's correction, ``(2^(1/2) - 1)^(-1/(2 order))`` (1.247 for order 2): the
cutoff named is where the two-pass filter halves the power. A filter rings at
a sharp corner; the smoothed angles are kept within the range the unsmoothed
ones covered over the video, so smoothing never invents an extreme (or a joint
limit the footage did not reach).

**The cutoff** (``method``):

* ``auto`` (the default for new projects): Winter's residual analysis on the
  whole video. For cutoffs from ``auto_range_hz[0]`` up to the highest the
  frame rate allows, the RMS difference between the raw and the filtered
  angles (all joints pooled) is computed. At high cutoffs that residual is
  noise and falls in a straight line; that line's value at 0 Hz is the noise's
  RMS. The cutoff is the lowest at which the residual is down to it.
  (D. A. Winter, *Biomechanics and Motor Control of Human Movement*, 4th ed.,
  2009, section 2.2.4.3.)
* ``lowpass``: a fixed ``cutoff_hz`` (6 Hz is the convention for walking
  kinematics).
* ``none``: the clip as the retarget gave it.

**What is smoothed**: every joint angle and the root (trunk path and
orientation; a 3D lift's heading, pitch and roll), over the whole video before
a clip is cut from it, so a cut's first and last frames have real neighbours.
The setting, the cutoff used and each joint's peak speed before and after are
recorded in the clip (:func:`provenance`).

Smoothing cannot tell a fit that jumps between a leg's two bends (an
``ambiguous`` frame of the 3D lift) from a fast movement: it only spreads such
a jump over a few frames.

Units: deg, mm, Hz.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from calflab.project.motions import MotionClip


class ClipSmoothing(BaseModel):
    """How clips cut from footage are smoothed (``FootageSettings.smoothing``)."""

    #: "auto": a low-pass whose cutoff comes from the video (Winter's residual analysis); "lowpass": at
    #: ``cutoff_hz``; "none": the clip as retargeted
    method: Literal["none", "lowpass", "auto"] = "auto"
    cutoff_hz: float = 6.0  # for "lowpass" (the biomechanics convention for walking; PROVISIONAL)
    order: int = 2
    #: the lowest cutoff "auto" may choose, and the step it searches in (Hz)
    auto_min_hz: float = 1.0
    auto_step_hz: float = 0.5

    def active(self, fps: float) -> bool:
        if self.method == "auto":
            return max_cutoff_hz(fps, self.order) > self.auto_min_hz
        return self.method == "lowpass" and 0 < self.cutoff_hz <= max_cutoff_hz(fps, self.order)


def _correction(order: int) -> float:
    """Winter's correction for a filter run twice: design frequency = cutoff / this."""
    return float((math.sqrt(2.0) - 1.0) ** (1.0 / (2 * order)))


def max_cutoff_hz(fps: float, order: int = 2) -> float:
    """The highest cutoff whose corrected design frequency stays under 95 % of the Nyquist frequency."""
    return 0.95 * 0.5 * fps * _correction(order)


def lowpass(v: np.ndarray, fps: float, cutoff_hz: float, order: int = 2) -> np.ndarray:
    """``v`` [frames] or [frames, k] low-passed along frames (zero lag); unchanged with too few frames."""
    from scipy.signal import butter, sosfiltfilt

    a = np.asarray(v, dtype=float)
    if a.shape[0] < 4 or cutoff_hz <= 0:
        return a
    wn = min(cutoff_hz / _correction(order) / (0.5 * fps), 0.99)
    sos = butter(order, wn, output="sos")
    pad = min(3 * (2 * len(sos) + 1), a.shape[0] - 1)
    return np.asarray(sosfiltfilt(sos, a, axis=0, padlen=pad))


def residual_cutoff(angles: np.ndarray, fps: float, s: ClipSmoothing) -> dict[str, Any]:
    """Winter's residual analysis of ``angles`` [frames, joints] (deg): the cutoff (Hz), the noise RMS (deg) and
    the residual curve."""
    top = max_cutoff_hz(fps, s.order)
    fcs = np.arange(s.auto_min_hz, top + 1e-9, s.auto_step_hz)
    res = np.array([float(np.sqrt(np.mean((angles - lowpass(angles, fps, fc, s.order)) ** 2))) for fc in fcs])
    hi = fcs >= fcs[0] + 0.6 * (fcs[-1] - fcs[0])  # the top 40 % of the band: noise
    if hi.sum() >= 2:
        _, noise = np.polyfit(fcs[hi], res[hi], 1)
    else:
        noise = float(res[-1])
    below = np.where(res <= noise)[0]
    fc = float(fcs[below[0]]) if below.size else float(fcs[-1])
    return {"cutoff_hz": round(fc, 2), "noise_rms_deg": round(float(max(noise, 0.0)), 3),
            "residual_deg": {f"{f:g}": round(float(r), 3) for f, r in zip(fcs, res, strict=True)}}


def smooth_clip(clip: MotionClip, s: ClipSmoothing) -> tuple[MotionClip, dict[str, Any]]:
    """A copy of ``clip`` with its joints and root low-passed (and a 3D lift's heading, pitch and roll in
    ``meta["lift"]``), and what was done (the cutoff used; for "auto", the residual analysis). With the setting
    off, an unchanged copy."""
    out = clip.model_copy(deep=True)
    fps = clip.fps
    if not s.active(fps) or not clip.joints:
        return out, {"applied": False}
    names = sorted(clip.joints)
    raw = np.stack([np.asarray(clip.joints[k], dtype=float) for k in names], axis=1)
    info: dict[str, Any] = {"applied": True}
    if s.method == "auto":
        info.update(residual_cutoff(raw, fps, s))
        fc = info["cutoff_hz"]
    else:
        fc = s.cutoff_hz
        info["cutoff_hz"] = fc
    sm = np.clip(lowpass(raw, fps, fc, s.order), raw.min(axis=0), raw.max(axis=0))  # no new extremes
    out.joints = {k: [round(float(x), 4) for x in sm[:, i]] for i, k in enumerate(names)}
    if clip.root_pos:
        p = lowpass(np.asarray(clip.root_pos, dtype=float), fps, fc, s.order)
        out.root_pos = [(float(a), float(b), float(c)) for a, b, c in p]
    if clip.root_quat:
        q = np.asarray(clip.root_quat, dtype=float)
        for f in range(1, len(q)):  # one hemisphere, so the components are continuous
            if float(np.dot(q[f], q[f - 1])) < 0:
                q[f] = -q[f]
        q = lowpass(q, fps, fc, s.order)
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        out.root_quat = [(float(a), float(b), float(c), float(d)) for a, b, c, d in q]
    lm = out.meta.get("lift")
    if isinstance(lm, dict):
        for k in ("heading_deg", "pitch_deg", "roll_deg"):
            if k in lm:
                lm[k] = [round(float(x), 3) for x in lowpass(np.asarray(lm[k]), fps, fc, s.order)]
    return out, info


def provenance(s: ClipSmoothing, fps: float, info: dict[str, Any], before: MotionClip | None = None,
               after: MotionClip | None = None) -> dict[str, Any]:
    """What a clip's ``meta["smoothing"]`` records: the setting, whether and how it applied, and (given the cut
    clip before and after) each joint's peak frame-to-frame speed both ways, deg/s."""
    d: dict[str, Any] = {**s.model_dump(mode="json"), "fps": fps, **info}
    if s.method != "none" and not info.get("applied"):
        d["note"] = (f"Not applied: the cutoff must be above 0 and at most {max_cutoff_hz(fps, s.order):.1f} Hz at "
                     f"{fps:g} fps.")
    elif info.get("applied"):
        how = ("chosen by Winter's residual analysis of the whole video (all joints)" if s.method == "auto" else
               "as set")
        d["filter"] = (f"Butterworth order {s.order}, forward and backward (zero lag), cutoff {info['cutoff_hz']:g} Hz "
                       f"{how}; Winter's correction for two passes; kept within the range the raw angles covered; "
                       "applied to the whole video before cutting.")
    if info.get("applied") and before is not None and after is not None:
        def peak(v: list[float]) -> float:
            a = np.asarray(v, dtype=float)
            return round(float(np.max(np.abs(np.diff(a)))) * fps, 1) if a.size > 1 else 0.0

        d["peak_speed_deg_s"] = {k: {"raw": peak(before.joints[k]), "smoothed": peak(after.joints[k])}
                                 for k in after.joints if k in before.joints}
    return d
