"""Belted or direct carpus on g020-008-r01-mc (after session R18; ADR-123..).

R18 built ``g020-008-r01-mc``: g020-008-r01 with every belt drive on McMaster-Carr parts. Its carpus is belted 1:1
(3MGT 45T/45T, 600 mm, C 232.5 mm) with the C002 carpus servo on the upper leg. This study adds
``g020-008-r01-mc-direct``, the same body with only ``carpus_belt`` off: the C002 sits on the carpus joint (the
generator's direct layout: outboard of the upper-leg tube, centred on the joint axis). Lengths, servos, springs and the
stifle and hock belts are unchanged. Both bodies build at mass model explicit_v2 with the project's current catalog
(Gates 17611-T allowable, breaking strength assumed), as R18's ``base_payload`` gives them.

Stages (``python docs/studies/carpus_r18.py <project> <stage> [--opts]``):

* ``body``       add the direct body to ``mcmaster_r18.json`` (``bodies``, ``labels``, ``order``: beside the swap);
* ``mass``       mass_breakdown of both; the front leg's mass, centre of mass and moment of inertia about the shoulder
                 axis, from the simulator's own compiled model;
* ``clearance``  the carpus hardware (direct: the servo case; belted: the driven pulley) against the front cannon and
                 the ground through the carpus range, and what the model cannot check;
* ``statics``    holding torque at the shoulder and carpus in the standing pose;
* ``loads``      R18's three load plays (level stand, the R16 lowest stand, the 256 mm/s walk) on seed 0: shoulder and
                 carpus servo torque, joint speed use, torque-speed envelope, current, belts;
* ``replay``     the R16 repertoire (107 behaviours, seeds 0-2, 30 s, margin 0.2) on both bodies, judged as R18
                 judged it; the direct body's records are merged into ``mcmaster_r18.json`` for the compare page;
* ``suite``      the R11c suite (screen + 11 behaviours, 60 s, seeds 0-2), scored as ``mcmaster_r18.py confirm`` does;
* ``sheets``     the direct body's production sheet and bill of materials (``sheets_r18/``), against the swap's;
* ``store``      the direct body's seed-0 runs for ``compare.html?set=r18`` (``mcmaster_r18.py store``);
* ``summary``    the tables (``carpus_r18_tables.md``).

Units: mm, g, deg in files; N*m (torque), N (belt tension), A (current), kg*m^2 / g*mm^2 (inertia), mm/s, deg/s.
Nothing in ``config/``, the library or any ``verified`` flag is changed; no hardware is added.
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path("docs/studies").resolve()))

import mcmaster_r18 as m  # noqa: E402

OUT = Path("docs/studies/carpus_r18.json")
TABLES = Path("docs/studies/carpus_r18_tables.md")
SWAP = m.SWAP
DIRECT = "g020-008-r01-mc-direct"
BODIES = (SWAP, DIRECT)
SIDES = ("fl", "fr")
JOINTS = ("shoulder", "carpus")
#: the display order of compare set r18: the direct body beside the belted swap
ORDER = [m.BASE, SWAP, DIRECT, "r18-a", "r18-b", "r18-c"]


def _load() -> dict[str, Any]:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}


def _save(d: dict[str, Any]) -> None:
    OUT.write_text(json.dumps(d, indent=1, default=float), encoding="utf-8")


def _r(x: Any, nd: int = 3) -> Any:
    return None if x is None else round(float(x), nd)


# --------------------------------------------------------------------- the direct body
def direct_genes(swap_genes: dict[str, Any]) -> dict[str, Any]:
    """The swap's genes with only ``carpus_belt`` off (its carpus belt genes stay, unused while the carpus is direct)."""
    return {**swap_genes, "carpus_belt": False}


def body(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.constraints import infeasible
    from calflab.evolve.hardware import _build

    data = m._load()
    bs = data.setdefault("bodies", {})
    bs[DIRECT] = direct_genes(bs[SWAP])
    data.setdefault("labels", {})[DIRECT] = "direct carpus: C002 on the joint"
    data["order"] = [n for n in ORDER if n == m.BASE or n in bs]
    m._save(data)
    pl = m.bodies(lab)
    d_sw, _l = _build(pl[SWAP])
    d_di, _l = _build(pl[DIRECT])
    drives = d_di.spec.metadata["feral"]["belt_drives"]
    if "carpus" in drives or not all(v["ok"] for v in drives.values()) or infeasible(d_di.spec):
        raise SystemExit(f"direct body does not build cleanly: {list(drives)} {infeasible(d_di.spec)}")
    gs, gd = dict(d_sw.genome.values), dict(d_di.genome.values)
    diff = {k: [gs.get(k), gd.get(k)] for k in sorted(set(gs) | set(gd)) if gs.get(k) != gd.get(k)}
    out = _load()
    out["body"] = {"genes_differ": diff, "drives_swap": sorted(d_sw.spec.metadata["feral"]["belt_drives"]),
                   "drives_direct": sorted(drives), "servos": {k: v for k, v in gd.items() if k.startswith("servo_")}}
    _save(out)
    print("direct body stored; genes that differ:", diff)


# --------------------------------------------------------------------- mass, centre of mass, inertia
def _compiled(pl: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    import mujoco
    from calflab.evolve.hardware import _build
    from calflab.sim.mjcf import CompileOptions, compile_mjcf

    design, lib = _build(pl)
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(pl["compile"]), seed=0)
    model = mujoco.MjModel.from_xml_string(cm.xml)
    return design, lib, cm, model


def front_leg(pl: dict[str, Any], side: str = "fl", carpus_deg: float | None = None) -> dict[str, Any]:
    """The front leg (upper leg + cannon, everything on them) from the simulator's compiled model, in the standing pose
    (carpus at ``carpus_deg`` if given): mass (g), centre of mass relative to the shoulder axis in the upper leg's
    frame (mm: x forward, y outboard, z along the leg, negative = down the leg) and its distance from the axis, and
    the moment of inertia about the shoulder axis (kg*m^2): the leg's own, plus the reflected rotor inertia the
    simulator adds (``armature``, a defaulted library value)."""
    import mujoco
    import numpy as np

    _design, _lib, cm, model = _compiled(pl)
    data = mujoco.MjData(model)
    for jid, rad in cm.rest.items():
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
        if j >= 0:
            data.qpos[model.jnt_qposadr[j]] = rad
    if carpus_deg is not None:
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"joint.{side}.carpus")
        data.qpos[model.jnt_qposadr[j]] = math.radians(carpus_deg)
    mujoco.mj_forward(model, data)
    js = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"joint.{side}.shoulder")
    a = np.asarray(data.xanchor[js], float)
    ax = np.asarray(data.xaxis[js], float)
    ax /= np.linalg.norm(ax)
    up = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"leg.{side}.upper")
    R_up = np.asarray(data.xmat[up], float).reshape(3, 3)
    tot, mc, i_axis = 0.0, np.zeros(3), 0.0
    parts = []
    for bname in (f"leg.{side}.upper", f"leg.{side}.cannon"):
        b = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, bname)
        mass = float(model.body_mass[b])
        c = np.asarray(data.xipos[b], float)
        R = np.asarray(data.ximat[b], float).reshape(3, 3)
        i_world = R @ np.diag(model.body_inertia[b]) @ R.T
        r = c - a
        i_own = float(ax @ i_world @ ax)
        i_par = mass * float(r @ r - (r @ ax) ** 2)
        parts.append({"body": bname, "mass_g": round(mass * 1000.0, 1), "i_own_kgm2": i_own, "i_parallel_kgm2": i_par})
        tot += mass
        mc += mass * c
        i_axis += i_own + i_par
    com = mc / tot
    rel = R_up.T @ (com - a) * 1000.0
    # outboard positive on either side
    rel_out = [float(rel[0]), float(rel[1]) * (1.0 if side.endswith("l") else -1.0), float(rel[2])]
    dperp = float(np.linalg.norm((com - a) - ((com - a) @ ax) * ax)) * 1000.0
    arm_dof = model.jnt_dofadr[js]
    return {"side": side, "carpus_deg": carpus_deg if carpus_deg is not None else math.degrees(cm.rest[f"joint.{side}.carpus"]),
            "mass_g": round(tot * 1000.0, 1), "com_in_upper_mm": [round(v, 1) for v in rel_out],
            "com_from_shoulder_axis_mm": round(dperp, 1), "inertia_shoulder_kgm2": round(i_axis, 6),
            "inertia_shoulder_gmm2": round(i_axis * 1e9, 0),
            "armature_shoulder_kgm2": float(model.dof_armature[arm_dof]),
            "parts": [{**p, "i_own_kgm2": round(p["i_own_kgm2"], 7), "i_parallel_kgm2": round(p["i_parallel_kgm2"], 6)}
                      for p in parts]}


