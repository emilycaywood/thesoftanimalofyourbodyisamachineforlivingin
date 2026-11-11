"""Session R15 (ADR-110): behaviours from their outcome, searched per body; a pilot on two bodies.

Stages:

* ``pilot``: for each body (``--bodies``, default g007-002 and g012-009) and behaviour (``--behaviours``, default
  stand, suckle, trot, lie), ``calflab.evolve.outcomes.optimise`` with the pilot's spaces and warm starts, at
  ``mass_model`` = ``--model`` (default explicit_v2). The searches run side by side, sharing one process pool
  (``--workers``). Writes ``docs/studies/outcomes_r15.json``; the plays are cached in
  ``<project>/.cache/outcomes``.
* ``store``: each body's best version of each behaviour played once more on seed 0 at the judging length and saved as
  a ``sim`` run (``R15 <body> <behaviour>: seed 0``) to watch in Journal > Runs.
* ``report``: markdown tables from the JSON (``outcomes_r15_tables.md``).
* ``estimate``: the joint body-and-behaviour search at three budgets, from the measured play times.

Run:  python docs/studies/outcomes_r15.py <project dir> pilot|store|report|estimate [--workers=14] [--pop=12]
      [--gens=20] [--model=explicit_v2] [--bodies=g007-002,g012-009] [--behaviours=stand,suckle,trot,lie]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path("docs/studies/outcomes_r15.json")
TABLES = Path("docs/studies/outcomes_r15_tables.md")
LIERISE = Path("docs/studies/lierise_r13.json")
BODIES = ["g007-002", "g012-009"]
BEHAVIOURS = ["stand", "suckle", "trot", "lie"]
#: a gate only that behaviour's records carry (to sort cached plays by behaviour)
GATE_OF = {"suckle": "pressing", "trot": "useful_speed", "stand": "standing", "lie": "lay_down"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def payloads(lab: Any, bodies: list[str], model: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per body the worker payload of R13/R14 (Stage C run's genome, Stage B's generator and compile settings) with
    ``mass_model`` = ``model``."""
    from lierise_r13 import body_payloads

    out, ev = body_payloads(lab, bodies)
    for p in out.values():
        p["genome"]["values"] = {**p["genome"]["values"], "mass_model": model}
    return out, ev


def lie_versions(body: str) -> list[dict[str, Any]]:
    """R13's evolved lie_rise for this body (feral_motion params), and its lying-pose version if any."""
    d = _load(LIERISE)
    out = []
    for key in ("bodies", "bodies_lying"):
        b = (d.get(key) or {}).get(body) or {}
        seeds = b.get("best_seeds") or []
        if seeds:
            p = dict(seeds[0]["controller"]["params"])
            p.pop("mode", None)
            out.append(p)
    return out


