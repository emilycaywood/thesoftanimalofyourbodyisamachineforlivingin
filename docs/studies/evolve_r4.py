"""Session R step 4 (ADR-091): evolve the body with the vigour preset, on the researcher's budget.

Edits the project through commands (logged, undoable): the hip ab/ad springs on in the starting body, and the
fitness node's preset set to ``vigour``. Then MAP-Elites + CMA-ES, 6 generations x 8 bodies, inner 2 x 4,
archive vigour_kept x worst_margin, every evolvable gene.

Run:  python docs/studies/evolve_r4.py <project dir>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from calflab.app.lab import Lab

lab = Lab.open(Path(sys.argv[1]), create=False)
lab.execute("set_genes", {"values": {"spring_hip_abd": True}})
fit = lab.state.graph.role("fitness")
lab.execute("set_node_params", {"node": fit.id, "params": {"preset": "vigour"}})
params = {"generations": 6, "batch_size": 8, "inner_iterations": 2, "inner_popsize": 4,
          "descriptor_x": "vigour_kept", "descriptor_y": "worst_margin", "grid_x": 10, "grid_y": 8, "seed": 0}
print("estimate:", lab.estimate_evolve("map_elites_cma", params, {})["run"], flush=True)
t = time.perf_counter()
job = lab.run_evolve("map_elites_cma", params)
last = ""
while job.status not in ("done", "failed", "cancelled"):
    time.sleep(5)
    v = job.view()
    msg = f"{v.get('progress', 0):.2f} {v.get('message', '')}"
    if msg != last:
        print(f"[{time.perf_counter() - t:6.0f} s] {msg}", flush=True)
        last = msg
print("status", job.status, "result", job.result, "error", getattr(job, "error", None), flush=True)
print(f"wall {time.perf_counter() - t:.0f} s", flush=True)
lab.close()
