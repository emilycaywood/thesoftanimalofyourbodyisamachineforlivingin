"""Session R8 (ADR-099): faster joints. Which limit binds at each joint in the trot, walk and turn, and what each
lever would buy, in simulation only (the project document, catalogs and component values are not changed).

Per what-if a copy of the working body's spec is changed in memory:

* ``now``: the working body;
* ``carpus 1.5:1`` / ``carpus 1:1``: less reduction at the front carpi (the joint is faster by 2/ratio, the servo
  carries 2/ratio more of the joint torque; the belt is judged with the same driver pulley, so its tension per
  servo torque is unchanged);
* ``all belts 1.5:1``: every belted joint at 1.5:1;
* ``hip ab/ad 2:1``: the hip ab/ad behind a 2:1 belt (half the speed, twice the torque; no belt check: there is
  no such belt in the catalog);
* ``hip springs x2``: the hip ab/ad springs at twice their rate (``spring_hip_abd_k``);
* ``mass x0.9``: every mass 10 % lighter (optimistic: 14 parts are still missing and would add mass);
* ``45T``: today's pulleys are 30T/60T; ``carpus 1:1`` alone keeps the 30T driver (30T/30T), ``carpus 1:1 45T``
  uses 45T/45T: belt tension per servo torque / 1.5 (pulley masses, belt length and fit not modelled);
* ``hock 1.5:1``: 30T/45T;
* combinations of the above.

For each, the trot grid of ``trot_r6c.py`` (cycle 0.6-1.2 s x stride 0.5-1.5, lift 0.6) plus the walk and the
turn at the primitives' defaults, seed 0, margin 0.2, judged as everywhere else. For every play and joint: the
peak speed over the margin-lowered limit, the sustained torque share over its 0.25, the belt's, and which of
these is nearest its limit (the binding one).

Run:  python docs/studies/joints_r8.py <project dir> <out.json> [--cases=now,carpus 1:1,...] [--grid=small] [--seed=0] [--randomize]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

CASES: dict[str, dict[str, Any]] = {
    "now": {},
    "carpus 1.5:1": {"ratio": {"carpus": 1.5}},
    "carpus 1:1": {"ratio": {"carpus": 1.0}},
    "all belts 1.5:1": {"ratio": {"*": 1.5}},
    "hip ab/ad 2:1": {"hip_belt": 2.0},
    "hip springs x2": {"genes": {"spring_hip_abd_k": 2.0}},
    "mass x0.9": {"mass": 0.9},
    "carpus 1:1 + hip 2:1": {"ratio": {"carpus": 1.0}, "hip_belt": 2.0},
    "all 1.5:1 + hip 2:1": {"ratio": {"*": 1.5}, "hip_belt": 2.0},
    "all 1.5:1 + hip 2:1 + springs x2 + mass x0.9": {"ratio": {"*": 1.5}, "hip_belt": 2.0,
                                                     "genes": {"spring_hip_abd_k": 2.0}, "mass": 0.9},
    "carpus 1:1 45T + hip 2:1": {"ratio": {"carpus": 1.0}, "d1": {"carpus": 1.5}, "hip_belt": 2.0},
    "carpus 1:1 45T + hock 1.5:1": {"ratio": {"carpus": 1.0, "hock": 1.5}, "d1": {"carpus": 1.5}},
    "carpus 1:1 45T + hock 1.5:1 + hip 2:1": {"ratio": {"carpus": 1.0, "hock": 1.5}, "d1": {"carpus": 1.5},
                                              "hip_belt": 2.0},
}


def body(design: Any, overrides: list[Any], generator: str, gen_params: dict[str, Any], case: dict[str, Any]) -> Any:
    from calflab.design import build_design
    from calflab.model.spec import Transmission

    genome = design.genome
    if case.get("genes"):
        vals = dict(genome.values)
        for k, f in case["genes"].items():
            vals[k] = float(vals[k]) * float(f)
        genome = genome.model_copy(update={"values": vals})
    spec = build_design(genome, overrides, generator, gen_params).spec.model_copy(deep=True)
    for tr in spec.transmissions:
        drive = tr.id.split(".")[-1]
        r = case.get("ratio", {})
        if tr.type == "belt" and (drive in r or "*" in r):
            tr.ratio = float(r.get(drive, r.get("*")))
    for drive, f in (case.get("d1") or {}).items():  # a larger driver pulley: less belt tension per servo torque
        bd_ = ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).get(drive)
        if bd_ is not None:
            bd_["d1_mm"] = float(bd_["d1_mm"]) * float(f)
    if case.get("mass"):  # every mass (and inertia) scaled; actuator component masses are geoms too
        f = float(case["mass"])
        for bd in spec.bodies:
            for gm in bd.geoms:
                gm.mass_g *= f
                if gm.inertia is not None:
                    gm.inertia = tuple(v * f for v in gm.inertia)  # type: ignore[assignment]
    if case.get("hip_belt"):
        eff = next((tr.efficiency for tr in spec.transmissions if tr.type == "belt"), 1.0)
        for a in spec.actuators:
            if a.joint.endswith(".hip_abd") and not a.transmission:
                tid = f"tr.{a.joint.split('.')[1]}.hip_abd"
                spec.transmissions.append(Transmission(id=tid, type="belt", ratio=float(case["hip_belt"]),
                                                       efficiency=eff))
                a.transmission = tid
    return spec


def per_joint(ro: Any, spec: Any, lib: Any, margin: float) -> dict[str, dict[str, Any]]:
    """Per joint: speed / (limit x (1 - margin)), sustained torque share / 0.25, belt share / 0.25 (1 = at the
    margin-lowered limit), and the binding one."""
    from calflab.behave.interpret import _checks
    from calflab.mech.loads import analyse

    c = _checks(spec)
    keep = 1.0 - margin
    checks = {**c, "rated_fraction": c["rated_fraction"] * keep, "breaking_fraction": c["breaking_fraction"] * keep}
    belts = {d: dict(r) for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items()}
    for r in belts.values():
        if r.get("allowable_working_tension_n") is not None:
            r["allowable_working_tension_n"] = float(r["allowable_working_tension_n"]) * keep
    rows = {r["joint"].replace("joint.", ""): r for r in analyse(ro, spec, lib, 2.0, checks, belts)["summary"]}
    lim = np.asarray(ro.meta.get("speed_limit") or [], dtype=float)
    m = ro.t >= 0
    out = {}
    for k, aid in enumerate(ro.actuator_ids):
        a = next(x for x in spec.actuators if x.id == aid)
        j = a.joint.replace("joint.", "")
        r = rows.get(j, {})
        sp = float(np.max(np.abs(ro.dq[m][:, k])) / (lim[k] * keep)) if len(lim) else None
        tq = (float(r["above_rated_fraction_of_cycle"]) / c["sustained_fraction"]
              if r.get("above_rated_fraction_of_cycle") is not None else None)
        bt = (float(r["above_allowable_fraction_of_cycle"]) / c["sustained_fraction"]
              if isinstance(r.get("above_allowable_fraction_of_cycle"), float) else None)
        vals = {"speed": sp, "torque": tq, "belt": bt}
        known = {n: v for n, v in vals.items() if v is not None}
        out[j] = {**{n: (round(v, 3) if v is not None else None) for n, v in vals.items()},
                  "binds": max(known, key=lambda n: known[n]) if known else None,
                  "speed_deg_s": round(float(np.degrees(np.max(np.abs(ro.dq[m][:, k])))), 1),
                  "limit_deg_s": round(float(np.degrees(lim[k])), 1) if len(lim) else None}
    return out


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.behave.interpret import InterpretSettings, judge, play_primitive
    from calflab.components import library
    from calflab.plugins import load_plugins, registry

    load_plugins()
    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    names = opts["cases"].split(",") if "cases" in opts else list(CASES)
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    design = lab.design()
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    overrides = [o for o in lab.state.overrides if o.enabled]
    compile_doc = dict(g.role("model").params)
    lab.close()
    lib = library()
    margin = 0.2
    if "randomize" in opts:  # judged as the diversity preset does: friction 0.7-1.1, mass x0.95-1.05 per seed
        import calflab.behave.physics as phys
        from calflab.behave.study import randomization

        strip = phys.compile_params
        rand = randomization(True, (0.7, 1.1), (0.95, 1.05))
        phys.compile_params = lambda doc: {**strip(doc), "randomization": rand}  # type: ignore[assignment]
    s = InterpretSettings(margin=margin, seed=int(opts.get("seed", 0)))
    small = opts.get("grid") == "small"
    trots = [(c, st) for c in ((0.6, 0.8, 1.2) if small else (0.6, 0.8, 1.0, 1.2))
             for st in ((0.5, 1.0) if small else (0.5, 1.0, 1.5))]
    plays = [("trot", {"cycle_s": c, "stride": st, "lift": 0.6, "turn": 0.0}) for c, st in trots]
    plays += [("walk", {}), ("turn", {})]
    out: dict[str, Any] = {}
    for name in names:
        case = CASES[name]
        spec = body(design, overrides, generator, gen_params, case)
        doc = dict(compile_doc)
        rows = []
        t = time.perf_counter()
        for key, prm in plays:
            prim = registry.get("motion_primitive", key)(prm)  # type: ignore[call-arg]
            ro, t0, t1, _c = play_primitive(prim, spec, lib, doc, s)
            j = judge(ro, spec, lib, margin)
            pj = per_joint(ro, spec, lib, margin)
            trunk = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
            mm = (ro.t >= t0) & (ro.t < t1)
            dist = float(np.linalg.norm(ro.body_pos[mm, trunk, :2][-1] - ro.body_pos[mm, trunk, :2][0])) * 1000.0
            speed = dist / max(1e-6, float(ro.t[mm][-1] - ro.t[mm][0]))
            worst = sorted(((k, v["margin"]) for k, v in j["constraints"].items() if v.get("margin") is not None),
                           key=lambda kv: kv[1])[:2]
            rows.append({"primitive": key, "params": prim.params.model_dump(mode="json"), "within": j["within_limits"],
                         "fell": j["fell"], "margin": j["margin"], "worst": worst, "speed_mm_s": round(speed, 1),
                         "joints": pj})
            binds = {jj: v["binds"] for jj, v in pj.items() if v["binds"] and (v[v["binds"]] or 0) >= 0.9}
            print(f"{name:28s} {key:5s} {prm.get('cycle_s', ''):>4} {prm.get('stride', ''):>4}: "
                  f"{'OK ' if j['within_limits'] else '   '}{(j['margin'] or 0):+.2f} {worst[0][0] if worst else '':15s} "
                  f"{speed:5.0f} mm/s  near/over: {binds}", flush=True)
        out[name] = {"case": case, "plays": rows, "wall_s": round(time.perf_counter() - t, 1)}
        outp.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
