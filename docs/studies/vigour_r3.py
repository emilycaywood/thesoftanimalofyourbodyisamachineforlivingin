"""Session R step 3 (ADR-090): the vigour preset on two bodies, timed, and Estimate cost for a few budgets.

In memory on a scratch copy of the project (its fitness node is pointed at ``vigour`` in memory only).
Bodies: today's, and wide blocks + half splay + hip springs (body E of ``width_r2c.md``).

Run:  python docs/studies/vigour_r3.py <project dir> <out.json>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from calflab.app.lab import Lab
from calflab.design import genome_definition
from calflab.evolve.tasks import evaluate_candidate
from calflab.fitness import presets

proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
lab = Lab.open(proj, create=False)
lab.state.graph.role("fitness").params["preset"] = "vigour"  # scratch copy, in memory: what Estimate cost reads
gdef = genome_definition("feral_calf")
genes0: dict[str, Any] = gdef.complete(dict(lab.state.graph.role("genome").params))
out: dict[str, Any] = {"estimates": [], "bodies": []}

for gens, batch, iters, pop in ((3, 8, 2, 4), (6, 8, 2, 4), (10, 16, 2, 4), (6, 8, 4, 6)):
    est = lab.estimate_evolve("map_elites_cma", {"generations": gens, "batch_size": batch, "inner_iterations": iters,
                                                 "inner_popsize": pop, "descriptor_x": "vigour_kept",
                                                 "descriptor_y": "worst_margin"}, {})
    out["estimates"].append(est)
    r = est["run"]
    print(f"estimate g{gens} b{batch} it{iters} pop{pop}: {r['rollouts']} plays max, cpu {r['cpu_s'] / 3600:.2f} h, "
          f"wall {r['wall_s'] / 3600:.2f} h on {est['workers']} workers; per body {r['per_body']}", flush=True)

BODIES = {
    "today": {},
    "E wide blocks, half splay, hip springs": {"hind_leg_splay": 6.0, "front_leg_splay": 5.25, "hip_block_widen": 59.6,
                                               "chest_block_widen": 52.2, "spring_hip_abd": True,
                                               "spring_stifle_k": 0.1969, "spring_hock_k": 0.1285,
                                               "spring_shoulder_k": 0.0217, "spring_hip_abd_k": 0.1778},
}
start = lab.design()
fitness = lab.prepare_suite(presets()["vigour"].model_dump(mode="json"), start)
print("targets:", json.dumps({k: {kk: v[kk] for kk in ("primitive", "base", "ref_speed_mm_s") if kk in v}
                              for k, v in fitness["evaluation"]["suite"]["targets"].items()}), flush=True)
for name, genes in BODIES.items():
    values = {**genes0, **genes}
    payload = {"genome": {"definition": "feral_calf", "version": gdef.version, "values": values},
               "overrides": [], "generator": "feral_calf", "generator_params": lab.job_generator_params(lab.state.graph),
               "compile": dict(lab.state.graph.role("model").params), "sim": {},
               "controller": {"key": "feral_motion", "params": {}}, "fitness": fitness,
               "descriptors": ["vigour_kept", "worst_margin", "hoof_width"], "inner": {"iterations": 2, "popsize": 4}}
    t = time.perf_counter()
    res = evaluate_candidate(payload)
    wall = time.perf_counter() - t
    v = res["metrics"]["vigour"]
    print(f"\n== {name}: fitness {res['fitness']:.3f} vigour {v['kept']:.3f} worst margin {v['worst_margin']:.2f} "
          f"feasible {v['feasible']}/5; plays {v['plays']} (cache hits {v['cache_hits']}), {wall:.0f} s", flush=True)
    for m, r in v["motions"].items():
        print(f"   {m:6s} {r['primitive']:12s} kept {r['kept']:.2f} feasible {r['feasible']!s:5} margin {r['margin']} "
              f"searched {r['searched']} within {r['within_in_search']} verified {r['verified']} viol {r['violations']} "
              f"params {r['params']}", flush=True)
    out["bodies"].append({"name": name, "genes": genes, "wall_s": round(wall, 1), "result": res})
outp.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
