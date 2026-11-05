"""Session R6b (ADR-096): a small behaviour-diversity run with given optimizer settings, to measure its cost.

Run:  python docs/studies/coverage_trial.py <project dir> '<params as JSON>'
e.g.  python docs/studies/coverage_trial.py projects/robot-calf-final '{"generations": 3, "batch_size": 14, "coverage": true}'
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from calflab.app.lab import Lab


def main() -> None:
    proj = Path(sys.argv[1])
    params = json.loads(sys.argv[2])
    lab = Lab.open(proj, create=False)
    t = time.perf_counter()
    job = lab.run_evolve("map_elites_behaviour", params)
    while job.status not in ("done", "failed", "cancelled"):
        time.sleep(5)
    wall = time.perf_counter() - t
    print("status", job.status, job.error, f"wall {wall:.0f} s", flush=True)
    if job.status == "done":
        run = job.result["run_id"]
        d = proj / "runs" / run
        cands = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x]
        arch = json.loads((d / "archive.json").read_text(encoding="utf-8"))
        rollouts = sum(1 + len(s["seeds"]) - 1 for c in cands for s in [c.get("metrics") or {"seeds": [0]}])
        main_safe = [c for c in cands if all(s["within"] for s in (c.get("metrics") or {}).get("seeds", [{"within": False}]))]
        cov = [c for c in main_safe if (c.get("metrics") or {}).get("coverage")]
        forced = sum(len(s["seeds"]) for c in cov for s in c["metrics"]["coverage"]["plays"])
        safe = [c for c in cands if (c.get("metrics") or {}).get("within_limits")]
        print(f"run {run}: {len(cands)} candidates; main rollouts {rollouts}; passed the seeds {len(main_safe)}; "
              f"forced plays {forced}; safe {len(safe)}", flush=True)
        for c in main_safe:
            m = c["metrics"]
            plays = (m.get("coverage") or {}).get("plays", [])
            print(f"  {c['id'][-8:]} safe {m['within_limits']} margin {m['safety_margin']:+.2f} forced "
                  f"{[(p['state'], p['from'], p['reach'], len(p['seeds'])) for p in plays]} "
                  f"{c.get('unsafe_reasons') or (m.get('unsafe_reasons') or '')}", flush=True)
        for h in arch["history"]:
            print("  ", {k: h.get(k) for k in ("generation", "coverage", "elites", "safe_elites")}, flush=True)
    lab.close()


if __name__ == "__main__":  # the local pool spawns workers (Windows)
    main()
