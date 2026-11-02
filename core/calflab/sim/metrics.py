"""Metrics computed from a rollout. Inputs are SI; outputs carry explicit units
(see :data:`METRIC_DEFS`) and are plain JSON-able values.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.sim.rollout import Rollout

#: key -> (label, unit, direction) where direction is "higher" or "lower" is better.
METRIC_DEFS: dict[str, tuple[str, str, str]] = {
    "speed_mps": ("Forward speed", "m/s", "higher"),
    "distance_m": ("Distance travelled", "m", "higher"),
    "lateral_drift_m": ("Sideways drift", "m", "lower"),
    "cost_of_transport": ("Cost of transport", "", "lower"),
    "energy_j": ("Mechanical energy", "J", "lower"),
    "mean_power_w": ("Mean mechanical power", "W", "lower"),
    "stability": ("Stability score", "", "higher"),
    "roll_rms_deg": ("Roll RMS", "deg", "lower"),
    "pitch_rms_deg": ("Pitch RMS", "deg", "lower"),
    "height_std_mm": ("Trunk height variation", "mm", "lower"),
    "survival": ("Upright fraction", "", "higher"),
    "torque_rms_nm": ("Torque RMS", "N*m", "lower"),
    "torque_peak_nm": ("Peak torque", "N*m", "lower"),
    "torque_margin_min": ("Worst torque margin", "", "higher"),
    "speed_margin_min": ("Worst joint speed margin", "", "higher"),
    "temp_peak_c": ("Peak actuator temperature", "degC", "lower"),
    "foot_impact_mps": ("Mean foot impact speed", "m/s", "lower"),
    "foot_impact_peak_mps": ("Peak foot impact speed", "m/s", "lower"),
    "time_to_stand_s": ("Time to stand from lying", "s", "lower"),
    "joint_limit_violation": ("Time at joint limits", "", "lower"),
    "tracking_rms_deg": ("Joint tracking error (RMS)", "deg", "lower"),
}

COT_CAP = 100.0


def _tilt(quat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Roll and pitch (rad) from (w, x, y, z) quaternions [T, 4]."""
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1.0, 1.0))
    return roll, pitch


