"""Session R7 (ADR-098): the safe R6c behaviours with variation added. For each safe cell of a run without
variation, the same generator with every variation gene set to a share of its range, judged with the run's
coverage and capped durations (forced plays at the variation's extremes).

Run:  python docs/studies/vary_r6c_r7.py <project dir> <run id> <out.json> [--levels=0.1,0.3] [--workers=7]
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
            "descriptors": out["descriptors"], "movement": m["movement"], "x": payload["x"]}


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.design import build_design
    from calflab.evolve.diversity import WITHIN_GLOBAL, WITHIN_STATE, palette_for
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins

    load_plugins()
    proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[4:] if a.startswith("--"))
    levels = [float(v) for v in (opts.get("levels") or "0.1,0.3").split(",")]
    d = proj / "runs" / run_id
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    cands = {c["id"]: c for c in (json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x)}
    arch = json.loads((d / "archive.json").read_text(encoding="utf-8"))["archive"]
    safe = [cands[c["candidate"]] for c in arch["cells"] if c.get("within_limits")]
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    lab.close()
    p = run["inputs"]["params"]
    spec = build_design(Genome.model_validate(safe[0]["genome"]), [Override.model_validate(o) for o in run["overrides"]],
                        generator, gen_params).spec
    extra = len(WITHIN_GLOBAL) + len(palette_for(spec, list(p["palette"]) or None)) * len(WITHIN_STATE)
    base = {"overrides": run["overrides"], "generator": generator, "generator_params": gen_params,
            "compile": run["inputs"]["compile"], "fitness": run["fitness"]["preset"], "palette": list(p["palette"]),
            "duration_s": float(p["duration_s"]), "margin": float(p["margin"]),
            "unpredictability_weight": p["unpredictability_weight"], "descriptors": [p["descriptor_x"], p["descriptor_y"]],
            "coverage": True, "performance_s": p.get("performance_s", 60.0), "coverage_p": p.get("coverage_p", 0.05),
            "coverage_after_s": p.get("coverage_after_s", 6.0), "cap_durations": True, "vary_within": True}
    jobs = [(c, lv) for lv in levels for c in safe]
    payloads = [{**base, "genome": c["genome"], "x": list(c["controller_x"]) + [lv] * extra} for c, lv in jobs]
    with Pool(int(opts.get("workers") or 7)) as pool:
        outs = pool.map(_task, payloads)
    rows = []
    for (c, lv), o in zip(jobs, outs, strict=True):
        rows.append({"candidate": c["id"], "cell": c["cell"], "level": lv, **o})
        print(f"{c['id'][-8:]} level {lv}: {'SAFE ' if o['within'] else 'unsafe'} {o['margin']:+.2f} "
              f"{ {k: round(v, 2) for k, v in o['descriptors'].items()} } {(o['unsafe'] or [''])[0][:120]}", flush=True)
    outp.write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
