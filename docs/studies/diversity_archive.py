"""Session R (ADR-094): read a behaviour-diversity run. Which kinds of movement are within every limit, what each
safe cell's generator does, which movements never become safe and which limit stops them.

Run:  python docs/studies/diversity_archive.py <project dir> <run id> <out.json>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    d = proj / "runs" / run_id
    cands = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x]
    arch = json.loads((d / "archive.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in cands}
    cells = arch["archive"]["cells"]
    axes = arch["archive"]["axes"]
    safe = [c for c in cells if c.get("within_limits")]
    print(f"{len(cands)} candidates; {len(cells)} cells, {len(safe)} within every limit on 3 seeds")
    print("axes:", [(a["key"], a["range"], a["cells"]) for a in axes])
    evaluated = [c for c in cands if c["status"] in ("new", "improved", "rejected")]
    n_safe_all = sum(1 for c in evaluated if (c.get("metrics") or {}).get("within_limits"))
    print(f"evaluated {len(evaluated)}, of which within limits {n_safe_all}; status {dict(Counter(c['status'] for c in cands))}")

    why = Counter()
    states_unsafe, states_safe = Counter(), Counter()
    for c in evaluated:
        m = c.get("metrics") or {}
        played = m.get("states_played") or []
        if m.get("within_limits"):
            states_safe.update(played)
            continue
        states_unsafe.update(played)
        for s in m.get("seeds") or []:
            if not s["within"]:
                why.update(["fall"] if s["fell"] else s["violations"])
    print("limits the unsafe ones went over:", dict(why.most_common()))
    print("states played by safe candidates:", dict(states_safe.most_common()))
    print("states played by unsafe candidates:", dict(states_unsafe.most_common()))

    rows = []
    for c in sorted(safe, key=lambda c: (c["i"], c["j"])):
        cand = by_id[c["candidate"]]
        m = cand["metrics"]
        gen = m.get("generator") or {}
        sts = gen.get("states") or {}
        mv = m.get("movement") or {}
        top = sorted(sts.items(), key=lambda kv: -kv[1]["weight"])
        row = {"cell": [c["i"], c["j"]], "candidate": cand["id"], "generation": cand["generation"],
               "fitness": c["fitness"], "margin": m.get("safety_margin"), "unpredictability": m.get("unpredictability"),
               "descriptors": c["descriptors"], "played": m.get("states_played"), "sharpness": gen.get("sharpness"),
               "blend_s": gen.get("blend_s"),
               "states": {n: {"weight": s["weight"], "duration_s": s["duration_s"], "primitive": s["primitive"],
                              "params": s["params"]} for n, s in top},
               "movement": {k: round(v, 3) for k, v in mv.items() if isinstance(v, int | float)},
               "episodes_seed0": (m.get("seeds") or [{}])[0].get("episodes")}
        rows.append(row)
        d0, d1 = (c["descriptors"][a["key"]] for a in axes)
        print(f"\n({c['i']},{c['j']}) {cand['id'][-8:]} fit {c['fitness']:+.3f} margin {m.get('safety_margin'):+.2f} "
              f"unp {m.get('unpredictability'):.2f}  {axes[0]['key']} {d0:.2f}  {axes[1]['key']} {d1:.2f}  "
              f"stillness {mv.get('stillness_ratio', 0):.2f} trunk {mv.get('trunk_speed_mm_s', 0):.0f} mm/s")
        print(f"   sharpness {gen.get('sharpness')} blend {gen.get('blend_s')} s; played {m.get('states_played')}")
        print("   weights: " + ", ".join(f"{n} {s['weight']:.2f} ({s['duration_s']:.1f} s)" for n, s in top[:6]))
        print(f"   seed 0 sequence: {' > '.join((row['episodes_seed0'] or [])[:14])}")
    hist = arch.get("history") or []
    print("\nhistory:")
    for h in hist:
        print("  ", {k: h.get(k) for k in ("generation", "best", "coverage", "elites", "safe_elites", "unsafe")})
    outp.write_text(json.dumps({"safe_cells": rows, "why_unsafe": dict(why), "states_safe": dict(states_safe),
                                "states_unsafe": dict(states_unsafe), "history": hist,
                                "evaluated": len(evaluated), "safe_evaluated": n_safe_all}, indent=1, default=float),
                    encoding="utf-8")


if __name__ == "__main__":
    main()
