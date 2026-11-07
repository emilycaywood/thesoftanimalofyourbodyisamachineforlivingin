"""Session R11c (ADR-103): full hardware and bounded geometry evolution toward a production body, driven through the
lab's own evolution with preset ``hardware_r11c`` (the project document is never changed).

Stages:

* ``stageA``: one generation that judges only the working body and the preset's 14 seed bodies (geometry fixed);
* ``stageB``: the full search (every gene on), seeded from Stage A's bodies; ``--generations`` / ``--batch``;
* ``table``: markdown tables of the judged bodies of the given runs (``--runs=a,b``);
* ``geometry``: the geometry table (CSV) of given candidates (``--cands=a,b``) to ``docs/studies/geometry_r11c``.

Run:  python docs/studies/production_r11c.py <project dir> stageA|stageB|table|geometry [--generations=1] [--batch=15]
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
        if stage in ("stageA", "stageB"):
            a = stage == "stageA"
            params: dict[str, Any] = {"generations": int(opts.get("generations", 1 if a else 3)),
                                      "batch_size": int(opts.get("batch", 15 if a else 14)),
                                      "vary_geometry": not a, "what_if_pulleys": False, "seed_bodies": True,
                                      "sigma_init": float(opts.get("sigma_init", 0.1)),
                                      "sigma_iso": float(opts.get("sigma_iso", 0.05)),
                                      "seed": int(opts.get("seed", 0))}
            t0 = time.time()
            job = lab.run_evolve("map_elites_hardware", params, None, None, None, "hardware_r11c")
            print("run", (job.result or {}).get("run_id"), params, flush=True)
            j = wait(lab, job)
            print(j.status, getattr(j, "error", None), j.result, f"{time.time() - t0:.0f} s", flush=True)
            return
        if stage == "table":
            for run_id in opts["runs"].split(","):
                for c in lab.registry.list_candidates(run_id):
                    s = (c.get("metrics") or {}).get("hardware")
                    if not s:
                        if c.get("status") == "infeasible":
                            print(f"\n### {c['id']} REJECTED: {c.get('error')}")
                        continue
                    print(f"\n### {c['id']} {s.get('label', '')}: {s['minutes_held']}/{s['minutes_of']} min, trot "
                          f"{s['trot_speed_mm_s']:.0f} mm/s, cost {s['costs']['cost_index']:.2f}, fitness "
                          f"{c['fitness']:.3f}")
                    for t in s["tables"]:
                        print(f"\n{t['title']}\n\n| " + " | ".join(t["columns"]) + " |\n|" + "---|" * len(t["columns"]))
                        for r in t["rows"]:
                            print("| " + " | ".join(str(x) for x in r) + " |")
            return
        if stage == "sheets":
            # geometry CSV + parts list for the given candidates (``--cands=id:label,id:label``)
            from calflab.bridge.production_sheet import geometry_csv, geometry_rows, parts_list
            from calflab.components import library
            from calflab.design import build_design, genome_definition
            from calflab.evolve.production import SpringSpace, spring_checks
            from calflab.mech.belts import BeltCatalog
            from calflab.model.genome import Genome

            out_dir = Path("docs/studies/sheets_r11c")
            out_dir.mkdir(parents=True, exist_ok=True)
            gp = lab.job_generator_params(lab.state.graph)
            cat = BeltCatalog.from_dict(gp["belt_catalog"])
            gdef = genome_definition("feral_calf")
            for item in opts["cands"].split(","):
                cid, label = item.split(":", 1) if ":" in item else (item, item)
                run_id = cid.rsplit("-g", 1)[0]
                c = next(x for x in lab.registry.list_candidates(run_id) if x["id"] == cid)
                vals = gdef.complete(c["genome"]["values"])
                d = build_design(Genome(definition="feral_calf", version=gdef.version, values=vals), [], "feral_calf", gp)
                _why, srep = spring_checks(d.spec, vals, SpringSpace())
                slug = "".join(ch if ch.isalnum() else "_" for ch in label).strip("_")
                (out_dir / f"{slug}_geometry.csv").write_bytes(geometry_csv(geometry_rows(d.spec, vals)).encode())
                parts = parts_list(d.spec, vals, cat, srep, library())
                parts["candidate"], parts["label"] = cid, label
                (out_dir / f"{slug}_parts.json").write_bytes(json.dumps(parts, indent=1).encode())
                print("wrote", slug)
            return
        if stage == "summary":
            out = []
            for run_id in opts["runs"].split(","):
                for c in lab.registry.list_candidates(run_id):
                    s = (c.get("metrics") or {}).get("hardware")
                    if s:
                        out.append({"id": c["id"], "label": s.get("label"), "minutes": s["minutes_held"],
                                    "of": s["minutes_of"], "trot": s["trot_speed_mm_s"], "fastest": s["fastest_trot"],
                                    "screen": s["screen"], "cost": s["costs"]["cost_index"], "fitness": c["fitness"],
                                    "stoppers": s["stoppers"][:3], "belt_loads": s.get("belt_loads"),
                                    "springs_sim": s.get("spring_peaks_sim_n"), "mass": s["costs"]["mass_g"],
                                    "passed": s["passed_screen"], "perf": [(r["label"], r["held"]) for r in s["performances"]]})
            print(json.dumps(out, indent=1))
            return
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
