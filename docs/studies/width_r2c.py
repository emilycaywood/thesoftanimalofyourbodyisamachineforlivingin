"""Session R, after step 2 (ADR-089): wide hooves from wider blocks, splay, and springs that hold the weight.

Each body is built in memory from the project's genes plus a variant, played in physics (torque-speed servos,
derating 1, seed 0, as ``calflab.behave.interpret``) and judged at margin 0.2. Nothing in the project changes.

"GC springs": every enabled spring's rate is scaled so its torque at standing equals what the weight puts on its
joint (``static_spring_report``: gravity_nm / torque_nm), the hip ab/ad springs included when they are on.

Run:  python docs/studies/width_r2c.py <project dir> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from calflab.app.lab import Lab
from calflab.app.physics_jobs import _context
from calflab.behave.interpret import InterpretSettings, judge, play_primitive
from calflab.components.library import library
from calflab.design import genome_definition
from calflab.mech.loads import static_spring_report
from calflab.mech.statics import default_contacts
from calflab.plugins import registry

proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
lab = Lab.open(proj, create=False)
ctx = _context(lab)
doc = dict(ctx["doc_compile"])
lib = library()
s = InterpretSettings()
genes0: dict[str, Any] = genome_definition("feral_calf").complete(dict(lab.state.graph.role("genome").params))
interp = json.loads((proj / "runs/20261104-042426-interpret-ef3c/interpretation.json").read_text(encoding="utf-8"))
params = {r["behaviour"]: (r["primitive"], r["params"]) for r in interp["records"]}
MOTIONS = {"walk": ("walk", {}), "trot": ("trot", {}), "interp trot": params["other"], "interp step": params["step"]}
SPRING_K = {"stifle": "spring_stifle_k", "hock": "spring_hock_k", "shoulder": "spring_shoulder_k",
            "hip_abd": "spring_hip_abd_k"}


def build(genes: dict[str, Any]):
    return lab.design(lab.variant_graph(genes={**genes0, **genes})).spec


def hoof_y(spec) -> dict[str, float]:
    """Half the left-right distance between the hooves (mm), hind and front, standing."""
    poses = spec.world_poses()
    ys = {b: abs(p[1]) for b, p in default_contacts(spec, poses)}
    return {"hind": max(v for b, v in ys.items() if ".h" in b), "front": max(v for b, v in ys.items() if ".f" in b)}


def gc(genes: dict[str, Any]) -> dict[str, Any]:
    """The same body with every enabled spring's rate set to hold the weight at standing (hl / fl springs)."""
    spec = build(genes)
    out = dict(genes)
    for r in static_spring_report(spec):
        kind = r["joint"].split(".")[-1]
        if not (r["spring"].startswith("spring.hl.") or r["spring"].startswith("spring.fl.")):
            continue
        k0 = float({**genes0, **genes}[SPRING_K[kind]])
        if abs(r["torque_nm"]) > 1e-9:
            out[SPRING_K[kind]] = round(min(3.0, k0 * abs(r["gravity_nm"]) / abs(r["torque_nm"])), 4)
    return out


base = build({})
y_today = hoof_y(base)
y_zero = hoof_y(build({"hind_leg_splay": 0.0, "front_leg_splay": 0.0}))
print("today splay", genes0["hind_leg_splay"], genes0["front_leg_splay"], "hoof half-width", y_today, flush=True)


def same_width(hind_splay: float, front_splay: float, frac: float = 1.0) -> dict[str, Any]:
    """Splays as given; blocks widened so the hooves stand ``frac`` of the way from splay-0 width to today's."""
    g = {"hind_leg_splay": hind_splay, "front_leg_splay": front_splay}
    y = hoof_y(build(g))
    g["hip_block_widen"] = round(max(0.0, y_zero["hind"] + frac * (y_today["hind"] - y_zero["hind"]) - y["hind"]), 1)
    g["chest_block_widen"] = round(max(0.0, y_zero["front"] + frac * (y_today["front"] - y_zero["front"]) - y["front"]), 1)
    return g


hs, fs = float(genes0["hind_leg_splay"]), float(genes0["front_leg_splay"])
VARIANTS: list[tuple[str, dict[str, Any]]] = [
    ("A today (splayed, narrow blocks)", {}),
    ("B straight legs, narrow blocks", {"hind_leg_splay": 0.0, "front_leg_splay": 0.0}),
    ("C straight legs, wide blocks (today's hoof width)", same_width(0.0, 0.0)),
]
VARIANTS.append(("D = C + GC springs", gc(VARIANTS[2][1])))
VARIANTS.append(("E half splay, wide blocks, hip springs, GC springs",
                 gc({**same_width(hs / 2, fs / 2), "spring_hip_abd": True})))
VARIANTS.append(("F today's splay, hip springs, GC springs", gc({"spring_hip_abd": True})))
VARIANTS.append(("G straight legs, half-wide blocks, GC springs", gc(same_width(0.0, 0.0, 0.5))))

res = []
for vname, genes in VARIANTS:
    spec = build(genes)
    meta = spec.metadata.get("feral") or {}
    hy = hoof_y(spec)
    show = {k: v for k, v in genes.items() if k.endswith(("widen", "splay", "_k")) or k == "spring_hip_abd"}
    print(f"\n== {vname}: hoof half-width hind {hy['hind']:.0f} front {hy['front']:.0f} mm; {show}", flush=True)
    if not meta.get("belts_ok", True):
        res.append({"variant": vname, "genes": genes, "rejected": "belt check"})
        print("   REJECTED: belt check", flush=True)
        continue
    for mname, (pkey, pp) in MOTIONS.items():
        prim = registry.get("motion_primitive", pkey)(pp)
        ro, _t0, _t1, _ = play_primitive(prim, spec, lib, doc, s)
        j = judge(ro, spec, lib, 0.2)
        c = {k: v["margin"] for k, v in j["constraints"].items()}
        res.append({"variant": vname, "motion": mname, "genes": show, "hoof_half_width_mm": hy,
                    "margin": j["margin"], "fell": j["fell"], "violations": j["violations"], "constraints": c,
                    "mass_g": spec.total_mass_g()})
        print(f"   {mname:12s} {j['margin']!s:>7} fell={j['fell']!s:5} "
              + " ".join(f"{k[:10]}={v:+.2f}" for k, v in c.items() if v is not None and v < 0.3), flush=True)
outp.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
