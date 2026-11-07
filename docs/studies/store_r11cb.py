"""Session R11c-B: store replayable runs of a series of bodies from a hardware run (e.g. the best body's ancestors), so
they can be watched side by side with ``compare.html?runs=<id>,<id>,...``.

Each body is rebuilt from its candidate's genome and plays the chosen screen plays (``lie_rise``, ``trot 0.4/2``, ...)
and performances (``R7-lively``, ...) on one seed, judged as the run judged it, and stored as a run of kind ``sim``
titled ``R11c-B <label> <play>: seed N``. The project document is never changed.

Run:  python docs/studies/store_r11cb.py <project dir> <out.json> --plays=lie_rise,trot 0.4/2,R7-lively [--seed=0]
          [--port=8020] [--workers=7] <candidate id>=<label> ...
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote


def play(payload: dict[str, Any], item: dict[str, Any], seed: int, seconds: float, margin: float) -> dict[str, Any]:
    """One play in a worker: a screen play (primitive) or a performance; the rollout file and the judged record."""
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
    if item["kind"] == "screen":
        from calflab.behave.interpret import InterpretSettings

        prim = registry.get("motion_primitive", item["primitive"])(item["params"])  # type: ignore[call-arg]
        s = InterpretSettings(margin=margin, seed=seed)
        key, params = prim.controller(design.spec, lib)  # type: ignore[attr-defined]
        off, per = float(prim.warmup_s()), float(prim.period_s())  # type: ignore[attr-defined]
        length = per if prim.one_shot else s.cycles * per  # type: ignore[attr-defined]
        t0, t1 = off, off + min(max(length, s.min_play_s), s.max_play_s)
        ctrl = {"key": key, "params": params}
        duration = round(t1 + 0.3, 3)
    else:
        ctrl = item["controller"]
        t0, t1, duration = 0.0, seconds, seconds
    settings = SimSettings(duration_s=duration, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                           stop_on_fall=False, seed=seed)
    ro = run_rollout(cm, registry.get("controller", ctrl["key"])(ctrl["params"]), settings, lib)  # type: ignore[arg-type]
    rec = judge_play(ro, design.spec, lib, margin, t0, t1)
    path = Path(tempfile.mkdtemp()) / "rollout.npz"
    ro.save(path)
    return {"label": item["label"], "report": rec, "rollout": str(path), "compile": copts, "controller": ctrl,
            "wall_s": round(time.perf_counter() - t, 1)}


def links(stored: dict[str, Any], order: list[str], port: str) -> None:
    url = f"http://localhost:{port}/compare.html"
    labels = sorted({p["label"] for b in stored.values() for p in b["plays"]})
    for lab_ in labels:
        ids, names = [], []
        for cid in order:
            r = next((p for p in stored[cid]["plays"] if p["label"] == lab_), None)
            if r:
                ids.append(r["run"])
                m = r["margin"]
                names.append(f"{stored[cid]['label']} ({'within' if r['within'] else 'over'} "
                             f"{'n/a' if m is None else f'{m:+.2f}'})")
        print(f"* **{lab_}**: [side by side]({url}?runs={','.join(ids)}&labels={quote('|'.join(names))})")


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.app.scene import build_scene
    from calflab.evolve.hardware import HardwareSettings, _build, catalog_with_what_ifs, screen_plays
    from calflab.plugins import load_plugins
    from calflab.project.registry import RunRecord

    load_plugins()
    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    port, seed = opts.get("port") or "8020", int(opts.get("seed") or 0)
    wanted = [p.strip() for p in (opts.get("plays") or "lie_rise").split(",")]
    stored: dict[str, Any] = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else {}
    picks = dict(a.split("=", 1) for a in sys.argv[3:] if not a.startswith("--"))
    lab = Lab.open(proj, create=False)
    try:
        jobs, meta = [], {}
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
            meta[cid] = {"label": label, "payload": payload, "scene": build_scene(design, lab.state.layers,
                                                                                    lab.state.settings),
                         "run": cand["run_id"], "hw": hw}
            stored[cid] = {"label": label, "run": cand["run_id"], "plays": []}
            screens = {p["key"]: p for p in screen_plays(hw)}
            perfs = {p.label: p for p in hw.performances}
            for w in wanted:
                if w in screens:
                    item = {"kind": "screen", "label": w, **screens[w]}
                elif w in perfs:
                    item = {"kind": "performance", "label": w,
                            "controller": perfs[w].model_dump(mode="json")["controller"]}
                else:
                    raise SystemExit(f"unknown play {w!r}; screen: {list(screens)}; performances: {list(perfs)}")
                jobs.append((cid, payload, item, seed, hw.performance_s, hw.margin))
        t = time.perf_counter()
        with ProcessPoolExecutor(max_workers=int(opts.get("workers") or 7)) as ex:
            futs = {ex.submit(play, *j[1:]): j[0] for j in jobs}
            for f in as_completed(futs):
                cid = futs[f]
                r, m = f.result(), meta[futs[f]]
                rep = r["report"]
                sim_id = lab.registry.new_run_id("sim")
                rdir = lab.registry.run_dir(sim_id)
                rdir.mkdir(parents=True, exist_ok=True)
                shutil.move(r["rollout"], rdir / "rollout.npz")
                (rdir / "scene.json").write_text(json.dumps(m["scene"]), encoding="utf-8")
                lab.registry.save_run(RunRecord(
                    id=sim_id, kind="sim", title=f"R11c-B {m['label']} {r['label']}: seed {seed}",
                    duration_s=r["wall_s"], seed=seed, backend="local",
                    inputs={"source": {"run": m["run"], "candidate": cid, "play": r["label"]},
                            "compile": r["compile"], "margin": m["hw"].margin,
                            "report": {k: v for k, v in rep.items() if k != "joints"}, "joints": rep["joints"]},
                    genome=m["payload"]["genome"], overrides=m["payload"]["overrides"], controller=r["controller"],
                    metrics={"within_limits": rep["within"], "safety_margin": rep["margin"], "closest": rep["closest"],
                             "fell": rep["fell"]},
                    artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
                    parent=m["run"], tags=["R11c-B", m["label"], r["label"]]))
                stored[cid]["plays"].append({"label": r["label"], "seed": seed, "run": sim_id, "within": rep["within"],
                                             "margin": rep["margin"], "closest": rep["closest"]})
                print(f"{m['label']:28s} {r['label']:12s}: {'within' if rep['within'] else 'OVER  '} {rep['margin']} "
                      f"{rep['closest']}; run {sim_id} ({time.perf_counter() - t:.0f} s)", flush=True)
                outp.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    finally:
        lab.close()
    links(stored, list(picks), port)


if __name__ == "__main__":
    main()
