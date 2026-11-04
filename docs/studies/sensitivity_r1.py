"""Step 1: one-at-a-time sensitivity of the gaits and the interpreted primitives (scratch, in memory only)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from calflab.app.lab import Lab
from calflab.app.physics_jobs import _context
from calflab.behave.interpret import InterpretSettings, judge, play_primitive
from calflab.components.library import Library, library
from calflab.plugins import registry

proj = Path(sys.argv[1])
out = Path(sys.argv[2])
lab = Lab.open(proj, create=False)
ctx = _context(lab)
spec0 = ctx["design"].spec
doc0 = dict(ctx["doc_compile"])
lib0 = library()
servo_key = "sts3215_c018"
s = InterpretSettings()

interp = json.loads((proj / "runs/20261104-042426-interpret-ef3c/interpretation.json").read_text(encoding="utf-8"))
params = {r["behaviour"]: (r["primitive"], r["params"]) for r in interp["records"]}
MOTIONS = {
    "walk (as is)": ("walk", {}),
    "trot (as is)": ("trot", {}),
    "interpreted trot (fast play)": params["other"],
    "interpreted step": params["step"],
}


def lib_with(scale_stall=1.0, scale_rated=1.0, scale_speed=1.0) -> Library:
    comps = []
    for k in list(lib0._by_key):
        c = lib0._by_key[k]
        if k == servo_key:
            c = c.model_copy(update={"stall_torque_nm": c.stall_torque_nm * scale_stall,
                                     "rated_torque_nm": c.rated_torque_nm * scale_rated,
                                     "no_load_speed_rpm": c.no_load_speed_rpm * scale_speed})
            assert c.stall_torque_nm > 0
        comps.append(c)
    return Library(comps, lib0.incomplete)


def doc_with(mass=1.0, armature=1.0) -> dict:
    d = dict(doc0)
    d["armature_scale"] = armature
    if mass != 1.0:
        f = float(d.get("floor_friction", 0.9))
        d["randomization"] = {"enabled": True, "friction": [f, f], "mass_scale": [mass, mass],
                              "torque_scale": [1, 1], "kp_scale": [1, 1], "damping_scale": [1, 1],
                              "skin_scale": [1, 1]}
    return d


def spec_with(spring=1.0, mass=1.0):
    sp0 = spec0
    if mass != 1.0:
        def g2(g):
            upd = {"mass_g": g.mass_g * mass}
            if g.inertia is not None:
                upd["inertia"] = type(g.inertia)(x * mass for x in g.inertia)
            return g.model_copy(update=upd)
        sp0 = sp0.model_copy(update={"bodies": [b.model_copy(update={"geoms": [g2(g) for g in b.geoms]})
                                                for b in sp0.bodies]})
    if spring == 1.0:
        return sp0
    return sp0.model_copy(update={"springs": [sp.model_copy(update={"k_n_per_mm": sp.k_n_per_mm * spring})
                                              for sp in sp0.springs]})


V12 = 12.0
VARIANTS = [("baseline", {}, 1.0)]
VARIANTS += [(f"mass x{m}", {"mass": m}, m) for m in (0.9, 1.1, 1.2, 1.3)]
VARIANTS += [(f"armature x{a}", {"armature": a}, a) for a in (0.2, 0.5, 1.5, 2.0)]
VARIANTS += [(f"spring rates x{k}", {"spring": k}, k) for k in (0.0, 0.5, 1.5, 2.0, 3.0)]
VARIANTS += [(f"rated torque x{r}", {"rated": r}, r) for r in (0.8, 0.9, 1.1, 1.2)]
VARIANTS += [(f"servo at {v} V (stall, rated, speed x V/12)", {"volt": v}, v) for v in (10.5, 11.1, 12.6)]

rows = []
t_all = time.perf_counter()
for mname, (pkey, pparams) in MOTIONS.items():
    for vname, kw, val in VARIANTS:
        volt = kw.get("volt")
        sv = volt / V12 if volt else 1.0
        lib = lib_with(sv, sv * kw.get("rated", 1.0), sv)
        spec = spec_with(kw.get("spring", 1.0), kw.get("mass", 1.0))
        doc = doc_with(1.0, kw.get("armature", 1.0))
        prim = registry.get("motion_primitive", pkey)(pparams)
        t = time.perf_counter()
        ro, t0, t1, _c = play_primitive(prim, spec, lib, doc, s)
        j = judge(ro, spec, lib, s.margin)
        cons = {k: (v["margin"], v["value"], v["limit"]) for k, v in j["constraints"].items()}
        worst = min(((k, v[0]) for k, v in cons.items() if v[0] is not None), key=lambda kv: kv[1])
        if kw.get("mass"):
            assert abs(spec.total_mass_g() - spec0.total_mass_g() * kw["mass"]) < 1e-6
        rows.append({"motion": mname, "variant": vname, "value": val, "margin": j["margin"], "fell": j["fell"],
                     "fall_t": j["fall_time_s"], "violations": j["violations"], "worst": worst[0],
                     "constraints": cons, "wall": round(time.perf_counter() - t, 1)})
        print(f"{mname:30s} {vname:44s} margin {j['margin']!s:>7} worst {worst[0]:16s} fell {j['fell']} "
              f"viol {','.join(j['violations'])}", flush=True)
out.write_text(json.dumps({"rows": rows, "wall_s": time.perf_counter() - t_all,
                           "mass_g": spec0.total_mass_g()}, indent=1, default=float), encoding="utf-8")
print("done", round(time.perf_counter() - t_all), "s")
