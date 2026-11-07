"""Session R12 / Stage C (ADR-105): a fairness check on the R11c-B front. Every body gets behaviours evolved for it.

Stage B (run ``20261107-043030-evolve-c02e``) judged each body with R6c's and R7's 11 behaviours, which were evolved
for today's working body. Here each of the five named front bodies, and the working body for the same treatment, gets
its own behaviour-diversity run (``map_elites_behaviour``: coverage, capped durations, variation within a movement,
``variation_weight`` 0.5; R7's settings, ADR-098), seeded from R7's eleven safe generators (run
``20261105-232649-evolve-4237``). The run starts from the stored candidate's body (``run_evolve(candidate=...)``); the
project document is never changed. Then the safe cells of each run are judged with the R11c suite: the Stage B run's
own preset (``hardware_r11c``: seeds 0-2, friction 0.7-1.1, mass x0.95-1.05, margin 0.2, torque-speed servos), its
screen (trot grid, walk, turn, lie_rise; replayed from the play cache, which proves the body is the one Stage B judged)
and each new behaviour played for 60 s on every seed, summarised by ``calflab.evolve.hardware.summarise``.

Stages:

* ``evolve <body> ...``: one diversity run per body (``working`` or a Stage B candidate suffix); ``--generations``
  (15) ``--batch`` (28) ``--seed`` (0). Runs are titled ``R12 Stage C <body>``.
* ``judge``: every body's latest finished ``R12 Stage C`` run -> ``docs/studies/stagec_r12.json`` (``--workers`` 7).
* ``report``: markdown tables from that JSON.

Run:  python docs/studies/stagec_r12.py <project dir> evolve|judge|report [args]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

R7_RUN = "20261105-232649-evolve-4237"
B_RUN = "20261107-043030-evolve-c02e"
BODIES = ["working", "g020-008-r01", "g012-009", "g011-003", "g009-000", "g007-002"]
TITLE = "R12 Stage C "  # ``--prefix=`` for trials
OUT = Path("docs/studies/stagec_r12.json")


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
        time.sleep(15)


def r7_safe(lab: Any) -> list[dict[str, Any]]:
    """R7's safe generators: every candidate of run 4237 within every limit (11)."""
    return [c for c in lab.registry.list_candidates(R7_RUN) if (c.get("metrics") or {}).get("within_limits")]


def b_candidate(lab: Any, body: str) -> dict[str, Any] | None:
    """The Stage B candidate of a body (the working body is Stage B's ``working body`` seed)."""
    cands = lab.registry.list_candidates(B_RUN)
    if body == "working":
        return next((c for c in cands if ((c.get("metrics") or {}).get("hardware") or {}).get("label") == "working body"),
                    None)
    return next(c for c in cands if c["id"].endswith(body))


def evolve(lab: Any, bodies: list[str], opts: dict[str, str]) -> None:
    r7 = lab.registry.get_run(R7_RUN)
    params = dict(r7.inputs["params"])
    params.update({"start_vectors": [list(c["controller_x"]) for c in r7_safe(lab)],
                   "generations": int(opts.get("generations", 15)), "batch_size": int(opts.get("batch", 28)),
                   "seed": int(opts.get("seed", 0))})
    for body in bodies:
        cid = None if body == "working" else b_candidate(lab, body)["id"]  # type: ignore[index]
        t0 = time.time()
        job = lab.run_evolve("map_elites_behaviour", params, None, None, None, "diversity", candidate=cid)
        rid = (job.result or {}).get("run_id")
        print("run", rid, body, cid, flush=True)
        j = wait(lab, job)
        rid = (j.result or {}).get("run_id") or rid
        rec = lab.registry.get_run(rid)
        rec.title = f"{TITLE}{body}"
        rec.tags = sorted(set(rec.tags) | {"R12", "stage-c", body})
        lab.registry.save_run(rec)
        print(j.status, getattr(j, "error", None), f"{time.time() - t0:.0f} s", flush=True)


def stage_c_runs(lab: Any) -> dict[str, str]:
    out: dict[str, tuple[str, str]] = {}
    for r in lab.registry.list_runs("evolve"):
        rec = lab.registry.get_run(r["id"])
        if not rec.title.startswith(TITLE) or rec.status != "done":
            continue
        body = rec.title[len(TITLE):]
        if body not in out or rec.id > out[body][0]:
            out[body] = (rec.id, body)
    return {b: v[0] for b, v in out.items()}