def mass(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.hardware import _build
    from calflab.model.mass import mass_breakdown

    bs = m.bodies(lab)
    out = _load()
    res: dict[str, Any] = {}
    geoms: dict[str, dict[str, Any]] = {}
    for n in BODIES:
        design, lib = _build(bs[n])
        spec = design.spec
        mb = mass_breakdown(spec, lib)
        geoms[n] = {g.id: {"body": b.id, "label": g.label, "mass_g": round(g.mass_g, 2), "source": g.mass_source}
                    for b in spec.bodies for g in b.geoms if g.mass_g > 0}
        res[n] = {"total_g": round(spec.total_mass_g(), 1), "by_source_g": mb["by_source_g"],
                  "bodies_g": {b["body"]: round(b["total_g"], 1) for b in mb["bodies"]},
                  "missing": mb.get("missing") or mb.get("missing_items") or [],
                  "front_leg": {s: front_leg(bs[n], s) for s in SIDES},
                  "front_leg_through_carpus": [front_leg(bs[n], "fl", q) for q in (-10.0, 45.0, 90.0, 130.0)]}
        print(n, res[n]["total_g"], res[n]["front_leg"]["fl"]["mass_g"], res[n]["front_leg"]["fl"]["inertia_shoulder_kgm2"],
              flush=True)
    a, b = geoms[SWAP], geoms[DIRECT]
    res["difference"] = {
        "only_belted": {k: v for k, v in a.items() if k not in b},
        "only_direct": {k: v for k, v in b.items() if k not in a},
        "moved": {k: {"belted": a[k], "direct": b[k]} for k in a if k in b and a[k] != b[k]},
    }
    out["mass"] = res
    _save(out)


# --------------------------------------------------------------------- clearance
def _qrot(q: Any, v: Any) -> Any:
    """Rotate vectors v [..., 3] by quaternions q [..., 4] (w, x, y, z)."""
    import numpy as np

    q = np.asarray(q, float)
    v = np.asarray(v, float)
    w, u = q[..., :1], q[..., 1:]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def _qmul(a: Any, b: Any) -> Any:
    import numpy as np

    a, b = np.asarray(a, float), np.asarray(b, float)
    w1, x1, y1, z1 = np.moveaxis(a, -1, 0)
    w2, x2, y2, z2 = np.moveaxis(b, -1, 0)
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], axis=-1)


def geom_low(g: Any, pos: Any, quat: Any) -> Any:
    """Lowest world z (mm) of a geom on a body at world pose(s) ``pos`` [..., 3] mm, ``quat`` [..., 4]."""
    import numpy as np

    pos, quat = np.asarray(pos, float), np.asarray(quat, float)
    q = _qmul(quat, np.broadcast_to(np.asarray(g.quat, float), quat.shape))
    c = pos + _qrot(quat, np.broadcast_to(np.asarray(g.pos, float), pos.shape))
    a, b, h = g.size
    if g.shape == "box":
        lows = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    corner = np.broadcast_to(np.asarray((sx * a / 2, sy * b / 2, sz * h / 2), float), pos.shape)
                    lows.append((c + _qrot(q, corner))[..., 2])
        return np.min(np.stack(lows), axis=0)
    if g.shape == "sphere":
        return c[..., 2] - a
    if g.shape in ("cylinder", "capsule"):
        az = _qrot(q, np.broadcast_to(np.asarray((0.0, 0.0, 1.0)), pos.shape))[..., 2]
        cap = a if g.shape == "capsule" else a * np.sqrt(np.clip(1.0 - az**2, 0.0, 1.0))
        return c[..., 2] - b / 2.0 * np.abs(az) - cap
    raise ValueError(g.shape)


def _cyl_box_gap(p0: Any, d: Any, length: float, r: float, centre: Any, half: Any, n: int = 400) -> float:
    """Smallest gap (mm) between a cylinder (axis from p0 along unit d, length, radius r) and an axis-aligned box
    (centre, half extents), all in one frame: min over axis samples of the point-to-box distance, minus r (exact for a
    gap across the cylinder's side, which is the case here)."""
    import numpy as np

    s = np.linspace(0.0, length, n)[:, None]
    pts = np.asarray(p0, float) + s * np.asarray(d, float)
    q = np.abs(pts - np.asarray(centre, float)) - np.asarray(half, float)
    dist = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(np.max(q, axis=1), 0.0)
    return float(np.min(dist) - r)


