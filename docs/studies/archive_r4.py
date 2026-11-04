"""Session R step 4 (ADR-091): read an evolution's archive. Which bodies keep the most vigour, what changed from
the starting body, how many candidates were infeasible and why.

Run:  python docs/studies/archive_r4.py <project dir> <run id> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from calflab.design import genome_definition

proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
run_dir = proj / "runs" / run_id
cands = [json.loads(line) for line in (run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
arch = json.loads((run_dir / "archive.json").read_text(encoding="utf-8"))
rec = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").is_file() else {}
gdef = genome_definition("feral_calf")
start = gdef.complete((rec.get("genome") or {}).get("values") or cands[0]["genome"]["values"])
evolvable = {g.id: g for g in gdef.evolvable(None)}

status = Counter(c["status"] for c in cands)
print(f"{len(cands)} candidates: {dict(status)}")


def reason_kind(text: str) -> str:
    t = re.sub(r"[-+]?\d+(\.\d+)?", "#", text or "")
    return t[:140]


reasons = Counter(reason_kind(c.get("error") or "") for c in cands if c["status"] in ("infeasible", "failed", "unsafe"))
print("\nwhy not evaluated:")
for r, n in reasons.most_common():
    print(f"  {n:3d}  {r}")

ok = [c for c in cands if c["status"] not in ("infeasible", "failed", "unsafe")]
ok.sort(key=lambda c: -c["fitness"])


def changes(values: dict[str, Any]) -> dict[str, tuple[float, float]]:
    out = {}
    for gid, g in evolvable.items():
        a, b = float(start[gid]), float(values[gid])
        if g.max is not None and g.min is not None and abs(b - a) > 0.05 * (g.max - g.min):
            out[gid] = (round(a, 3), round(b, 3))
    return out


rows = []
for c in ok:
    v = (c.get("metrics") or {}).get("vigour") or {}
    mot = {m: {"kept": r["kept"], "margin": r["margin"], "feasible": r["feasible"], "violations": r["violations"]}
           for m, r in (v.get("motions") or {}).items()}
    rows.append({"id": c["id"], "generation": c["generation"], "status": c["status"], "fitness": c["fitness"],
                 "vigour": v.get("kept"), "worst_margin": v.get("worst_margin"), "feasible": v.get("feasible"),
                 "hoof_half_width_mm": (c.get("metrics") or {}).get("hoof_half_width_mm"), "mass_g": c["mass_g"],
                 "motions": mot, "changes": changes(c["genome"]["values"]),
                 "params": {m: r["params"] for m, r in (v.get("motions") or {}).items()}})
print("\nbest 8 by fitness:")
for r in rows[:8]:
    print(f"  {r['id']} g{r['generation']} fit {r['fitness']:+.3f} vigour {r['vigour']:.3f} worst {r['worst_margin']:+.2f} "
          f"feasible {r['feasible']}/5 hooves {r['hoof_half_width_mm']} mass {r['mass_g']:.0f} g")
    print("     " + "  ".join(f"{m} {x['kept']:.2f}/{x['margin'] if x['margin'] is None else round(x['margin'], 2)}"
                              for m, x in r["motions"].items()))
    print("     changed: " + ", ".join(f"{k} {a:g}->{b:g}" for k, (a, b) in r["changes"].items()))
best_v = max(rows, key=lambda r: (r["vigour"] or 0.0)) if rows else None
if best_v:
    print(f"\nmost vigour: {best_v['id']} vigour {best_v['vigour']:.3f} worst {best_v['worst_margin']:+.2f}")
within = [r for r in rows if (r["worst_margin"] or -9) >= 0]
print(f"\nbodies with every motion within the limits (worst margin >= 0): {len(within)}")
per_motion = {m: sum(1 for r in rows if r["motions"].get(m, {}).get("feasible")) for m in
              ("walk", "trot", "stand", "step", "other")}
print("bodies where each motion is within limits on 3 seeds:", per_motion)
trot_viol = Counter(v for r in rows for v in r["motions"].get("trot", {}).get("violations", []))
print("trot's violations across bodies:", dict(trot_viol))
print("\nhistory:")
for h in arch.get("history", []):
    print("  ", {k: h[k] for k in ("generation", "best", "gen_best", "coverage", "elites", "infeasible", "failed")})
outp.write_text(json.dumps({"status": dict(status), "reasons": dict(reasons), "rows": rows,
                            "history": arch.get("history"), "per_motion": per_motion}, indent=1, default=float),
                encoding="utf-8")
