"""Joint, servo, spring and belt loads from a rollout (ADR-069).

For every actuated joint, at every recorded frame:

* joint torque from the servo through its drive (N*m), as the simulator applied it;
* servo-side torque = joint torque / (ratio x efficiency);
* spring torque about the joint (N*m), from the springs across it;
* belt tension T = servo torque / (D1 / 2) (N), for a belted joint;
* servo load as a percentage of its rated and of its stall torque.

Flags (thresholds from the generator's params, all in the run record):

* a servo above ``rated_fraction`` x rated torque for more than
  ``sustained_fraction`` of any one gait cycle;
* a servo at or above its stall torque at any moment (the simulator caps a
  servo at stall, so this is the moment it saturates);
* belt tension above the belt system's allowable working tension for more
  than ``sustained_fraction`` of any one gait cycle ("unknown" where the
  allowable tension is not known);
* belt tension peaks above ``breaking_fraction`` x breaking strength.

Units: s, N, N*m, %.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.sim.rollout import Rollout

#: scenario name -> controller mode and simulated duration (s) after settling
SCENARIOS: dict[str, dict[str, Any]] = {
    "stand": {"mode": "stand", "label": "Quiet standing"},
    "walk": {"mode": "walk", "label": "Slow walk"},
    "trot": {"mode": "trot", "label": "Trot"},
    "lie_rise": {"mode": "lie_rise", "label": "Lying down and rising (hind end first, then front from kneeling)"},
}


def scenario_duration(mode: str, ctrl: dict[str, Any]) -> float:
    """How long to simulate a scenario (s): standing 4 s; walk ramp + 3 cycles; lie/rise its script + 2 s."""
    if mode == "walk":
        return float(ctrl.get("ramp", 1.5)) + 3.0 * float(ctrl.get("cycle_s", 4.0))
    if mode == "trot":
        return float(ctrl.get("ramp", 1.5)) + 10.0 * float(ctrl.get("trot_cycle_s", 0.6))
    if mode == "lie_rise":
        return 5.0 * float(ctrl.get("phase_s", 2.0)) + float(ctrl.get("hold_s", 1.5)) + 2.0
    return 4.0


def windowed_fraction(above: np.ndarray, t: np.ndarray, window_s: float) -> float:
    """Largest fraction of frames above a limit in any window of ``window_s`` (whole run if shorter)."""
    n = len(above)
    if n == 0:
        return 0.0
    if t[-1] - t[0] <= window_s:
        return float(np.mean(above))
    c = np.concatenate([[0], np.cumsum(above.astype(int))])
    best = 0.0
    j = 0
    for i in range(n):
        while j < n and t[j] - t[i] < window_s:
            j += 1
        best = max(best, (c[j] - c[i]) / max(1, j - i))
        if j >= n:
            break
    return float(best)


def analyse(
    rollout: Rollout,
    spec: RobotSpec,
    lib: Any,
    cycle_s: float,
    checks: dict[str, float],
    belts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Per-frame loads and a per-joint summary of one rollout (from t >= 0)."""
    m = rollout.t >= 0.0
    t = rollout.t[m]
    trans = {tr.id: tr for tr in spec.transmissions}
    act_of = {a.id: a for a in spec.actuators}
    belts = belts or {}
    rated_frac = float(checks.get("rated_fraction", 0.6))
    sustained = float(checks.get("sustained_fraction", 0.25))
    breaking_frac = float(checks.get("breaking_fraction", 0.25))
    spring_joint = {sp.id: sp.joint for sp in spec.springs}
    cols: dict[str, np.ndarray] = {"t_s": t}
    summary: list[dict[str, Any]] = []
    flags: list[str] = []
    for i, aid in enumerate(rollout.actuator_ids):
        a = act_of.get(aid)
        if a is None:
            continue
        jid = a.joint
        comp = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        ratio, eff = (tr.ratio, tr.efficiency) if tr else (1.0, 1.0)
        tau_j = rollout.torque[m, i].astype(float)
        tau_s = tau_j / (ratio * eff)
        spring = np.zeros_like(tau_j)
        if rollout.spring_torque is not None:
            for s, sid in enumerate(rollout.spring_ids):
                if spring_joint.get(sid) == jid:
                    spring += rollout.spring_torque[m, s].astype(float)
        qi = rollout.joint_ids.index(jid) if jid in rollout.joint_ids else None
        angle = u.rad_to_deg(rollout.q[m, qi].astype(float)) if qi is not None else np.zeros_like(tau_j)
        rated = comp.rated_torque_nm
        stall = comp.stall_torque_nm
        short = jid.replace("joint.", "")
        cols[f"{short}.angle_deg"] = angle
        cols[f"{short}.joint_nm"] = tau_j
        cols[f"{short}.servo_nm"] = tau_s
        cols[f"{short}.spring_nm"] = spring
        cols[f"{short}.total_nm"] = tau_j + spring
        cols[f"{short}.pct_stall"] = 100.0 * np.abs(tau_s) / stall
        if rated:
            cols[f"{short}.pct_rated"] = 100.0 * np.abs(tau_s) / rated
        row: dict[str, Any] = {
            "joint": jid,
            "actuator": aid,
            "servo": comp.key,
            "drive": f"belt {ratio:g}:1" if tr and tr.type == "belt" else "direct",
            "ratio": ratio,
            "efficiency": eff,
            "joint_torque_peak_nm": float(np.max(np.abs(tau_j))) if len(t) else 0.0,
            "joint_torque_rms_nm": float(np.sqrt(np.mean(tau_j**2))) if len(t) else 0.0,
            "servo_torque_peak_nm": float(np.max(np.abs(tau_s))) if len(t) else 0.0,
            "servo_torque_mean_abs_nm": float(np.mean(np.abs(tau_s))) if len(t) else 0.0,
            "spring_torque_mean_nm": float(np.mean(spring)) if len(t) else 0.0,
            "spring_torque_peak_nm": float(np.max(np.abs(spring))) if len(t) else 0.0,
            "rated_nm": rated,
            "stall_nm": stall,
            "pct_stall_peak": float(100.0 * np.max(np.abs(tau_s)) / stall) if len(t) else 0.0,
            "pct_rated_peak": float(100.0 * np.max(np.abs(tau_s)) / rated) if rated and len(t) else None,
        }
        if rated:
            frac = windowed_fraction(np.abs(tau_s) > rated_frac * rated, t, cycle_s)
            row["above_rated_fraction_of_cycle"] = frac
            row["sustained_above_rated"] = frac > sustained
            if frac > sustained:
                flags.append(f"{short}: servo above {rated_frac:.0%} of rated torque for {frac:.0%} of a gait cycle "
                             f"(sustained limit {sustained:.0%})")
        else:
            row["above_rated_fraction_of_cycle"] = None
            row["sustained_above_rated"] = None
        stall_hit = np.abs(tau_s) >= 0.999 * stall
        row["at_stall"] = bool(np.any(stall_hit))
        row["stall_time_s"] = float(np.sum(stall_hit) * (rollout.meta.get("record_dt") or 0.0))
        if row["at_stall"]:
            first = float(t[np.argmax(stall_hit)])
            flags.append(f"{short}: servo at or above stall torque ({stall:g} N*m), first at t = {first:.2f} s")
        drive = short.split(".")[-1]
        belt = belts.get(drive) if tr and tr.type == "belt" else None
        if belt is not None:
            d1 = float(belt["d1_mm"])
            tension = np.abs(tau_s) / u.mm_to_m(d1 / 2.0)
            cols[f"{short}.belt_n"] = tension
            allow, brk = belt.get("allowable_working_tension_n"), belt.get("breaking_strength_n")
            row.update({
                "belt_system": belt["choice"]["system"],
                "belt_length": belt["choice"]["length"],
                "pulleys": belt["choice"]["pulleys"],
                "c_mm": belt.get("c_mm"),
                "belt_tension_peak_n": float(np.max(tension)) if len(t) else 0.0,
                "belt_tension_mean_n": float(np.mean(tension)) if len(t) else 0.0,
                "allowable_n": allow,
                "breaking_n": brk,
            })
            if allow is None:
                row["above_allowable_fraction_of_cycle"] = None
                row["sustained_above_allowable"] = "unknown"
            else:
                frac = windowed_fraction(tension > float(allow), t, cycle_s)
                row["above_allowable_fraction_of_cycle"] = frac
                row["sustained_above_allowable"] = frac > sustained
                if frac > sustained:
                    flags.append(f"{short}: belt above its allowable working tension ({allow:g} N) for {frac:.0%} of a gait "
                                 f"cycle (sustained limit {sustained:.0%})")
            if brk is None:
                row["peak_over_breaking"] = None
                row["breaking_flag"] = "unknown"
            else:
                ratio_b = row["belt_tension_peak_n"] / float(brk)
                row["peak_over_breaking"] = ratio_b
                row["breaking_flag"] = ratio_b > breaking_frac
                if ratio_b > breaking_frac:
                    flags.append(f"{short}: belt tension peak {row['belt_tension_peak_n']:.0f} N is {ratio_b:.0%} of breaking "
                                 f"strength ({brk:g} N; limit {breaking_frac:.0%})")
        summary.append(row)
    trunk = rollout.body_ids.index(spec.root.id) if spec.root.id in rollout.body_ids else 0
    quat = rollout.body_quat[m, trunk]
    up = 1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2) if len(quat) else np.ones(1)
    outcome = {
        "fell": bool(rollout.meta.get("fell")),
        "min_trunk_up": float(np.min(up)),
        "trunk_height_end_mm": float(u.from_si(float(rollout.body_pos[-1, trunk, 2]), "mm")) if rollout.n_frames else 0.0,
        "distance_mm": float(u.from_si(float(rollout.body_pos[-1, trunk, 0] - rollout.body_pos[0, trunk, 0]), "mm")) if rollout.n_frames else 0.0,
    }
    if outcome["fell"] or outcome["min_trunk_up"] < 0.5:
        flags.insert(0, "The body fell over in this run: its loads after the fall are not the motion's loads.")
    return {"columns": cols, "summary": summary, "flags": flags, "outcome": outcome,
            "window_s": cycle_s, "checks": {"rated_fraction": rated_frac, "sustained_fraction": sustained,
                                            "breaking_fraction": breaking_frac}}


