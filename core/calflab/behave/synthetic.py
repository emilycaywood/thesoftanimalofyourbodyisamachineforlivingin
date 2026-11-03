"""Synthetic footage: a stick calf drawn from the robot's own forward kinematics (ADR-076).

Used to test the whole pipeline (video file -> tracker -> retarget ->
segmentation -> clips) against angles that are known exactly, and as a demo
when no real footage is at hand. The feral calf is posed by forward
kinematics from a script of stretches (standing still, walking with a known
period, pawing), moved along the ground while walking, and drawn from its
left side (it faces left in the image, so its left legs are the near ones):
far legs in light grey, near legs in dark grey, and one coloured disc per
landmark. The ``synthetic`` tracker finds those discs by colour.

Units: mm (body), pixels (image), s, degrees.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.model.spec import RobotSpec
from calflab.model.xform import quat_rotate

#: landmark -> (body, where on it, RGB marker colour). ``where``: "origin", "end" (end of its tube), or a local
#: point (mm). Names are those of the ``feral_calf_side`` retarget map.
MARKERS: dict[str, tuple[str, Any, tuple[int, int, int]]] = {
    "hip": ("leg.h{s}.femur", "origin", (230, 25, 75)),
    "stifle": ("leg.h{s}.tibia", "origin", (60, 180, 75)),
    "hock": ("leg.h{s}.cannon", "origin", (0, 130, 200)),
    "hind_fetlock": ("leg.h{s}.cannon", "end", (245, 130, 48)),
    "shoulder": ("leg.f{s}.upper", "origin", (145, 30, 180)),
    "withers": ("trunk", "withers", (240, 50, 230)),
    "carpus": ("leg.f{s}.cannon", "origin", (128, 128, 0)),
    "fore_fetlock": ("leg.f{s}.cannon", "end", (0, 0, 128)),
}
STICKS = [("hip", "stifle"), ("stifle", "hock"), ("hock", "hind_fetlock"), ("shoulder", "carpus"),
          ("carpus", "fore_fetlock"), ("hip", "shoulder")]
#: palette: 0 background, 1 far legs, 2 near legs and trunk, 3 ground, 4.. markers
BASE_PALETTE = [(250, 250, 245), (200, 200, 200), (70, 70, 70), (150, 120, 90)]


class Stretch(BaseModel):
    """One stretch of the script."""

    kind: str = "stand"  # stand | walk | paw
    seconds: float = 2.0
    period_s: float = 1.2  # walk and paw
    speed_mm_s: float = 150.0  # walk: ground speed of the trunk


class SyntheticScript(BaseModel):
    stretches: list[Stretch] = Field(default_factory=lambda: [
        Stretch(kind="stand", seconds=2.0), Stretch(kind="walk", seconds=4.0), Stretch(kind="stand", seconds=2.0)])
    fps: float = 20.0
    width: int = 400
    height: int = 180
    px_per_mm: float = 0.25
    marker_radius: int = 3


def gait_angles(kind: str, phase: float) -> dict[str, float]:
    """Joint angles (deg relative to standing) of the near (left) legs at gait phase 0..1; the far legs use
    phase + 0.5. Positive = flexion (stifle, hock, carpus) or the leg swung back (shoulder)."""
    s = math.sin(2 * math.pi * phase)
    c = math.cos(2 * math.pi * phase)
    if kind == "walk":
        return {"stifle": 10.0 * s, "hock": 6.0 * (1.0 - c), "shoulder": -12.0 * s, "carpus": 12.5 * (1.0 - c)}
    if kind == "paw":
        return {"stifle": 0.0, "hock": 0.0, "shoulder": -15.0 * max(0.0, s), "carpus": 60.0 * max(0.0, s)}
    return {"stifle": 0.0, "hock": 0.0, "shoulder": 0.0, "carpus": 0.0}


def script_angles(script: SyntheticScript) -> tuple[np.ndarray, list[dict[str, float]], list[dict[str, Any]]]:
    """Per frame: trunk x (mm), joint angles (deg relative to standing, both sides) and the ground truth of the
    stretches (start/end frame, kind, period)."""
    xs: list[float] = []
    angles: list[dict[str, float]] = []
    truth: list[dict[str, Any]] = []
    x = 0.0
    f0 = 0
    for st in script.stretches:
        n = int(round(st.seconds * script.fps))
        for k in range(n):
            t = k / script.fps
            phase = (t / st.period_s) % 1.0 if st.kind in ("walk", "paw") else 0.0
            near = gait_angles(st.kind, phase)
            far = gait_angles(st.kind, (phase + 0.5) % 1.0) if st.kind == "walk" else gait_angles("stand", 0.0)
            a = {}
            for side, vals in (("l", near), ("r", far)):
                a[f"joint.h{side}.stifle"] = vals["stifle"]
                a[f"joint.h{side}.hock"] = vals["hock"]
                a[f"joint.f{side}.shoulder"] = vals["shoulder"]
                a[f"joint.f{side}.carpus"] = vals["carpus"]
            angles.append(a)
            xs.append(x)
            if st.kind == "walk":
                x += st.speed_mm_s / script.fps
        truth.append({"kind": st.kind, "start": f0, "end": f0 + n, "period_s": st.period_s if st.kind != "stand" else None})
        f0 += n
    return np.array(xs), angles, truth


def landmarks(spec: RobotSpec, angles: dict[str, float], trunk_x: float, side: str = "l") -> dict[str, tuple[float, float]]:
    """(x, z) in mm of every marker of one side with the joints at ``angles`` (deg relative to standing)."""
    rest = spec.rest_angles()
    full = {j: rest[j] + angles.get(j, 0.0) for j in rest}
    root = spec.root.pos
    poses = spec.world_poses(full, root_pos=(root[0] + trunk_x, root[1], root[2]))
    out: dict[str, tuple[float, float]] = {}
    shoulder_body = f"leg.f{side}.upper"
    for name, (body, where, _) in MARKERS.items():
        bid = body.format(s=side)
        bp, bq = poses[bid]
        if where == "origin":
            p = bp
        elif where == "end":
            tube = next(g for g in spec.body(bid).geoms if g.id.endswith(".tube"))
            r = quat_rotate(bq, (0.0, 0.0, -tube.size[1]))
            p = (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2])
        else:  # withers: 60 mm above the shoulder axle, in the trunk's frame
            sp = poses[shoulder_body][0]
            r = quat_rotate(bq, (0.0, 0.0, 60.0))
            p = (sp[0] + r[0], sp[1] + r[1], sp[2] + r[2])
        out[name] = (p[0], p[2])
    return out


def palette() -> np.ndarray:
    return np.array(BASE_PALETTE + [c for _, _, c in MARKERS.values()], dtype=np.uint8)


def _line(img: np.ndarray, a: tuple[float, float], b: tuple[float, float], value: int, width: int = 2) -> None:
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2) + 2
    for t in np.linspace(0.0, 1.0, n):
        x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        img[max(0, int(y) - width // 2):int(y) + (width + 1) // 2, max(0, int(x) - width // 2):int(x) + (width + 1) // 2] = value


def _disc(img: np.ndarray, c: tuple[float, float], r: int, value: int) -> None:
    h, w = img.shape
    yy, xx = np.ogrid[:h, :w]
    img[(xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= r * r] = value


def render(spec: RobotSpec, script: SyntheticScript) -> tuple[np.ndarray, dict[str, Any]]:
    """Frames ([n, h, w] palette indices) and the ground truth: angles per frame, stretches, marker pixels."""
    xs, angles, truth = script_angles(script)
    w, h, k = script.width, script.height, script.px_per_mm
    ground_y = h - 10
    x0 = w - 20.0 - 300.0 * k  # the calf faces left (world +x = image -x); its hind hooves start 20 px from the edge

    def px(p: tuple[float, float]) -> tuple[float, float]:
        return (x0 - p[0] * k, ground_y - p[1] * k)

    frames = np.zeros((len(xs), h, w), dtype=np.uint8)
    points = np.zeros((len(xs), len(MARKERS), 2))
    names = list(MARKERS)
    for f, (x, a) in enumerate(zip(xs, angles, strict=True)):
        img = frames[f]
        img[ground_y:, :] = 3
        far = {n: px(p) for n, p in landmarks(spec, a, x, "r").items()}
        near = {n: px(p) for n, p in landmarks(spec, a, x, "l").items()}
        for s, e in STICKS[:-1]:
            _line(img, far[s], far[e], 1)
        for s, e in STICKS:
            _line(img, near[s], near[e], 2)
        for i, n in enumerate(names):
            _disc(img, near[n], script.marker_radius, 4 + i)
            points[f, i] = near[n]
    return frames, {"angles": angles, "stretches": truth, "names": names, "points_px": points, "fps": script.fps}


def write_synthetic_video(spec: RobotSpec, path: Path, script: SyntheticScript | None = None) -> dict[str, Any]:
    """Render and write an AVI; returns the ground truth (see :func:`render`)."""
    from calflab.behave.video import write_avi

    script = script or SyntheticScript()
    frames, truth = render(spec, script)
    write_avi(path, frames, script.fps, palette())
    return truth
