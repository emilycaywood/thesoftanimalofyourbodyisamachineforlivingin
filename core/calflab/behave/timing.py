"""Repeated frames: a recording whose frame rate is higher than its source's (ADR-083).

A screen recording of a video playing (or a phone that drops frames) writes
some images twice: the file says 30 fps, but the animal moves only in every
other frame, or in two of three. Per frame, the motion is then nothing, then
two frames' worth at once, and every joint's peak speed is about doubled. A
low-pass spreads such a step but cannot tell it from a fast movement.

The repeats are found in the images themselves, not in the tracked points: a
frame is a repeat when it differs from the previous one by less than
``rel_threshold`` of the video's 90th-percentile difference between
consecutive frames (mean absolute difference of grey levels, on a reduced
copy). A very slow movement can pass for a repeat too; interpolating it
between its neighbours changes almost nothing. Only
short runs count (``max_run``): a longer run of identical frames is a still
scene or a frozen recording, not a stutter, and is kept as it is.

Clips are then re-timed: a value at a repeated frame is replaced by linear
interpolation between the frames around it, i.e. each new image is taken to
show the animal at the time it first appears. The lift itself is not changed.

Units: grey levels 0-255, frames.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel

log = logging.getLogger(__name__)


class RepeatedFrames(BaseModel):
    """How clips treat frames the recording repeated. First guesses from one screen recording (PROVISIONAL)."""

    #: "interpolate": re-time clips across repeated frames; "keep": use every frame as it is (as before ADR-083)
    method: Literal["interpolate", "keep"] = "interpolate"
    rel_threshold: float = 0.15  # a repeat differs from the previous frame by less than this share of the 90th pct
    max_run: int = 3  # longer runs of identical frames are a still scene or a frozen recording: kept


def frame_differences(path: Path, width: int = 320) -> np.ndarray:
    """[frames - 1] mean absolute grey-level difference between consecutive frames (0-255), on frames reduced to
    ``width`` px."""
    from calflab.behave.video import open_video

    out: list[float] = []
    prev: np.ndarray | None = None
    with open_video(Path(path)) as r:
        for _, img in r.frames():
            step = max(1, img.shape[1] // max(width, 1))
            grey = img[::step, ::step].astype(np.float32).mean(axis=2)
            if prev is not None:
                out.append(float(np.mean(np.abs(grey - prev))))
            prev = grey
    return np.asarray(out)


def repeated_from_differences(diffs: np.ndarray, s: RepeatedFrames | None = None) -> np.ndarray:
    """[frames] True where a frame repeats the previous one (the first frame never does); runs longer than
    ``max_run`` are not counted."""
    s = s or RepeatedFrames()
    d = np.asarray(diffs, dtype=float)
    rep = np.zeros(d.size + 1, dtype=bool)
    if d.size == 0:
        return rep
    moving = d[d > 0]
    if moving.size == 0:
        return rep
    # against a high percentile, not the median: in a recording at twice its source's rate half the steps are
    # repeats, and the median would be one of them
    rep[1:] = d < s.rel_threshold * float(np.percentile(d, 90))
    i = 0
    while i < rep.size:  # drop long runs: still scenes, frozen recordings
        if not rep[i]:
            i += 1
            continue
        j = i
        while j < rep.size and rep[j]:
            j += 1
        if j - i > s.max_run:
            rep[i:j] = False
        i = j
    return rep


def repeated_frames(path: Path, s: RepeatedFrames | None = None) -> np.ndarray:
    """[frames] repeated frames of a video file (see :func:`repeated_from_differences`)."""
    return repeated_from_differences(frame_differences(path), s)


def retime(v: np.ndarray, repeated: np.ndarray) -> np.ndarray:
    """Values at repeated frames replaced by linear interpolation between the frames around them (held at the
    ends)."""
    v = np.asarray(v, dtype=float)
    rep = np.asarray(repeated, dtype=bool)
    if rep.size != v.size or not rep.any() or rep.all():
        return v
    idx = np.arange(v.size)
    return np.interp(idx, idx[~rep], v[~rep])
