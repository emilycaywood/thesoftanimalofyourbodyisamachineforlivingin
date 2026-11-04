"""A clip played in physics (ADR-084): what a built robot would go through.

The kinematic preview (:mod:`calflab.behave.preview`) poses the body; the clip
report (:mod:`calflab.behave.feasibility`) compares peak speeds with the servo's
no-load speed. Neither knows mass, inertia, contact, springs or belts. Here the
clip is played by the **behaviors controller in MuJoCo**, with:

* servos limited in torque **and** speed: the torque-speed envelope of
  :mod:`calflab.sim.servo` from the library's stall torque and no-load speed,
  torque derating 1 (a servo may reach stall, as in the load analysis);
* the belts and springs as the design has them.

The clip is played once at its own speed and amplitude, after a lead-in that
eases the body from standing into the clip's first pose and before a return
to standing (both cosine ramps; neither counts in the tracking). Then:

* **tracking** per joint against the clip (clamped to the joint ranges, as the
  robot can play it) and against what the controller commanded;
* **servos** per joint: torque against rated and stall, speed against the
  servo's at that joint, envelope use;
* **belts**: tension against allowable working tension and breaking strength
  (:func:`calflab.mech.loads.analyse`);
* **hooves**: peak contact force and the impacts (touch-down speed and the
  force in the 50 ms after), against body weight; no hoof limit is in the
  library, so these are reported, not judged;
* **battery** current (:mod:`calflab.mech.limits`): known only with every
  servo's stall current; otherwise a lower bound;
* whether the body **falls**;
* the **constraints** of :func:`calflab.evolve.safety.safety_report`, with the
  researcher's margin: the same limits the repertoire evolution judges by;
* a **time strip**: per limit, per time bucket, ok / near (over 90 % of the
  limit) / over, with the joint responsible, and the spans over a limit as
  events with their time and video frames.

Units: s, deg, deg/s, N*m, N, A, W.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.project.motions import MotionClip
from calflab.schema import P

#: strip levels
OK, NEAR, OVER = 0, 1, 2
STRIP_COLUMNS = 240
#: limits judged over a window, not per frame
SUSTAINED = ("rated", "belt")


class PhysicsSettings(BaseModel):
    """How a clip is played in physics."""

    margin: float = P(0.2, ge=0.0, le=0.9, step=0.05,
                      desc="Safety margin: every limit (stall, rated, speed, envelope, belt tensions) is lowered to "
                           "(1 - margin) x itself. 0.2 = keep 20 % in hand.")
    lead_in_s: float = P(1.0, unit="s", ge=0.2, le=5.0, step=0.1,
                         desc="Ease from standing into the clip's first pose (not counted in the tracking).")
    return_s: float = P(1.0, unit="s", ge=0.2, le=5.0, step=0.1,
                        desc="Ease from the clip's last pose back to standing (judged, not tracked).")
    hold_s: float = P(0.5, unit="s", ge=0.0, le=5.0, step=0.1, desc="Standing still at the end (judged).")
    command_speed_fraction: float = P(
        -1.0, ge=-1.0, le=1.0, step=0.05,
        desc="The behaviors controller's command speed cap (fraction of each servo's speed); -1 = the document's "
             "behaviors setting (0.9 by default), 0 = no cap, so only the servo model limits speed.")
    seed: int = P(0, ge=0, ui="number", desc="Seed (the controller's draws; the clip itself is played as given).")


def _ramp(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """n frames from a toward b on a cosine, excluding a, including b."""
    if n <= 0:
        return np.zeros((0, len(a)))
    w = 0.5 - 0.5 * np.cos(np.pi * np.arange(1, n + 1) / n)
    return a[None, :] + w[:, None] * (b - a)[None, :]


def playback_clip(clip: MotionClip, spec: RobotSpec, s: PhysicsSettings) -> tuple[MotionClip, dict[str, Any]]:
    """The clip with a lead-in from standing and a return to standing (angles relative to standing, as clips are),
    and where the clip itself starts and ends in it (s)."""
    if clip.frames < 2:
        raise ValueError(f"Clip {clip.id or clip.name!r} has fewer than two frames")
    ids = [j for j in clip.joints if any(j == a.joint for a in spec.actuators)]
    if not ids:
        raise ValueError(f"Clip {clip.id or clip.name!r} moves none of this body's servo joints")
    v = np.array([clip.joints[j] for j in ids], dtype=float).T  # [frames, joints]
    zero = np.zeros(len(ids))
    n_in = max(1, int(round(s.lead_in_s * clip.fps)))
    n_out = max(1, int(round(s.return_s * clip.fps)))
    n_hold = int(round(s.hold_s * clip.fps))
    paths = clip.meta.get("stance_paths") or {}
    if paths.get("lead_in") and paths.get("return") and all(j in paths["lead_in"] for j in ids):
        # planted by calflab.behave.stance: follow its solved way in and back (cosine-timed samples), and hold
        # where the way back ends, so supporting hooves are not dragged by a blend of angles
        def along(start: np.ndarray, path: dict[str, list[float]], frac: np.ndarray) -> np.ndarray:
            rows = np.array([path[j] for j in ids], dtype=float).T
            grid = np.concatenate([[0.0], np.arange(1, len(rows) + 1) / len(rows)])
            vals = np.vstack([start[None, :], rows])
            return np.stack([np.interp(frac, grid, vals[:, k]) for k in range(len(ids))], axis=1)

        lead = along(zero, paths["lead_in"], np.arange(n_in) / n_in)
        back = along(v[-1], paths["return"], np.arange(1, n_out + 1) / n_out)
        hold = np.repeat(back[-1:], n_hold, axis=0)
    else:
        lead = np.vstack([zero[None, :], _ramp(zero, v[0], n_in)[:-1]])
        back = _ramp(v[-1], zero, n_out)
        hold = np.zeros((n_hold, len(ids)))
    full = np.vstack([lead, v, back, hold])
    out = MotionClip(id=f"{clip.id or 'clip'}.physics", name=clip.name, fps=clip.fps,
                     joints={j: [float(x) for x in full[:, k]] for k, j in enumerate(ids)}, source="physics")
    t0 = len(lead) / clip.fps
    return out, {"clip_t0": t0, "clip_t1": t0 + clip.frames / clip.fps, "end_t": len(full) / clip.fps,
                 "lead_frames": len(lead), "joints": ids}


def controller_params(base: dict[str, Any], play: MotionClip, s: PhysicsSettings) -> dict[str, Any]:
    """The behaviors controller set to play ``play`` once, then hold standing still: no draws, no mirroring, no
    composition (tempo, amplitude and low-pass 1 / 1 / off), the document's command speed cap unless set."""
    p = dict(base)
    for k in ("transitions", "affect_curve", "clips", "pools"):
        p.pop(k, None)
    p.update({
        "repertoire": [
            {"name": "clip", "kind": "clip", "clip": play.id, "speed": [1.0, 1.0], "amplitude": [1.0, 1.0],
             "repeats": [1, 1], "mirror": False},
            {"name": "stand", "kind": "idle", "weight": 0.0, "duration_s": [3600.0, 3600.0]},
        ],
        "transitions": {"clip": {"stand": 1.0}, "stand": {"stand": 1.0}},
        "start": "clip", "blend_s": 0.0, "idle_noise_deg": 0.0, "tempo": 1.0, "amplitude": 1.0, "idle_share": -1.0,
        "lowpass_hz": 0.0, "repeat_prob": 0.0, "pause_prob": 0.0, "play_required_first": False,
        "clips": {play.id: {"fps": play.fps, "joints": play.joints, "affect": None}}, "pools": {},
    })
    if s.command_speed_fraction >= 0:
        p["speed_fraction"] = s.command_speed_fraction
    return p


