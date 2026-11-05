"""Session R6 (ADR-095): play picked cells of a behaviour-diversity run (ADR-094) as 60 s performances on the run's
three randomised seeds, with a full physics report (every limit at the run's margin, falls), and store each
performance as a run of kind ``sim`` that replays in the viewport.

For each candidate:
* the 24 s evaluation is re-run with the run's own task (``evaluate_behaviour``) and its margins compared with the
  stored ones (the replay must reproduce the run);
* each seed is played for 60 s with the same settings; the report has every constraint with its value, limit,
  margin and the joint / belt where it is worst, judged over the whole minute, over its first 24 s and over 12 s
  windows (does the minute stay within what 24 s did, or does something build up?);
* the episodes played, their shares of the minute, and the movement features (quantity of motion etc.).

Run:  python docs/studies/perform_r6.py <project dir> <run id> <out.json> [--seconds=60] [--seeds=0,1,2]
          <candidate suffix>=<label> ...
e.g.  python docs/studies/perform_r6.py projects/robot-calf-final 20261104-181642-evolve-2650 out.json \
          g011-020=calm g014-007=irregular g015-016=active
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from calflab.app.lab import Lab

SECONDS = 60.0
WINDOW_S = 12.0


def cut(ro: Any, t0: float, t1: float) -> Any:
    """The rollout between t0 and t1 (s, controller time; the settling frames before 0 are kept with the first
    window so the report sees the same start as a full rollout)."""
    keep = (ro.t < t1) & ((ro.t >= t0) | (t0 <= 0.0))
    fields = {f.name: (getattr(ro, f.name)[keep] if isinstance(getattr(ro, f.name), np.ndarray)
                       and getattr(ro, f.name).shape[:1] == ro.t.shape else getattr(ro, f.name))
              for f in dataclasses.fields(ro)}
    out = dataclasses.replace(ro, **fields)
    ft = ro.meta.get("fall_time")
    if ro.meta.get("fell") and ft is not None and not (t0 <= float(ft) < t1):
        out.meta = {**ro.meta, "fell": False, "fall_time": None}
    return out


def report(ro: Any, spec: Any, lib: Any, margin: float) -> dict[str, Any]:
    """Every constraint (value, limit, margin, where) and the closest one; falls."""
    from calflab.behave.interpret import _checks
    from calflab.evolve.safety import SafetyPolicy, safety_report
    from calflab.sim import compute_metrics

    c = _checks(spec)
    pol = SafetyPolicy(margin=margin, rated_fraction=c["rated_fraction"], sustained_fraction=c["sustained_fraction"],
                       breaking_fraction=c["breaking_fraction"])
    rep = safety_report(ro, spec, lib, pol, compute_metrics(ro))
    rows = {r["key"]: {k: r[k] for k in ("value", "limit", "margin", "violated", "unknown", "detail")}
            for r in rep["constraints"] if r["key"] != "fall"}
    known = {k: r for k, r in rows.items() if r["margin"] is not None and not r["unknown"]}
    closest = min(known, key=lambda k: known[k]["margin"]) if known else None
    fell = bool(ro.meta.get("fell"))
    return {"margin": rep["margin"], "violations": list(rep["violations"]), "fell": fell,
            "fall_time_s": ro.meta.get("fall_time"), "within": not rep["violations"] and not fell,
            "closest": closest, "closest_detail": known[closest]["detail"] if closest else "",
            "constraints": rows}


def main() -> None:
    from calflab.app.scene import build_scene
    from calflab.behave.descriptors import movement_features
    from calflab.behave.physics import compile_params
    from calflab.behave.study import randomization
    from calflab.components import library
    from calflab.design import build_design
    from calflab.evolve.diversity import evaluate_behaviour
    from calflab.fitness.preset import FitnessPreset
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins, registry
    from calflab.project.registry import RunRecord
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    proj, run_id, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    opts = dict(a[2:].split("=", 1) for a in sys.argv[4:] if a.startswith("--"))
    picks = dict(a.split("=", 1) for a in sys.argv[4:] if not a.startswith("--"))
    seconds = float(opts.get("seconds", SECONDS))
    only_seeds = [int(v) for v in opts["seeds"].split(",")] if "seeds" in opts else None
    load_plugins()
    lib = library()
    lab = Lab.open(proj, create=False)
    d = proj / "runs" / run_id
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    cands = {c["id"]: c for c in (json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x)}
    p = run["inputs"]["params"]
    margin = float(p["margin"])
    g = lab.state.graph
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    fitness = run["fitness"]["preset"]
    ev = FitnessPreset.model_validate(fitness).evaluation
    assert ev is not None
    base = {"overrides": run["overrides"], "generator": generator, "generator_params": gen_params,
            "compile": run["inputs"]["compile"], "fitness": fitness, "palette": list(p["palette"]),
            "duration_s": float(p["duration_s"]), "margin": margin,
            "unpredictability_weight": p["unpredictability_weight"], "descriptors": [p["descriptor_x"], p["descriptor_y"]],
            "cap_durations": bool(p.get("cap_durations", False))}
    copts = {**compile_params(run["inputs"]["compile"]), "randomization": randomization(ev.randomize, ev.friction, ev.mass_scale)}
    results = []
    for suffix, label in picks.items():
        cid = next(k for k in cands if k.endswith(suffix))
        cand = cands[cid]
        t = time.perf_counter()
        # 1. the run's own 24 s evaluation, re-run
        out24 = evaluate_behaviour({**base, "genome": cand["genome"], "x": cand["controller_x"]})
        stored = [(s["seed"], s["margin"]) for s in cand["metrics"]["seeds"]]
        again = [(s["seed"], s["margin"]) for s in out24["metrics"]["seeds"]]
        same_ctrl = out24["controller_params"] == cand["controller"]["params"]
        print(f"\n{label} {cid}: 24 s stored {stored}, re-run {again}, same controller {same_ctrl} "
              f"({time.perf_counter() - t:.0f} s)", flush=True)
        ctrl = out24["controller_params"]
        design = build_design(Genome.model_validate(cand["genome"]), [Override.model_validate(o) for o in run["overrides"]],
                              generator, gen_params)
        spec = design.spec
        seeds = []
        for seed in only_seeds if only_seeds is not None else ev.seeds:
            t = time.perf_counter()
            cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
            settings = SimSettings(duration_s=min(seconds, 60.0), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                                   start_pose="stand", stop_on_fall=True, seed=seed)
            # the 60 s bound is the Simulate panel's slider range, not a physics limit: a longer study play sets
            # the length after validation (ADR-097)
            settings = settings.model_copy(update={"duration_s": seconds})
            ro = run_rollout(cm, registry.get("controller", "interpreted")(ctrl), settings, lib)  # type: ignore[arg-type]
            whole = report(ro, spec, lib, margin)
            first = report(cut(ro, 0.0, 24.0), spec, lib, margin)
            windows = []
            for w0 in np.arange(0.0, seconds, WINDOW_S):
                r = report(cut(ro, float(w0), float(w0) + WINDOW_S), spec, lib, margin)
                windows.append({"t0": float(w0), "margin": r["margin"], "closest": r["closest"], "within": r["within"]})
            eps = [e for e in ((ro.meta.get("controller_log") or {}).get("episodes") or []) if isinstance(e, dict)]
            end = float(ro.t[-1])
            share: Counter[str] = Counter()
            for e in eps:
                share[e["name"]] += max(0.0, float(e.get("t1", end)) - float(e["t0"]))
            mv = movement_features(ro, spec)
            desc = {k: float(registry.get("behavior_descriptor", k)().describe_candidate(  # type: ignore[attr-defined]
                spec, {"movement": mv}, ctrl)) for k in base["descriptors"]}
            # 2. store it as a run that replays in the viewport
            sim_id = lab.registry.new_run_id("sim")
            rdir = lab.registry.run_dir(sim_id)
            ro.save(rdir / "rollout.npz")
            (rdir / "scene.json").write_text(json.dumps(build_scene(design, lab.state.layers, lab.state.settings)),
                                             encoding="utf-8")
            title = f"{opts.get('tag', 'R6')} {label} {tuple(cand['cell'] or [])} {suffix}: {seconds:.0f} s, seed {seed}"
            lab.registry.save_run(RunRecord(
                id=sim_id, kind="sim", title=title, duration_s=time.perf_counter() - t, seed=seed, backend="local",
                inputs={"source": {"run": run_id, "candidate": cid, "label": label}, "seconds": seconds,
                        "compile": copts, "margin": margin, "report": whole, "first_24_s": first, "windows": windows},
                genome=cand["genome"], overrides=run["overrides"],
                controller={"key": "interpreted", "params": ctrl},
                metrics={"within_limits": whole["within"], "safety_margin": whole["margin"], "closest": whole["closest"],
                         "fell": whole["fell"], "movement": mv, "descriptors": desc},
                artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
                parent=run_id, tags=[opts.get("tag", "R6"), label]))
            lab.bus.emit("runs.changed", run_id=sim_id)
            seq = [e["name"] for e in eps]
            print(f"  seed {seed}: {seconds:.0f} s margin {whole['margin']:+.3f} closest {whole['closest']} "
                  f"({whole['closest_detail']}) within {whole['within']} fell {whole['fell']}; first 24 s "
                  f"{first['margin']:+.3f}; windows {[round(w['margin'], 3) for w in windows]}; "
                  f"{len(eps)} episodes; desc {({k: round(v, 2) for k, v in desc.items()})}; run {sim_id} "
                  f"({time.perf_counter() - t:.0f} s)", flush=True)
            print(f"     {' > '.join(seq)}", flush=True)
            seeds.append({"seed": seed, "run": sim_id, "report": whole, "first_24_s": first, "windows": windows,
                          "episodes": eps, "share_s": dict(share), "movement": mv, "descriptors": desc})
        results.append({"label": label, "candidate": cid, "cell": cand["cell"], "stored_24": stored, "rerun_24": again,
                        "rerun_24_same_controller": same_ctrl, "descriptors_24": cand["descriptors"],
                        "controller": ctrl, "seeds": seeds})
    outp.write_text(json.dumps(results, indent=1, default=float), encoding="utf-8")
    lab.close()


if __name__ == "__main__":
    main()
