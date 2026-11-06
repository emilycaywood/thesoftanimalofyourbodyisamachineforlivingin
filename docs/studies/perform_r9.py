"""Session R9 (ADR-100): play R6c's and R7's safe behaviours on a what-if body (new servos, optionally pulleys) for
60 s on the run's three randomised seeds, judged as ``perform_r6.py`` judges them, and store each as a run of kind
``sim`` titled ``R9 what-if ...`` that replays in the viewport.

The body is the working one changed in memory as in ``servos_r9.py`` (the document is not changed). The scene stored
with each run is built from that what-if spec, so the Mass tab of the replay shows the new servos. The controller
is the candidate's stored one (``perform_r6.py`` showed the re-run reproduces it).

Run:  python docs/studies/perform_r9.py <project dir> <out.json> "<case>" [--seconds=60] [--seeds=0,1,2]
          [--workers=7] <run id>:<candidate suffix>=<label> ...
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def play(spec_json: str, copts: dict[str, Any], ctrl: dict[str, Any], seed: int, seconds: float,
         margin: float) -> dict[str, Any]:
    """One performance (in a worker): the rollout file and the report over the whole play, its first 24 s and 12 s
    windows."""
    import tempfile

    import numpy as np
    from calflab.behave.descriptors import movement_features
    from calflab.components import library
    from calflab.model.spec import RobotSpec
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout
    from perform_r6 import WINDOW_S, cut, report

    load_plugins()
    lib = library()
    spec = RobotSpec.model_validate_json(spec_json)
    t = time.perf_counter()
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
    settings = SimSettings(duration_s=60.0, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                           stop_on_fall=True, seed=seed).model_copy(update={"duration_s": seconds})
    ro = run_rollout(cm, registry.get("controller", "interpreted")(ctrl), settings, lib)  # type: ignore[arg-type]
    whole = report(ro, spec, lib, margin)
    first = report(cut(ro, 0.0, 24.0), spec, lib, margin)
    windows = []
    for w0 in np.arange(0.0, seconds, WINDOW_S):
        r = report(cut(ro, float(w0), float(w0) + WINDOW_S), spec, lib, margin)
        windows.append({"t0": float(w0), "margin": r["margin"], "closest": r["closest"], "within": r["within"]})
    eps = [e for e in ((ro.meta.get("controller_log") or {}).get("episodes") or []) if isinstance(e, dict)]
    path = Path(tempfile.mkdtemp()) / "rollout.npz"
    ro.save(path)
    return {"seed": seed, "report": whole, "first_24_s": first, "windows": windows, "episodes": eps,
            "movement": movement_features(ro, spec), "rollout": str(path), "wall_s": round(time.perf_counter() - t, 1)}


def main() -> None:
    import shutil

    from calflab.app.lab import Lab
    from calflab.app.scene import build_scene
    from calflab.behave.physics import compile_params
    from calflab.behave.study import randomization
    from calflab.components import library
    from calflab.design import build_design
    from calflab.fitness.preset import FitnessPreset
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins
    from calflab.project.registry import RunRecord
    from servos_r9 import parse_case, what_if

    proj, outp, case_name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[4:] if a.startswith("--"))
    picks = [a for a in sys.argv[4:] if not a.startswith("--")]
    seconds = float(opts.get("seconds", 60))
    load_plugins()
    lib = library()
    case = parse_case(case_name)
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    jobs = []
    meta: dict[str, Any] = {}
    for pick in picks:
        ref, label = pick.split("=", 1)
        run_id, suffix = ref.split(":", 1)
        d = proj / "runs" / run_id
        run = json.loads((d / "run.json").read_text(encoding="utf-8"))
        cands = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if x]
        cand = next(c for c in cands if c["id"].endswith(suffix))
        ev = FitnessPreset.model_validate(run["fitness"]["preset"]).evaluation
        assert ev is not None
        margin = float(run["inputs"]["params"]["margin"])
        copts = {**compile_params(run["inputs"]["compile"]),
                 "randomization": randomization(ev.randomize, ev.friction, ev.mass_scale)}
        design = build_design(Genome.model_validate(cand["genome"]), [Override.model_validate(o) for o in run["overrides"]],
                              generator, gen_params)
        spec = what_if(design, [Override.model_validate(o) for o in run["overrides"]], generator, gen_params, case, lib)
        scene = build_scene(dataclasses.replace(design, spec=spec), lab.state.layers, lab.state.settings)
        key = f"{run_id}:{suffix}"
        meta[key] = {"label": label, "run": run_id, "candidate": cand["id"], "cell": cand["cell"], "margin": margin,
                     "copts": copts, "ctrl": cand["controller"]["params"], "genome": cand["genome"],
                     "overrides": run["overrides"], "scene": scene, "seeds": []}
        for seed in [int(s) for s in opts.get("seeds", ",".join(str(s) for s in ev.seeds)).split(",")]:
            jobs.append((key, spec.model_dump_json(), copts, cand["controller"]["params"], seed, seconds, margin))
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 7))) as ex:
        futs = {ex.submit(play, *j[1:]): j[0] for j in jobs}
        for f in as_completed(futs):
            key = futs[f]
            r = f.result()
            m = meta[key]
            whole = r["report"]
            if opts.get("store", "1") == "0":  # report only: no run in the project
                Path(r.pop("rollout")).unlink(missing_ok=True)
                m["seeds"].append(dict(r))
                print(f"{m['label']:12s} seed {r['seed']}: margin {whole['margin']:+.3f} closest {whole['closest']} "
                      f"({whole['closest_detail']}) within {whole['within']} fell {whole['fell']} "
                      f"({r['wall_s']:.0f} s; {time.perf_counter() - t:.0f} s total)", flush=True)
                save(outp, case_name, meta)
                continue
            sim_id = lab.registry.new_run_id("sim")
            rdir = lab.registry.run_dir(sim_id)
            rdir.mkdir(parents=True, exist_ok=True)
            shutil.move(r.pop("rollout"), rdir / "rollout.npz")
            (rdir / "scene.json").write_text(json.dumps(m["scene"]), encoding="utf-8")
            title = (f"R9 what-if ({case_name}) {m['label']} {tuple(m['cell'] or [])}: {seconds:.0f} s, "
                     f"seed {r['seed']}")
            lab.registry.save_run(RunRecord(
                id=sim_id, kind="sim", title=title, duration_s=r["wall_s"], seed=r["seed"], backend="local",
                inputs={"source": {"run": m["run"], "candidate": m["candidate"], "label": m["label"]},
                        "what_if": {"case": case_name, **case, "note": "in-memory spec change; the genome and "
                                    "overrides stored here build the working body, not this one (ADR-100)"},
                        "seconds": seconds, "compile": m["copts"], "margin": m["margin"], "report": whole,
                        "first_24_s": r["first_24_s"], "windows": r["windows"]},
                genome=m["genome"], overrides=m["overrides"], controller={"key": "interpreted", "params": m["ctrl"]},
                metrics={"within_limits": whole["within"], "safety_margin": whole["margin"], "closest": whole["closest"],
                         "fell": whole["fell"], "movement": r["movement"]},
                artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
                parent=m["run"], tags=["R9", m["label"], "what-if"]))
            m["seeds"].append({k: v for k, v in r.items()} | {"run": sim_id})
            print(f"{m['label']:12s} seed {r['seed']}: margin {whole['margin']:+.3f} closest {whole['closest']} "
                  f"({whole['closest_detail']}) within {whole['within']} fell {whole['fell']}; run {sim_id} "
                  f"({r['wall_s']:.0f} s; {time.perf_counter() - t:.0f} s total)", flush=True)
            save(outp, case_name, meta)
    lab.close()


def save(outp: Path, case_name: str, meta: dict[str, Any]) -> None:
    outp.write_text(json.dumps({"case": case_name, **{k: {kk: vv for kk, vv in v.items() if kk != "scene"}
                                                      for k, v in meta.items()}}, separators=(",", ":"), default=float),
                    encoding="utf-8")


if __name__ == "__main__":
    main()