def compile_params(doc: dict[str, Any]) -> dict[str, Any]:
    """The document's model settings with the physics review's: derating 1, torque-speed servos, nothing random."""
    out = {k: v for k, v in doc.items() if k != "randomization"}
    out.update({"torque_derating": 1.0, "servo_model": "torque_speed"})
    return out


def play(clip: MotionClip, spec: RobotSpec, lib: Any, base_params: dict[str, Any], doc_compile: dict[str, Any],
         s: PhysicsSettings, cancelled: Any = None) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Simulate ``clip`` on ``spec``. Returns the rollout, the timing of the clip in it and the controller params."""
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    pb, timing = playback_clip(clip, spec, s)
    params = controller_params(base_params, pb, s)
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(compile_params(doc_compile)), s.seed)
    settings = SimSettings(duration_s=round(timing["end_t"] + 0.05, 3), control_hz=50.0, record_hz=50.0,
                           settle_s=0.4, start_pose="stand", stop_on_fall=True, seed=s.seed)
    ctrl = registry.get("controller", "behaviors")(params)
    rollout = run_rollout(cm, ctrl, settings, lib, cancelled=cancelled)  # type: ignore[arg-type]
    rollout.meta["physics_play"] = {"clip": clip.id, **timing}
    return rollout, timing, params


# ---------------------------------------------------------------------- report
def _clip_reference(clip: MotionClip, spec: RobotSpec, t: np.ndarray, t0: float) -> dict[str, np.ndarray]:
    """The clip's absolute joint angles (deg) at times t (clip time = t - t0), clamped to the joint ranges."""
    rest = spec.rest_angles()
    ct = (t - t0) * clip.fps
    idx = np.arange(clip.frames, dtype=float)
    out = {}
    for jid, vals in clip.joints.items():
        try:
            j = spec.joint(jid)
        except KeyError:
            continue
        ang = rest[jid] + np.interp(ct, idx, np.asarray(vals, dtype=float))
        out[jid] = np.clip(ang, j.range_deg[0], j.range_deg[1])
    return out


