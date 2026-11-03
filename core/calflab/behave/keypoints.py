"""Keypoint tracks from reference footage (ADR-073).

CALFLAB does not track video itself. A pose tracker (DeepLabCut, SLEAP,
Anipose, or clicking points by hand in any video tool) produces 2D image
coordinates of named body landmarks per frame; this module reads them:

* **DeepLabCut CSV**: three header rows (scorer / bodyparts / coords), then
  ``frame, x, y, likelihood`` per body part.
* **Long CSV**: one row per frame and landmark, columns ``frame, keypoint, x,
  y`` and optionally ``likelihood``.
* **Wide CSV**: one row per frame, columns ``frame`` and ``<name>_x``,
  ``<name>_y`` (optionally ``<name>_likelihood``).

Coordinates stay in image units (pixels); only angles are taken from them, so
the camera's scale never matters. Image y points down: it is flipped so up
is positive. Points below a likelihood threshold become gaps, short gaps are
filled by linear interpolation, and a centred moving average removes jitter.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

Format = Literal["auto", "dlc", "long", "wide"]


class KeypointTracks(BaseModel):
    """2D landmark positions per frame (image units, y up). NaN = not seen."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    fps: float
    names: list[str]
    xy: np.ndarray  # [frames, landmarks, 2]
    likelihood: np.ndarray  # [frames, landmarks]; 1 where the format has none
    source: str = ""
    #: who made the tracks: {tracker, model, version, params} (ADR-077); empty for a CSV read directly
    model: dict[str, Any] = Field(default_factory=dict)
    #: (width, height) of the video in pixels, when the tracks come from a video
    image_size: tuple[int, int] | None = None

    @property
    def frames(self) -> int:
        return int(self.xy.shape[0])

    def index(self, name: str) -> int:
        low = [n.lower() for n in self.names]
        return low.index(name.lower())

    def has(self, name: str) -> bool:
        return name.lower() in (n.lower() for n in self.names)

    def point(self, name: str) -> np.ndarray:
        """[frames, 2] for one landmark."""
        return self.xy[:, self.index(name), :]


