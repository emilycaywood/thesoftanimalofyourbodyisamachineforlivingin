"""Physical limits of the servos and the battery, per frame (ADR-084).

Used by the physics review of clips (:mod:`calflab.behave.physics`) and by the
safety constraints of the repertoire evolution (:mod:`calflab.evolve.safety`),
so both judge a motion on the same numbers:

* the torque-speed **envelope** of every servo (:mod:`calflab.sim.servo`): how
  much of it each frame uses, from the joint torque the simulator applied and
  the joint speed;
* **speed** against the servo's no-load speed at that joint (a 2:1 belt halves
  it);
* the **battery current**. A servo's current is |servo torque| / kt + idle,
  kt = stall torque / stall current, only when the library has its stall
  current. Without it the current is unknown, and the lab gives a lower bound
  instead: the mechanical power the servos put out (positive work only) divided
  by the servo's rated voltage. Motor and driver losses would only add to it.

Only library values are used; a value the library does not have is reported as
unknown, never filled in.

Units: N*m, rad/s (deg/s in reports), W, A, V.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab import units as u
from calflab.model.spec import RobotSpec
from calflab.sim.servo import envelope_use


def joint_figures(comp: Any, tr: Any) -> dict[str, float]:
    """A servo's figures at the joint it drives through transmission ``tr`` (None = direct): ratio, efficiency,
    stall torque (N*m) and no-load speed (rad/s). The one place these are worked out (simulator columns and the lab's
    per-joint servo table, ADR-101)."""
    ratio, eff = (float(tr.ratio), float(tr.efficiency)) if tr else (1.0, 1.0)
    return {"ratio": ratio, "efficiency": eff, "stall_joint_nm": comp.stall_torque_nm * ratio * eff,
            "no_load_joint_rad_s": u.deg_to_rad(comp.no_load_speed_rpm * 6.0) / ratio}


def joint_servos(spec: RobotSpec, lib: Any) -> list[dict[str, Any]]:
    """Per actuated joint, the servo on it and its limits there (ADR-101): the component, its mass (g) and
    ``verified`` flag, the belt ratio, stall and rated torque at the servo and at the joint (N*m; rated None = not
    given), and the no-load speed at the joint (deg/s). For the lab's Mass tab; the simulator uses the same figures."""
    trans = {t.id: t for t in spec.transmissions}
    joints = {j.id: j for j in spec.joints}
    out = []
    for a in spec.actuators:
        comp = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        f = joint_figures(comp, tr)
        rated = comp.rated_torque_nm
        j = joints.get(a.joint)
        out.append({
            "actuator": a.id, "joint": a.joint, "joint_name": (j.name or j.id) if j else a.joint,
            "component": comp.key, "name": comp.name, "verified": comp.verified, "mass_g": comp.mass_g,
            "drive": tr.type if tr else "direct", "ratio": f["ratio"], "efficiency": f["efficiency"],
            "stall_servo_nm": comp.stall_torque_nm, "rated_servo_nm": rated,
            "stall_joint_nm": round(f["stall_joint_nm"], 4),
            "rated_joint_nm": None if rated is None else round(rated * f["ratio"] * f["efficiency"], 4),
            "speed_joint_deg_s": round(u.rad_to_deg(f["no_load_joint_rad_s"]), 2),
            "voltage_v": comp.voltage_v, "unknown": list(comp.unknown),
        })
    return out


def servo_columns(rollout: Any, spec: RobotSpec, lib: Any) -> list[dict[str, Any]]:
    """Per actuator, over the controller's part of the rollout (t >= 0): joint torque, joint speed, the stall
    torque and no-load speed at the joint, envelope use and speed ratio per frame."""
    m = rollout.t >= 0.0
    trans = {t.id: t for t in spec.transmissions}
    acts = {a.id: a for a in spec.actuators}
    # The simulator holds a torque-speed servo on its envelope at every physics step; the recorded torque comes from
    # the speed one 2 ms step before the recorded speed, so a frame can read a few % over 100 %: it is shown as 100 %.
    # Under the torque-only model, over 100 % means a motion the real servo could not make.
    cap = 1.0 if rollout.meta.get("servo_model") == "torque_speed" else np.inf
    out = []
    for i, aid in enumerate(rollout.actuator_ids):
        a = acts.get(aid)
        if a is None:
            continue
        comp = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        f = joint_figures(comp, tr)
        ratio, eff, stall_j, w0_j = f["ratio"], f["efficiency"], f["stall_joint_nm"], f["no_load_joint_rad_s"]
        tau = rollout.torque[m, i].astype(float)
        w = rollout.dq[m, i].astype(float)
        out.append({
            "actuator": aid, "joint": a.joint, "component": comp.key, "ratio": ratio, "efficiency": eff,
            "stall_joint_nm": stall_j, "no_load_joint_rad_s": w0_j, "torque": tau, "omega": w,
            "use": np.minimum(envelope_use(tau, w, np.full_like(tau, stall_j), np.full_like(w, w0_j)), cap),
            "speed_ratio": np.abs(w) / max(w0_j, 1e-9),
            "voltage_v": comp.voltage_v, "stall_current_a": comp.stall_current_a, "idle_current_a": comp.idle_current_a,
            "stall_servo_nm": comp.stall_torque_nm,
        })
    return out


def battery_current(rollout: Any, cols: list[dict[str, Any]]) -> dict[str, Any]:
    """Battery current per frame: the servos' sum when every stall current is known; otherwise unknown, with a
    lower bound from mechanical power / rated voltage."""
    m = rollout.t >= 0.0
    t = rollout.t[m]
    n = len(t)
    power = np.zeros(n)
    for c in cols:
        power += np.maximum(0.0, c["torque"] * c["omega"])
    volts = sorted({float(c["voltage_v"]) for c in cols if c.get("voltage_v")})
    v = volts[0] if len(volts) == 1 else None
    unknown = [c["actuator"] for c in cols if c["stall_current_a"] is None]
    current = None
    if cols and not unknown:
        current = np.zeros(n)
        for c in cols:
            kt = c["stall_servo_nm"] / max(float(c["stall_current_a"]), 1e-9)
            current += np.abs(c["torque"]) / (c["ratio"] * c["efficiency"]) / kt + float(c["idle_current_a"])
    bound = power / v if v else None
    return {
        "t": t,
        "power_w": power,
        "current_a": current,
        "current_lower_bound_a": bound,
        "voltage_v": v,
        "known": current is not None,
        "missing_stall_current": unknown,
        "note": ("Battery current from each servo's torque and stall current (idle current included)." if current is not None
                 else f"Current UNKNOWN: no stall current in the library for {', '.join(sorted({c['component'] for c in cols if c['stall_current_a'] is None}))}. "
                      f"Lower bound = mechanical power out / {v:g} V (the servo's rated voltage); motor and driver losses, "
                      "idle draw and the electronics would only add to it." if v else
                      "Current UNKNOWN: no stall current, and the servos' voltages differ or are missing."),
    }