def carpus_hardware(spec: Any, side: str) -> list[tuple[str, Any]]:
    """The carpus hardware that sits at the joint: (body id, geom) of the direct servo case (and horn), or the belted
    drive's driven pulley on the cannon. The belted driver servo is high on the upper leg and is listed too."""
    want = {f"act.{side}.carpus.motor", f"belt.{side}.carpus.driven", f"act.{side}.carpus.horn"}
    return [(b.id, g) for b in spec.bodies for g in b.geoms if g.id in want]


def clearance(lab: Any, opts: dict[str, str]) -> None:
    """Through the carpus range (1 deg steps, every other joint at its standing angle, the upper leg at its standing
    angle): the lowest point of the carpus hardware against the leg's lowest collision point (where the leg would
    rest on the ground: the hoof, or the carpus itself once the cannon folds), and the direct case's gap to the front
    cannon tube. The servo case and the pulleys are visual geoms (no collision in the simulator), so this is the only
    place they are checked."""
    import numpy as np
    from calflab.evolve.hardware import _build

    bs = m.bodies(lab)
    out = _load()
    res: dict[str, Any] = {}
    for n in BODIES:
        design, lib = _build(bs[n])
        spec = design.spec
        rest = spec.rest_angles()
        per: dict[str, Any] = {}
        for side in SIDES:
            jc = next(j for j in spec.joints if j.id == f"joint.{side}.carpus")
            lo, hi = jc.range_deg
            leg_geoms = [(b.id, g) for b in spec.bodies if b.id in (f"leg.{side}.upper", f"leg.{side}.cannon")
                         for g in b.geoms if g.role in ("collision", "both")]
            hw = carpus_hardware(spec, side)
            rows = []
            for qd in np.arange(lo, hi + 0.5, 1.0):
                poses = spec.world_poses({**rest, jc.id: float(qd)})
                leg_low = min(float(geom_low(g, poses[bid][0], poses[bid][1])) for bid, g in leg_geoms)
                row: dict[str, Any] = {"carpus_deg": float(qd), "leg_low_mm": round(leg_low, 1)}
                for bid, g in hw:
                    row[g.id] = round(float(geom_low(g, poses[bid][0], poses[bid][1])) - leg_low, 1)
                rows.append(row)
            hw_ids = [g.id for _b, g in hw]
            summary: dict[str, Any] = {}
            for gid in hw_ids:
                vals = [(r[gid], r["carpus_deg"]) for r in rows]
                mn = min(vals)
                neg = [q for v, q in vals if v < 0]
                at_rest = next(r[gid] for r in rows if abs(r["carpus_deg"] - rest[jc.id]) < 0.5)
                summary[gid] = {"at_standing_mm": at_rest, "min_mm": mn[0], "min_at_deg": mn[1],
                                "lowest_point_from_deg": min(neg) if neg else None}
            # the direct servo case against the cannon tube (both in the upper leg's frame)
            gap = None
            motor = next((g for b, g in hw if g.id.endswith("carpus.motor") and b == f"leg.{side}.upper"), None)
            if motor is not None:
                up = next(b for b in spec.bodies if b.id == f"leg.{side}.upper")
                can = next(b for b in spec.bodies if b.id == f"leg.{side}.cannon")
                tube = next(g for g in can.geoms if g.id == f"leg.{side}.cannon.tube")
                gaps = []
                for qd in np.arange(lo, hi + 0.5, 5.0):
                    poses = spec.world_poses({**rest, jc.id: float(qd)})
                    pu, qu = poses[up.id]
                    pc, qc = poses[can.id]
                    inv = np.asarray((qu[0], -qu[1], -qu[2], -qu[3]))
                    p0 = _qrot(inv, np.asarray(pc) - np.asarray(pu))
                    dirc = _qrot(inv, _qrot(qc, _qrot(tube.quat, (0.0, 0.0, -1.0))))
                    gaps.append(_cyl_box_gap(p0, dirc, float(tube.size[1]), float(tube.size[0]), motor.pos,
                                             np.asarray(motor.size) / 2.0))
                gap = {"min_mm": round(min(gaps), 2), "max_mm": round(max(gaps), 2),
                       "servo_case_mm": list(motor.size), "case_centre_in_upper_mm": list(motor.pos),
                       "cannon_tube_radius_mm": tube.size[0]}
            per[side] = {"range_deg": [lo, hi], "standing_deg": rest[jc.id], "hardware": summary, "cannon_gap": gap,
                         "sweep": rows[:: 5]}
        res[n] = per
        print(n, json.dumps({s: per[s]["hardware"] for s in SIDES}), json.dumps(per["fl"]["cannon_gap"]), flush=True)
    res["not_checked"] = [
        "the servo's output-axis offset along its case (not entered): the model centres the case on the carpus axis; a "
        "real STS3250's output shaft is off-centre, which moves the case's lowest point by up to that offset",
        "the lateral stack: horn, any bearing or adapter between the case and the cannon, and the cannon's own fitting "
        "at the joint; the model places the case 2 mm outboard of the upper-leg tube by a fixed constant",
        "the case against the other front leg, the chest block and the springs (no spring on the carpus of this body)",
        "contact with the ground in the simulator: the case and the pulleys are visual geoms, so a play never feels them",
    ]
    out["clearance"] = res
    _save(out)


def play_clearance(ro: Any, spec: Any) -> dict[str, Any]:
    """Per front side, the lowest point of the carpus hardware above the floor (z = 0) over the play (mm), and the
    carpus angle (deg) at that moment."""
    import numpy as np

    msk = ro.t >= 0
    out: dict[str, Any] = {}
    jidx = {j: i for i, j in enumerate(ro.joint_ids)}
    for side in SIDES:
        for bid, g in carpus_hardware(spec, side):
            if g.id.endswith(".horn") or bid not in ro.body_ids:
                continue
            k = ro.body_ids.index(bid)
            pos = np.asarray(ro.body_pos[msk, k], float) * 1000.0
            quat = np.asarray(ro.body_quat[msk, k], float)
            low = geom_low(g, pos, quat)
            i = int(np.argmin(low))
            qi = jidx.get(f"joint.{side}.carpus")
            out[g.id] = {"min_mm": round(float(low[i]), 1),
                         "carpus_deg": None if qi is None else round(math.degrees(float(ro.q[msk][i, qi])), 1)}
    return out


