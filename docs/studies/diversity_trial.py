"""Session R (ADR-093): set the fitness node to `diversity` (a command), Estimate cost for a few budgets, and run a
small trial of MAP-Elites over behaviour on the working body (2 generations x 14) to check the whole path.

Run:  python docs/studies/diversity_trial.py <project dir> [generations batch]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from calflab.app.lab import Lab


def main() -> None:
    lab = Lab.open(Path(sys.argv[1]), create=False)
    gens = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 14
    fit = lab.state.graph.role("fitness")
    if fit.params.get("preset") != "diversity":
        lab.execute("set_node_params", {"node": fit.id, "params": {"preset": "diversity"}})
    for g, b in ((6, 14), (10, 28), (20, 28)):
        est = lab.estimate_evolve("map_elites_behaviour", {"generations": g, "batch_size": b}, {})
        r = est["run"]
        print(f"estimate {g} x {b}: {r['rollouts']} plays, cpu {r['cpu_s'] / 3600:.2f} h, wall {r['wall_s'] / 60:.0f} min "
              f"on {est['workers']} workers (+ about 70 s finding the start settings)", flush=True)
    t = time.perf_counter()
    job = lab.run_evolve("map_elites_behaviour", {"generations": gens, "batch_size": batch})
    while job.status not in ("done", "failed", "cancelled"):
        time.sleep(5)
    print("status", job.status, job.result, job.error, f"wall {time.perf_counter() - t:.0f} s", flush=True)
    if job.status == "done":
        run = job.result["run_id"]
        arch = json.loads((Path(sys.argv[1]) / "runs" / run / "archive.json").read_text(encoding="utf-8"))
        for h in arch["history"]:
            print("  ", {k: h.get(k) for k in ("generation", "best", "coverage", "elites", "safe_elites", "unsafe")})
        cells = arch["archive"]["cells"]
        safe = [c for c in cells if c.get("within_limits")]
        print(f"cells {len(cells)}, safe {len(safe)}")
        for c in sorted(cells, key=lambda c: -c["fitness"])[:10]:
            print(f"   ({c['i']},{c['j']}) fit {c['fitness']:+.3f} safe {c['within_limits']} margin {c['safety_margin']} "
                  f"unp {c['unpredictability']} {c['descriptors']} played {c['states_played']}")
        start = arch["archive"].get("start") or {}
        print("start settings within limits:", {n: s["within"] for n, s in start.items()})
    lab.close()


if __name__ == "__main__":  # the local pool spawns workers (Windows)
    main()
