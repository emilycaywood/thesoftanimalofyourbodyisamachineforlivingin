"""Does the camera move? The background's shift between frames (ADR-085).

A pan moves the whole image; the lift (weak perspective) then reads the animal
travelling. Here the background's shift between consecutive frames is measured
by phase correlation on small grey frames, in a band of ground around the
hooves (a hand-held camera that walks shifts the far background less than the
grass under the animal: parallax), with the animal's box (from the tracked
points, padded) filled with the band's mean so the animal itself does not
count. The shift is reported in px per frame and in the animal's body
lengths per second. It is a measurement of the image only; nothing is removed
from the lift (a turning camera and a turning animal stay apart only in
heading, which weak perspective does not mix with a pan).

Units: px, s.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def background_shift(video: Path, tracks: Any, width: int = 320, pad: float = 0.25) -> dict[str, Any]:
    """Per frame, the background's shift from the previous frame (px at full size). Needs OpenCV."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open {video}")
    xy = np.asarray(tracks.xy, dtype=float)
    shifts: list[float] = [0.0]
    vectors: list[tuple[float, float]] = [(0.0, 0.0)]  # (dx, dy) in the tracks' frame (px, y up)
    prev = None
    win = None
    f = 0
    scale = 1.0
    band: tuple[int, int] | None = None
    while True:
        ok, img = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        scale = width / g.shape[1]
        small = cv2.resize(g, (width, int(round(g.shape[0] * scale))))
        if band is None:  # the ground band: from the hooves' median height, a body height above and below it
            rows = -xy[:, :, 1]
            ok = np.isfinite(rows)
            if ok.any():
                low = float(np.nanmedian(np.nanmax(np.where(ok, rows, np.nan), axis=1)))
                tall = float(np.nanmedian(np.nanmax(np.where(ok, rows, np.nan), axis=1)
                                          - np.nanmin(np.where(ok, rows, np.nan), axis=1)))
                band = (int(max(0, (low - 0.6 * tall) * scale)), int(min(small.shape[0], (low + 0.8 * tall) * scale)))
                if band[1] - band[0] < 32:
                    band = (0, small.shape[0])
            else:
                band = (0, small.shape[0])
        if f < len(xy):
            pts = xy[f][np.isfinite(xy[f]).all(axis=1)]
            if len(pts):
                x0, x1 = pts[:, 0].min(), pts[:, 0].max()
                y0, y1 = (-pts[:, 1]).min(), (-pts[:, 1]).max()  # tracks are y up
                px, py = pad * (x1 - x0 + 1), pad * (y1 - y0 + 1)
                a, b = int(max(0, (x0 - px) * scale)), int(min(small.shape[1], (x1 + px) * scale))
                c, d = int(max(0, (y0 - py - 0.3 * (y1 - y0)) * scale)), int(min(small.shape[0], (y1 + py) * scale))
                small[c:d, a:b] = float(small[band[0]:band[1]].mean())
        small = np.ascontiguousarray(small[band[0]:band[1]])
        if win is None:
            win = cv2.createHanningWindow((small.shape[1], small.shape[0]), cv2.CV_32F)
        if prev is not None:
            (dx, dy), _resp = cv2.phaseCorrelate(prev, small, win)
            shifts.append(float(np.hypot(dx, dy)) / scale)
            vectors.append((float(dx) / scale, -float(dy) / scale))
        prev = small
        f += 1
    cap.release()
    return {"shift_px": shifts, "vector_px": vectors, "frames": f}


def camera_motion(video: Path, tracks: Any, body_px: float, fps: float, moves_bl_s: float,
                  shift: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summary: median and 90th percentile of the background's speed in body lengths/s, and whether the camera
    moves (median above ``moves_bl_s``). Shifts are averaged over half a second, so repeated frames (a screen
    recording: zero shift, then twice the shift) count right."""
    bs = shift or background_shift(video, tracks)
    v = np.asarray(bs["shift_px"][1:], dtype=float)
    w = max(1, int(round(0.5 * fps)))  # over half a second, so a repeated frame's zero and the next frame's double
    bl = (np.convolve(v, np.ones(w) / w, mode="valid") if len(v) >= w else np.array([v.mean() if len(v) else 0.0]))
    bl = bl * fps / max(body_px, 1e-9)  # shift average out
    med = float(np.median(bl))
    return {"method": "phase correlation of the background (animal masked)", "median_bl_s": round(med, 3),
            "p90_bl_s": round(float(np.percentile(bl, 90)), 3), "moves": med > moves_bl_s,
            "threshold_bl_s": moves_bl_s, "frames": bs["frames"]}
