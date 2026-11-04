"""Motion signals: what the reading looks at, from a video's 3D lift or from a robot rollout (ADR-085).

The calf and the robot are read by the same code, so the two must give the same
signals in the same units:

* ``joints``: joint angles relative to the robot's standing pose (deg), the
  robot's own joints only (the lift fits the robot's skeleton);
* ``heading_deg`` (+ = turning left), ``pitch_deg`` (nose down +), ``roll_deg``;
* ``root_mm``: the trunk origin over the ground (x, y) and its height (z), mm at
  the robot's leg length: the lift scales the calf so its hind leg is the
  robot's, so speeds compare leg for leg;
* ``hoof_mm``: each hoof's height (mm) above the ground. From a lift there is
  no ground, so it is the height above the lowest hoof of the frame (one hoof
  is always down); from a rollout, above the floor;
* ``hoof_speed_bl_s`` (lift only): each tracked paw's speed over the ground in the image, body lengths per
  second: its image motion minus the background's (a moving camera), with repeated frames interpolated over.
  The stance cue of video gait analysis: a hoof in stance stands still;
* ``reliable``: frames to read (the lift's ok/ambiguous frames; every frame of
  a rollout);
* ``body_length_mm``: hip-to-shoulder length (the calf's fitted one).

Units: s, mm, deg.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.model.xform import quat_rotate, quat_to_matrix

LEGS = ("hl", "hr", "fl", "fr")


@dataclasses.dataclass
class MotionSignals:
    fps: float
    joints: dict[str, np.ndarray]
    heading_deg: np.ndarray
    pitch_deg: np.ndarray
    roll_deg: np.ndarray
    root_mm: np.ndarray  # [F, 3]
    hoof_mm: dict[str, np.ndarray]
    reliable: np.ndarray
    body_length_mm: float
    source: str = ""
    #: video frame of each signal frame (lift: the frame itself; rollout: None)
    video_frame: np.ndarray | None = None
    #: per frame, how far the head (nose) moved against the shoulders, body lengths/s (lift only; the robot has none)
    head_bl_s: np.ndarray | None = None
    #: per leg, the tracked paw's speed over the ground in the image, body lengths/s (lift only)
    hoof_speed_bl_s: dict[str, np.ndarray] | None = None
    #: per leg, frames the paw was tracked confidently (lift only)
    hoof_seen: dict[str, np.ndarray] | None = None

    @property
    def frames(self) -> int:
        return len(self.heading_deg)

    @property
    def t(self) -> np.ndarray:
        return np.arange(self.frames) / self.fps

    def cut(self, a: int, b: int) -> MotionSignals:
        def c(v: Any) -> Any:
            return None if v is None else v[a:b]
        return dataclasses.replace(
            self, joints={k: v[a:b] for k, v in self.joints.items()}, heading_deg=self.heading_deg[a:b],
            pitch_deg=self.pitch_deg[a:b], roll_deg=self.roll_deg[a:b], root_mm=self.root_mm[a:b],
            hoof_mm={k: v[a:b] for k, v in self.hoof_mm.items()}, reliable=self.reliable[a:b],
            video_frame=c(self.video_frame), head_bl_s=c(self.head_bl_s),
            hoof_speed_bl_s=None if self.hoof_speed_bl_s is None else {k: v[a:b] for k, v in self.hoof_speed_bl_s.items()},
            hoof_seen=None if self.hoof_seen is None else {k: v[a:b] for k, v in self.hoof_seen.items()})


def robot_length_mm(spec: RobotSpec) -> float:
    """Hip-to-shoulder distance of the robot (mm)."""
    root = spec.root.id
    hind = [b.pos[0] for b in spec.bodies if b.parent == root and b.id.startswith("leg.h")]
    front = [b.pos[0] for b in spec.bodies if b.parent == root and b.id.startswith("leg.f")]
    return abs(sum(front) / len(front) - sum(hind) / len(hind)) if hind and front else 500.0


def _feet(spec: RobotSpec) -> list[tuple[str, str, tuple[float, ...], float]]:
    """(leg, body id, foot geom position in the body, radius) per hoof."""
    out = []
    for b in spec.bodies:
        for g in b.geoms:
            if g.foot:
                leg = b.id.split(".")[1] if b.id.startswith("leg.") else b.id
                out.append((leg, b.id, tuple(g.pos), float(g.size[0])))
    return out


def _rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def hoof_heights_posed(spec: RobotSpec, angles_abs: dict[str, np.ndarray], pitch_deg: np.ndarray,
                       roll_deg: np.ndarray) -> dict[str, np.ndarray]:
    """Per hoof, its height (mm) above the lowest hoof, the robot posed at ``angles_abs`` (absolute deg per joint
    and frame) and tilted by the trunk's pitch and roll."""
    n = len(pitch_deg)
    rest = spec.rest_angles()
    feet = _feet(spec)
    z = np.zeros((n, len(feet)))
    for f in range(n):
        full = {j: float(angles_abs[j][f]) if j in angles_abs else v for j, v in rest.items()}
        poses = spec.world_poses(full, root_pos=(0.0, 0.0, 0.0))
        tilt = _ry(u.deg_to_rad(float(pitch_deg[f]))) @ _rx(u.deg_to_rad(float(roll_deg[f])))
        for k, (_leg, bid, gp, r) in enumerate(feet):
            bp, bq = poses[bid]
            p = np.array(bp) + quat_to_matrix(bq) @ np.array(gp)
            z[f, k] = (tilt @ p)[2] - r
    z = z - z.min(axis=1, keepdims=True)
    return {leg: z[:, k] for k, (leg, *_rest) in enumerate(feet)}


