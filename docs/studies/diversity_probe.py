"""Session R (ADR-093): how often a random behaviour generator stays within limits on the working body, and what one
costs. Read-only on the project. 14 random generators (uniform in [0, 1]^D), 24 s, three randomised seeds, in
parallel on the local pool.

Run:  python docs/studies/diversity_probe.py <project dir> <out.json>
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from calflab.app.lab import Lab
from calflab.components import library
from calflab.evolve.diversity import layout, palette_for, safe_centres, start_vector
from calflab.fitness import presets
from calflab.plugins import Task, registry


def main() -> None:
    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "defaults"
    lab = Lab.open(proj, create=False)
    design = lab.design()
    g = lab.state.graph
    pal = palette_for(design.spec)
    dim = len(layout(pal))
    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    centres = safe_centres(design.spec, library(), dict(g.role("model").params), pal, 0.2) if mode == "centres" else None
    if centres:
        print(f"centres in {time.perf_counter() - t0:.0f} s:", {n: (c["within"], c["margin"], c["plays"], c["params"])
                                                               for n, c in centres.items()}, flush=True)
    base = {"genome": design.genome.model_dump(mode="json"), "overrides": [], "generator": "feral_calf",
            "generator_params": lab.job_generator_params(g), "compile": dict(g.role("model").params),
            "fitness": presets()["diversity"].model_dump(mode="json"), "palette": [n for n, _k, _b in pal],
            "duration_s": 24.0, "margin": 0.2, "unpredictability_weight": 0.5,
            "descriptors": ["quantity_of_motion", "tempo_regularity", "stillness_ratio", "expressive_range"]}
    tasks = [Task(fn="calflab.evolve.diversity:evaluate_behaviour", payload={**base, "x": [float(v) for v in (rng.uniform(0, 1, dim) if mode == "uniform" else start_vector(pal, rng, 0.1, centres))]},
                  id=f"probe-{i:02d}") for i in range(14)]
    backend = registry.get("compute_backend", lab.backend_key)()
    print(f"palette {[n for n, _k, _b in pal]}, {dim} genes, {getattr(backend, 'n_workers', lambda: '?')()} workers",
          flush=True)
    t = time.perf_counter()
    outs = backend.map(tasks, on_result=lambda i, r: None, cancelled=lambda: False)
    wall = time.perf_counter() - t
    rows, why = [], Counter()
    for task, out in zip(tasks, outs, strict=True):
        m = out.get("metrics") or {}
        safe = not out.get("unsafe") and not out.get("error")
        for s in m.get("seeds") or []:
            if not s["within"]:
                why.update(["fall"] if s["fell"] else s["violations"])
        rows.append({"id": task.id, "safe": safe, "error": out.get("error"), "unsafe": out.get("unsafe"),
                     "margin": m.get("safety_margin"), "unpredictability": m.get("unpredictability"),
                     "states_played": m.get("states_played"), "descriptors": out.get("descriptors"),
                     "movement": m.get("movement")})
        print(f"{task.id} safe {safe!s:5} margin {m.get('safety_margin')} unp {m.get('unpredictability')} "
              f"played {m.get('states_played')} {out.get('unsafe') or out.get('error') or out.get('descriptors')}",
              flush=True)
    print(f"\n{sum(r['safe'] for r in rows)}/14 within every limit on 3 seeds; wall {wall:.0f} s for 14; why not: {dict(why)}")
    outp.write_text(json.dumps({"wall_s": wall, "rows": rows, "why": dict(why)}, indent=1, default=float),
                    encoding="utf-8")
    lab.close()


if __name__ == "__main__":  # the local pool spawns workers (Windows)
    main()