def _spans(flags: np.ndarray, t: np.ndarray) -> list[tuple[int, int]]:
    """Index spans [a, b) where flags is true."""
    out = []
    i, n = 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def report(rollout: Any, clip: MotionClip, spec: RobotSpec, lib: Any, timing: dict[str, Any],
           margin: float, frame_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the physics review shows, computed here (no logic in the UI)."""
    from calflab.evolve.safety import SafetyPolicy, safety_report, until_fall
    from calflab.mech.limits import battery_current, servo_columns
    from calflab.mech.loads import analyse
    from calflab.sim import compute_metrics

    keep = 1.0 - margin
    feral = spec.metadata.get("feral") or {}
    checks = {"rated_fraction": 0.6, "sustained_fraction": 0.25, "breaking_fraction": 0.25, **(feral.get("checks") or {})}
    m = rollout.t >= 0.0
    t = rollout.t[m]
    n = len(t)
    in_clip = (t >= timing["clip_t0"]) & (t < timing["clip_t1"])
    phase = np.where(t < timing["clip_t0"], 0, np.where(in_clip, 1, 2))  # lead-in, clip, return/hold
    loads = analyse(rollout, spec, lib, 2.0, checks, feral.get("belt_drives") or {})
    cols = loads["columns"]
    # the per-joint table, like the constraints, stops at a fall: what a body does while falling is not the clip's
    fall_at = rollout.meta.get("fall_time") if rollout.meta.get("fell") else None
    pre = t <= float(fall_at) if fall_at is not None else np.ones(n, dtype=bool)
    if not pre.any():
        pre = np.ones(n, dtype=bool)
    loads_pre = analyse(until_fall(rollout), spec, lib, 2.0, checks, feral.get("belt_drives") or {}) if fall_at is not None else loads
    servos = servo_columns(rollout, spec, lib)
    ref = _clip_reference(clip, spec, t, timing["clip_t0"])
    aj = list(rollout.meta.get("actuator_joint") or [])
    qa = {j: u.rad_to_deg(rollout.q[m, rollout.joint_ids.index(j)].astype(float)) for j in aj if j in rollout.joint_ids}
    ctrl = {j: u.rad_to_deg(rollout.ctrl[m, i].astype(float)) for i, j in enumerate(aj)}
    rest = spec.rest_angles()
    belts = feral.get("belt_drives") or {}

    # per limit, per frame: value / limit (with the margin) and which joint
    limits: dict[str, dict[str, Any]] = {}

    def add(key: str, label: str, ratio: np.ndarray, joint: str) -> None:
        cur = limits.setdefault(key, {"label": label, "ratio": np.zeros(n), "joint": np.array([""] * n, dtype=object)})
        better = ratio > cur["ratio"]
        cur["ratio"] = np.where(better, ratio, cur["ratio"])
        cur["joint"] = np.where(better, joint, cur["joint"])

    rows = []
    summary = {r["joint"]: r for r in loads_pre["summary"]}
    judged = in_clip & pre
    for c in servos:
        jid = c["joint"]
        short = jid.replace("joint.", "")
        srow = summary.get(jid, {})
        stall_s, rated_s = srow.get("stall_nm"), srow.get("rated_nm")
        tau_s = np.abs(cols.get(f"{short}.servo_nm", np.zeros(n)))
        add("envelope", "Torque-speed envelope", c["use"] / keep, short)
        add("speed", "Speed against the servo's", c["speed_ratio"] / keep, short)
        if stall_s:
            add("stall", "Torque against stall", tau_s / (stall_s * keep), short)
        if rated_s:
            add("rated", f"Torque against {checks['rated_fraction']:.0%} of rated", tau_s / (rated_s * checks["rated_fraction"] * keep), short)
        belt = belts.get(short.split(".")[-1]) if f"{short}.belt_n" in cols else None
        tension = cols.get(f"{short}.belt_n")
        if belt is not None and tension is not None:
            if belt.get("allowable_working_tension_n"):
                add("belt", "Belt tension against allowable", tension / (float(belt["allowable_working_tension_n"]) * keep), short)
            if belt.get("breaking_strength_n"):
                add("belt_breaking", f"Belt tension against {checks['breaking_fraction']:.0%} of breaking",
                    tension / (float(belt["breaking_strength_n"]) * checks["breaking_fraction"] * keep), short)
        lo, hi = spec.joint(jid).range_deg
        if jid in qa:
            near = np.minimum(qa[jid] - lo, hi - qa[jid])
            add("joint_limit", "At a joint limit (within 1 deg)", np.where(near <= 1.0, 1.01, 0.0), short)
        err = (qa[jid] - ref[jid]) if jid in qa and jid in ref else None
        cmd_err = (qa[jid] - ctrl[jid]) if jid in qa and jid in ctrl else None
        row: dict[str, Any] = {
            "joint": jid, "drive": srow.get("drive"), "in_clip": jid in clip.joints,
            "range_deg": [lo, hi],
            "tracking_rms_deg": float(np.sqrt(np.mean(err[judged] ** 2))) if err is not None and judged.any() else None,
            "tracking_peak_deg": float(np.max(np.abs(err[judged]))) if err is not None and judged.any() else None,
            "command_rms_deg": float(np.sqrt(np.mean(cmd_err[judged] ** 2))) if cmd_err is not None and judged.any() else None,
            "servo_torque_peak_nm": float(np.max(tau_s[pre])) if n else 0.0,
            "rated_nm": rated_s, "stall_nm": stall_s,
            "pct_rated_peak": srow.get("pct_rated_peak"), "pct_stall_peak": srow.get("pct_stall_peak"),
            "above_rated_fraction": srow.get("above_rated_fraction_of_cycle"),
            "speed_peak_deg_s": float(u.rad_to_deg(float(np.max(np.abs(c["omega"][pre]))))) if n else 0.0,
            "speed_limit_deg_s": float(u.rad_to_deg(c["no_load_joint_rad_s"])),
            "envelope_peak": float(np.max(c["use"][pre])) if n else 0.0,
            "envelope_saturated_fraction": float(np.mean(c["use"][pre] >= 0.98)) if n else 0.0,
            "belt_tension_peak_n": srow.get("belt_tension_peak_n"),
            "belt_allowable_n": srow.get("allowable_n"), "belt_breaking_n": srow.get("breaking_n"),
            "rest_deg": rest.get(jid, 0.0),
        }
        rows.append(row)

    # hooves: contact and impacts, against body weight (no hoof limit in the library)
    weight_n = float(rollout.meta.get("total_mass_kg") or 0.0) * 9.81
    stance = clip.meta.get("stance") or {}
    planned = stance.get("support_fraction") or {}
    ff = rollout.foot_force[m].astype(float) if rollout.foot_force.size else np.zeros((n, 0))
    hooves = []
    for k, g in enumerate(rollout.foot_geoms):
        f = ff[:, k] if ff.shape[1] > k else np.zeros(n)
        imp = [(ti, sp) for (ti, fi, sp) in rollout.impacts if fi == k]
        forces = []
        for ti, _sp in imp:
            w = (t >= ti) & (t <= ti + 0.05)
            forces.append(float(np.max(f[w])) if w.any() else 0.0)
        hooves.append({
            "foot": g, "peak_force_n": float(np.max(f[pre])) if n else 0.0,
            "contact_fraction": float(np.mean(f[judged] > 1.0)) if judged.any() else None,
            "planned_support_fraction": planned.get(g),
            "peak_over_weight": float(np.max(f)) / weight_n if n and weight_n else None,
            "impacts": len(imp), "peak_impact_speed_m_s": max((sp for _ti, sp in imp), default=0.0),
            "peak_impact_force_n": max(forces, default=0.0),
        })
    total_contact = ff.sum(axis=1) if ff.size else np.zeros(n)
    battery = battery_current(rollout, servos)

    policy = SafetyPolicy(margin=margin, **({"rated_fraction": checks["rated_fraction"],
                                             "sustained_fraction": checks["sustained_fraction"],
                                             "breaking_fraction": checks["breaking_fraction"]}))
    metrics = compute_metrics(rollout)
    safety = safety_report(rollout, spec, lib, policy, metrics)
    fell = bool(rollout.meta.get("fell"))
    fall_t = rollout.meta.get("fall_time")
    if fell and fall_t is not None:
        add("fall", "The body has fallen", np.where(t >= float(fall_t), 1.01, 0.0), "trunk")

    # frames: clip time -> clip frame -> video frame
    fm = frame_map or {}

    def video_frame(ti: float) -> int | None:
        if fm.get("start") is None or not (timing["clip_t0"] <= ti < timing["clip_t1"]):
            return None
        return int(fm["start"]) + int(math.floor((ti - timing["clip_t0"]) * clip.fps * float(fm.get("frames_per_clip_frame", 1.0))))

    # strip: buckets of frames, the worst level per limit
    nb = min(STRIP_COLUMNS, max(1, n))
    edges = np.linspace(0, n, nb + 1).astype(int)
    strip_rows = []
    events = []
    order = ["fall", "envelope", "speed", "stall", "rated", "belt", "belt_breaking", "joint_limit"]
    for key in [k for k in order if k in limits]:
        lim = limits[key]
        r = lim["ratio"]
        lev = np.where(r > 1.0, OVER, np.where(r > 0.9, NEAR, OK))
        cells, who = [], []
        for a, b in zip(edges[:-1], edges[1:], strict=True):
            if b <= a:
                b = a + 1
            k = a + int(np.argmax(r[a:b]))
            cells.append(int(lev[a:b].max()))
            who.append(str(lim["joint"][k]) if lev[a:b].max() > OK else "")
        strip_rows.append({"key": key, "label": lim["label"], "levels": cells, "joints": who,
                           "peak": float(np.max(r)) if n else 0.0,
                           "peak_joint": str(lim["joint"][int(np.argmax(r))]) if n else "",
                           "over_fraction": float(np.mean(r > 1.0)) if n else 0.0})
        for a, b in _spans(r > 1.0, t):
            k = a + int(np.argmax(r[a:b]))
            events.append({"key": key, "label": lim["label"], "joint": str(lim["joint"][k]), "t0": float(t[a]),
                           "t1": float(t[b - 1]), "peak": float(r[k]), "t_peak": float(t[k]),
                           "phase": ["lead-in", "clip", "return"][int(phase[k])], "rollout_frame": int(np.flatnonzero(m)[k]),
                           "video_frame": video_frame(float(t[k]))})
    events.sort(key=lambda e: e["t0"])
    # what limits the clip first: the earliest moment over an instantaneous limit. Rated torque and the belt's
    # allowable tension are judged as sustained (the constraints table); one frame over them is not a violation.
    first = next((e for e in events if e["key"] not in SUSTAINED), None)
    bucket_t = [float(t[min(n - 1, a)]) for a in edges[:-1]] if n else []
    index = np.flatnonzero(m)  # rows of the recorded rollout, as the viewport's playback counts them
    strip = {
        "t": bucket_t, "t_end": float(t[-1]) if n else 0.0,
        "rollout_frame": [int(index[min(n - 1, a)]) for a in edges[:-1]] if n else [],
        "phase": [int(phase[min(n - 1, a)]) for a in edges[:-1]] if n else [],
        "video_frame": [video_frame(x) for x in bucket_t],
        "rows": strip_rows,
        "series": {  # small per-bucket series for the strip's tooltip lines
            "contact_n": [float(total_contact[a:max(b, a + 1)].max()) for a, b in zip(edges[:-1], edges[1:], strict=True)] if n else [],
            "power_w": [float(battery["power_w"][a:max(b, a + 1)].max()) for a, b in zip(edges[:-1], edges[1:], strict=True)] if n else [],
        },
    }
    clip_rows = [r for r in rows if r["in_clip"] and r["tracking_rms_deg"] is not None]
    err_all = [qa[j][judged] - ref[j][judged] for j in aj if j in qa and j in ref and j in clip.joints]
    within = not safety["violations"]
    first_limit = None
    if first is not None:
        first_limit = {k: first[k] for k in ("key", "label", "joint", "t0", "peak", "phase", "video_frame")}
    out = {
        "clip": clip.id, "name": clip.name, "fps": clip.fps, "frames": clip.frames, "duration_s": clip.duration_s,
        "timing": timing, "margin": margin,
        "judged_until_s": float(fall_at) if fall_at is not None else None,
        "within_limits": within and not fell,
        "verdict": ("falls" if fell else "within limits" if within else "over a limit"),
        "fell": fell, "fall_time_s": fall_t,
        "first_limit": first_limit,
        "tracking_rms_deg": float(np.sqrt(np.mean(np.concatenate(err_all) ** 2))) if err_all else None,
        "tracking_peak_deg": max((r["tracking_peak_deg"] for r in clip_rows), default=None),
        "joints": rows,
        "constraints": safety["constraints"],
        "safety": {k: safety[k] for k in ("rejected", "reject_reasons", "penalty", "margin", "violations")},
        "hooves": hooves, "body_weight_n": weight_n,
        "hooves_down_fewer_than_3_fraction": (float(np.mean((ff[judged] > 1.0).sum(axis=1) < 3))
                                              if judged.any() and ff.size else None),
        "stance": ({"min_support": (stance.get("settings") or {}).get("min_support"),
                    "stability_margin_mm": (stance.get("settings") or {}).get("stability_margin_mm"),
                    **{k: stance.get(k) for k in ("fewer_than_min_support_frames", "com_outside_before_fraction",
                                                  "com_outside_after_fraction", "slip_after_mm", "return_end")}}
                   if stance else None),
        "peak_contact_total_n": float(np.max(total_contact)) if n else 0.0,
        "battery": {
            "known": battery["known"], "voltage_v": battery["voltage_v"], "note": battery["note"],
            "missing_stall_current": battery["missing_stall_current"],
            "peak_power_w": float(np.max(battery["power_w"])) if n else 0.0,
            "mean_power_w": float(np.mean(battery["power_w"])) if n else 0.0,
            "peak_current_a": float(np.max(battery["current_a"])) if battery["current_a"] is not None and n else None,
            "peak_current_lower_bound_a": (float(np.max(battery["current_lower_bound_a"]))
                                           if battery["current_lower_bound_a"] is not None and n else None),
        },
        "events": events[:200], "events_total": len(events),
        "strip": strip,
        "servo_model": rollout.meta.get("servo_model"),
        "mass_kg": rollout.meta.get("total_mass_kg"),
    }
    return out


def clip_part(rollout: Any, timing: dict[str, Any]) -> Any:
    """The rollout cut to the clip itself (time from 0), for movement features."""
    keep = (rollout.t >= timing["clip_t0"]) & (rollout.t < timing["clip_t1"])
    if keep.sum() < 4:
        return rollout
    cut = {f.name: (getattr(rollout, f.name)[keep] if isinstance(getattr(rollout, f.name), np.ndarray)
                    and getattr(rollout, f.name).shape[:1] == rollout.t.shape else getattr(rollout, f.name))
           for f in dataclasses.fields(rollout)}
    cut["t"] = rollout.t[keep] - timing["clip_t0"]
    return dataclasses.replace(rollout, **cut)