def _lowpass(v: np.ndarray, fps: float, hz: float) -> np.ndarray:
    from calflab.behave.smoothing import lowpass, max_cutoff_hz

    if hz <= 0 or len(v) < 12:
        return np.asarray(v, dtype=float)
    return lowpass(np.asarray(v, dtype=float), fps, min(hz, 0.9 * max_cutoff_hz(fps)))


def from_lift(res: Any, spec: RobotSpec, tracks: Any = None, cutoff_hz: float = 4.0, retime: bool = True,
              background: list[tuple[float, float]] | None = None, lmap: Any = None) -> MotionSignals:
    """Signals of a lifted video (:class:`calflab.behave.lift.LiftResult`): unreliable and repeated frames are
    interpolated over by :func:`calflab.behave.lift.lift_clip` (and stay marked unreliable here), then everything
    is low-passed at ``cutoff_hz`` (zero lag)."""
    from calflab.behave.lift import lift_clip

    clip = lift_clip(res, spec, None, "reading", retime)
    fps = float(res.fps)
    rest = spec.rest_angles()
    joints = {j: _lowpass(np.asarray(v, dtype=float), fps, cutoff_hz) for j, v in clip.joints.items()}
    lm = clip.meta["lift"]
    heading = _lowpass(np.asarray(lm["heading_deg"], dtype=float), fps, cutoff_hz)
    pitch = _lowpass(np.asarray(lm["pitch_deg"], dtype=float), fps, cutoff_hz)
    roll = _lowpass(np.asarray(lm["roll_deg"], dtype=float), fps, cutoff_hz)
    root = np.array(clip.root_pos, dtype=float)
    root = np.stack([_lowpass(root[:, k], fps, cutoff_hz) for k in range(3)], axis=1)
    hooves = hoof_heights_posed(spec, {j: rest[j] + v for j, v in joints.items()}, pitch, roll)
    length = robot_length_mm(spec) * float(res.proportions.get("trunk_length", 1.0))
    head = None
    paws: tuple[dict[str, np.ndarray], dict[str, np.ndarray]] | None = None
    if tracks is not None:
        body_px = length * float(np.median(res.scale_px_per_mm))
        head = _head_motion(tracks, fps, cutoff_hz, body_px)
        rep = np.asarray(res.repeated, dtype=bool) if retime and len(res.repeated) == res.frames else None
        paws = _paw_speeds(tracks, lmap, fps, body_px, background, rep, cutoff_hz)
    return MotionSignals(fps=fps, joints=joints, heading_deg=heading, pitch_deg=pitch, roll_deg=roll, root_mm=root,
                         hoof_mm=hooves, reliable=res.reliable(), body_length_mm=length, source="lift",
                         video_frame=np.arange(res.frames), head_bl_s=head,
                         hoof_speed_bl_s=paws[0] if paws else None, hoof_seen=paws[1] if paws else None)


def _paw_names(lmap: Any) -> dict[str, str]:
    """Leg -> tracked paw name, from a lift map's foot landmarks (AP-10K names if no map)."""
    if lmap is None:
        return {"hl": "L_B_Paw", "hr": "R_B_Paw", "fl": "L_F_Paw", "fr": "R_F_Paw"}
    lms, _pairs, _ties = lmap.expanded()
    out = {}
    for name, d in lms.items():
        if d.foot and d.body.startswith("leg."):
            out[d.body.split(".")[1]] = name
    return out