# --------------------------------------------------------------------- statics and loads
def statics(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.hardware import _build
    from calflab.mech.statics import static_loads

    bs = m.bodies(lab)
    out = _load()
    res: dict[str, Any] = {}
    for n in BODIES:
        design, lib = _build(bs[n])
        spec = design.spec
        sl = static_loads(spec)
        trans = {tr.id: tr for tr in spec.transmissions}
        drives = spec.metadata["feral"]["belt_drives"]
        rows = {}
        for a in spec.actuators:
            short = a.joint.replace("joint.", "")
            if short.split(".")[0] not in SIDES:
                continue
            tr = trans.get(a.transmission) if a.transmission else None
            ratio, eff = (tr.ratio, tr.efficiency) if tr else (1.0, 1.0)
            comp = lib.actuator(a.component)
            joint_nm = -sl[a.joint]["net_nm"]
            servo_nm = joint_nm / (ratio * eff)
            drv = drives.get(short.split(".")[-1]) if tr else None
            rows[short] = {"servo": comp.key, "drive": f"belt {ratio:g}:1" if tr else "direct",
                           "gravity_nm": round(sl[a.joint]["gravity_nm"], 4), "spring_nm": round(sl[a.joint]["spring_nm"], 4),
                           "joint_nm": round(joint_nm, 4), "servo_nm": round(servo_nm, 4),
                           "of_rated": _r(abs(servo_nm) / comp.rated_torque_nm) if comp.rated_torque_nm else None,
                           "of_stall": _r(abs(servo_nm) / comp.stall_torque_nm),
                           "current_a": (_r(abs(servo_nm) / (comp.stall_torque_nm / comp.stall_current_a)
                                            + comp.idle_current_a) if comp.stall_current_a else None),
                           "belt_n": None if drv is None else round(abs(servo_nm) / (float(drv["d1_mm"]) / 2000.0), 1)}
        res[n] = rows
        print(n, {k: (v["joint_nm"], v["servo_nm"]) for k, v in rows.items()}, flush=True)
    out["statics"] = res
    _save(out)


def extras(ro: Any, spec: Any, lib: Any, margin: float) -> dict[str, Any]:
    """Per front shoulder and carpus: servo torque peak / mean |.| (N*m), joint speed peak (deg/s) and its use of the
    recorded speed limit, the torque-speed envelope use (peak, share of the play above 0.9), current per servo (A, from
    torque and the library's stall current; idle current is a defaulted library value), the margin-lowered limit
    uses (``per_joint``); the whole body's known current; and the carpus hardware's lowest point above the floor."""
    import numpy as np
    from calflab.evolve.hardware import current_of, per_joint
    from calflab.mech.limits import servo_columns

    cols = {c["joint"].replace("joint.", ""): c for c in servo_columns(ro, spec, lib)}
    pj = per_joint(ro, spec, lib, margin)
    lim = np.asarray(ro.meta.get("speed_limit") or [], dtype=float)
    acts = {a.id: a for a in spec.actuators}
    lim_by = {acts[aid].joint.replace("joint.", ""): float(lim[k]) for k, aid in enumerate(ro.actuator_ids)
              if len(lim) == len(ro.actuator_ids)}
    out: dict[str, Any] = {}
    for side in SIDES:
        for jn in JOINTS:
            j = f"{side}.{jn}"
            c = cols[j]
            tau_s = np.abs(c["torque"]) / (c["ratio"] * c["efficiency"])
            w = np.abs(c["omega"])
            cur = None
            if c["stall_current_a"]:
                cur = tau_s / (c["stall_servo_nm"] / float(c["stall_current_a"])) + float(c["idle_current_a"])
            use = np.asarray(c["use"], float)
            out[j] = {"servo_peak_nm": _r(tau_s.max()), "servo_mean_nm": _r(tau_s.mean()),
                      "speed_peak_deg_s": _r(math.degrees(float(w.max())), 1),
                      "speed_use": _r(float(w.max()) / lim_by[j]) if j in lim_by else None,
                      "envelope_peak": _r(use.max()), "envelope_above_09": _r(float(np.mean(use > 0.9))),
                      "current_peak_a": None if cur is None else _r(cur.max()),
                      "current_mean_a": None if cur is None else _r(cur.mean()),
                      "uses": pj.get(j)}
    out["current"] = current_of(ro, spec, lib)
    out["clearance"] = play_clearance(ro, spec)
    return out


def _play_x(job: dict[str, Any]) -> dict[str, Any]:
    rec, ro, spec, lib = m._play_full(job)
    rec["x"] = extras(ro, spec, lib, job["margin"])
    return rec


def _run(jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    res = []
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, r in enumerate(pool.map(_play_x, jobs)):
            res.append(r)
            if i % 25 == 0:
                print(f"done {i + 1}/{len(jobs)} in {time.perf_counter() - t:.0f} s", flush=True)
    return res


def loads(lab: Any, opts: dict[str, str]) -> None:
    _pl, margin = m.base_payload(lab)
    jobs = m._jobs(lab, list(BODIES), list(m.LOAD_PLAYS.values()), [0], margin)
    res = _run(jobs, int(opts.get("workers", 6)))
    out = _load()
    out["loads"] = {"plays": res, "which": m.LOAD_PLAYS}
    _save(out)


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in ("holds", "within", "margin", "violations", "binding"))


def replay(lab: Any, opts: dict[str, str]) -> None:
    """Both bodies on the R16 repertoire, seeds 0-2, judged as R18 judged it, with the extras. The direct body's
    records (without the extras) go into ``mcmaster_r18.json`` ``replay``; the swap's fresh records are compared with
    the ones R18 stored (a determinism check) and not written there."""
    _pl, margin = m.base_payload(lab)
    names = (opts.get("bodies") or ",".join(BODIES)).split(",")
    seeds = [int(s) for s in opts.get("seeds", "0,1,2").split(",")]
    keys = opts["keys"].split(",") if opts.get("keys") else None
    jobs = m._jobs(lab, names, keys, seeds, margin)
    print(len(jobs), "plays", flush=True)
    t = time.perf_counter()
    res = _run(jobs, int(opts.get("workers", 14)))
    out = _load()
    rp = out.setdefault("replay", {})
    for n in names:
        new = {(r["key"], r["seed"]): r for r in res if r["body"] == n}
        rp[n] = [r for r in rp.get(n, []) if (r["key"], r["seed"]) not in new] + list(new.values())
    out.setdefault("timing", {})[f"replay {','.join(names)}"] = {"plays": len(jobs),
                                                                  "seconds": round(time.perf_counter() - t, 1)}
    data = m._load()
    if SWAP in names:
        old = {(r["key"], r["seed"]): r for r in (data.get("replay") or {}).get(SWAP, [])}
        fresh = [r for r in res if r["body"] == SWAP]
        diff = [f"{r['key']} s{r['seed']}" for r in fresh if (r["key"], r["seed"]) in old
                and not _same(r, old[(r["key"], r["seed"])])]
        out["determinism"] = {"compared": sum((r["key"], r["seed"]) in old for r in fresh), "differ": diff}
        print("swap vs R18's stored records:", out["determinism"]["compared"], "compared,", len(diff), "differ",
              flush=True)
    if DIRECT in names:
        mine = [{k: v for k, v in r.items() if k != "x"} for r in res if r["body"] == DIRECT]
        new_keys = {(r["key"], r["seed"]) for r in mine}
        rpm = data.setdefault("replay", {})
        rpm[DIRECT] = [r for r in rpm.get(DIRECT, []) if (r["key"], r["seed"]) not in new_keys] + mine
        m._save(data)
    _save(out)


# --------------------------------------------------------------------- the R11c suite, as confirm scores it
def _perform(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.hardware import perform_task, screen_task

    if job["kind"] == "screen":
        return screen_task(job["payload"])
    return perform_task(job["payload"])


def suite(lab: Any, opts: dict[str, str]) -> None:
    """Both bodies through the R11c suite (screen + 11 behaviours, 60 s) on seeds 0-2, with the preset, controllers,
    cache and baseline exactly as ``mcmaster_r18.py confirm`` used them, summarised as Stage B summarises a body."""
    from calflab.evolve.hardware import HardwareSettings, _build, baseline_of, summarise
    from calflab.fitness.preset import EvaluationSettings

    data = m._load()
    runs = data["confirm"]["runs"]
    run = lab.registry.get_run(runs[-1])
    pre = lab.prepare_hardware(run.fitness["preset"])
    ev = EvaluationSettings.model_validate({**pre["evaluation"], "seeds": [0, 1, 2]})
    hw = HardwareSettings.model_validate(ev.hardware)
    hw.cache_dir = str(Path(lab.project.path) / ".cache" / "hardware")
    base_pl, _m = m.base_payload(lab)
    if hw.baseline is None:
        d0, _lib = _build(base_pl)
        hw.baseline = baseline_of(d0.spec, dict(d0.genome.values))
    bs = m.bodies(lab)
    jobs, index = [], []
    for n in BODIES:
        payload = {"genome": bs[n]["genome"], "overrides": run.overrides, "generator": "feral_calf",
                   "generator_params": base_pl["generator_params"], "compile": run.inputs["compile"],
                   "evaluation": ev.model_dump(mode="json"), "hardware": hw.model_dump(mode="json")}
        jobs.append({"kind": "screen", "payload": payload})
        index.append((n, "screen"))
        for j in range(len(hw.performances)):
            jobs.append({"kind": "perf", "payload": {**payload, "performance": j}})
            index.append((n, "perf"))
    same = {"overrides": run.overrides == base_pl["overrides"], "compile": run.inputs["compile"] == base_pl["compile"]}
    print(len(jobs), "tasks; run settings equal to the study payload's:", same, flush=True)
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 15))) as pool:
        outs = list(pool.map(_perform, jobs))
    res: dict[str, Any] = {}
    for n in BODIES:
        scr = next(o for (b, kind), o in zip(index, outs, strict=True) if b == n and kind == "screen")
        perfs = [o for (b, kind), o in zip(index, outs, strict=True) if b == n and kind == "perf"]
        if "plays" not in scr:
            res[n] = {"error": scr.get("infeasible") or scr.get("error")}
            continue
        s0 = summarise(scr, None, hw, 3)
        s = summarise(scr, perfs if s0["passed_screen"] else None, hw, 3)
        res[n] = {"summary": s, "screen_plays": scr["plays"]}
        print(n, s.get("fitness"), s.get("minutes_held"), s.get("screen_held"), flush=True)
    out = _load()
    out["suite"] = {"bodies": res, "preset": run.fitness["preset"], "run": runs[-1], "same_as_payload": same,
                    "seconds": round(time.perf_counter() - t, 1)}
    _save(out)