def _num(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _sniff(rows: list[list[str]]) -> Format:
    if len(rows) > 3 and rows[0] and rows[0][0].strip().lower() == "scorer":
        return "dlc"
    head = [h.strip().lower() for h in rows[0]] if rows else []
    if "keypoint" in head or "bodypart" in head or "landmark" in head:
        return "long"
    if any(h.endswith("_x") for h in head):
        return "wide"
    raise ValueError("Cannot tell the format: expected a DeepLabCut CSV (scorer/bodyparts/coords header), a long CSV "
                     "(frame, keypoint, x, y) or a wide CSV (frame, <name>_x, <name>_y)")


def parse_tracks(text: str, fps: float, fmt: Format = "auto", source: str = "") -> KeypointTracks:
    """Read keypoint tracks from CSV text. ``fps`` is the footage's frame rate."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("The file is empty")
    kind = _sniff(rows) if fmt == "auto" else fmt
    if kind == "dlc":
        parts, coords = rows[1], rows[2]
        names: list[str] = []
        cols: dict[tuple[str, str], int] = {}
        for i in range(1, len(parts)):
            name, c = parts[i].strip(), coords[i].strip().lower()
            if name not in names:
                names.append(name)
            cols[(name, c)] = i
        body = rows[3:]
        xy = np.full((len(body), len(names), 2), np.nan)
        lk = np.ones((len(body), len(names)))
        for f, r in enumerate(body):
            for k, n in enumerate(names):
                xy[f, k, 0] = _num(r[cols[(n, "x")]])
                xy[f, k, 1] = _num(r[cols[(n, "y")]])
                if (n, "likelihood") in cols:
                    lk[f, k] = _num(r[cols[(n, "likelihood")]])
    elif kind == "long":
        head = [h.strip().lower() for h in rows[0]]
        key = next(h for h in ("keypoint", "bodypart", "landmark") if h in head)
        fi, ki, xi, yi = head.index("frame"), head.index(key), head.index("x"), head.index("y")
        li = head.index("likelihood") if "likelihood" in head else None
        recs = rows[1:]
        frames = sorted({int(float(r[fi])) for r in recs})
        names = list(dict.fromkeys(r[ki].strip() for r in recs))
        fpos = {f: i for i, f in enumerate(frames)}
        xy = np.full((len(frames), len(names), 2), np.nan)
        lk = np.ones((len(frames), len(names)))
        for r in recs:
            f, k = fpos[int(float(r[fi]))], names.index(r[ki].strip())
            xy[f, k] = (_num(r[xi]), _num(r[yi]))
            if li is not None:
                lk[f, k] = _num(r[li])
    else:
        head = [h.strip() for h in rows[0]]
        names = [h[:-2] for h in head if h.lower().endswith("_x")]
        body = rows[1:]
        xy = np.full((len(body), len(names), 2), np.nan)
        lk = np.ones((len(body), len(names)))
        low = [h.lower() for h in head]
        for f, r in enumerate(body):
            for k, n in enumerate(names):
                xy[f, k, 0] = _num(r[low.index(f"{n.lower()}_x")])
                xy[f, k, 1] = _num(r[low.index(f"{n.lower()}_y")])
                if f"{n.lower()}_likelihood" in low:
                    lk[f, k] = _num(r[low.index(f"{n.lower()}_likelihood")])
    xy[:, :, 1] = -xy[:, :, 1]  # image y points down
    return KeypointTracks(fps=fps, names=names, xy=xy, likelihood=np.nan_to_num(lk, nan=0.0), source=source)


def read_tracks(path: Path, fps: float, fmt: Format = "auto") -> KeypointTracks:
    return parse_tracks(Path(path).read_text(encoding="utf-8-sig"), fps, fmt, source=Path(path).name)


def clean(tracks: KeypointTracks, min_likelihood: float = 0.6, max_gap_frames: int = 10, smooth_frames: int = 3) -> tuple[KeypointTracks, dict[str, float]]:
    """Drop low-confidence points, fill gaps up to ``max_gap_frames`` by linear
    interpolation, smooth with a centred moving average. Returns the cleaned
    tracks and, per landmark, the fraction of frames still missing."""
    xy = tracks.xy.copy()
    xy[tracks.likelihood < min_likelihood] = np.nan
    n = xy.shape[0]
    missing: dict[str, float] = {}
    for k, name in enumerate(tracks.names):
        for c in range(2):
            v = xy[:, k, c]
            ok = ~np.isnan(v)
            if ok.sum() >= 2:
                idx = np.arange(n)
                filled = np.interp(idx, idx[ok], v[ok])
                # only fill short gaps; long ones stay missing
                gap = np.zeros(n, dtype=int)
                run = 0
                for i in range(n):
                    run = run + 1 if not ok[i] else 0
                    gap[i] = run
                for i in range(n - 2, -1, -1):
                    if not ok[i] and gap[i + 1] > gap[i]:
                        gap[i] = gap[i + 1]
                inside = (idx > idx[ok][0]) & (idx < idx[ok][-1])
                use = ok | ((gap <= max_gap_frames) & inside)
                v = np.where(use, filled, np.nan)
            if smooth_frames > 1:
                w = smooth_frames
                pad = np.pad(v, (w // 2, w - 1 - w // 2), mode="edge")
                valid = ~np.isnan(pad)
                s = np.convolve(np.where(valid, pad, 0.0), np.ones(w), "valid")
                cnt = np.convolve(valid.astype(float), np.ones(w), "valid")
                v = np.where(~np.isnan(v), s / np.maximum(cnt, 1), np.nan)
            xy[:, k, c] = v
        missing[name] = float(np.mean(np.isnan(xy[:, k, 0])))
    return tracks.model_copy(update={"xy": xy}), missing