def frames_csv(result: dict[str, Any]) -> str:
    cols = result["columns"]
    names = list(cols)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(names)
    n = len(cols["t_s"])
    for k in range(n):
        w.writerow([f"{float(cols[c][k]):.5g}" for c in names])
    return out.getvalue()


SUMMARY_COLUMNS = [
    "joint", "drive", "servo", "joint_torque_peak_nm", "joint_torque_rms_nm", "servo_torque_peak_nm",
    "servo_torque_mean_abs_nm", "pct_rated_peak", "pct_stall_peak", "above_rated_fraction_of_cycle",
    "sustained_above_rated", "at_stall", "stall_time_s", "spring_torque_mean_nm", "spring_torque_peak_nm",
    "belt_system", "pulleys", "belt_length", "c_mm", "belt_tension_peak_n", "belt_tension_mean_n", "allowable_n",
    "above_allowable_fraction_of_cycle", "sustained_above_allowable", "breaking_n", "peak_over_breaking", "breaking_flag",
]


def summary_csv(result: dict[str, Any]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(SUMMARY_COLUMNS)
    for row in result["summary"]:
        w.writerow([_cell(row.get(c)) for c in SUMMARY_COLUMNS])
    return out.getvalue()


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}" if math.isfinite(v) else ""
    return str(v)