# --------------------------------------------------------------------- hardware difference and compare page
def sheets(lab: Any, opts: dict[str, str]) -> None:
    """The direct body's production sheet and bill of materials (``mcmaster_r18.py sheets``), against the swap's."""
    import csv
    import io

    m.sheets(lab, {"bodies": DIRECT})
    data = m._load()
    a, b = data["sheets"][SWAP], data["sheets"][DIRECT]
    ra = {r["part_number"]: r for r in a["rows"]}
    rb = {r["part_number"]: r for r in b["rows"]}
    rows = [{"part_number": p, "description": (ra.get(p) or rb.get(p))["description"],
             "qty_belted": (ra.get(p) or {}).get("qty", 0), "qty_direct": (rb.get(p) or {}).get("qty", 0),
             "unit_usd": (ra.get(p) or rb.get(p))["unit_usd"]} for p in sorted(set(ra) | set(rb))]
    oa = {o["item"]: o["qty"] for o in a["open_items"]}
    ob = {o["item"]: o["qty"] for o in b["open_items"]}

    def geo(slug: str) -> dict[tuple[str, str], dict[str, str]]:
        text = (m.SHEETS / f"{slug}_geometry.csv").read_text(encoding="utf-8")
        return {(r["kind"], r["id"]): r for r in csv.DictReader(io.StringIO(text))}

    ga, gb = geo("g020_008_r01_mc"), geo("g020_008_r01_mc_direct")
    out = _load()
    out["sheets"] = {"bom_belted_usd": a["total_usd"], "bom_direct_usd": b["total_usd"],
                     "saving_usd": round(a["total_usd"] - b["total_usd"], 2), "rows": rows,
                     "open_items": {k: [oa.get(k, 0), ob.get(k, 0)] for k in sorted(set(oa) | set(ob))},
                     "geometry_only_belted": [dict(v) for k, v in ga.items() if k not in gb],
                     "geometry_only_direct": [dict(v) for k, v in gb.items() if k not in ga],
                     "geometry_changed": [{"belted": dict(ga[k]), "direct": dict(gb[k])} for k in ga
                                          if k in gb and ga[k] != gb[k]]}
    _save(out)
    print("BOM", a["total_usd"], "->", b["total_usd"], "open", out["sheets"]["open_items"])


def store(lab: Any, opts: dict[str, str]) -> None:
    m.store(lab, {"bodies": DIRECT, "workers": opts.get("workers", "15")})


# --------------------------------------------------------------------- the final body (ADR-126)
FINAL = "calf-final"


