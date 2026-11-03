"""Movement features of a rollout (ADR-078).

These describe *how the body moved*, in kinematic terms, so that compositions
can be compared. They are not emotions and are never reported as such: what a
movement reads as is the researcher's judgement (their affect tags), not the
lab's. Each feature has a unit and a plain meaning:

* ``quantity_of_motion_deg_s``: mean joint speed over the actuated joints;
* ``trunk_speed_mm_s``: mean speed of the trunk over the ground;
* ``jerk_rms_deg_s3``: RMS of the third derivative of the joint angles (lower =
  smoother); ``smoothness`` = -log10 of it, for an axis that grows with
  smoothness;
* ``tempo_s`` and ``tempo_regularity``: the period of the joint activity's
  strongest repetition in 0.3-3 s and the height of that autocorrelation
  peak (0 = no rhythm, 1 = perfectly periodic);
* ``stillness_ratio``: share of the time the joints move slower than
  ``still_deg_s``;
* ``expressive_range_deg_s``: spread (90th minus 10th percentile) of the
  quantity of motion over 1 s windows: how far the performance ranges
  between stillness and activity;
* ``postural_height``: mean trunk height over the standing height (1 =
  standing tall);
* ``openness``: mean lateral spread of the feet over that of the standing pose
  (stance width);
* ``approach_mm``: net travel along the trunk's initial heading (+ = toward
  where it faced, - = retreat).

Units: deg, s, mm.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.model.xform import quat_rotate
from calflab.sim.rollout import Rollout

FEATURES: dict[str, tuple[str, str]] = {
    "quantity_of_motion_deg_s": ("Quantity of motion", "deg/s"),
    "trunk_speed_mm_s": ("Trunk speed", "mm/s"),
    "jerk_rms_deg_s3": ("Jerk (RMS)", "deg/s3"),
    "smoothness": ("Smoothness (-log10 jerk)", ""),
    "tempo_s": ("Tempo (period)", "s"),
    "tempo_regularity": ("Tempo regularity", ""),
    "stillness_ratio": ("Stillness ratio", ""),
    "expressive_range_deg_s": ("Expressive range", "deg/s"),
    "postural_height": ("Postural height", ""),
    "openness": ("Openness (stance width)", ""),
    "approach_mm": ("Approach (+) / retreat (-)", "mm"),
}
NOTE = "Movement features (kinematics), not emotions: what they read as is for a person to judge."


def _quat(q: Any) -> tuple[float, float, float, float]:
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def _foot_y(rollout: Rollout, spec: RobotSpec, frame: int) -> np.ndarray:
    """Lateral (y) world positions of the feet at one frame, mm."""
    out = []
    bidx = {b: i for i, b in enumerate(rollout.body_ids)}
    for b in spec.bodies:
        for g in b.geoms:
            if not g.foot or b.id not in bidx:
                continue
            i = bidx[b.id]
            p = rollout.body_pos[frame, i] * 1000.0
            r = quat_rotate(_quat(rollout.body_quat[frame, i]), g.pos)
            out.append(p[1] + r[1])
    return np.array(out)


def movement_features(rollout: Rollout, spec: RobotSpec, still_deg_s: float = 5.0) -> dict[str, Any]:
    """The features above for the controller's part of a rollout (t >= 0)."""
    m = rollout.t >= 0.0
    if m.sum() < 4:
        return {"note": NOTE}
    t = rollout.t[m]
    dt = float(np.median(np.diff(t)))
    aj = list(rollout.meta.get("actuator_joint") or [])
    cols = [rollout.joint_ids.index(j) for j in aj if j in rollout.joint_ids] or list(range(rollout.q.shape[1]))
    q = u.rad_to_deg(rollout.q[m][:, cols].astype(float))
    speed = np.abs(np.gradient(q, dt, axis=0))
    qom_t = speed.mean(axis=1)
    jerk = np.gradient(np.gradient(np.gradient(q, dt, axis=0), dt, axis=0), dt, axis=0)
    jerk_rms = float(np.sqrt(np.mean(jerk**2)))
    # tempo: autocorrelation of the joint activity
    x = qom_t - qom_t.mean()
    e = float(np.sum(x * x))
    tempo, reg = None, 0.0
    lo, hi = int(round(0.3 / dt)), min(int(round(3.0 / dt)), len(x) // 2)
    if e > 1e-9 and hi > lo + 1:
        ac = np.array([np.sum(x[: len(x) - k] * x[k:]) / e * len(x) / (len(x) - k) for k in range(hi + 1)])
        k = lo + int(np.argmax(ac[lo:hi]))
        tempo, reg = k * dt, float(max(0.0, min(1.0, ac[k])))
    win = max(1, int(round(1.0 / dt)))
    windows = [qom_t[i:i + win].mean() for i in range(0, len(qom_t) - win + 1, win)] or [float(qom_t.mean())]
    trunk = rollout.body_ids.index(spec.root.id) if spec.root.id in rollout.body_ids else 0
    pos = rollout.body_pos[m, trunk] * 1000.0
    vel = np.linalg.norm(np.gradient(pos[:, :2], dt, axis=0), axis=1)
    stand_h = float(spec.root.pos[2])
    fwd = quat_rotate(_quat(rollout.body_quat[m][0, trunk]), (1.0, 0.0, 0.0))
    heading = np.array([fwd[0], fwd[1]], dtype=float)
    heading = heading / (np.linalg.norm(heading) or 1.0)
    rest_y = []
    poses = spec.world_poses()
    for b in spec.bodies:
        for g in b.geoms:
            if g.foot:
                bp, bq = poses[b.id]
                rest_y.append(bp[1] + quat_rotate(bq, g.pos)[1])
    rest_spread = (max(rest_y) - min(rest_y)) if len(rest_y) > 1 else 0.0
    idx = np.nonzero(m)[0]
    sample = idx[:: max(1, len(idx) // 50)]
    spreads = [float(np.ptp(fy)) for fy in (_foot_y(rollout, spec, int(f)) for f in sample) if fy.size > 1]
    out = {
        "quantity_of_motion_deg_s": float(qom_t.mean()),
        "trunk_speed_mm_s": float(vel.mean()),
        "jerk_rms_deg_s3": jerk_rms,
        "smoothness": float(-math.log10(max(jerk_rms, 1e-9))),
        "tempo_s": None if tempo is None else round(float(tempo), 3),
        "tempo_regularity": reg,
        "stillness_ratio": float(np.mean(qom_t < still_deg_s)),
        "expressive_range_deg_s": float(np.percentile(windows, 90) - np.percentile(windows, 10)),
        "postural_height": float(np.mean(pos[:, 2]) / stand_h) if stand_h > 0 else None,
        "openness": float(np.mean(spreads) / rest_spread) if spreads and rest_spread > 0 else None,
        "approach_mm": float(np.dot(pos[-1, :2] - pos[0, :2], heading)),
        "note": NOTE,
    }
    return out


def clip_tracking(rollout: Rollout) -> dict[str, dict[str, float]]:
    """Per clip played (from the behaviors controller's episode log): RMS tracking error over the frames it played
    (deg), how long it played (s) and how many times."""
    log = (rollout.meta.get("controller_log") or {}).get("episodes") or []
    aj = list(rollout.meta.get("actuator_joint") or [])
    if not log or not aj or not all(j in rollout.joint_ids for j in aj):
        return {}
    qa = rollout.q[:, [rollout.joint_ids.index(j) for j in aj]]
    err = rollout.ctrl - qa
    out: dict[str, dict[str, Any]] = {}
    sums: dict[str, list[float]] = {}
    for ep in log:
        if ep.get("kind") != "clip":
            continue
        sel = (rollout.t >= ep["t0"]) & (rollout.t < ep["t1"])
        if not sel.any():
            continue
        acc = sums.setdefault(ep["clip"], [0.0, 0.0, 0.0, 0.0])
        acc[0] += float(np.sum(err[sel] ** 2))
        acc[1] += float(err[sel].size)
        acc[2] += float(ep["t1"] - ep["t0"])
        acc[3] += 1
    for cid, (sq, n, secs, count) in sums.items():
        out[cid] = {"tracking_rms_deg": float(u.rad_to_deg(math.sqrt(sq / n))) if n else 0.0,
                    "played_s": round(secs, 3), "times": int(count)}
    return out
