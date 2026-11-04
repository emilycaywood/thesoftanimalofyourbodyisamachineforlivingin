"""Session R, after step 4 (ADR-092): make body E of width_r2c.md the project's working body, through commands.

Run:  python docs/studies/body_r5.py <project dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

from calflab.app.lab import Lab
from calflab.evolve.vigour import hoof_half_width

E = {"hind_leg_splay": 6.0, "front_leg_splay": 5.25, "hip_block_widen": 59.6, "chest_block_widen": 52.2,
     "spring_hip_abd": True, "spring_stifle_k": 0.1969, "spring_hock_k": 0.1285, "spring_shoulder_k": 0.0217,
     "spring_hip_abd_k": 0.1778}

lab = Lab.open(Path(sys.argv[1]), create=False)
before = lab.design().spec
lab.execute("set_genes", {"values": E})
spec = lab.design().spec
meta = spec.metadata["feral"]
genes = lab.state.graph.role("genome").params
print("genes now:", {k: genes[k] for k in E})
print("belts ok:", meta["belts_ok"], "infeasible:", meta["infeasible"])
print("mass g:", round(before.total_mass_g(), 1), "->", round(spec.total_mass_g(), 1))
print("standing height mm:", meta["standing_height_mm"], "front angle deg:", meta["front_angle_deg"])
print("hoof half-width mm:", hoof_half_width(before), "->", hoof_half_width(spec))
print("blocks mm:", meta["hip_block_width_mm"], meta["chest_block_width_mm"])
lab.close()
