"""Can this body play a clip? (ADR-073)

Per joint the robot actuates: whether the clip moves it, how much of the clip
lies outside its range (the controller clamps those frames, so the robot
plays a flattened version), and the clip's fastest angle change against the
servo's no-load speed at that joint (a 2:1 belt halves it). From those, the
slow-down that would bring the whole clip within the servos' speed. Nothing
is changed here: the clip stays as the footage gave it.

Units: degrees, deg/s, s.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.model.spec import RobotSpec
from calflab.project.motions import MotionClip


def clip_report(clip: MotionClip, spec: RobotSpec, lib: Any) -> dict[str, Any]:
    trans = {t.id: t for t in spec.transmissions}
    rows = []
    slowest = 1.0
    out_frames = 0.0
    for a in spec.actuators:
        j = spec.joint(a.joint)
        comp = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        ratio = tr.ratio if tr else 1.0
        limit = comp.no_load_speed_rpm * 6.0 / ratio  # deg/s at the joint
        lo, hi = j.range_deg
        row: dict[str, Any] = {"joint": j.id, "range_deg": [lo, hi], "speed_limit_deg_s": round(limit, 1)}
        vals = clip.joints.get(j.id)
        if vals is None:
            row.update(in_clip=False, note="not in the clip: holds its standing angle")
            rows.append(row)
            continue
        v = np.asarray(vals, dtype=float)
        outside = (v < lo) | (v > hi)
        speed = np.abs(np.diff(v)) * clip.fps if len(v) > 1 else np.zeros(1)
        peak = float(np.max(speed)) if speed.size else 0.0
        factor = peak / limit if limit > 0 else float("inf")
        slowest = max(slowest, factor)
        out_frames = max(out_frames, float(np.mean(outside)))
        row.update(
            in_clip=True,
            min_deg=round(float(np.min(v)), 2),
            max_deg=round(float(np.max(v)), 2),
            out_of_range_fraction=round(float(np.mean(outside)), 3),
            peak_speed_deg_s=round(peak, 1),
            speed_ratio=round(factor, 3),
        )
        rows.append(row)
    unused = sorted(set(clip.joints) - {r["joint"] for r in rows})
    if out_frames > 0 and slowest > 1.0:
        verdict = "clamped_and_too_fast"
    elif out_frames > 0:
        verdict = "clamped"
    elif slowest > 1.0:
        verdict = "too_fast"
    else:
        verdict = "plays"
    notes = {
        "plays": "Every joint stays in its range and within its servo's speed.",
        "clamped": "Some frames lie outside a joint's range: the robot plays them at the limit.",
        "too_fast": f"Faster than the servos at some joint: play it at {1 / slowest:.2f}x speed or slower.",
        "clamped_and_too_fast": f"Clamped at a range limit, and faster than the servos: play it at {1 / slowest:.2f}x "
                                "speed or slower.",
    }
    return {
        "clip": clip.id,
        "name": clip.name,
        "duration_s": round(clip.duration_s, 3),
        "fps": clip.fps,
        "joints": rows,
        "clip_joints_not_on_body": unused,
        "max_speed_ratio": round(slowest, 3),
        "max_out_of_range_fraction": round(out_frames, 3),
        "playable_speed": round(min(1.0, 1.0 / slowest), 3),
        "verdict": verdict,
        "note": notes[verdict],
    }
