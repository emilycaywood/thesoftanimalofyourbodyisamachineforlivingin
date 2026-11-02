"""Keypoint tracks -> robot joint angles: a retarget map (ADR-073).

A map is a YAML file (``config/retarget/<name>.yaml``, or the project's own
``motions/maps/<name>.yaml``, which wins) that says, per robot joint, which
tracked landmarks give its angle:

* ``flexion: [a, b, c]``: the interior angle at ``b`` between ``b->a`` and
  ``b->c``. The joint angle is how much that angle closed relative to the
  reference frame (flexion positive), as the feral calf's stifle, hock and
  carpus count it.
* ``swing: [from, to]``: the direction of the segment ``from->to`` measured
  in the trunk's frame (``trunk: [rear, front]`` landmarks), from straight
  down toward the front. The joint angle is how far it swung *back* from
  the reference frame, as the shoulder counts it.

Any landmark may be given as a list of alternatives (the first one the
tracks have is used), and ``sign`` and ``scale`` adjust a joint. Angles are
relative to a **reference frame** of the footage (``standing``: ``first``,
``median`` or a frame index), so the robot plays the animal's *change* of
angle from its own standing pose: proportions and camera scale do not
matter. A side view sees one side; the far legs ``copy`` the near ones,
follow them ``half_cycle`` later (a gait with period ``period_s``) or
``hold`` their standing angle. Joints the footage cannot show (hip
ab/adduction in a side view) are not in the clip and hold their pose.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, Field

from calflab import units as u
from calflab.behave.keypoints import KeypointTracks, clean
from calflab.project.motions import MotionClip

Landmark = str | list[str]


class JointRule(BaseModel):
    flexion: list[Landmark] | None = None  # [a, b, c]
    swing: list[Landmark] | None = None  # [from, to], in the trunk frame
    sign: float = 1.0
    scale: float = 1.0


class RetargetMap(BaseModel):
    name: str
    description: str = ""
    body: str = ""  # genome definition the joint names belong to
    trunk: list[Landmark] = Field(default_factory=list)  # [rear, front]
    joints: dict[str, JointRule]  # "hl.stifle" -> rule
    near_side: Literal["left", "right"] = "left"  # which legs the camera sees
    far_side: Literal["copy", "half_cycle", "hold"] = "copy"
    period_s: float | None = None  # for half_cycle
    standing: str | int = "first"
    ground: list[Landmark] = Field(default_factory=list)  # landmarks on the ground (hooves): the ground line
    min_likelihood: float = 0.6
    max_gap_frames: int = 10
    smooth_frames: int = 3


def map_dirs(project_dir: Path | None) -> list[Path]:
    from calflab.paths import config_dir

    out = [config_dir() / "retarget"]
    if project_dir is not None:
        out.insert(0, Path(project_dir) / "motions" / "maps")
    return out


def list_maps(project_dir: Path | None) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for d in reversed(map_dirs(project_dir)):  # the project's own maps win
        for p in sorted(d.glob("*.yaml")) if d.is_dir() else []:
            try:
                m = RetargetMap.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
            except Exception as exc:
                seen[p.stem] = {"name": p.stem, "error": str(exc), "file": str(p)}
                continue
            seen[m.name] = {"name": m.name, "description": m.description, "body": m.body, "joints": sorted(m.joints),
                            "file": str(p)}
    return list(seen.values())


def load_map(name: str, project_dir: Path | None = None) -> RetargetMap:
    for d in map_dirs(project_dir):
        p = d / f"{name}.yaml"
        if p.is_file():
            return RetargetMap.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
    raise KeyError(f"No retarget map {name!r} (looked in {', '.join(str(d) for d in map_dirs(project_dir))})")


def _pick(tracks: KeypointTracks, lm: Landmark) -> str | None:
    for name in [lm] if isinstance(lm, str) else lm:
        if tracks.has(name):
            return name
    return None


def _interior(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    v1, v2 = a - b, c - b
    cos = np.sum(v1 * v2, axis=1) / (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1))
    return u.rad_to_deg(np.arccos(np.clip(cos, -1.0, 1.0)))


def _trunk_frame(rear: np.ndarray, front: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    f = front - rear
    f = f / np.linalg.norm(f, axis=1, keepdims=True)
    down = np.stack([f[:, 1], -f[:, 0]], axis=1)  # perpendicular...
    flip = down[:, 1] > 0  # ...pointing down (y up)
    down[flip] = -down[flip]
    return f, down


def _reference(v: np.ndarray, how: str | int) -> float:
    if isinstance(how, int) or (isinstance(how, str) and how.isdigit()):
        return float(v[int(how)])
    if how == "median":
        return float(np.nanmedian(v))
    ok = v[~np.isnan(v)]
    return float(ok[0]) if ok.size else float("nan")


def retarget(
    tracks: KeypointTracks,
    m: RetargetMap,
    name: str,
    standing: str | int | None = None,
    robot_height_mm: float | None = None,
) -> MotionClip:
    """A motion clip (degrees relative to standing; root in mm and quaternions) from keypoint tracks."""
    cleaned, missing = clean(tracks, m.min_likelihood, m.max_gap_frames, m.smooth_frames)
    ref = m.standing if standing is None else standing
    near, far = ("l", "r") if m.near_side == "left" else ("r", "l")
    joints: dict[str, np.ndarray] = {}
    report: dict[str, Any] = {"joints": {}, "omitted": {}, "landmarks_missing": {k: round(v, 3) for k, v in missing.items()},
                              "reference": ref, "map": m.name, "far_side": m.far_side}
    rear = _pick(cleaned, m.trunk[0]) if len(m.trunk) == 2 else None
    front = _pick(cleaned, m.trunk[1]) if len(m.trunk) == 2 else None
    tf = _trunk_frame(cleaned.point(rear), cleaned.point(front)) if rear and front else None
    for jname, rule in m.joints.items():
        pts = rule.flexion or rule.swing or []
        names = [_pick(cleaned, p) for p in pts]
        if None in names or not pts:
            report["omitted"][jname] = f"landmarks not tracked: {[p for p, n in zip(pts, names, strict=True) if n is None]}"
            continue
        if rule.flexion:
            a, b, c = (cleaned.point(n) for n in names)  # type: ignore[arg-type]
            ang = _interior(a, b, c)
            val = _reference(ang, ref) - ang
        else:
            if tf is None:
                report["omitted"][jname] = "a swing joint needs trunk: [rear, front] landmarks"
                continue
            seg = cleaned.point(names[1]) - cleaned.point(names[0])  # type: ignore[arg-type]
            f, down = tf
            ang = u.rad_to_deg(np.arctan2(np.sum(seg * f, axis=1), np.sum(seg * down, axis=1)))
            val = _reference(ang, ref) - ang  # swinging back = forward angle getting smaller
        val = rule.sign * rule.scale * val
        joints[jname] = val
        report["joints"][f"joint.{jname}"] = {"landmarks": names, "missing_frames": round(float(np.mean(np.isnan(val))), 3)}
    # the far side of a side view
    period_frames = int(round((m.period_s or 0.0) * tracks.fps))
    for jname in list(joints):
        leg, part = jname.split(".", 1)
        if not leg.endswith(near):
            continue
        twin = f"{leg[:-1]}{far}.{part}"
        if twin in joints:
            continue
        if m.far_side == "copy":
            joints[twin] = joints[jname].copy()
        elif m.far_side == "half_cycle":
            if period_frames < 2:
                raise ValueError("far_side: half_cycle needs period_s (the gait's period in the footage)")
            joints[twin] = np.roll(joints[jname], period_frames // 2)
        report["joints"].setdefault(f"joint.{twin}", {"from": f"joint.{jname}", "far_side": m.far_side})
    # gaps left after cleaning hold the last known angle (or the reference) rather than inventing motion
    for k, v in joints.items():
        if np.all(np.isnan(v)):
            joints[k] = np.zeros_like(v)
            continue
        idx = np.arange(len(v))
        ok = ~np.isnan(v)
        joints[k] = np.interp(idx, idx[ok], v[ok])
    root_pos: list[tuple[float, float, float]] = []
    root_quat: list[tuple[float, float, float, float]] = []
    if tf is not None and rear and front:
        f, _ = tf
        pitch = u.rad_to_deg(np.arctan2(-f[:, 1], np.abs(f[:, 0])))  # nose down = positive
        pitch = np.nan_to_num(pitch - _reference(pitch, ref))
        mid = (cleaned.point(rear) + cleaned.point(front)) / 2.0
        gnames = [n for n in (_pick(cleaned, g) for g in m.ground) if n]
        ground_y = float(np.nanmin([np.nanmin(cleaned.point(g)[:, 1]) for g in gnames])) if gnames else float(np.nanmin(mid[:, 1]))
        height_px = mid[:, 1] - ground_y
        h_ref = _reference(height_px, ref)
        mm_per_px = (robot_height_mm / h_ref) if robot_height_mm and h_ref and h_ref > 0 else 1.0
        facing = 1.0 if np.nanmedian(f[:, 0]) >= 0 else -1.0
        x0 = mid[~np.isnan(mid[:, 0]), 0][0] if np.any(~np.isnan(mid[:, 0])) else 0.0
        for i in range(tracks.frames):
            x = facing * (mid[i, 0] - x0) * mm_per_px if not math.isnan(mid[i, 0]) else 0.0
            z = height_px[i] * mm_per_px if not math.isnan(height_px[i]) else (robot_height_mm or 0.0)
            root_pos.append((float(x), 0.0, float(z)))
            h = u.deg_to_rad(float(pitch[i])) / 2.0
            root_quat.append((math.cos(h), 0.0, math.sin(h), 0.0))
        report["root"] = {"scale_mm_per_px": round(mm_per_px, 4), "facing": "right" if facing > 0 else "left"}
    return MotionClip(
        name=name,
        fps=tracks.fps,
        joints={f"joint.{k}": [round(float(x), 4) for x in v] for k, v in sorted(joints.items())},
        root_pos=root_pos,
        root_quat=root_quat,
        source="footage",
        meta={"retarget": report, "footage": tracks.source, "frames": tracks.frames},
    )