def compute_metrics(r: Rollout) -> dict[str, Any]:
    m = r.meta
    active = r.t >= 0
    if not np.any(active):
        return {"speed_mps": 0.0, "fell": True, "survival": 0.0}
    t = r.t[active]
    trunk_pos = r.body_pos[active, 0, :]
    trunk_quat = r.body_quat[active, 0, :]
    duration = float(m["duration_s"])
    mass = float(m["total_mass_kg"])

    dx = float(trunk_pos[-1, 0] - trunk_pos[0, 0])
    dy = float(trunk_pos[-1, 1] - trunk_pos[0, 1])
    fell = bool(m.get("fell"))
    fall_time = m.get("fall_time")
    survival = 1.0 if not fell else float(min(1.0, max(0.0, (fall_time or 0.0) / duration)))
    energy = float(m["energy_j"])
    if dx > 0.05:
        cot = min(COT_CAP, energy / (mass * 9.81 * dx))
    else:
        cot = COT_CAP

    roll, pitch = _tilt(trunk_quat)
    roll_rms = float(u.rad_to_deg(math.sqrt(float(np.mean(roll**2)))))
    pitch_rms = float(u.rad_to_deg(math.sqrt(float(np.mean((pitch - np.mean(pitch)) ** 2)))))
    height_std = float(u.m_to_mm(float(np.std(trunk_pos[:, 2]))))
    stability = float(math.exp(-(roll_rms + pitch_rms) / 15.0)) * survival

    # how closely the joints followed their commands (deg RMS over actuated joints): imitation of a clip (ADR-073)
    aj = list(m.get("actuator_joint") or [])
    tracking = None
    if aj and r.ctrl.size and all(j in r.joint_ids for j in aj):
        qa = r.q[active][:, [r.joint_ids.index(j) for j in aj]]
        tracking = float(u.rad_to_deg(math.sqrt(float(np.mean((r.ctrl[active] - qa) ** 2)))))

    tq = r.torque[active]
    limit = np.array(m["torque_limit"]) if m.get("torque_limit") else np.ones(tq.shape[1])
    rms_by = np.sqrt(np.mean(tq**2, axis=0)) if tq.size else np.zeros(0)
    peak_by = np.max(np.abs(tq), axis=0) if tq.size else np.zeros(0)
    margin_by = 1.0 - peak_by / np.maximum(limit, 1e-9)
    # share of the time each motor gives (nearly) all its usable torque: a peak says "once", this says "how long"
    saturated_by = np.mean(np.abs(tq) >= 0.98 * np.maximum(limit, 1e-9), axis=0) if tq.size else np.zeros(0)
    # Joint speed against each motor's recorded no-load speed. The simulator limits torque, not speed
    # (ADR-047), so a negative margin means the rollout moved a joint faster than its motor can turn.
    dq = r.dq[active]
    speed_by = np.max(np.abs(dq), axis=0) if dq.size else np.zeros(tq.shape[1])
    s_lim = m.get("speed_limit") or []
    has_speed = len(s_lim) == speed_by.shape[0] and len(s_lim) > 0
    speed_limit = np.array(s_lim) if has_speed else np.zeros(0)
    speed_margin_by = 1.0 - speed_by / np.maximum(speed_limit, 1e-9) if has_speed else np.zeros(0)
    temp = r.temp[active]
    temp_by = np.max(temp, axis=0) if temp.size else np.zeros(0)

    lim = m.get("limits", {})
    q = r.q[active]
    near = np.zeros(q.shape[0], dtype=bool)
    tol = u.deg_to_rad(1.0)
    for j, jid in enumerate(r.joint_ids):
        if jid in lim:
            lo, hi = lim[jid]
            near |= (q[:, j] < lo + tol) | (q[:, j] > hi - tol)
    violation = float(np.mean(near)) if near.size else 0.0

    speeds = [s for (ti, _f, s) in r.impacts if ti >= 0]
    out: dict[str, Any] = {
        "speed_mps": dx / duration,
        "distance_m": dx,
        "lateral_drift_m": abs(dy),
        "cost_of_transport": cot,
        "energy_j": energy,
        "mean_power_w": energy / max(float(t[-1] - t[0]), 1e-6),
        "stability": stability,
        "roll_rms_deg": roll_rms,
        "pitch_rms_deg": pitch_rms,
        "height_std_mm": height_std,
        "fell": fell,
        "survival": survival,
        "torque_rms_nm": float(math.sqrt(float(np.mean(tq**2)))) if tq.size else 0.0,
        "torque_peak_nm": float(np.max(peak_by)) if peak_by.size else 0.0,
        "torque_margin_min": float(np.min(margin_by)) if margin_by.size else 1.0,
        "speed_margin_min": float(np.min(speed_margin_by)) if has_speed else None,
        "temp_peak_c": float(np.max(temp_by)) if temp_by.size else 0.0,
        "foot_impact_mps": float(np.mean(speeds)) if speeds else 0.0,
        "foot_impact_peak_mps": float(np.max(speeds)) if speeds else 0.0,
        "time_to_stand_s": m.get("time_to_stand"),
        "joint_limit_violation": violation,
        "tracking_rms_deg": tracking,
        "mass_kg": mass,
        "by_actuator": {
            aid: {
                "joint": m["actuator_joint"][i],
                "torque_rms_nm": float(rms_by[i]),
                "torque_peak_nm": float(peak_by[i]),
                "torque_limit_nm": float(limit[i]),
                "torque_margin": float(margin_by[i]),
                "torque_saturated": float(saturated_by[i]),
                "temp_peak_c": float(temp_by[i]),
                "speed_peak_deg_s": float(u.rad_to_deg(float(speed_by[i]))),
                **(
                    {"speed_limit_deg_s": float(u.rad_to_deg(float(speed_limit[i]))), "speed_margin": float(speed_margin_by[i])}
                    if has_speed
                    else {}
                ),
            }
            for i, aid in enumerate(r.actuator_ids)
        },
    }
    return out


def timeseries(r: Rollout) -> dict[str, Any]:
    """Channels for the metric plot, aligned with the playback frames."""
    roll, pitch = _tilt(r.body_quat[:, 0, :]) if r.n_frames else (np.zeros(0), np.zeros(0))
    x = r.body_pos[:, 0, 0] if r.n_frames else np.zeros(0)
    dt = float(r.meta.get("record_dt", 0.02))
    speed = np.gradient(x, dt) if r.n_frames > 1 else np.zeros_like(x)
    power = np.sum(np.abs(r.torque * r.dq), axis=1) if r.n_frames else np.zeros(0)

    def ch(label: str, unit: str, values: np.ndarray, group: str) -> dict[str, Any]:
        return {"label": label, "unit": unit, "group": group, "values": [round(float(v), 5) for v in values]}

    channels: dict[str, Any] = {
        "speed": ch("Forward speed", "m/s", speed, "Body"),
        "height": ch("Trunk height", "mm", r.body_pos[:, 0, 2] * 1000.0 if r.n_frames else np.zeros(0), "Body"),
        "roll": ch("Roll", "deg", np.degrees(roll), "Body"),
        "pitch": ch("Pitch", "deg", np.degrees(pitch), "Body"),
        "power": ch("Mechanical power", "W", power, "Energy"),
    }
    for i, aid in enumerate(r.actuator_ids):
        channels[f"torque:{aid}"] = ch(f"Torque {aid}", "N*m", r.torque[:, i], "Torque")
        channels[f"temp:{aid}"] = ch(f"Temperature {aid}", "degC", r.temp[:, i], "Temperature")
    for i, gid in enumerate(r.foot_geoms):
        channels[f"foot:{gid}"] = ch(f"Foot force {gid}", "N", r.foot_force[:, i], "Contact")
    return {"t": [round(float(v), 4) for v in r.t], "channels": channels}
