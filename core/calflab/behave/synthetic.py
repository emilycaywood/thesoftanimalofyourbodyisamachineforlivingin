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


# ---------------------------------------------------------------------- 3D: any camera, both sides (ADR-080)
class Camera3D(BaseModel):
    """Where the synthetic camera looks from. ``yaw_deg`` is the animal's starting heading against a left-side view
    (+ = turned toward the camera); elevation + = looking down."""

    yaw_deg: float = 0.0
    elevation_deg: float = 10.0
    roll_deg: float = 0.0
    px_per_mm: float = 0.5  # at the starting distance
    width: int = 640
    height: int = 360
    hfov_deg: float = 60.0  # for the image scale changing with distance


class Script3D(BaseModel):
    """A walk with hip ab/adduction and a slow turn, seen from :class:`Camera3D`."""

    seconds: float = 4.0
    fps: float = 30.0
    period_s: float = 1.0
    turn_deg: float = 40.0  # heading change over the clip (+ = turning left, toward the camera when facing left)
    abduction_deg: float = 8.0  # hind ab/adduction amplitude
    speed_mm_s: float = 100.0
    #: the animal's proportions against the robot's (log ratios as the lift fits them: 0 = the robot's)
    trunk_length: float = 1.0
    trunk_width: float = 1.0
    front_leg: float = 1.0
    noise_px: float = 1.0
    drop: float = 0.05  # share of points dropped (low confidence)
    far_confidence: float = 0.75  # the far side's mean confidence (the near side's is about 0.95)
    seed: int = 0


def gait_angles_3d(joint: str, phase: float, abduction_deg: float) -> float:
    """Angle change (deg, from standing) of one joint at gait phase 0..1; the right legs run half a cycle later."""
    s, c = math.sin(2 * math.pi * phase), math.cos(2 * math.pi * phase)
    part = joint.split(".")[-1]
    return {"stifle": 10.0 * s, "hock": 6.0 * (1.0 - c), "hip_abd": abduction_deg * math.sin(2 * math.pi * phase + 1.0),
            "shoulder": -12.0 * s, "carpus": 12.5 * (1.0 - c)}.get(part, 0.0)


def synthetic_tracks_3d(spec: RobotSpec, lmap: Any, camera: Camera3D | None = None, script: Script3D | None = None
                        ) -> tuple[Any, dict[str, Any]]:
    """Keypoint tracks of the robot's own forward kinematics seen from ``camera`` (weak perspective, the scale
    following the distance), with noise and dropped points; and the truth per frame: absolute angles of the
    fitted joints (deg), heading, view yaw, near side."""
    from calflab import units as u
    from calflab.behave.keypoints import KeypointTracks
    from calflab.behave.lift import N_POSE, Skeleton, camera_matrix, project

    cam = camera or Camera3D()
    sc = script or Script3D()
    sk = Skeleton(spec, lmap)
    rng = np.random.default_rng(sc.seed)
    n = int(round(sc.seconds * sc.fps))
    t = np.arange(n) / sc.fps
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / max(sc.seconds, 1e-9), 0.0, 1.0))
    heading = u.deg_to_rad(cam.yaw_deg + sc.turn_deg * ramp)
    pitch = u.deg_to_rad(2.0 * np.sin(2 * np.pi * t / sc.period_s))
    roll = u.deg_to_rad(1.0 * np.sin(2 * np.pi * t / sc.period_s + 0.5))
    d = np.zeros((n, sk.n))
    for i, jid in enumerate(sk.free_ids):
        late = 0.5 if ".hr." in jid or ".fr." in jid else 0.0
        sgn = -1.0 if "hip_abd" in jid and late else 1.0
        d[:, i] = [u.deg_to_rad(sgn * gait_angles_3d(jid, (tt / sc.period_s + late) % 1.0, sc.abduction_deg)) for tt in t]
    d = np.clip(d, sk.free_lo, sk.free_hi)
    # the trunk walks along its heading; the camera looks at where it starts
    step = sc.speed_mm_s / sc.fps
    pos = np.zeros((n, 3))
    for f in range(1, n):
        pos[f] = pos[f - 1] + step * np.array([math.cos(heading[f]), math.sin(heading[f]), 0.0])
    cm = camera_matrix(u.deg_to_rad(cam.elevation_deg), u.deg_to_rad(cam.roll_deg))
    f_px = (cam.width / 2.0) / math.tan(u.deg_to_rad(cam.hfov_deg) / 2.0)
    dist0 = f_px / cam.px_per_mm
    pc = pos @ cm.T  # camera frame; + z toward the camera
    scale = f_px / (dist0 - pc[:, 2])
    tx = cam.width / 2.0 + scale * pc[:, 0]
    ty = -cam.height / 2.0 + scale * pc[:, 1] - 0.15 * cam.height
    glob = sk.initial_globals()
    glob[:5] = [math.log(sc.trunk_length), math.log(sc.trunk_width), math.log(sc.front_leg),
                u.deg_to_rad(cam.elevation_deg), u.deg_to_rad(cam.roll_deg)]
    x = np.concatenate([np.stack([heading, pitch, roll, np.log(scale), tx, ty], axis=1), d], axis=1)
    assert x.shape[1] == N_POSE + sk.n
    uv = project(sk, x, glob)
    uv = uv + rng.normal(0.0, sc.noise_px, uv.shape)
    near_left = np.cos(heading) > 0
    conf = np.where(sk.side_of[None] == 0, 0.9, 0.0) + np.where(
        (sk.side_of[None] > 0) == near_left[:, None], rng.uniform(0.85, 1.0, uv.shape[:2]),
        np.clip(rng.normal(sc.far_confidence, 0.05, uv.shape[:2]), 0.0, 1.0))
    conf = np.where(sk.side_of[None] == 0, rng.uniform(0.85, 1.0, uv.shape[:2]), conf)
    dropped = rng.random(uv.shape[:2]) < sc.drop
    conf[dropped] = 0.05
    uv[dropped] = np.nan
    tracks = KeypointTracks(fps=sc.fps, names=list(sk.names), xy=uv, likelihood=conf, source="synthetic 3D",
                            model={"tracker": "synthetic_3d", "camera": cam.model_dump(), "script": sc.model_dump()},
                            image_size=(cam.width, cam.height))
    full = sk.full_angles(d)
    truth = {
        "joints_deg": {j: u.rad_to_deg(full[:, k]) for k, j in enumerate(sk.joint_ids)},
        "free_ids": sk.free_ids,
        "heading_deg": u.rad_to_deg(heading),
        "view_yaw_deg": u.rad_to_deg(np.arctan2(np.sin(heading), np.abs(np.cos(heading)))),
        "pitch_deg": u.rad_to_deg(pitch), "roll_deg": u.rad_to_deg(roll),
        "elevation_deg": cam.elevation_deg, "roll_cam_deg": cam.roll_deg,
        "position_mm": pos, "scale": scale,
    }
    return tracks, truth
