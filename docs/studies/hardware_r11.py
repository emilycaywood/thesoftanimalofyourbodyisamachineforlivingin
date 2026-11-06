"""Session R11 (ADR-102): hardware chosen by the loads of behaviour, driven through the lab's own evolution.

Stages (the project document is never changed; the preset is passed by name):

* ``estimate``: ``Lab.estimate_evolve`` for the trial and for full-run budgets;
* ``seeds``: one generation that only judges the starting body and R9's / R10's seed bodies that use R8's 45T
  what-if pulleys (``what_if_pulleys`` on, flagged everywhere); the search itself stays on the catalog;
* ``trial``: a few generations on the catalog only (what-ifs off), seeded with the working body and R10's 40T/80T
  body (R9's best and R10's 1:1 45T are skipped there because they need what-ifs);
* ``table``: the judged bodies of the given runs, with the binding limit per joint, as markdown.

Run:  python docs/studies/hardware_r11.py <project dir> estimate|seeds|trial|table [--generations=3] [--batch=7]
          [--whatif=1] [--runs=a,b]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def wait(lab: Any, job: Any) -> Any:
    last = ""
    while True:
        j = lab.jobs.get(job.id) if hasattr(lab.jobs, "get") else job
        msg = f"{j.status} {getattr(j, 'progress', 0):.2f} {getattr(j, 'message', '')}"
        if msg != last:
            print(time.strftime("%H:%M:%S"), msg, flush=True)
            last = msg
        if j.status in ("done", "failed", "cancelled"):
            return j
        time.sleep(10)


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    load_plugins()
    proj, stage = Path(sys.argv[1]), sys.argv[2]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[3:] if a.startswith("--"))
    lab = Lab.open(proj, create=False)
    try:
        if stage == "estimate":
            out = {}
            for gens, batch in ((3, 7), (10, 14), (20, 14), (30, 21)):
                for rate in (0.5, 0.8):
                    e = lab.estimate_evolve("map_elites_hardware", {"generations": gens, "batch_size": batch}, None,
                                            "hardware", rate)
                    out[f"{gens}x{batch} pass {rate:.0%}"] = e["run"]
            print(json.dumps(out, indent=1))
            print(e["note"])
            return
        if stage in ("seeds", "trial"):
            params: dict[str, Any] = {"generations": int(opts.get("generations", 1 if stage == "seeds" else 3)),
                                      "batch_size": int(opts.get("batch", 3 if stage == "seeds" else 7)),
                                      "what_if_pulleys": stage == "seeds" or opts.get("whatif") == "1",
                                      "seed": int(opts.get("seed", 0))}
            job = lab.run_evolve("map_elites_hardware", params, None, None, None, "hardware")
            run_id = (job.result or {}).get("run_id")
            print("run", run_id, params, flush=True)
            j = wait(lab, job)
            print(j.status, getattr(j, "error", None), j.result, flush=True)
            return
        if stage == "table":
            for run_id in opts["runs"].split(","):
                for c in lab.registry.list_candidates(run_id):
                    s = (c.get("metrics") or {}).get("hardware")
                    if not s:
                        continue
                    print(f"\n### {c['id']} {s.get('label', '')}: {s['minutes_held']}/{s['minutes_of']} min, trot "
                          f"{s['trot_speed_mm_s']:.0f} mm/s, cost {s['costs']['cost_index']:.2f}, fitness "
                          f"{c['fitness']:.3f}")
                    for t in s["tables"]:
                        print(f"\n{t['title']}\n\n| " + " | ".join(t["columns"]) + " |\n|" + "---|" * len(t["columns"]))
                        for r in t["rows"]:
                            print("| " + " | ".join(r) + " |")
            return
        raise SystemExit(f"unknown stage {stage!r}")
    finally:
        lab.close()


if __name__ == "__main__":
    main()