def final(lab: Any, opts: dict[str, str]) -> None:
    """The researcher's final body (2026-11-13): ``calf-final`` = ``g020-008-r01-mc-direct``. Adds it to the study's
    ``bodies`` with the same genes (and ``aliases``: its earlier name), and saves it in the project as the design
    ``calf-final`` (v001), built from the study payload exactly as every stage builds it (explicit_v2, the project's
    catalog). The working document is not changed; the earlier name keeps its runs, replays and compare cells."""
    from calflab.evolve.hardware import _build
    from calflab.project.registry import DesignRecord, RunRecord

    data = m._load()
    bs = data.setdefault("bodies", {})
    bs[FINAL] = dict(bs[DIRECT])
    data.setdefault("aliases", {})[FINAL] = DIRECT
    data.setdefault("labels", {})[FINAL] = "calf-final: the final body (= g020-008-r01-mc-direct)"
    data["labels"][DIRECT] = "= calf-final, the final body: direct carpus, C002 on the joint"
    m._save(data)
    pl = m.bodies(lab)[FINAL]
    d, _lib = _build(pl)
    d0, _l = _build(m.bodies(lab)[DIRECT])
    if d.spec.model_dump(mode="json") != d0.spec.model_dump(mode="json"):
        raise SystemExit("calf-final does not build identically to g020-008-r01-mc-direct")
    existing = [x for x in lab.registry.list_designs() if x.get("name") == FINAL]
    if existing and not opts.get("again"):
        print("already saved:", [x["id"] for x in existing])
        return
    version = lab.registry.next_design_version(FINAL)
    rec = DesignRecord(
        id=f"{FINAL}-v{version:03d}", name=FINAL, version=version,
        note=("The final body (researcher, 2026-11-13; ADR-126): g020-008-r01-mc with a direct-drive carpus, every belt "
              "drive on McMaster-Carr parts. Built from docs/studies/mcmaster_r18.json body g020-008-r01-mc-direct, "
              "mass model explicit_v2, the project's belt catalog (Gates allowable, breaking strength assumed)."),
        genome=d.genome.model_dump(mode="json"), overrides=list(pl.get("overrides") or []), graph={},
        spec=d.spec.model_dump(mode="json"), mass_g=d.spec.total_mass_g())
    lab.registry.save_design(rec)
    lab.registry.save_run(RunRecord(id=lab.registry.new_run_id("bake"), kind="bake", title=f"Bake {rec.id}",
                                    genome=rec.genome, overrides=rec.overrides,
                                    artifacts={"design": f"designs/{rec.id}/design.json"}, parent=rec.id))
    out = _load()
    out["final"] = {"name": FINAL, "same_as": DIRECT, "design": rec.id, "mass_g": round(rec.mass_g, 1)}
    _save(out)
    print("saved design", rec.id, round(rec.mass_g, 1), "g")


# --------------------------------------------------------------------- tables
def _f(v: Any, nd: int = 2) -> str:
    return m._f(v, nd)


