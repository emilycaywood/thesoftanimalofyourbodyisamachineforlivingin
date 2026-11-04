"""Session R (ADR-089): why the trot is worse on wide blocks. Per-joint mean torque and trunk roll, trot as is.

Run:  python docs/studies/width_r2c_trot.py <project dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from calflab.app.lab import Lab
from calflab.app.physics_jobs import _context
from calflab.behave.interpret import InterpretSettings, judge, play_primitive
from calflab.components.library import library
from calflab.design import genome_definition
from calflab.plugins import registry

proj = Path(sys.argv[1])
lab = Lab.open(proj, create=False)
ctx = _context(lab)
doc = dict(ctx["doc_compile"])
lib = library()
s = InterpretSettings()
g0 = genome_definition("feral_calf").complete(dict(lab.state.graph.role("genome").params))
WIDE = {"hind_leg_splay": 0.0, "front_leg_splay": 0.0, "hip_block_widen": 119.8, "chest_block_widen": 105.2}
V = {"B narrow, straight": {"hind_leg_splay": 0.0, "front_leg_splay": 0.0}, "C wide, straight": WIDE,
     "C wide, straight, roll_gain 0": WIDE}

for name, genes in V.items():
    spec = lab.design(lab.variant_graph(genes={**g0, **genes})).spec
    prim = registry.get("motion_primitive", "trot")({})
    if name.endswith("roll_gain 0"):
        orig = prim.controller

        def ctl(sp, lb, orig=orig):
            k, p = orig(sp, lb)
            return k, {**p, "roll_gain": 0.0}
        prim.controller = ctl  # type: ignore[method-assign]
    ro, *_ = play_primitive(prim, spec, lib, doc, s)
    j = judge(ro, spec, lib, 0.2)
    print("==", name, j["margin"])
    for k, v in j["constraints"].items():
        if v["margin"] is not None and v["margin"] < 0.3:
            print("  ", k, v)
    bi = ro.body_ids.index("trunk")
    q = ro.body_quat[:, bi]
    roll = np.degrees(np.arctan2(2 * (q[:, 0] * q[:, 1] + q[:, 2] * q[:, 3]), 1 - 2 * (q[:, 1] ** 2 + q[:, 2] ** 2)))
    print(f"   trunk roll deg: rms {np.sqrt(np.mean(roll ** 2)):.2f} max {np.abs(roll).max():.2f}; mean |torque|:")
    print("   ", {a.replace("act.", ""): round(float(np.mean(np.abs(ro.torque[:, i]))), 3)
                  for i, a in enumerate(ro.actuator_ids)})
