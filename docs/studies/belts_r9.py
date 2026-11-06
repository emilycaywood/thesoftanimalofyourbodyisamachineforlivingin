"""Session R9 (ADR-100): which catalog belt lengths fit each catalog pulley pair at the carpus and the hock, with
every belt check of ADR-063/064 (derived C, servo on its segment, teeth in mesh, the hock servo against the stifle
belt), on an in-memory genome. The document is not changed (a real change goes through ``set_belt_drive``).

Only pairs already in the project's catalog are tried (today: 30T-60T, 36T-72T, 40T-80T, all 2:1).

Run:  python docs/studies/belts_r9.py <project dir> [<out.json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.design import build_design
    from calflab.mech.belts import load_catalog
    from calflab.plugins import load_plugins

    load_plugins()
    proj = Path(sys.argv[1])
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    design = lab.design()
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    overrides = [o for o in lab.state.overrides if o.enabled]
    lab.close()
    catalog, _note = load_catalog(proj)
    vals0 = dict(design.genome.values)
    now = (design.spec.metadata.get("feral") or {}).get("belt_drives") or {}
    out: dict[str, Any] = {"now": {d: {"choice": r["choice"], "c_mm": r.get("c_mm")} for d, r in now.items()}}
    for drive in ("carpus", "hock"):
        system = vals0[f"belt_{drive}_system"]
        sysd = catalog.system(system)
        rows = []
        for pair in catalog.pairs:
            for e in catalog.lengths_for(sysd):
                if not catalog.length_status(sysd, e)[0]:
                    continue
                vals = {**vals0, f"belt_{drive}_pulleys": pair.id, f"belt_{drive}_length": e.id}
                try:
                    d = build_design(design.genome.model_copy(update={"values": vals}), overrides, generator, gen_params)
                except Exception as exc:  # noqa: BLE001 - a choice the generator refuses is a result here
                    rows.append({"pair": pair.id, "length": e.id, "ok": False, "why": str(exc)[:160]})
                    continue
                fer = d.spec.metadata.get("feral") or {}
                rep = (fer.get("belt_drives") or {}).get(drive) or {}
                fails = [c for c in rep.get("checks", []) if isinstance(c, dict) and c.get("status") == "fail"]
                rows.append({"pair": pair.id, "length": e.id, "ok": bool(rep.get("ok")), "c_mm": rep.get("c_mm"),
                             "d1_mm": rep.get("d1_mm"), "ratio": rep.get("ratio"),
                             "unknown": [c.get("label") or c.get("key") for c in rep.get("checks", [])
                                         if isinstance(c, dict) and c.get("status") == "unknown"],
                             "why": "; ".join(str(c.get("detail") or c.get("label")) for c in fails)[:200]})
        out[drive] = rows
        ok = [r for r in rows if r["ok"]]
        print(f"{drive}: today {now[drive]['choice']} C {now[drive].get('c_mm'):.1f}")
        for pair in catalog.pairs:
            p_ok = [r for r in ok if r["pair"] == pair.id]
            print(f"  {pair.id}: {len(p_ok)} lengths pass: "
                  + ", ".join(f"{r['length']} (C {r['c_mm']:.1f})" for r in p_ok))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
