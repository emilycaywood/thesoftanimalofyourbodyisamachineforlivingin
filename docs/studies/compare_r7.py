"""Session R7 (ADR-098): compare two behaviour-diversity runs and their one-minute performances.

* the archives: candidates, how many passed their seeds, safe cells, the safe region (quantity of motion, tempo
  regularity, unpredictability, margin), what stopped the rest;
* the performances (runs of kind ``sim`` whose parent is the run, as ``perform_r6.py`` stores them): within the
  limits, closest limit, the movement features, and two measures of movement *within* a state:
  * **repeat dissimilarity**: for every two episodes of the same state on one seed, the RMS difference of their
    joint angles over the first 2 s after the cross-fade (deg), over the RMS of the movement itself (deg about
    the episode's mean); 0 = the second play repeats the first exactly;
  * **posture spread**: the standard deviation of the trunk height (mm) and of its roll and pitch (deg) while
    standing or shifting (stand / shift / step episodes).

Run:  python docs/studies/compare_r7.py <project dir> <run A> <run B> <out.json>
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np


def archive(proj: Path, run_id: str) -> dict[str, Any]:
    d = proj / "runs" / run_id
    cands = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x]
    arch = json.loads((d / "archive.json").read_text(encoding="utf-8"))
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    passed = [c for c in cands if all(s["within"] for s in (c.get("metrics") or {}).get("seeds", [{"within": False}]))]
    safe_cells = [c for c in arch.get("cells", []) if c.get("within_limits")]
    stops: Counter[str] = Counter()
    for c in cands:
        for r in (c.get("error") or "").split("; "):
            for v in r.split(": ", 1)[-1].split(", "):
                if v and not v.startswith("seed"):
                    stops[v] += 1
    by_id = {c["id"]: c for c in cands}
    cells = []
    for c in safe_cells:
        m = by_id[c["candidate"]]["metrics"]
        cells.append({"cell": c.get("index") or c.get("cell"), "candidate": c["candidate"],
                      "qom": round(m["movement"].get("quantity_of_motion_deg_s", 0.0), 2),
                      "regularity": round(m["movement"].get("tempo_regularity", 0.0), 2),
                      "unpredictability": m.get("unpredictability"), "margin": m.get("safety_margin"),
                      "states": m.get("states_played"),
                      "within": (m.get("generator") or {}).get("within")})
    return {"run": run_id, "duration_s": run.get("duration_s"), "candidates": len(cands), "passed_seeds": len(passed),
            "safe_cells": len(safe_cells), "cells": cells, "stops": dict(stops.most_common(6))}


def _angles(ro: Any) -> np.ndarray:
    aj = list(ro.meta.get("actuator_joint") or [])
    cols = [ro.joint_ids.index(j) for j in aj if j in ro.joint_ids] or list(range(ro.q.shape[1]))
    return np.degrees(ro.q[:, cols].astype(float))


def within_measures(ro: Any, spec: Any, ctrl: dict[str, Any]) -> dict[str, Any]:
    eps = [e for e in ((ro.meta.get("controller_log") or {}).get("episodes") or []) if isinstance(e, dict)]
    q = _angles(ro)
    t = ro.t
    blend = float(ctrl.get("blend_s", 0.6))
    win = 2.0
    segs: dict[str, list[np.ndarray]] = {}
    for e in eps:
        t0 = float(e["t0"]) + float(e.get("blend_s", blend))
        t1 = float(e.get("t1", t[-1]))
        if t1 - t0 < win:
            continue
        m = (t >= t0) & (t < t0 + win)
        segs.setdefault(e["name"], []).append(q[m])
    dis = {}
    for name, ss in segs.items():
        vals = []
        for a, b in combinations(ss, 2):
            n = min(len(a), len(b))
            if n < 10:
                continue
            a, b = a[:n], b[:n]
            amp = math.sqrt(0.5 * (np.mean((a - a.mean(0)) ** 2) + np.mean((b - b.mean(0)) ** 2)))
            vals.append(float(np.sqrt(np.mean((a - b) ** 2)) / max(amp, 0.5)))
        if vals:
            dis[name] = round(float(np.mean(vals)), 3)
    trunk = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
    still = np.zeros(len(t), dtype=bool)
    for e in eps:
        if e["name"].startswith(("stand", "shift", "step")):
            still |= (t >= float(e["t0"])) & (t < float(e.get("t1", t[-1])))
    still &= t >= 0
    out: dict[str, Any] = {"repeat_dissimilarity": dis,
                           "repeat_dissimilarity_mean": round(float(np.mean(list(dis.values()))), 3) if dis else None}
    if still.sum() > 10:
        z = ro.body_pos[still, trunk, 2] * 1000.0
        qq = ro.body_quat[still, trunk]
        w, x, y, zq = qq[:, 0], qq[:, 1], qq[:, 2], qq[:, 3]
        roll = np.degrees(np.arctan2(2 * (w * x + y * zq), 1 - 2 * (x * x + y * y)))
        pitch = np.degrees(np.arcsin(np.clip(2 * (w * y - zq * x), -1, 1)))
        out.update(height_sd_mm=round(float(z.std()), 2), roll_sd_deg=round(float(roll.std()), 3),
                   pitch_sd_deg=round(float(pitch.std()), 3), still_share=round(float(still.mean()), 3))
    return out


def performances(proj: Path, run_id: str, lab: Any) -> list[dict[str, Any]]:
    from calflab.design import build_design
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.sim.rollout import Rollout

    out = []
    for r in lab.registry.list_runs("sim", limit=2000):
        rec = lab.registry.get_run(r["id"])
        if rec.parent != run_id or float((rec.inputs or {}).get("seconds", 0)) != 60.0:
            continue
        ro = Rollout.load(proj / rec.artifacts["rollout"])
        spec = build_design(Genome.model_validate(rec.genome), [Override.model_validate(o) for o in rec.overrides],
                            "feral_calf", None).spec
        ctrl = rec.controller["params"]
        mv = rec.metrics.get("movement") or {}
        out.append({"sim": rec.id, "title": rec.title, "label": rec.inputs["source"]["label"], "seed": rec.seed,
                    "within": rec.metrics.get("within_limits"), "margin": rec.metrics.get("safety_margin"),
                    "closest": rec.metrics.get("closest"),
                    "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in mv.items() if k != "note"},
                    **within_measures(ro, spec, ctrl)})
    return sorted(out, key=lambda x: (x["label"], x["seed"]))


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    load_plugins()
    proj, a, b, outp = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    lab = Lab.open(proj, create=False)
    res = {k: {"archive": archive(proj, r), "performances": performances(proj, r, lab)} for k, r in (("A", a), ("B", b))}
    lab.close()
    outp.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    for k, v in res.items():
        ar = v["archive"]
        print(f"{k} {ar['run']}: {ar['candidates']} candidates, {ar['passed_seeds']} passed seeds, "
              f"{ar['safe_cells']} safe cells; stops {ar['stops']}")
        for c in ar["cells"]:
            print(f"   {c['cell']} {c['candidate'][-8:]} QoM {c['qom']} reg {c['regularity']} margin {c['margin']}")
        for p in v["performances"]:
            f = p["features"]
            print(f"   {p['label']:10s} s{p['seed']} within {p['within']} {p['margin']:+.3f} {p['closest']}; "
                  f"QoM {f.get('quantity_of_motion_deg_s')} reg {f.get('tempo_regularity')} jerk {f.get('jerk_rms_deg_s3')}"
                  f" range {f.get('expressive_range_deg_s')}; repeat {p['repeat_dissimilarity_mean']} "
                  f"h_sd {p.get('height_sd_mm')} roll_sd {p.get('roll_sd_deg')} pitch_sd {p.get('pitch_sd_deg')}")


if __name__ == "__main__":
    main()