def _by_key(recs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    from collections import defaultdict

    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        by[r["key"]].append(r)
    return by


def judged(rs: list[dict[str, Any]]) -> dict[str, Any]:
    """One behaviour over its seeds as R18 judged it: holds, within (every limit incl. sustained belt tension), the
    worst margin and the worst seed's binding limit."""
    worst = min(rs, key=lambda r: r["margin"] if r["margin"] is not None else 9.0)
    b = worst.get("binding") or {}
    return {"holds": all(r["holds"] for r in rs), "within": all(r["within"] for r in rs),
            "ok": all(r["holds"] and r["within"] for r in rs),
            "margin": min((r["margin"] for r in rs if r["margin"] is not None), default=None),
            "binds": f"{b.get('joint') or '-'} {b.get('limit') or ''}".strip(),
            "violations": sorted({v for r in rs for v in r["violations"]})}


def summary(lab: Any, opts: dict[str, str]) -> None:  # noqa: C901 - one table after another
    from collections import Counter

    d = _load()
    L = ["# Belted or direct carpus on g020-008-r01-mc (tables; generated by `docs/studies/carpus_r18.py summary`)", "",
         "Breaking strength assumed (51 lbf per 1/8 in of width); allowable working tension Gates 17611-T (179.6 N for "
         "9 mm 3MGT; ADR-120). *within* = within every limit at margin 0.2, sustained belt tension included.", ""]
    ms = d.get("mass") or {}
    if ms:
        L += ["## 1. Mass", "", "| body | total g | trunk g | front upper leg g | front cannon g | front leg g | "
              "front leg CoM from shoulder axis mm | CoM in the upper leg (x fwd, y out, z along) mm | I about the shoulder "
              "kg*m^2 | + armature kg*m^2 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for n in BODIES:
            r = ms[n]
            fl = r["front_leg"]["fl"]
            L.append(f"| {n} | {r['total_g']:.1f} | {r['bodies_g'].get('trunk', 0):.1f} | "
                     f"{r['bodies_g'].get('leg.fl.upper', 0):.1f} | {r['bodies_g'].get('leg.fl.cannon', 0):.1f} | "
                     f"{fl['mass_g']:.1f} | {fl['com_from_shoulder_axis_mm']:.1f} | "
                     f"{', '.join(f'{v:.1f}' for v in fl['com_in_upper_mm'])} | {fl['inertia_shoulder_kgm2']:.5f} | "
                     f"{fl['armature_shoulder_kgm2']:.4f} |")
        L += ["", "Front-left leg about the shoulder axis through the carpus range (kg*m^2):", "",
              "| body | " + " | ".join(f"carpus {x['carpus_deg']:g} deg" for x in ms[SWAP]["front_leg_through_carpus"])
              + " |", "|---|" + "---|" * len(ms[SWAP]["front_leg_through_carpus"])]
        for n in BODIES:
            L.append(f"| {n} | " + " | ".join(f"{x['inertia_shoulder_kgm2']:.5f} ({x['com_from_shoulder_axis_mm']:.0f} mm)"
                                              for x in ms[n]["front_leg_through_carpus"]) + " |")
        df = ms["difference"]
        L += ["", "Mass items that differ (per item, both sides listed):", "", "| item | body | belted g | direct g | source |",
              "|---|---|---|---|---|"]
        for k, v in df["only_belted"].items():
            L.append(f"| {k} ({v['label']}) | {v['body']} | {v['mass_g']:.1f} | - | {v['source']} |")
        for k, v in df["only_direct"].items():
            L.append(f"| {k} ({v['label']}) | {v['body']} | - | {v['mass_g']:.1f} | {v['source']} |")
        for k, v in df["moved"].items():
            L.append(f"| {k} ({v['direct']['label']}) | {v['belted']['body']} -> {v['direct']['body']} | "
                     f"{v['belted']['mass_g']:.1f} | {v['direct']['mass_g']:.1f} | moved |")
        L.append("")
    cl = d.get("clearance") or {}
    if cl:
        L += ["## 2. Carpus hardware clearance (left; the right mirrors it)", "",
              "Lowest point of each part minus the leg's lowest collision point (where the leg would rest on the ground), "
              "upper leg at its standing angle, carpus through its range in 1 deg steps. Negative = the part is lower "
              "than the hoof or the carpus tube: it would touch the ground first.", "",
              "| body | part | at standing (0 deg) mm | least mm | at carpus deg | the lowest point from deg |",
              "|---|---|---|---|---|---|"]
        for n in BODIES:
            for gid, v in cl[n]["fl"]["hardware"].items():
                L.append(f"| {n} | {gid} | {v['at_standing_mm']:.1f} | {v['min_mm']:.1f} | {v['min_at_deg']:g} | "
                         f"{_f(v['lowest_point_from_deg'])} |")
        g = cl[DIRECT]["fl"]["cannon_gap"]
        if g:
            L += ["", f"Direct servo case ({' x '.join(f'{x:g}' for x in g['servo_case_mm'])} mm, centred at "
                  f"{', '.join(f'{x:g}' for x in g['case_centre_in_upper_mm'])} mm in the upper leg) against the front "
                  f"cannon tube (radius {g['cannon_tube_radius_mm']:g} mm): gap {g['min_mm']:.1f} to {g['max_mm']:.1f} mm "
                  "through the range, all of it lateral (the case is outboard of the tube's plane)."]
        L += ["", "Not checked by the model: " + "; ".join(cl["not_checked"]) + ".", ""]
    st = d.get("statics") or {}
    if st:
        L += ["## 3. Holding torque, standing pose (statics)", "",
              "| body | joint | servo | drive | gravity N*m | spring N*m | joint N*m | servo N*m | of rated | of stall | "
              "current A | belt N |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in BODIES:
            for j, r in st[n].items():
                L.append(f"| {n} | {j} | {r['servo']} | {r['drive']} | {r['gravity_nm']:.3f} | {r['spring_nm']:.3f} | "
                         f"{r['joint_nm']:.3f} | {r['servo_nm']:.3f} | {_f(r['of_rated'], 3)} | {_f(r['of_stall'], 3)} | "
                         f"{_f(r['current_a'])} | {_f(r['belt_n'], 1)} |")
        L.append("")
    ld = d.get("loads") or {}
    if ld:
        names = {v: k for k, v in ld["which"].items()}
        L += ["## 4. Load plays (seed 0)", "",
              "Per joint, the larger of the two sides. Speed use = peak joint speed / the recorded no-load joint speed; "
              "envelope = the torque-speed envelope use (peak; share of the play above 0.9). Current from torque and "
              "the library's stall current (C002 4.2 A at 12 V; idle current defaulted).", "",
              "| play | body | holds | within | margin | binds | joint | servo peak / mean N*m | speed peak deg/s (use) | "
              "envelope peak (>0.9) | current peak / mean A | belt peak / mean N |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(ld["plays"], key=lambda r: (r["key"], BODIES.index(r["body"]))):
            b = r.get("binding") or {}
            for jn in JOINTS:
                vs = [r["x"][f"{s}.{jn}"] for s in SIDES]
                v = max(vs, key=lambda v: v["servo_peak_nm"])
                belts = [x for k, x in r["belts"].items() if k.endswith(jn)]
                bt = (f"{max(x['belt_peak_n'] for x in belts):.0f} / {max(x['belt_mean_n'] for x in belts):.0f}"
                      if belts else "-")
                L.append(f"| {names.get(r['key'], r['key'])} | {r['body']} | {_f(r['holds'])} | {_f(r['within'])} | "
                         f"{_f(r['margin'])} | {b.get('joint', '-')} {b.get('limit', '')} | {jn} | "
                         f"{max(x['servo_peak_nm'] for x in vs):.2f} / {max(x['servo_mean_nm'] for x in vs):.2f} | "
                         f"{max(x['speed_peak_deg_s'] for x in vs):.0f} ({max(x['speed_use'] or 0 for x in vs):.2f}) | "
                         f"{max(x['envelope_peak'] for x in vs):.2f} ({max(x['envelope_above_09'] for x in vs):.2f}) | "
                         f"{_f(max(x['current_peak_a'] or 0 for x in vs))} / {_f(max(x['current_mean_a'] or 0 for x in vs))} | "
                         f"{bt} |")
            c = r["x"]["current"]
            L.append(f"| {names.get(r['key'], r['key'])} | {r['body']} | | | | | whole body, {c['known_servos']} servos "
                     f"with a stall current | | | | {_f(c['known_peak_a'])} / {_f(c['known_mean_a'])} | |")
        L.append("")
    rp = d.get("replay") or {}
    if all(n in rp for n in BODIES):
        bw, bd = _by_key(rp[SWAP]), _by_key(rp[DIRECT])
        keys = sorted(set(bw) | set(bd))
        jw = {k: judged(bw[k]) for k in keys if k in bw}
        jd = {k: judged(bd[k]) for k in keys if k in bd}
        full = [k for k in keys if k.startswith("full:")]
        L += ["## 5. The R16 repertoire (107 behaviours, seeds 0-2, 30 s, margin 0.2)", "",
              "| body | behaviours | hold on all seeds | hold and within every limit | of the full-search cells |",
              "|---|---|---|---|---|"]
        for n, jj in ((SWAP, jw), (DIRECT, jd)):
            L.append(f"| {n} | {len(jj)} | {sum(v['holds'] for v in jj.values())} | "
                     f"{sum(v['ok'] for v in jj.values())} | {sum(jj[k]['ok'] for k in full if k in jj)} of {len(full)} |")
        gain = [k for k in keys if jd.get(k, {}).get("ok") and not jw.get(k, {}).get("ok")]
        lose = [k for k in keys if jw.get(k, {}).get("ok") and not jd.get(k, {}).get("ok")]
        L += ["", f"Gained by the direct carpus: {', '.join(gain) or 'none'}. Lost: {', '.join(lose) or 'none'}.", ""]
        cw = Counter(v["binds"] for v in jw.values())
        cd = Counter(v["binds"] for v in jd.values())
        L += ["What binds (the worst seed's binding limit, counted over behaviours):", "",
              "| binding limit | belted | direct |", "|---|---|---|"]
        for k in sorted(set(cw) | set(cd), key=lambda k: -(cw.get(k, 0) + cd.get(k, 0))):
            L.append(f"| {k} | {cw.get(k, 0)} | {cd.get(k, 0)} |")

        def front(recs: list[dict[str, Any]], j: str, f: str) -> float:
            return max((r["x"][f"{s}.{j}"][f] or 0.0) for r in recs for s in SIDES)

        def clear(recs: list[dict[str, Any]]) -> float | None:
            vals = [v["min_mm"] for r in recs for g, v in r["x"]["clearance"].items()
                    if g.endswith("carpus.motor") and r["body"] == DIRECT or g.endswith("carpus.driven")]
            return min(vals) if vals else None

        L += ["", "Per behaviour (worst seed): holds / within, margin, binding limit; then the front servos (largest of "
              "both sides and all seeds): shoulder and carpus servo peak N*m, carpus speed use, carpus envelope peak; "
              "and the lowest point of the carpus hardware above the floor (mm; belted: the driven pulley, direct: "
              "the servo case).", "",
              "| behaviour | belted | margin | binds | direct | margin | binds | shoulder peak N*m (b -> d) | "
              "carpus peak N*m (b -> d) | carpus speed use (b -> d) | carpus envelope (b -> d) | hardware above floor mm "
              "(b -> d) |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k in keys:
            a, b = jw.get(k), jd.get(k)
            if a is None or b is None:
                continue
            ra, rb = bw[k], bd[k]

            def hw(v: dict[str, Any]) -> str:
                return f"{'yes' if v['holds'] else 'no'} / {'yes' if v['within'] else 'no'}"

            L.append(f"| {k} | {hw(a)} | {_f(a['margin'])} | {a['binds']} | {hw(b)} | {_f(b['margin'])} | {b['binds']} | "
                     f"{front(ra, 'shoulder', 'servo_peak_nm'):.2f} -> {front(rb, 'shoulder', 'servo_peak_nm'):.2f} | "
                     f"{front(ra, 'carpus', 'servo_peak_nm'):.2f} -> {front(rb, 'carpus', 'servo_peak_nm'):.2f} | "
                     f"{front(ra, 'carpus', 'speed_use'):.2f} -> {front(rb, 'carpus', 'speed_use'):.2f} | "
                     f"{front(ra, 'carpus', 'envelope_peak'):.2f} -> {front(rb, 'carpus', 'envelope_peak'):.2f} | "
                     f"{_f(clear(ra), 0)} -> {_f(clear(rb), 0)} |")
        dt = d.get("determinism")
        if dt:
            L += ["", f"Determinism: the swap's fresh plays against R18's stored records: {dt['compared']} compared, "
                  f"{len(dt['differ'])} differ{': ' + ', '.join(dt['differ']) if dt['differ'] else ''}."]
        L.append("")
    su = (d.get("suite") or {}).get("bodies") or {}
    if su:
        L += ["## 6. The R11c suite (screen + 11 behaviours, 60 s, seeds 0-2), scored as `confirm`", "",
              "| body | fitness (3 seeds) | suite minutes held | trot within mm/s | screen held | stoppers |",
              "|---|---|---|---|---|---|"]
        for n in BODIES:
            s = (su.get(n) or {}).get("summary") or {}
            L.append(f"| {n} | {_f(s.get('fitness'), 3)} | {s.get('minutes_held')}/{s.get('minutes_of')} | "
                     f"{_f(s.get('trot_speed_mm_s'), 0)} | {s.get('screen_held')}/{s.get('screen_plays')} | "
                     f"{', '.join(f'{a} {b} ({c})' for a, b, c in (s.get('stoppers') or [])[:4])} |")
        L += ["", "Per suite behaviour (seeds held of 3, worst margin, closest limit per seed):", "",
              "| behaviour | belted | direct |", "|---|---|---|"]
        pa = {p["label"]: p for p in ((su.get(SWAP) or {}).get("summary") or {}).get("performances") or []}
        pb = {p["label"]: p for p in ((su.get(DIRECT) or {}).get("summary") or {}).get("performances") or []}
        for lab_ in list(pa) + [x for x in pb if x not in pa]:
            def cell(p: dict[str, Any] | None) -> str:
                if not p:
                    return "-"
                return f"{p['held']}/{p['of']}, {_f(p['worst_margin'])}, {', '.join(p['closest'])}"

            L.append(f"| {lab_} | {cell(pa.get(lab_))} | {cell(pb.get(lab_))} |")
        L += ["", "Screen (per play: held, worst margin over the seeds):", "", "| play | belted | direct |", "|---|---|---|"]
        sa = {p["key"]: p for p in (su.get(SWAP) or {}).get("screen_plays") or []}
        sb = {p["key"]: p for p in (su.get(DIRECT) or {}).get("screen_plays") or []}
        for k in list(sa) + [x for x in sb if x not in sa]:
            def sc(p: dict[str, Any] | None) -> str:
                if not p:
                    return "-"
                ms_ = [s.get("margin") for s in p["seeds"] if s.get("margin") is not None]
                return f"{'held' if p['held'] else 'not held'}, {_f(min(ms_) if ms_ else None)}"

            L.append(f"| {k} | {sc(sa.get(k))} | {sc(sb.get(k))} |")
        L.append("")
    sh = d.get("sheets") or {}
    if sh:
        L += ["## 7. Bill of materials", "", f"Belted USD {sh['bom_belted_usd']:.2f}, direct USD {sh['bom_direct_usd']:.2f} "
              f"(saves USD {sh['saving_usd']:.2f}).", "", "| part | description | belted qty | direct qty | each USD |",
              "|---|---|---|---|---|"]
        for r in sh["rows"]:
            L.append(f"| {r['part_number']} | {r['description']} | {r['qty_belted']} | {r['qty_direct']} | "
                     f"{r['unit_usd']:.2f} |")
        L += ["", "Open items (belted -> direct): " + ", ".join(f"{k} {v[0]} -> {v[1]}" for k, v in sh["open_items"].items())
              + ".", "", "Production sheet geometry rows only in the belted sheet: "
              + (", ".join(r["id"] for r in sh["geometry_only_belted"]) or "none") + "; only in the direct sheet: "
              + (", ".join(r["id"] for r in sh["geometry_only_direct"]) or "none") + "; changed: "
              + (", ".join(f"{c['direct']['id']} ({c['belted']['value'] or c['belted']['x_mm']} -> "
                           f"{c['direct']['value'] or c['direct']['x_mm']})" for c in sh["geometry_changed"]) or "none")
              + ".", ""]
    TABLES.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", TABLES)


# --------------------------------------------------------------------- main
def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj, stage = Path(sys.argv[1]), sys.argv[2]
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    load_plugins()
    lab = Lab.open(proj, create=False)
    try:
        globals()[stage](lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