# ---------------------------------------------------------------------------------------------------- workers
def perform(payload: dict[str, Any]) -> dict[str, Any]:
    """One new behaviour for 60 s on every seed of the R11c suite: ``perform_task``'s record plus the movement
    features of each minute (quantity of motion, ...)."""
    from calflab.behave.descriptors import movement_features
    from calflab.evolve.hardware import HardwareSettings, _build, compile_options, judge_play
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    design, lib = _build(payload)
    hw = HardwareSettings.model_validate(payload["hardware"])
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    perf = payload["perf"]
    seeds = []
    for seed in list(ev.seeds) or [0]:
        cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(copts), seed)
        settings = SimSettings(duration_s=hw.performance_s, control_hz=50.0, record_hz=50.0, settle_s=0.4,
                               start_pose="stand", stop_on_fall=True, seed=seed)
        ctrl = perf["controller"]
        ro = run_rollout(cm, registry.get("controller", ctrl["key"])(ctrl["params"]), settings, lib)  # type: ignore[arg-type]
        rec = judge_play(ro, design.spec, lib, hw.margin, 0.0, hw.performance_s)
        mv = movement_features(ro, design.spec)
        rec["movement"] = {k: v for k, v in mv.items() if isinstance(v, int | float)}
        rec["played_s"] = round(float(ro.t[-1]), 2) if len(ro.t) else 0.0
        eps = [e for e in ((ro.meta.get("controller_log") or {}).get("episodes") or []) if isinstance(e, dict)]
        rec["states"] = sorted({str(e.get("name")) for e in eps})
        seeds.append({"seed": seed, **rec})
    return {"body": payload["body"], "label": perf["label"], "seeds": seeds}


