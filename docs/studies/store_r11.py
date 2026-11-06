"""Session R11 (ADR-102): store the behaviours of chosen bodies from a hardware run as replayable runs, and print
compare.html links against today's body (the R6c / R7 runs played on it).

Each body is rebuilt from its candidate's genome (servo and belt genes included, so *Load* or *Simulate* from a stored
run gives that body; a body with a ``-whatif`` pulley pair cannot be loaded, since the project catalog does not have
that pair). Each of the preset's behaviours is played for 60 s on every seed, judged as the run judged it, and stored
as a run of kind ``sim`` titled ``R11 <label> <behaviour>: 60 s, seed N``.

Run:  python docs/studies/store_r11.py <project dir> <out.json> [--port=8020] [--workers=7] <candidate id>=<label> ...
      python docs/studies/store_r11.py <project dir> <out.json> --links-only [--port=8020]
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote


def play(payload: dict[str, Any], perf: dict[str, Any], seed: int, seconds: float, margin: float) -> dict[str, Any]:
    """One performance in a worker: the rollout file and the judged record."""
    import tempfile

    from calflab.evolve.hardware import _build, compile_options, judge_play
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    design, lib = _build(payload)
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    t = time.perf_counter()
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(copts), seed)
    settings = SimSettings(duration_s=seconds, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                           stop_on_fall=True, seed=seed)
    ctrl = perf["controller"]
    ro = run_rollout(cm, registry.get("controller", ctrl["key"])(ctrl["params"]), settings, lib)  # type: ignore[arg-type]
    rec = judge_play(ro, design.spec, lib, margin, 0.0, seconds)
    path = Path(tempfile.mkdtemp()) / "rollout.npz"
    ro.save(path)
    return {"seed": seed, "label": perf["label"], "report": rec, "rollout": str(path), "compile": copts,
            "wall_s": round(time.perf_counter() - t, 1)}


def links(proj: Path, stored: dict[str, Any], port: str) -> None:
    import sqlite3

    con = sqlite3.connect(f"file:{proj / 'index.sqlite'}?mode=ro", uri=True)
    runs = dict(con.execute("select id, title from runs"))
    today: dict[tuple[str, int], str] = {}
    for rid, title in runs.items():
        m = re.match(r"(R6c|R7) (\S+) \(.*\) \S+: 60 s, seed (\d)", title or "")
        if m:
            today[(f"{m.group(1)}-{m.group(2)}", int(m.group(3)))] = rid
    url = f"http://localhost:{port}/compare.html"
    for cid, body in stored.items():
        print(f"\n**{body['label']}** (`{cid}`)\n")
        print("| behaviour | seed | today | R11 body (margin) | link |")
        print("|---|---|---|---|---|")
        for r in sorted(body["plays"], key=lambda r: (r["label"], r["seed"])):
            a = today.get((r["label"], r["seed"]))
            if a is None:
                continue
            la, lb = quote(f"today {r['label']} s{r['seed']}"), quote(f"R11 {body['label']} {r['label']} s{r['seed']}")
            m = r["margin"]
            print(f"| {r['label']} | {r['seed']} | {a} | {r['run']} ({'within' if r['within'] else 'over'}, "
                  f"{'n/a' if m is None else f'{m:+.2f}'}) | [compare]({url}?a={a}&b={r['run']}&la={la}&lb={lb}) |")


def main() -> None:
    import shutil

    from calflab.app.lab import Lab
    from calflab.app.scene import build_scene
    from calflab.evolve.hardware import HardwareSettings, _build, catalog_with_what_ifs
    from calflab.plugins import load_plugins
    from calflab.project.registry import RunRecord

    load_plugins()
    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    port = opts.get("port") or "8020"
    stored: dict[str, Any] = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else {}
    if "links-only" in opts:
        links(proj, stored, port)
        return
    picks = dict(a.split("=", 1) for a in sys.argv[3:] if not a.startswith("--"))
    lab = Lab.open(proj, create=False)
    try:
        jobs = []
        meta: dict[str, Any] = {}
        for cid, label in picks.items():
            cand = lab.registry.get_candidate(cid)
            run = lab.registry.get_run(cand["run_id"])
            fit = run.fitness["preset"]  # type: ignore[index]
            hw = HardwareSettings.model_validate(lab.prepare_hardware(fit)["evaluation"]["hardware"])
            gp = dict(lab.job_generator_params(lab.state.graph))
            whatif = bool(run.inputs.get("params", {}).get("what_if_pulleys"))
            gp["belt_catalog"] = catalog_with_what_ifs(gp["belt_catalog"], whatif)
            payload = {"genome": cand["genome"], "overrides": run.overrides, "generator": "feral_calf",
                       "generator_params": gp, "compile": run.inputs.get("compile", {}),
                       "evaluation": fit["evaluation"]}
            design, _lib = _build(payload)
            scene = build_scene(design, lab.state.layers, lab.state.settings)
            meta[cid] = {"label": label, "payload": payload, "scene": scene, "run": cand["run_id"], "hw": hw,
                         "whatif": whatif}
            stored[cid] = {"label": label, "run": cand["run_id"], "plays": []}
            for perf in hw.performances:
                for seed in fit["evaluation"]["seeds"]:
                    jobs.append((cid, payload, perf.model_dump(mode="json"), seed, hw.performance_s, hw.margin))
        t = time.perf_counter()
        with ProcessPoolExecutor(max_workers=int(opts.get("workers") or 7)) as ex:
            futs = {ex.submit(play, *j[1:]): j[0] for j in jobs}
            for f in as_completed(futs):
                cid = futs[f]
                r = f.result()
                m = meta[cid]
                rep = r["report"]
                sim_id = lab.registry.new_run_id("sim")
                rdir = lab.registry.run_dir(sim_id)
                rdir.mkdir(parents=True, exist_ok=True)
                shutil.move(r["rollout"], rdir / "rollout.npz")
                (rdir / "scene.json").write_text(json.dumps(m["scene"]), encoding="utf-8")
                title = f"R11 {m['label']} {r['label']}: 60 s, seed {r['seed']}"
                lab.registry.save_run(RunRecord(
                    id=sim_id, kind="sim", title=title, duration_s=r["wall_s"], seed=r["seed"], backend="local",
                    inputs={"source": {"run": m["run"], "candidate": cid, "behaviour": r["label"]},
                            "hardware_run": {"what_if_pulleys": m["whatif"],
                                             "note": "genome with servo and belt genes (ADR-102)"
                                             + ("; uses a -whatif pulley pair NOT in the catalog" if m["whatif"]
                                                else "")},
                            "seconds": m["hw"].performance_s, "compile": r["compile"], "margin": m["hw"].margin,
                            "report": {k: v for k, v in rep.items() if k != "joints"}, "joints": rep["joints"]},
                    genome=m["payload"]["genome"], overrides=m["payload"]["overrides"],
                    controller=next(p.controller for p in m["hw"].performances if p.label == r["label"]),
                    metrics={"within_limits": rep["within"], "safety_margin": rep["margin"], "closest": rep["closest"],
                             "fell": rep["fell"]},
                    artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
                    parent=m["run"], tags=["R11", m["label"], r["label"]]))
                stored[cid]["plays"].append({"label": r["label"], "seed": r["seed"], "run": sim_id,
                                             "within": rep["within"], "margin": rep["margin"],
                                             "closest": rep["closest"]})
                print(f"{m['label']:24s} {r['label']:14s} seed {r['seed']}: {'within' if rep['within'] else 'OVER  '} "
                      f"{rep['margin']} {rep['closest']}; run {sim_id} ({time.perf_counter() - t:.0f} s)", flush=True)
                outp.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    finally:
        lab.close()
    links(proj, stored, port)


if __name__ == "__main__":
    main()