def pilot(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.outcomes import (
        OutcomeSearch,
        default_spaces,
        optimise,
        warm_starts,
    )

    bodies = (opts.get("bodies") or ",".join(BODIES)).split(",")
    behaviours = (opts.get("behaviours") or ",".join(BEHAVIOURS)).split(",")
    model = opts.get("model", "explicit_v2")
    workers = int(opts.get("workers", 14))
    s = OutcomeSearch(popsize=int(opts.get("pop", 12)), generations=int(opts.get("gens", 20)))
    pl, ev = payloads(lab, bodies, model)
    margin = float(ev["hardware"]["margin"])
    cache = str(Path(sys.argv[1]) / ".cache" / "outcomes")
    spaces = default_spaces()
    data = _load(OUT)
    data.setdefault("pilot", {})
    data["settings"] = {"model": model, "search": s.model_dump(), "margin": margin, "workers": workers,
                        "spaces": {b: spaces[b].model_dump(mode="json") for b in behaviours}}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        def map_fn(fn: Any, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return list(pool.map(fn, jobs))

        def one(body: str, beh: str) -> tuple[str, str, dict[str, Any]]:
            starts = warm_starts(beh, lie_versions(body) if beh == "lie" else None)
            r = optimise(pl[body], spaces[beh], margin, s, starts, map_fn, cache,
                         report=lambda m: print(f"[{body}] {m} ({time.time() - t0:.0f} s)", flush=True))
            return body, beh, r

        with ThreadPoolExecutor(max_workers=len(bodies) * len(behaviours)) as th:
            futs = {th.submit(one, b, beh): (b, beh) for b in bodies for beh in behaviours}
            for f in as_completed(futs):
                try:
                    body, beh, r = f.result()
                except Exception as e:  # one search failing must not lose the others
                    body, beh = futs[f]
                    data.setdefault("failed", {})[f"{body} {beh}"] = repr(e)
                    print(f"FAILED {body} {beh}: {e!r}", flush=True)
                    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
                    continue
                data["pilot"].setdefault(body, {})[beh] = r
                best = r["best"]
                print(f"DONE {body} {beh}: holds {best['holds']} rank {best['rank']} wall {r['wall_s']} s "
                      f"plays {r['plays']}", flush=True)
                OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
    data["pilot_wall_s"] = round(time.time() - t0, 1)
    data["mass_g"] = {b: _mass(pl[b]) for b in bodies}
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
    print("pilot wall", data["pilot_wall_s"], "s", flush=True)


def _mass(payload: dict[str, Any]) -> float:
    from calflab.evolve.hardware import _build

    d, _ = _build(payload)
    return round(d.spec.total_mass_g(), 1)


def store(lab: Any, opts: dict[str, str]) -> None:
    """Each best version on seed 0 at the judging length, stored as a sim run."""
    from calflab.evolve.outcomes import BehaviourSpace, controller_params, play_length, play_seed

    data = _load(OUT)
    model = data["settings"]["model"]
    bodies = list(data["pilot"])
    pl, ev = payloads(lab, bodies, model)
    margin = float(ev["hardware"]["margin"])
    tmp = Path(sys.argv[1]) / ".cache" / "outcomes_rollouts"
    stored = data.setdefault("stored", {})
    for body in bodies:
        for beh, r in data["pilot"][body].items():
            space = BehaviourSpace.model_validate(r["space"])
            params = r["best"]["params"]
            path = tmp / f"{body}_{beh}.npz"
            rec = play_seed(pl[body], space, params, 0, margin, judging=True, rollout_path=str(path))
            run_id = _store_run(lab, pl[body], f"R15 {body} {beh}: seed 0", path,
                                {"key": "outcome_motion", "params": controller_params(space, params)},
                                play_length(space, params, True), rec)
            stored.setdefault(body, {})[beh] = run_id
            print(body, beh, run_id, rec["holds"], rec["outcome"].get("score"), flush=True)
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())


def _store_run(lab: Any, payload: dict[str, Any], title: str, rollout: Path, controller: dict[str, Any],
               length: float, rec: dict[str, Any]) -> str:
    """A ``sim`` run holding a saved rollout, as ``calflab.app.compare.store_play`` stores its plays."""
    import shutil

    from calflab.app.scene import build_scene
    from calflab.evolve.hardware import _build
    from calflab.project.registry import RunRecord

    design, _lib = _build(payload)
    sim_id = lab.registry.new_run_id("sim")
    rdir = lab.registry.run_dir(sim_id)
    rdir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(rollout), rdir / "rollout.npz")
    (rdir / "scene.json").write_text(json.dumps(build_scene(design, lab.state.layers, lab.state.settings)),
                                     encoding="utf-8")
    lab.registry.save_run(RunRecord(
        id=sim_id, kind="sim", title=title, duration_s=rec["wall_s"], seed=0, backend="local",
        inputs={"outcomes_r15": {"length_s": length, "outcome": rec["outcome"]}, "margin": 0.2,
                "report": {k: v for k, v in rec.items() if k not in ("joints", "outcome")}, "joints": rec["joints"]},
        genome=payload["genome"], overrides=payload["overrides"], controller=controller,
        metrics={"within_limits": rec["within"], "safety_margin": rec["margin"], "closest": rec["closest"],
                 "holds": rec["holds"], "score": rec["outcome"].get("score")},
        artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
        parent=payload.get("stage_c_run"), tags=["outcomes_r15"]))
    return sim_id


# ---------------------------------------------------------------------------------------------------- report
def _f(v: Any, nd: int = 2) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int | float):
        return f"{v:.{nd}f}"
    return str(v)


def _worst(best: dict[str, Any]) -> dict[str, Any]:
    return min(best["seeds"], key=lambda r: r["rank"])


