"""Step 2: where the load goes. Per joint: static weight in stance vs dynamics, and what the springs carry.

For every recorded frame the pose is rebuilt in MuJoCo (root from the trunk's recorded pose, joints from q).
Static joint load S (N*m, joint side) = gravity on everything below the joint minus the ground's vertical
reactions that balance the whole weight over the hooves that are down (min-norm, as calflab.mech.statics).
What actuator + springs must supply to hold the pose still = S. The servo's static share = S - spring.
Dynamics D = measured actuator torque - (S - spring): accelerations, ground forces above the weight, passive.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---- record the full 3D hoof forces at every control step (the runner's own instant), for this study only
import calflab.sim as _sim
import mujoco
import numpy as np
from calflab.app.lab import Lab
from calflab.app.physics_jobs import _context
from calflab.behave.interpret import InterpretSettings, judge, play_primitive
from calflab.behave.physics import compile_params
from calflab.components.library import library
from calflab.mech.loads import windowed_fraction
from calflab.plugins import registry
from calflab.sim import CompileOptions, compile_mjcf

_REC: list = []
_STATE = {"on": False, "model": None}
_orig_kin = mujoco.mj_kinematics
_orig_run = _sim.run_rollout


def _kin(model, data):
    _orig_kin(model, data)
    if not _STATE["on"]:
        return
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    buf = np.zeros(6)
    out = {}
    for i in range(data.ncon):
        c = data.contact[i]
        g1, g2 = int(c.geom1), int(c.geom2)
        if floor not in (g1, g2):
            continue
        foot = g2 if g1 == floor else g1
        mujoco.mj_contactForce(model, data, i, buf)
        fw = c.frame.reshape(3, 3).T @ buf[:3]
        if foot == g1:
            fw = -fw
        f, p = out.get(foot, (np.zeros(3), np.zeros(3)))
        out[foot] = (f + fw, p + c.pos * max(fw[2], 1e-9))
    _REC.append({g: (f, p / max(f[2], 1e-9)) for g, (f, p) in out.items()})


def _run(*a, **k):
    _REC.clear()
    _STATE["on"] = True
    try:
        return _orig_run(*a, **k)
    finally:
        _STATE["on"] = False


mujoco.mj_kinematics = _kin
_sim.run_rollout = _run

proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
lab = Lab.open(proj, create=False)
ctx = _context(lab)
spec, doc = ctx["design"].spec, dict(ctx["doc_compile"])
lib = library()
s = InterpretSettings()
interp = json.loads((proj / "runs/20261104-042426-interpret-ef3c/interpretation.json").read_text(encoding="utf-8"))
params = {r["behaviour"]: (r["primitive"], r["params"]) for r in interp["records"]}
MOTIONS = {"stand (check)": ("stand", {}), "walk": ("walk", {}), "trot": ("trot", {}),
           "interpreted trot": params["other"], "interpreted step": params["step"]}
MARGIN = 0.2
keep = 1 - MARGIN
feral = spec.metadata.get("feral") or {}
belts = feral.get("belt_drives") or {}
checks = {"rated_fraction": 0.6, "sustained_fraction": 0.25, **(feral.get("checks") or {})}
trans = {t.id: t for t in spec.transmissions}
acts = {a.id: a for a in spec.actuators}


def decompose(ro):
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(compile_params(doc)), s.seed)
    m = mujoco.MjModel.from_xml_string(cm.xml)
    d = mujoco.MjData(m)
    free = [j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE][0]
    root_body = int(m.jnt_bodyid[free])
    root_name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, root_body)
    bi = ro.body_ids.index(root_name)
    jq = {jid: int(m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jid)]) for jid in ro.joint_ids}
    foot_gid = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, g) for g in ro.foot_geoms]
    weight = float(np.sum(m.body_mass)) * 9.81
    a_dof, a_joint = [], []
    for aid in ro.actuator_ids:
        jid = acts[aid].joint
        a_joint.append(jid)
        a_dof.append(int(m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jid)]))
    sp_joint = {sp.id: sp.joint for sp in spec.springs}
    mask = ro.t >= 0
    idx = np.nonzero(mask)[0]
    S = np.zeros((len(idx), len(a_dof)))
    SP = np.zeros_like(S)
    ndown = np.zeros(len(idx), dtype=int)
    fzratio = np.ones(len(idx))
    fcheck = np.zeros(len(idx))
    recs = list(_REC)
    jac = np.zeros((3, m.nv))
    for n, k in enumerate(idx):
        d.qpos[:] = m.qpos0
        d.qpos[0:3] = ro.body_pos[k, bi]
        d.qpos[3:7] = ro.body_quat[k, bi]
        for jid, adr in jq.items():
            d.qpos[adr] = ro.q[k, ro.joint_ids.index(jid)]
        d.qvel[:] = 0
        d.qacc[:] = 0
        mujoco.mj_forward(m, d)
        bias = d.qfrc_bias.copy()  # gravity only (qvel = 0)
        step = int(round((ro.t[k] + 0.4) / 0.02))  # settle 0.4 s, control 50 Hz (as play_primitive)
        cf = recs[step] if step < len(recs) else {}
        down = [i for i, g in enumerate(foot_gid) if g in cf and cf[g][0][2] > 1.0]
        ndown[n] = len(down)
        tauF = np.zeros(m.nv)
        fz_sum = sum(cf[foot_gid[i]][0][2] for i in down)
        if down and fz_sum > 0:
            scale = weight / fz_sum  # the ground forces as they were, scaled to carry just the weight
            for i in down:
                f, p = cf[foot_gid[i]]
                mujoco.mj_jac(m, d, jac, None, p, int(m.geom_bodyid[foot_gid[i]]))
                tauF += jac.T @ (f * scale)
            fzratio[n] = fz_sum / weight
            fcheck[n] = abs(fz_sum - sum(ro.foot_force[k]))
        S[n] = (bias - tauF)[a_dof]
        if ro.spring_torque is not None:
            for si, sid in enumerate(ro.spring_ids):
                if sp_joint.get(sid) in a_joint:
                    SP[n, a_joint.index(sp_joint[sid])] += ro.spring_torque[k, si]
    print(f'  ground/weight mean {fzratio.mean():.2f} max {fzratio.max():.2f}; |sum Fz - recorded| max {fcheck.max():.2f} N')
    return idx, a_joint, S, SP, ndown


rows = {}
for name, (pkey, pp) in MOTIONS.items():
    prim = registry.get("motion_primitive", pkey)(pp)
    ro, t0, t1, _ = play_primitive(prim, spec, lib, doc, s)
    j = judge(ro, spec, lib, MARGIN)
    idx, joints, S, SP, ndown = decompose(ro)
    t = ro.t[idx]
    meas = ro.torque[idx].astype(float)
    out = []
    for c, jid in enumerate(joints):
        a = next(a for a in spec.actuators if a.joint == jid)
        comp = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        gain = tr.ratio * tr.efficiency if tr else 1.0
        rated_thr = checks["rated_fraction"] * keep * comp.rated_torque_nm  # servo side, N*m
        servo = meas[:, c] / gain
        static_servo = (S[:, c] - SP[:, c]) / gain
        static_nospring = S[:, c] / gain
        dyn = servo - static_servo
        own = jid.split(".")[-1]
        bd = belts.get(own) if tr and tr.type == "belt" else None
        row = {"joint": jid.replace("joint.", ""), "gain": gain,
               "servo_mean_abs": float(np.mean(np.abs(servo))),
               "static_with_springs_mean": float(np.mean(static_servo)),
               "static_no_springs_mean": float(np.mean(static_nospring)),
               "spring_mean_servo_side": float(np.mean(SP[:, c] / gain)),
               "dyn_rms": float(np.sqrt(np.mean(dyn ** 2))),
               "sust_measured": windowed_fraction(np.abs(servo) > rated_thr, t, 2.0),
               "sust_static_with_springs": windowed_fraction(np.abs(static_servo) > rated_thr, t, 2.0),
               "sust_static_no_springs": windowed_fraction(np.abs(static_nospring) > rated_thr, t, 2.0),
               "rated_thr": rated_thr}
        if bd and bd.get("allowable_working_tension_n") and bd.get("d1_mm"):
            belt_thr = float(bd["allowable_working_tension_n"]) * keep * (float(bd["d1_mm"]) / 2000.0)
            row.update({"belt_thr_servo_nm": belt_thr,
                        "belt_measured": windowed_fraction(np.abs(servo) > belt_thr, t, 2.0),
                        "belt_static_with_springs": windowed_fraction(np.abs(static_servo) > belt_thr, t, 2.0),
                        "belt_static_no_springs": windowed_fraction(np.abs(static_nospring) > belt_thr, t, 2.0)})
        out.append(row)
    rows[name] = {"margin": j["margin"], "violations": j["violations"], "joints": out,
                  "share_down": {str(n): float(np.mean(ndown == n)) for n in range(5)}}
    print(f"\n== {name}: margin {j['margin']} {j['violations']}  hooves down "
          + " ".join(f"{n}:{np.mean(ndown == n):.0%}" for n in range(5)))
    print(f"{'joint':14s} {'thr':>5s} {'|servo|':>7s} {'stat+sp':>7s} {'stat':>7s} {'spring':>7s} {'dynRMS':>7s} "
          f"| sust meas/stat+sp/stat | belt meas/stat+sp/stat")
    for r in out:
        b = (f"{r['belt_measured']:.2f}/{r['belt_static_with_springs']:.2f}/{r['belt_static_no_springs']:.2f} "
             f"(thr {r['belt_thr_servo_nm']:.2f})") if "belt_measured" in r else ""
        print(f"{r['joint']:14s} {r['rated_thr']:5.2f} {r['servo_mean_abs']:7.3f} {r['static_with_springs_mean']:+7.3f} "
              f"{r['static_no_springs_mean']:+7.3f} {r['spring_mean_servo_side']:+7.3f} {r['dyn_rms']:7.3f} | "
              f"{r['sust_measured']:.2f}/{r['sust_static_with_springs']:.2f}/{r['sust_static_no_springs']:.2f} | {b}")
outp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