def spring_relief(with_springs: dict[str, Any], without: dict[str, Any]) -> list[dict[str, Any]]:
    """How much the springs take off each servo and belt: the same run with and without springs."""
    off = {r["joint"]: r for r in without["summary"]}
    rows = []
    for r in with_springs["summary"]:
        o = off.get(r["joint"])
        if o is None:
            continue
        row = {
            "joint": r["joint"],
            "servo_mean_abs_nm": r["servo_torque_mean_abs_nm"],
            "servo_mean_abs_no_springs_nm": o["servo_torque_mean_abs_nm"],
            "servo_mean_reduction_nm": o["servo_torque_mean_abs_nm"] - r["servo_torque_mean_abs_nm"],
            "servo_peak_nm": r["servo_torque_peak_nm"],
            "servo_peak_no_springs_nm": o["servo_torque_peak_nm"],
            "servo_peak_reduction_nm": o["servo_torque_peak_nm"] - r["servo_torque_peak_nm"],
        }
        if "belt_tension_mean_n" in r and "belt_tension_mean_n" in o:
            row.update({
                "belt_mean_n": r["belt_tension_mean_n"], "belt_mean_no_springs_n": o["belt_tension_mean_n"],
                "belt_mean_reduction_n": o["belt_tension_mean_n"] - r["belt_tension_mean_n"],
                "belt_peak_n": r["belt_tension_peak_n"], "belt_peak_no_springs_n": o["belt_tension_peak_n"],
                "belt_peak_reduction_n": o["belt_tension_peak_n"] - r["belt_tension_peak_n"],
            })
        rows.append(row)
    return rows


