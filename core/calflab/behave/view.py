"""Which side of the animal faces the camera, and is it a side view? (ADR-076)

* **Near side.** An animal that faces right in the image shows the camera its
  right side; facing left, its left side. The facing is the direction from the
  rear to the front trunk landmark, taken over the whole video. When the
  tracker gives both sides (AP-10K: ``L_Hip`` and ``R_Hip``), the side whose
  points are tracked more confidently is reported too, as a cross-check (the
  far legs are hidden behind the body, so their points are less certain).
* **Camera view.** In a true side view the left and right hips (and
  shoulders) lie on top of each other; turned by a yaw angle they separate
  horizontally by about W sin(yaw) while the trunk shortens to L cos(yaw), so
  separation / trunk length = (W / L) tan(yaw). W / L is an assumption about
  calves (the map's ``view.width_over_length``). Where only one side is
  tracked, the yaw is unknown and the report says so; the trunk's apparent
  length against the video's own longest stretch still shows frames where the
  animal turned.

Units: image pixels, degrees.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.behave.keypoints import KeypointTracks


def _first(tracks: KeypointTracks, names: list[str]) -> str | None:
    for n in names:
        if tracks.has(n):
            return n
    return None


def _alts(lm: Any, side_names: dict[str, str]) -> list[str]:
    """Every concrete name a landmark entry may stand for (``{side}`` filled with each side's name)."""
    items = [lm] if isinstance(lm, str) else list(lm)
    out: list[str] = []
    for x in items:
        if "{side}" in x:
            out += [x.replace("{side}", s) for s in side_names.values()] if side_names else []
        else:
            out.append(x)
    return out


def detect_near_side(tracks: KeypointTracks, m: Any) -> dict[str, Any]:
    """Near side from the facing direction (and, with two-sided landmarks, the tracking confidence)."""
    out: dict[str, Any] = {"near_side": "left" if m.joints_side == "left" else "right"}
    if len(m.trunk) == 2:
        rear = _first(tracks, _alts(m.trunk[0], m.side_names))
        front = _first(tracks, _alts(m.trunk[1], m.side_names))
        if rear and front:
            ok = tracks.likelihood[:, [tracks.index(rear), tracks.index(front)]].min(axis=1) >= m.min_likelihood
            dx = (tracks.point(front)[:, 0] - tracks.point(rear)[:, 0])[ok]
            dx = dx[~np.isnan(dx)]
            if dx.size:
                facing = "right" if np.median(dx) > 0 else "left"
                out.update(facing=facing, by_facing=facing, facing_frames=int(dx.size),
                           facing_consistency=round(float(np.mean(np.sign(dx) == np.sign(np.median(dx)))), 3))
                out["near_side"] = facing  # facing right shows the right side
    if m.side_names:
        conf = {}
        for side, tag in m.side_names.items():
            idx = [i for i, n in enumerate(tracks.names) if n.startswith(tag + "_") or n.startswith(tag + " ")]
            if idx:
                conf[side] = round(float(np.nanmean(tracks.likelihood[:, idx])), 3)
        if len(conf) == 2:
            by_conf = max(conf, key=lambda k: conf[k])
            out.update(confidence=conf, by_confidence=by_conf)
            if "by_facing" not in out:
                out["near_side"] = by_conf
            out["agree"] = out.get("by_facing", by_conf) == by_conf
    out["method"] = "facing" if "by_facing" in out else ("confidence" if "by_confidence" in out else "map default")
    return out


def view_report(tracks: KeypointTracks, m: Any) -> dict[str, Any]:
    """Per-frame yaw estimate (deg, NaN = unknown) and turned flags, and a verdict for the whole video."""
    n = tracks.frames
    yaw = np.full(n, np.nan)
    lk = tracks.likelihood
    thr = m.min_likelihood
    seps = []
    for pair in m.view.pairs:
        a, b = (_first(tracks, _alts(x, m.side_names)) for x in pair[:2])
        if a and b and a != b:
            ok = (lk[:, tracks.index(a)] >= thr) & (lk[:, tracks.index(b)] >= thr)
            sep = np.abs(tracks.point(a)[:, 0] - tracks.point(b)[:, 0])
            seps.append(np.where(ok, sep, np.nan))
    trunk_len = np.full(n, np.nan)
    if len(m.trunk) == 2:
        rear = _first(tracks, _alts(m.trunk[0], m.side_names))
        front = _first(tracks, _alts(m.trunk[1], m.side_names))
        if rear and front:
            ok = (lk[:, tracks.index(rear)] >= thr) & (lk[:, tracks.index(front)] >= thr)
            d = np.abs(tracks.point(front)[:, 0] - tracks.point(rear)[:, 0])
            trunk_len = np.where(ok, d, np.nan)
    if seps:
        with np.errstate(all="ignore"):
            sep = np.nanmean(np.vstack(seps), axis=0)
            ratio = sep / trunk_len
        yaw = u.rad_to_deg(np.arctan(ratio / max(m.view.width_over_length, 1e-6)))
    with np.errstate(all="ignore"):
        best = np.nanpercentile(trunk_len, 90) if np.any(~np.isnan(trunk_len)) else float("nan")
        shortened = trunk_len / best if best and best > 0 else np.full(n, np.nan)
    # a frame is "turned" if its yaw is over the limit, or (one side only) the trunk looks much shorter than at best
    limit = m.view.max_oblique_deg
    turned = np.where(~np.isnan(yaw), yaw > limit, shortened < math.cos(u.deg_to_rad(limit)))
    known = ~np.isnan(yaw)
    med = float(np.nanmedian(yaw)) if known.any() else None
    if med is not None:
        verdict = "side view OK" if med <= limit else "too oblique"
        note = (f"Median yaw from a side view about {med:.0f} deg (limit {limit:.0f}), from the left/right separation of "
                f"{', '.join('/'.join(p) for p in m.view.pairs)} with an assumed width/length of "
                f"{m.view.width_over_length:g}.")
    elif np.any(~np.isnan(shortened)):
        verdict = "unknown (one side tracked)"
        note = ("Only one side is tracked, so the yaw cannot be measured; frames where the trunk looks shorter than "
                f"cos({limit:.0f} deg) of its longest are marked as turned.")
    else:
        verdict = "unknown"
        note = "The trunk landmarks are not tracked."
    return {
        "verdict": verdict, "note": note, "median_yaw_deg": None if med is None else round(med, 1),
        "turned_fraction": round(float(np.mean(turned)), 3), "limit_deg": limit,
        "yaw_deg": [None if math.isnan(v) else round(float(v), 1) for v in yaw],
        "turned": [bool(t) for t in turned],
    }