def _paw_speeds(tracks: Any, lmap: Any, fps: float, body_px: float, background: list[tuple[float, float]] | None,
                repeated: np.ndarray | None, cutoff_hz: float = 4.0
                ) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]] | None:
    names = list(tracks.names)
    xy = np.asarray(tracks.xy, dtype=float)
    lk = np.asarray(tracks.likelihood, dtype=float)
    F = xy.shape[0]
    thr = float(getattr(lmap, "min_likelihood", 0.3)) if lmap is not None else 0.3
    bg = np.zeros((F, 2))
    if background is not None:
        b = np.asarray(background, dtype=float)[:F]
        bg[: len(b)] = b
    # the ground's position in the image, frame by frame (cumulative background shift)
    ground = np.cumsum(bg, axis=0)
    speeds, seen = {}, {}
    idx = np.arange(F)
    for leg, pn in _paw_names(lmap).items():
        if pn not in names or body_px <= 0:
            continue
        k = names.index(pn)
        ok = (lk[:, k] >= thr) & np.isfinite(xy[:, k]).all(axis=1)
        keep = ok & (~repeated if repeated is not None else True)
        if keep.sum() < 4:
            continue
        p = xy[:, k] - ground
        p = np.stack([_lowpass(np.interp(idx, idx[keep], p[keep, c]), fps, cutoff_hz) for c in range(2)], axis=1)
        speeds[leg] = np.linalg.norm(np.gradient(p, axis=0), axis=1) * fps / body_px
        seen[leg] = ok
    return (speeds, seen) if speeds else None


def _head_motion(tracks: Any, fps: float, cutoff_hz: float, body_px: float) -> np.ndarray | None:
    """Speed of the nose relative to the mean of the shoulders, in body lengths per second (the head and neck are
    the calf's own; the robot has neither)."""
    names = list(tracks.names)
    shoulders = [names.index(n) for n in ("L_Shoulder", "R_Shoulder") if n in names]
    if "Nose" not in names or not shoulders or body_px <= 0:
        return None
    xy = np.asarray(tracks.xy, dtype=float)
    lk = np.asarray(tracks.likelihood, dtype=float)
    nose = xy[:, names.index("Nose")]
    sh = np.nanmean(xy[:, shoulders], axis=1)
    rel = nose - sh
    ok = (lk[:, names.index("Nose")] >= 0.3) & np.isfinite(rel).all(axis=1)
    if ok.sum() < 6:
        return None
    idx = np.arange(len(rel))
    rel = np.stack([np.interp(idx, idx[ok], rel[ok, k]) for k in range(2)], axis=1)
    rel = np.stack([_lowpass(rel[:, k], fps, cutoff_hz) for k in range(2)], axis=1)
    return np.linalg.norm(np.gradient(rel, axis=0), axis=1) * fps / body_px


def _q4(q: Any) -> tuple[float, float, float, float]:
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def _euler(q: Any) -> tuple[float, float, float]:
    """Heading (yaw), pitch (nose down +) and roll (deg) of a (w, x, y, z) quaternion, Z-Y-X."""
    w, x, y, z = (float(v) for v in q)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    return u.rad_to_deg(yaw), u.rad_to_deg(pitch), u.rad_to_deg(roll)


def from_rollout(rollout: Any, spec: RobotSpec, t0: float = 0.0, t1: float | None = None) -> MotionSignals:
    """Signals of a robot rollout between t0 and t1 (s): the same quantities as from a lift. Hoof heights are
    above the floor; nothing is smoothed (the simulator has no tracker noise)."""
    m = rollout.t >= t0
    if t1 is not None:
        m &= rollout.t < t1
    idx = np.flatnonzero(m)
    if len(idx) < 2:
        raise ValueError("The rollout has fewer than two frames in that time")
    dt = float(np.median(np.diff(rollout.t[idx])))
    rest = spec.rest_angles()
    aj = [j for j in (rollout.meta.get("actuator_joint") or []) if j in rollout.joint_ids]
    joints = {j: u.rad_to_deg(rollout.q[idx, rollout.joint_ids.index(j)].astype(float)) - rest.get(j, 0.0) for j in aj}
    trunk = rollout.body_ids.index(spec.root.id) if spec.root.id in rollout.body_ids else 0
    eul = np.array([_euler(rollout.body_quat[i, trunk]) for i in idx])
    heading = np.rad2deg(np.unwrap(np.deg2rad(eul[:, 0])))
    root = rollout.body_pos[idx, trunk].astype(float) * 1000.0
    bidx = {b: i for i, b in enumerate(rollout.body_ids)}
    hooves: dict[str, np.ndarray] = {}
    for leg, bid, gp, r in _feet(spec):
        if bid not in bidx:
            continue
        k = bidx[bid]
        z = [rollout.body_pos[i, k][2] * 1000.0 + quat_rotate(_q4(rollout.body_quat[i, k]), gp)[2] - r  # type: ignore[arg-type]
             for i in idx]
        hooves[leg] = np.maximum(0.0, np.asarray(z, dtype=float))
    return MotionSignals(fps=1.0 / dt, joints=joints, heading_deg=heading, pitch_deg=eul[:, 1], roll_deg=eul[:, 2],
                         root_mm=root, hoof_mm=hooves, reliable=np.ones(len(idx), dtype=bool),
                         body_length_mm=robot_length_mm(spec), source="rollout")


