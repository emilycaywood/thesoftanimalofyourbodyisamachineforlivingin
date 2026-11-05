"""Session R6c follow-up: why the evolved trots are slow. Play the trot primitive alone on the working body over a
grid of cycle and stride (lift 0.6, as evolved), seed 0, every limit at margin 0.2, and print which limit each
setting reaches, with the trot's speed and the hooves' rate.

Run:  python docs/studies/trot_r6c.py <project dir> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from calflab.app.lab import Lab


def main() -> None:
    from calflab.behave.interpret import Interpreter, InterpretSettings
    from calflab.components import library

    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    lab = Lab.open(proj, create=False)
    spec = lab.design().spec
    compile_doc = lab.state.graph.role("model").params
    lab.close()
    it = Interpreter(spec, library(), compile_doc, InterpretSettings(margin=0.2, seed=0), None)
    rows = []
    for cycle in (0.6, 0.8, 1.0, 1.2):
        for stride in (0.5, 1.0, 1.5, 2.0):
            lift = 0.3 if (cycle, stride) == (0.6, 2.0) else 0.6
            e = it.evaluate("trot", {"cycle_s": cycle, "stride": stride, "lift": lift, "turn": 0.0}, {}, {})
            cons = {k: v["margin"] for k, v in e.constraints.items() if v.get("margin") is not None}
            worst = sorted(cons.items(), key=lambda kv: kv[1])[:3]
            f = e.features
            row = {"cycle_s": cycle, "stride": stride, "lift": lift, "within": e.within_limits, "fell": e.fell,
                   "margin": e.margin, "closest": worst, "features": f}
            rows.append(row)
            speed = f.get("speed_bl_s", f.get("speed"))
            print(f"cycle {cycle:.1f} s stride {stride:.1f} lift {lift:.1f}: within {e.within_limits!s:5s} "
                  f"fell {e.fell!s:5s} margin {e.margin if e.margin is None else round(e.margin, 2)}  closest "
                  f"{[(k, round(v, 2)) for k, v in worst]}  speed {speed}", flush=True)
    print("feature keys:", sorted(rows[0]["features"]))
    outp.write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