def report() -> None:
    data = _load(OUT)
    lines = ["# R15 pilot tables (generated by `outcomes_r15.py report`)", ""]
    st = data.get("settings", {})
    lines.append(f"Mass model {st.get('model')}, margin {st.get('margin')}, search {st.get('search')}, "
                 f"pilot wall {data.get('pilot_wall_s')} s on {st.get('workers')} workers.")
    lines.append("")
    lines += ["| body | behaviour | holds (3 seeds) | start rank | best rank | outcome (worst seed) | failed gates | "
              "binds (worst seed) | margin | plays | wall s |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for body, behs in (data.get("pilot") or {}).items():
        for beh, r in behs.items():
            b = r["best"]
            w = _worst(b)
            o = w["outcome"]
            fails = [k for k, v in (o.get("gates") or {}).items() if not v]
            out = {"stand": lambda o: f"effort mean {_f(o.get('effort_mean'), 3)} max {_f(o.get('effort_max'), 3)} "
                                      f"({o.get('worst')}), height {_f(o.get('height'))}",
                   "suckle": lambda o: f"push p20 {_f(o.get('push_p20_n'))} N ({_f(o.get('push_p20_bw'), 3)} bw), "
                                       f"cv {_f(o.get('push_cv'))}, slip {_f(o.get('slip_max_mm'), 1)} mm, "
                                       f"CoM margin {_f(o.get('com_margin_mm'), 0)} mm",
                   "trot": lambda o: f"{_f(o.get('speed_mm_s'), 0)} mm/s (slowest 5 s {_f(o.get('speed_min_mm_s'), 0)}),"
                                     f" drift {_f(o.get('drift_mm_s'), 0)} mm/s, "
                                     f"{(o.get('footfall') or {}).get('label')} lag "
                                     f"{_f((o.get('footfall') or {}).get('diagonal_lag'))}",
                   "lie": lambda o: f"down to {_f(o.get('lying_min'))} for {_f(o.get('lying_held_s'), 1)} s, descent "
                                    f"{_f(o.get('descent_peak_mm_s'), 0)} mm/s, impact {_f(o.get('impact_peak_bw'))} bw,"
                                    f" tilt {_f(o.get('tilt_max_deg'), 0)} deg, risen {_f(o.get('risen'))}"}[beh](o)
            bd = w.get("binding") or {}
            lines.append(f"| {body} | {beh} | {_f(b['holds'])} | {_f(r['start']['rank'])} | {_f(b['rank'])} | {out} | "
                         f"{', '.join(fails) or '–'} | {bd.get('joint')} {bd.get('limit')} {_f(bd.get('use'))} | "
                         f"{_f(w.get('margin'))} | {r['plays']} | {_f(r['wall_s'], 0)} |")
    lines += ["", "## Best versions (params)", ""]
    for body, behs in (data.get("pilot") or {}).items():
        for beh, r in behs.items():
            lines.append(f"* **{body} {beh}**: `{json.dumps(r['best']['params'])}`")
    lines += ["", "## Search progress (best rank so far after each generation)", ""]
    for body, behs in (data.get("pilot") or {}).items():
        for beh, r in behs.items():
            best = -1e9
            curve = []
            for g in sorted({p["generation"] for p in r["progress"]}):
                best = max(best, max(p["rank"] for p in r["progress"] if p["generation"] == g))
                curve.append(f"{best:+.2f}")
            lines.append(f"* {body} {beh}: {' '.join(curve)}")
    TABLES.write_bytes(("\n".join(lines) + "\n").encode())
    print("\n".join(lines))


# ---------------------------------------------------------------------------------------------------- estimate
#: the three budgets offered (ADR-110): inner search per behaviour (popsize, generations after the parent's best,
#: search seeds, versions judged long on three seeds) and the outer body search (bodies per generation, generations)
BUDGETS = {
    "S": {"pop": 8, "gens": 6, "seeds": 1, "judge_top": 1, "bodies": 12, "outer_gens": 10},
    "M": {"pop": 10, "gens": 10, "seeds": 2, "judge_top": 2, "bodies": 15, "outer_gens": 20},
    "L": {"pop": 12, "gens": 20, "seeds": 3, "judge_top": 3, "bodies": 15, "outer_gens": 30},
}


def measured() -> dict[str, Any]:
    """From the pilot: per behaviour the mean CPU-s of a search play and of a judging play, the share of candidates
    played on more than the first seed, and the pool's efficiency (CPU-s used / (wall x workers))."""
    data = _load(OUT)
    workers = int(data["settings"]["workers"])
    out: dict[str, Any] = {"behaviours": {}, "workers": workers}
    cpu_total = 0.0
    for beh in BEHAVIOURS:
        search, judge, cont, cands = [], [], 0, 0
        for body in data["pilot"]:
            r = data["pilot"][body].get(beh)
            if not r:
                continue
            n_search = r["plays"] - sum(len(e["seeds"]) for e in r["judged"])
            cands += len(r["progress"])
            cont += n_search - len(r["progress"])
            for e in r["judged"]:
                judge += [float(x.get("wall_s") or 0) for x in e["seeds"] if "wall_s" in x]
            search.append(r)
        out["behaviours"][beh] = {"continue_share": cont / max(1, cands * (len(data["settings"]["search"]["search_seeds"]) - 1)),
                                  "search_runs": len(search)}
    # CPU-s per play from the cache (records carry their own wall time and length)
    cache = Path(sys.argv[1]) / ".cache" / "outcomes"
    per: dict[str, dict[str, list[float]]] = {}
    for f in cache.glob("*.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        o = r.get("outcome", {})
        gates = o.get("gates") or {}
        beh = next((k for k, g in GATE_OF.items() if g in gates), None)
        if beh is None:
            continue
        long = float(r["length_s"]) > 20.0 and beh != "lie"
        per.setdefault(beh, {"search": [], "judge": []})["judge" if long else "search"].append(float(r["wall_s"]))
        cpu_total += float(r["wall_s"])
    for beh, v in per.items():
        b = out["behaviours"].setdefault(beh, {})
        b["cpu_search_s"] = round(sum(v["search"]) / max(1, len(v["search"])), 2)
        b["cpu_judge_s"] = round(sum(v["judge"]) / max(1, len(v["judge"])), 2) if v["judge"] else b["cpu_search_s"]
        b["n_search"], b["n_judge"] = len(v["search"]), len(v["judge"])
    wall = float(data.get("pilot_wall_s") or 0.0)
    out["cpu_total_s"] = round(cpu_total, 1)
    out["efficiency"] = round(cpu_total / max(1e-6, wall * workers), 3) if wall else None
    return out


def estimate(opts: dict[str, str]) -> None:
    """Joint body-and-behaviour search at three budgets (``BUDGETS``) from the pilot's measurements."""
    m = measured()
    eff = float(m["efficiency"] or 0.7)
    workers = int(opts.get("workers", m["workers"]))
    lines = [f"Measured: {json.dumps(m)}", "",
             "| budget | inner per behaviour | plays per body | CPU-min per body | bodies | wall per outer generation | "
             "wall total |", "|---|---|---|---|---|---|---|"]
    rows = {}
    for name, b in BUDGETS.items():
        plays = cpu = 0.0
        for beh in BEHAVIOURS:
            mb = m["behaviours"].get(beh) or {}
            cont = float(mb.get("continue_share", 1.0))
            cands = 2 + b["pop"] * b["gens"]  # the parent's best + the behaviour's own default, then CMA-ES
            n_search = cands * (1 + (b["seeds"] - 1) * cont)
            n_judge = b["judge_top"] * 3
            plays += n_search + n_judge
            cpu += n_search * float(mb.get("cpu_search_s", 4.0)) + n_judge * float(mb.get("cpu_judge_s", 15.0))
        per_gen_wall = cpu * b["bodies"] / (workers * eff)
        total = per_gen_wall * b["outer_gens"]
        rows[name] = {"plays_per_body": round(plays), "cpu_min_per_body": round(cpu / 60, 1),
                      "bodies": b["bodies"] * b["outer_gens"], "wall_per_gen_min": round(per_gen_wall / 60, 1),
                      "wall_total_h": round(total / 3600, 1)}
        lines.append(f"| {name} | pop {b['pop']} x {b['gens']} gens, {b['seeds']} seed(s), top {b['judge_top']} "
                     f"judged | {plays:.0f} | {cpu / 60:.1f} | {b['bodies']} x {b['outer_gens']} = "
                     f"{b['bodies'] * b['outer_gens']} | {per_gen_wall / 60:.0f} min | {total / 3600:.1f} h |")
    data = _load(OUT)
    data["estimate"] = {"measured": m, "budgets": BUDGETS, "rows": rows, "workers": workers}
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
    print("\n".join(lines))


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj, stage = Path(sys.argv[1]), sys.argv[2]
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    if stage == "report":
        report()
        return
    if stage == "estimate":
        estimate(opts)
        return
    load_plugins()
    lab = Lab.open(proj, create=False)
    try:
        if stage == "pilot":
            pilot(lab, opts)
        elif stage == "store":
            store(lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