# ---------------------------------------------------------------------- synthetic signals (a known sequence)
SYNTHETIC_ORDER = {"hl": 0.0, "fl": 0.25, "hr": 0.5, "fr": 0.75}  # lateral sequence


def synthetic_signals(spec: RobotSpec, sequence: list[tuple[str, float]], fps: float = 30.0, seed: int = 0
                      ) -> tuple[MotionSignals, list[tuple[str, float, float]]]:
    """Signals of a known behaviour sequence, posed on the robot's own skeleton (no video, no tracker): stand,
    weight_shift (trunk rolled and joints swayed, hooves down), step (one hoof lifted once), walk (lateral sequence,
    1.2 s cycle, 300 mm/s), turn (the same steps, 40 deg/s, 30 mm/s), other (diagonal pairs up 60 % of a 0.5 s
    cycle, 1500 mm/s). Returns the signals and the truth [(behaviour, t0, t1)]. For tests and for trying the
    reading without footage (ADR-085)."""
    rng = np.random.default_rng(seed)
    joints_of = [a.joint for a in spec.actuators]
    n = int(round(sum(d for _b, d in sequence) * fps))
    J = {j: np.zeros(n) for j in joints_of}
    hoof = {leg: np.zeros(n) for leg in LEGS}
    heading, roll, pitch = np.zeros(n), np.zeros(n), np.zeros(n)
    root = np.zeros((n, 3))
    truth = []
    f0 = 0
    x = y = h = 0.0
    for beh, dur in sequence:
        m = int(round(dur * fps))
        truth.append((beh, f0 / fps, (f0 + m) / fps))
        for k in range(m):
            f = f0 + k
            t = k / fps
            speed, rate = 0.0, 0.0
            if beh == "weight_shift":
                roll[f] = 4.0 * math.sin(2 * math.pi * t / 2.0)
                for j in joints_of:
                    if j.endswith(("stifle", "hip_abd")):
                        J[j][f] = 6.0 * math.sin(2 * math.pi * t / 2.0) * (1 if ".hl." in j or ".fl." in j else -1)
            elif beh == "step":
                c = t / dur
                if 0.35 < c < 0.65:
                    hoof["hr"][f] = 60.0 * math.sin(math.pi * (c - 0.35) / 0.3)
                    for j in joints_of:
                        if j.startswith("joint.hr.") and not j.endswith("abd"):
                            J[j][f] = 15.0 * math.sin(math.pi * (c - 0.35) / 0.3)
            elif beh in ("walk", "turn", "other"):
                T, sw, offs = (1.2, 0.25, SYNTHETIC_ORDER) if beh != "other" else (
                    0.5, 0.6, {"hl": 0.0, "fr": 0.0, "hr": 0.5, "fl": 0.5})
                speed = {"walk": 300.0, "turn": 30.0, "other": 1500.0}[beh]
                rate = 40.0 if beh == "turn" else 0.0
                for leg, off in offs.items():
                    ph = ((t / T) - off) % 1.0
                    up = ph < sw
                    hoof[leg][f] = 60.0 * math.sin(math.pi * ph / sw) if up else 0.0
                    for j in joints_of:
                        if j.startswith(f"joint.{leg}.") and not j.endswith("abd"):
                            J[j][f] = (20.0 * math.sin(math.pi * ph / sw) if up else 0.0) + 8.0 * math.cos(2 * math.pi * ph)
                pitch[f] = 1.5 * math.sin(4 * math.pi * t / T)
            h += rate / fps
            x += speed / fps * math.cos(math.radians(h))
            y += speed / fps * math.sin(math.radians(h))
            heading[f], root[f] = h, (x, y, spec.root.pos[2])
            for j in joints_of:
                J[j][f] += 0.1 * rng.standard_normal()
        f0 += m
    sig = MotionSignals(fps=fps, joints=J, heading_deg=heading, pitch_deg=pitch, roll_deg=roll, root_mm=root,
                        hoof_mm=hoof, reliable=np.ones(n, dtype=bool), body_length_mm=robot_length_mm(spec),
                        source="synthetic", video_frame=np.arange(n))
    return sig, truth