def static_spring_report(spec: RobotSpec) -> list[dict[str, Any]]:
    """Each spring in the standing pose: length, force, arm, torque, which way gravity folds its joint and
    whether the spring resists that (side check), and what it takes off the servo and belt (static)."""
    from calflab.mech.springs import side_check, spring_state
    from calflab.mech.statics import _world, joint_frames, static_loads

    poses = spec.world_poses()
    frames = joint_frames(spec, poses)
    loads = static_loads(spec)
    trans = {t.id: t for t in spec.transmissions}
    acts = {a.joint: a for a in spec.actuators}
    belts = (spec.metadata.get("feral") or {}).get("belt_drives", {})
    out = []
    for sp in spec.springs:
        jp, ax = frames[sp.joint]
        st = spring_state(_world(poses, sp.upper_body, sp.upper_pos), _world(poses, sp.lower_body, sp.lower_pos), jp, ax,
                          sp.k_n_per_mm, sp.free_length_mm)
        ld = loads[sp.joint]
        verdict, note = side_check(ld["gravity_nm"], st.torque_nm)
        a = acts.get(sp.joint)
        tr = trans.get(a.transmission) if a and a.transmission else None
        gain = tr.ratio * tr.efficiency if tr else 1.0
        own = sp.joint.split(".")[-1]
        d1 = belts.get(own, {}).get("d1_mm") if tr and tr.type == "belt" else None
        servo_without = abs(ld["gravity_nm"]) / gain
        servo_with = abs(ld["net_nm"]) / gain
        row = {
            "spring": sp.id, "joint": sp.joint, "length_mm": st.length_mm, "stretch_mm": st.stretch_mm,
            "force_n": st.force_n, "arm_mm": st.arm_mm, "torque_nm": st.torque_nm, "slack": st.slack,
            "gravity_nm": ld["gravity_nm"], "side": verdict, "side_note": note,
            "servo_without_nm": servo_without, "servo_with_nm": servo_with,
            "servo_reduction_nm": servo_without - servo_with,
        }
        if d1:
            without_n, with_n = servo_without / u.mm_to_m(d1 / 2.0), servo_with / u.mm_to_m(d1 / 2.0)
            row.update({"belt_without_n": without_n, "belt_with_n": with_n, "belt_reduction_n": without_n - with_n})
        out.append(row)
    return out
