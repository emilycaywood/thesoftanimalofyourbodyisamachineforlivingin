"""Step 2b: levers, one at a time, played in physics and judged at margin 0.2 (in memory; no file changed)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from calflab.app.lab import Lab
from calflab.app.physics_jobs import _context
from calflab.behave.interpret import InterpretSettings, judge, play_primitive
from calflab.components.library import library
from calflab.plugins import registry

proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
lab = Lab.open(proj, create=False)
ctx = _context(lab)
doc = dict(ctx["doc_compile"])
lib = library()
s = InterpretSettings()
genes0 = dict(lab.state.graph.role("genome").params)
interp = json.loads((proj / "runs/20261104-042426-interpret-ef3c/interpretation.json").read_text(encoding="utf-8"))
params = {r["behaviour"]: (r["primitive"], r["params"]) for r in interp["records"]}
MOTIONS = {"walk": ("walk", {}), "trot": ("trot", {}), "interp trot": params["other"], "interp step": params["step"]}

# gravity compensation at standing (step 2a): servo-side static / spring torque per joint type
GC = {"stifle": 0.141 / 0.255, "hock": 0.050 / 0.096, "shoulder": 0.054 / 0.197}

LEVERS: list[tuple[str, dict, dict]] = [("today", {}, {})]
LEVERS += [("springs = gravity at standing (stifle x0.55, hock x0.52, shoulder x0.27)",
            {"spring_stifle_k": genes0["spring_stifle_k"] * GC["stifle"],
             "spring_hock_k": genes0["spring_hock_k"] * GC["hock"],
             "spring_shoulder_k": genes0["spring_shoulder_k"] * GC["shoulder"]}, {})]
LEVERS += [("shoulder springs off", {"spring_shoulder": False}, {})]
LEVERS += [(f"hind splay {v}", {"hind_leg_splay": v}, {}) for v in (0.0, 6.0, 18.0)]
LEVERS += [(f"front splay {v}", {"front_leg_splay": v}, {}) for v in (0.0, 5.0)]
LEVERS += [("both splay 0", {"hind_leg_splay": 0.0, "front_leg_splay": 0.0}, {})]
LEVERS += [(f"femur_angle {v}", {"femur_angle": v}, {}) for v in (30.0, 50.0)]
LEVERS += [(f"tibia_angle {v}", {"tibia_angle": v}, {}) for v in (25.0, 45.0)]
LEVERS += [(f"front_angle {v}", {"front_angle": v}, {}) for v in (0.0, 10.0)]
LEVERS += [("trot roll_gain 0.25", {}, {"roll_gain": 0.25}), ("trot roll_gain 0", {}, {"roll_gain": 0.0}),
           ("walk sway 1.5", {}, {"sway": 1.5}), ("walk sway 6", {}, {"sway": 6.0})]
LEVERS += [("springs GC + both splay 0", {"spring_stifle_k": genes0["spring_stifle_k"] * GC["stifle"],
            "spring_hock_k": genes0["spring_hock_k"] * GC["hock"],
            "spring_shoulder_k": genes0["spring_shoulder_k"] * GC["shoulder"],
            "hind_leg_splay": 0.0, "front_leg_splay": 0.0}, {})]

res = []
for lname, genes, ctrl_extra in LEVERS:
    spec = None
    belts_ok = True
    if genes:
        g = lab.variant_graph(genes={**genes0, **genes})
        design = lab.design(g)
        meta = design.spec.metadata.get("feral") or {}
        belts_ok = bool(meta.get("belts_ok", True))
        spec = design.spec
    else:
        spec = ctx["design"].spec
    for mname, (pkey, pp) in MOTIONS.items():
        if ctrl_extra and (("roll_gain" in ctrl_extra and pkey != "trot") or ("sway" in ctrl_extra and pkey != "walk")):
            continue
        if not belts_ok:
            bad = [d for d, r in (spec.metadata["feral"]["belt_drives"]).items() if not r["ok"]]
            res.append({"lever": lname, "motion": mname, "rejected": f"belt check fails at {bad}"})
            print(f"{lname:60s} {mname:12s} REJECTED belts {bad}", flush=True)
            continue
        prim = registry.get("motion_primitive", pkey)(pp)
        if ctrl_extra:
            orig = prim.controller

            def ctl(sp, lb, orig=orig, extra=ctrl_extra):
                k, p = orig(sp, lb)
                return k, {**p, **extra}
            prim.controller = ctl  # type: ignore[method-assign]
        ro, t0, t1, _ = play_primitive(prim, spec, lib, doc, s)
        j = judge(ro, spec, lib, 0.2)
        c = {k: v["margin"] for k, v in j["constraints"].items()}
        res.append({"lever": lname, "motion": mname, "margin": j["margin"], "fell": j["fell"],
                    "violations": j["violations"], "constraints": c, "mass_g": spec.total_mass_g()})
        print(f"{lname:60s} {mname:12s} {j['margin']!s:>7} fell={j['fell']!s:5} "
              + " ".join(f"{k[:8]}={v:+.2f}" for k, v in c.items() if v is not None and v < 0.3), flush=True)
outp.write_text(json.dumps(res, indent=1), encoding="utf-8")
