"""Session R7 (ADR-098): re-judge a behaviour-diversity run's candidates that passed their seeds with the current
coverage (the run's own settings otherwise), on a local process pool. Prints before / after per candidate.

Run:  python docs/studies/rejudge_r7.py <project dir> <run id> <out.json> [--workers=7] [--no-variation]
"""
from __future__ import annotations

import json
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.diversity import evaluate_behaviour

    out = evaluate_behaviour(payload)
    m = out["metrics"]
    return {"within": m["within_limits"], "margin": m["safety_margin"], "unsafe": out.get("unsafe_reasons"),
            "descriptors": out["descriptors"], "coverage": m.get("coverage"), "movement": m["movement"]}


def main() -> None:
    from calflab.app.lab import Lab

    proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[4:] if a.startswith("--"))
    d = proj / "runs" / run_id
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    cands = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x]
    passed = [c for c in cands if all(s["within"] for s in (c.get("metrics") or {}).get("seeds", [{"within": False}]))]
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    lab.close()
    p = run["inputs"]["params"]
    base = {"overrides": run["overrides"], "generator": generator, "generator_params": gen_params,
            "compile": run["inputs"]["compile"], "fitness": run["fitness"]["preset"], "palette": list(p["palette"]),
            "duration_s": float(p["duration_s"]), "margin": float(p["margin"]),
            "unpredictability_weight": p["unpredictability_weight"], "descriptors": [p["descriptor_x"], p["descriptor_y"]],
            "coverage": p.get("coverage"), "performance_s": p.get("performance_s", 60.0),
            "coverage_p": p.get("coverage_p", 0.05), "coverage_after_s": p.get("coverage_after_s", 6.0),
            "cap_durations": p.get("cap_durations"), "vary_within": p.get("vary_within")}
    if "no-variation" in opts:  # the same sequences and primitives without the variation genes (ADR-093 layout)
        from calflab.design import build_design
        from calflab.evolve.diversity import layout, palette_for
        from calflab.model.genome import Genome
        from calflab.model.overrides import Override

        spec = build_design(Genome.model_validate(passed[0]["genome"]),
                            [Override.model_validate(o) for o in run["overrides"]], generator, gen_params).spec
        n = len(layout(palette_for(spec, list(p["palette"]) or None)))
        base["vary_within"] = False
        payloads = [{**base, "genome": c["genome"], "x": c["controller_x"][:n]} for c in passed]
    else:
        payloads = [{**base, "genome": c["genome"], "x": c["controller_x"]} for c in passed]
    with Pool(int(opts.get("workers") or 7)) as pool:
        outs = pool.map(_task, payloads)
    rows = []
    for c, o in zip(passed, outs, strict=True):
        rows.append({"candidate": c["id"], "cell": c["cell"], "before": {"within": c["metrics"]["within_limits"],
                     "margin": c["metrics"]["safety_margin"]}, "after": o})
        print(f"{c['id'][-8:]} cell {c['cell']}: before {c['metrics']['safety_margin']:+.2f} -> after "
              f"{'SAFE ' if o['within'] else 'unsafe'} {o['margin']:+.2f} {o['descriptors']} "
              f"{(o['unsafe'] or [''])[0][:110]}", flush=True)
    outp.write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")
    print(f"{sum(r['after']['within'] for r in rows)} of {len(rows)} safe", flush=True)


if __name__ == "__main__":
    main()
