"""Session R6b (ADR-096): try the three ways of judging a behaviour for a whole performance on cells of a
behaviour-diversity run, and time each.

* (b) coverage: the run's 24 s evaluation plus forced plays of every state likely in a minute;
* (c) the same generator without the steps (their genes dropped), judged over 60 s;
* (b+c) both.
(a), 60 s evaluations, was played in R6 (``perform_r6.py``): its result is read from there.

Run:  python docs/studies/options_r6b.py <project dir> <run id> <out.json> [--tries=b_coverage,...]
          <candidate suffix>=<label> ...
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from calflab.app.lab import Lab

NO_STEPS = ["stand", "shift_hl", "shift_hr", "walk", "trot", "turn"]


def main() -> None:
    from calflab.design import build_design
    from calflab.evolve.diversity import evaluate_behaviour, layout, palette_for
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins

    proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    opts = dict(a[2:].split("=", 1) for a in sys.argv[4:] if a.startswith("--"))
    picks = dict(a.split("=", 1) for a in sys.argv[4:] if not a.startswith("--"))
    load_plugins()
    lab = Lab.open(proj, create=False)
    d = proj / "runs" / run_id
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    cands = {c["id"]: c for c in (json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x)}
    p = run["inputs"]["params"]
    g = lab.state.graph
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    lab.close()
    base = {"overrides": run["overrides"], "generator": generator, "generator_params": gen_params,
            "compile": run["inputs"]["compile"], "fitness": run["fitness"]["preset"], "palette": [],
            "duration_s": float(p["duration_s"]), "margin": float(p["margin"]),
            "unpredictability_weight": p["unpredictability_weight"], "descriptors": [p["descriptor_x"], p["descriptor_y"]]}
    out: list[dict[str, Any]] = []
    for suffix, label in picks.items():
        cand = cands[next(k for k in cands if k.endswith(suffix))]
        spec = build_design(Genome.model_validate(cand["genome"]), [Override.model_validate(o) for o in run["overrides"]],
                            generator, gen_params).spec
        full = layout(palette_for(spec))
        x = list(cand["controller_x"])
        x_ns = [v for (state, _g, _lo, _hi), v in zip(full, x, strict=True) if not state.startswith("step_")]
        tries = {"b_coverage": {**base, "x": x, "coverage": True},
                 "c_no_steps_60s": {**base, "x": x_ns, "palette": NO_STEPS, "duration_s": 60.0},
                 "c_no_steps_24s": {**base, "x": x_ns, "palette": NO_STEPS},
                 "bc_no_steps_coverage": {**base, "x": x_ns, "palette": NO_STEPS, "coverage": True},
                 "b_coverage_capped": {**base, "x": x, "coverage": True, "cap_durations": True}}  # ADR-097
        if "tries" in opts:
            tries = {k: v for k, v in tries.items() if k in opts["tries"].split(",")}
        row: dict[str, Any] = {"label": label, "candidate": cand["id"]}
        for name, pay in tries.items():
            t = time.perf_counter()
            r = evaluate_behaviour({**pay, "genome": cand["genome"]})
            m = r["metrics"]
            row[name] = {"safe": m["within_limits"], "margin": m["safety_margin"], "unsafe": r.get("unsafe_reasons"),
                         "rollouts": r["evals"], "wall_s": round(time.perf_counter() - t, 1),
                         "descriptors": r["descriptors"], "played": m["states_played"],
                         "coverage": m.get("coverage")}
            cov = m.get("coverage") or {}
            print(f"{label:9s} {name:22s} safe {m['within_limits']!s:5s} margin {m['safety_margin']:+.3f} "
                  f"rollouts {r['evals']:2d} wall {time.perf_counter() - t:5.1f} s  "
                  f"forced {[(pl['state'], pl['from'], pl['reach']) for pl in cov.get('plays', [])]} "
                  f"{r.get('unsafe_reasons') or ''}", flush=True)
        out.append(row)
    outp.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
