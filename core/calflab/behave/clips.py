"""Cutting clips out of a retargeted video (ADR-076).

The whole video is retargeted once against one standing reference (the
middle of its longest still stretch, when there is one), with the near legs
only. A candidate is then a slice of those angles; its far legs are added on
the slice: ``copy``, ``half_cycle`` (a gait cut to whole cycles, so rolling
by half a period wraps cleanly) or ``hold``. Every clip records where it came
from: the video's SHA-256, the frame range, the tracker's model and version,
the full retarget map, the cleaning and segmentation settings.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.behave.keypoints import KeypointTracks
from calflab.behave.retarget import RetargetMap, for_side, retarget
from calflab.project.motions import MotionClip


def standing_frame(candidates: list[dict[str, Any]]) -> int | None:
    """The middle frame of the longest still stretch, or None."""
    idle = [c for c in candidates if c["kind"] == "idle"]
    if not idle:
        return None
    c = max(idle, key=lambda c: c["end"] - c["start"])
    return int((c["start"] + c["end"]) // 2)


def near_angles(tracks: KeypointTracks, m: RetargetMap, standing: str | int | None,
                robot_height_mm: float | None) -> MotionClip:
    """The whole video retargeted (near legs only; the map's side settled)."""
    clip = retarget(tracks, m.model_copy(update={"far_side": "hold"}), tracks.source or "video", standing,
                    robot_height_mm)
    return clip


def cut(full: MotionClip, start: int, end: int, name: str, far_side: str = "copy", period_s: float | None = None,
        near_side: str = "left") -> MotionClip:
    """Frames [start, end) of a retargeted video as a clip, with its far legs added."""
    if not 0 <= start < end <= full.frames:
        raise ValueError(f"Frame range {start}-{end} is outside the video (0-{full.frames})")
    near, far = ("l", "r") if near_side == "left" else ("r", "l")
    joints = {k: list(v[start:end]) for k, v in full.joints.items()}
    period_frames = int(round((period_s or 0.0) * full.fps))
    for k in list(joints):
        leg, part = k.removeprefix("joint.").split(".", 1)
        if not leg.endswith(near):
            continue
        twin = f"joint.{leg[:-1]}{far}.{part}"
        if twin in joints:
            continue
        if far_side == "copy":
            joints[twin] = list(joints[k])
        elif far_side == "half_cycle":
            if period_frames < 2:
                raise ValueError("far_side half_cycle needs the gait's period")
            joints[twin] = [float(x) for x in np.roll(np.asarray(joints[k]), period_frames // 2)]
    root_pos = list(full.root_pos[start:end])
    if root_pos:
        x0 = root_pos[0][0]
        root_pos = [(p[0] - x0, p[1], p[2]) for p in root_pos]
    return MotionClip(name=name, fps=full.fps, joints={k: [round(float(x), 4) for x in v] for k, v in sorted(joints.items())},
                      root_pos=root_pos, root_quat=list(full.root_quat[start:end]), source="footage",
                      meta={"frames": end - start, "frame_range": [start, end], "far_side": far_side,
                            "period_s": period_s, "near_side": near_side})


def settle_side(tracks: KeypointTracks, m: RetargetMap) -> tuple[RetargetMap, dict[str, Any] | None]:
    """The map for the side the footage shows (``near_side: auto`` is decided here)."""
    if m.near_side == "auto":
        from calflab.behave.view import detect_near_side

        rep = detect_near_side(tracks, m)
        return for_side(m, rep["near_side"]), rep
    if m.side_names:
        return for_side(m, m.near_side), None  # type: ignore[arg-type]
    return m, None