def screen(payload: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.hardware import screen_task

    out = screen_task(payload)
    out["body"] = payload["body"]
    return out


def judge(lab: Any, opts: dict[str, str]) -> None:
    from calflab.design import genome_definition
    from calflab.evolve.hardware import (
        HardwareSettings,
        Performance,
        baseline_of,
        catalog_with_what_ifs,
        summarise,
    )

    runs = stage_c_runs(lab)
    brun = lab.registry.get_run(B_RUN)
    preset = brun.fitness["preset"]
    ev = preset["evaluation"]
    hw0 = HardwareSettings.model_validate(ev["hardware"])
    hw0.cache_dir = str(Path(lab.project.path) / ".cache" / "hardware")
    gdef = genome_definition("feral_calf")
    # the Stage B run's start (the working body) for the cost baseline, as the optimizer sets it
    start_vals = gdef.complete(brun.genome["values"])
    bg = lab.variant_graph(start_vals)
    for role, key in (("model", "compile"), ("design", "generator_params")):
        bg.role(role).params = {k: v for k, v in brun.inputs[key].items() if k != "belt_catalog"}
    gp_b = lab.job_generator_params(bg)
    gp_b["belt_catalog"] = catalog_with_what_ifs(gp_b["belt_catalog"], False)
    hw0.baseline = baseline_of(lab.design(bg, []).spec, start_vals)
    bodies: dict[str, dict[str, Any]] = {}
    screens, perfs = [], []
    for body in BODIES:
        if body not in runs:
            print("no finished run for", body)
            continue
        rid = runs[body]
        run = lab.registry.get_run(rid)
        cands = {c["id"]: c for c in lab.registry.list_candidates(rid)}
        arch = json.loads((lab.registry.run_dir(rid) / "archive.json").read_text(encoding="utf-8"))
        safe_cells = [c for c in arch["archive"]["cells"] if c.get("within_limits")]
        safe_all = [c for c in cands.values() if (c.get("metrics") or {}).get("within_limits")]
        bc = b_candidate(lab, body)
        values = gdef.complete(run.genome["values"])
        common = {"body": body, "genome": {"definition": gdef.name, "version": gdef.version, "values": values},
                  "overrides": run.overrides, "generator": "feral_calf", "generator_params": gp_b,
                  "compile": brun.inputs["compile"], "evaluation": ev}
        new_perfs = []
        for cell in safe_cells:
            c = cands[cell["candidate"]]
            d = c["descriptors"]
            label = f"{c['id'].rsplit('-', 2)[-2]}-{c['id'].rsplit('-', 1)[-1]} q{d['quantity_of_motion']:.1f}"
            new_perfs.append({"label": label, "ref": f"{rid}:{c['id'].split(rid + '-')[-1]}",
                              "controller": c["controller"]})
        hw = hw0.model_copy(deep=True)
        hw.performances = [Performance(**p) for p in new_perfs]
        payload_hw = hw.model_dump(mode="json")
        screens.append({**common, "hardware": payload_hw})
        perfs += [{**common, "hardware": payload_hw, "perf": p} for p in new_perfs]
        hist = arch.get("history") or []
        bodies[body] = {"run": rid, "candidate": None if bc is None else bc["id"], "safe_cells": len(safe_cells),
                        "safe_candidates": len(safe_all), "evaluated": len(cands),
                        "coverage": hist[-1]["coverage"] if hist else None, "history": hist,
                        "cells": [{"candidate": c["candidate"], "cell": cands[c["candidate"]].get("cell"),
                                   "descriptors": cands[c["candidate"]]["descriptors"],
                                   "fitness": cands[c["candidate"]]["fitness"],
                                   "variation": (cands[c["candidate"]].get("fitness_terms") or {}).get("variation"),
                                   "unpredictability": (cands[c["candidate"]].get("fitness_terms") or {}).get(
                                       "unpredictability")} for c in safe_cells],
                        "stage_b": None if bc is None else {
                            k: bc["metrics"]["hardware"][k] for k in ("minutes_held", "minutes_of", "trot_speed_mm_s",
                                                                       "fastest_trot", "screen", "costs", "headroom")},
                        "_hw": payload_hw}
    print(f"{len(screens)} screens, {len(perfs)} behaviours x 3 seeds", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(int(opts.get("workers", 7))) as pool:
        sc = list(pool.map(screen, screens))
        print(f"screens done {time.time() - t0:.0f} s; evals {[s.get('evals') for s in sc]}", flush=True)
        pf = list(pool.map(perform, perfs))
    print(f"behaviours done {time.time() - t0:.0f} s", flush=True)
    for s in sc:
        b = bodies[s["body"]]
        mine = [p for p in pf if p["body"] == s["body"]]
        hw = HardwareSettings.model_validate(b.pop("_hw"))
        summ = summarise(s, mine, hw, len(ev["seeds"]))
        b["screen_evals"], b["screen_cache_hits"] = s.get("evals"), s.get("cache_hits")
        b["summary"] = summ
        b["behaviours"] = [{"label": p["label"], "seeds": [
            {k: x.get(k) for k in ("seed", "within", "fell", "margin", "closest", "violations", "played_s", "states")}
            | {"qom": x["movement"].get("quantity_of_motion_deg_s"), "regularity": x["movement"].get("tempo_regularity"),
               "stillness": x["movement"].get("stillness_ratio")} for x in p["seeds"]]} for p in mine]
    OUT.write_bytes(json.dumps({"stage_b_run": B_RUN, "r7_run": R7_RUN, "bodies": bodies}, indent=1,
                               default=float).encode())
    print("wrote", OUT, flush=True)


def report() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))["bodies"]
    print("| body | safe cells | behaviours held 3/3 | minutes | trot mm/s | lie_rise | walk | turn | qom held (min-max) |"
          " cost | Stage B minutes |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for body, b in data.items():
        s = b["summary"]
        held3 = sum(1 for r in s["performances"] if r["held"] == r["of"])
        q = [x["qom"] for r in b["behaviours"] for x in r["seeds"] if x["within"] and x["qom"] is not None]
        sb = b["stage_b"] or {}
        print(f"| {body} | {b['safe_cells']} | {held3} | {s['minutes_held']}/{s['minutes_of']} | "
              f"{s['trot_speed_mm_s']:.0f} | {_m(s['screen'].get('lie_rise'))} | {_m(s['screen'].get('walk'))} | "
              f"{_m(s['screen'].get('turn'))} | {min(q, default=0):.1f}-{max(q, default=0):.1f} | "
              f"{s['costs']['cost_index']:.2f} | {sb.get('minutes_held')}/{sb.get('minutes_of')} |")


def _m(row: dict[str, Any] | None) -> str:
    v = (row or {}).get("worst_margin")
    return "-" if v is None else f"{v:+.2f}"


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj, stage = Path(sys.argv[1]), sys.argv[2]
    args = [a for a in sys.argv[3:] if not a.startswith("--")]
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    global TITLE, OUT
    if opts.get("prefix"):
        TITLE = opts["prefix"].rstrip() + " "
        OUT = OUT.with_name(OUT.stem + "_" + "".join(ch for ch in TITLE.strip() if ch.isalnum()) + ".json")
    if stage == "report":
        report()
        return
    load_plugins()
    lab = Lab.open(proj, create=False)
    try:
        if stage == "evolve":
            evolve(lab, args or BODIES, opts)
        elif stage == "judge":
            judge(lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
