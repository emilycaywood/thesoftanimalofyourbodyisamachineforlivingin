"""Session R6c follow-up: what would let the trot be quicker? The trot grid of ``trot_r6c.py`` judged under
what-if settings, in simulation only (the project document is not changed):

* now: margin 0.2, sustained-torque check at rated_fraction 0.6 x rated torque;
* rated 1.0: the sustained check at the servo's full rated torque (10 kg.cm) instead of 0.6 of it;
* margin 0.1;
* both.

Run:  python docs/studies/trot_whatif_r6c.py <project dir> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from calflab.app.lab import Lab

CASES = {"now": (0.2, None), "rated 1.0": (0.2, 1.0), "margin 0.1": (0.1, None), "both": (0.1, 1.0)}


def main() -> None:
    from calflab.behave.interpret import Interpreter, InterpretSettings
    from calflab.components import library
    from calflab.design import build_design

    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    design = lab.design()
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    overrides = [o for o in lab.state.overrides if o.enabled]
    compile_doc = g.role("model").params
    lab.close()
    lib = library()
    out = {}
    for name, (margin, rated) in CASES.items():
        params = dict(gen_params) if rated is None else {**gen_params, "rated_fraction": rated}
        spec = build_design(design.genome, overrides, generator, params).spec
        it = Interpreter(spec, lib, compile_doc, InterpretSettings(margin=margin, seed=0, buffer=0.0), None)
        grid = {}
        for cycle in (0.6, 0.8, 1.0, 1.2):
            for stride in (0.5, 1.0, 1.5, 2.0):
                e = it.evaluate("trot", {"cycle_s": cycle, "stride": stride, "lift": 0.6, "turn": 0.0}, {}, {})
                cons = {k: v["margin"] for k, v in e.constraints.items() if v.get("margin") is not None}
                worst = min(cons, key=lambda k: cons[k]) if cons else None
                grid[f"{cycle}/{stride}"] = {"margin": e.margin, "within": e.within_limits and not e.fell,
                                             "closest": worst, "speed_mm_s": e.features.get("speed_mm_s")}
        out[name] = grid
        print(name, flush=True)
        for cycle in (0.6, 0.8, 1.0, 1.2):
            cells = [grid[f"{cycle}/{s}"] for s in (0.5, 1.0, 1.5, 2.0)]
            print(f"  cycle {cycle}: " + "  ".join(
                f"{'OK ' if c['within'] else '   '}{c['margin']:+.2f} {c['closest'][:9]:9s} {c['speed_mm_s']:4.0f}mm/s"
                for c in cells), flush=True)
    outp.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
