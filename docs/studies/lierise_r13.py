"""Session R13 (ADR-107): lying down and rising, diagnosed and evolved per body.

Bodies are built as ``calflab.app.compare`` builds the R12 set's bodies (each Stage C run's genome and overrides, the
Stage B run's generator params and compile options, the R11c suite: seeds 0-2, friction 0.7-1.1, mass x0.95-1.05,
torque-speed servos, derating 1, margin 0.2). Nothing is written to the project document.

Stages:

* ``diagnose [bodies]``: today's lie_rise on every seed over the whole motion (+ settle), per move the joint and limit
  that bind; also the screen's own play (cut at 10 s) to check it reproduces Stage C's number.
  -> ``docs/studies/lierise_r13_diag.json``
* ``optimise [bodies]``: CMA-ES per body on the worst-seed margin (``calflab.evolve.lie_rise.optimise``)
  (``--popsize`` 12 ``--generations`` 10 ``--workers`` 7). -> ``docs/studies/lierise_r13.json`` (merged per body)
* ``report``: markdown tables from both JSON files.

Run:  python docs/studies/lierise_r13.py <project dir> diagnose|optimise|report [bodies] [--opts]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

SET = "r12"
DIAG_BODIES = ["g020-008-r01", "g012-009", "g009-000", "working"]
ALL_BODIES = ["working", "g007-002", "g009-000", "g012-009", "g011-003", "g020-008-r01"]
DIAG = Path("docs/studies/lierise_r13_diag.json")
OUT = Path("docs/studies/lierise_r13.json")


def body_payloads(lab: Any, bodies: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per body the worker payload (as ``compare.todo``), and the suite's evaluation settings."""
    from calflab.app import compare as cmp
    from calflab.design import genome_definition

    spec = cmp.compare_set(SET)
    runs = cmp.stage_c_runs(lab, spec)
    brun = lab.registry.get_run(spec.stage_b_run)
    gp = cmp._generator_params(lab, brun)
    gdef = genome_definition("feral_calf")
    ev = brun.fitness["preset"]["evaluation"]
    out = {}
    for body in bodies:
        run = lab.registry.get_run(runs[body])
        out[body] = {"genome": {"definition": gdef.name, "version": gdef.version,
                                "values": gdef.complete(run.genome["values"])},
                     "overrides": run.overrides, "generator": "feral_calf", "generator_params": gp,
                     "compile": brun.inputs["compile"], "evaluation": ev, "stage_c_run": runs[body]}
    return out, ev


def _margin(ev: dict[str, Any]) -> float:
    return float(ev["hardware"]["margin"])


def _diag_job(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.hardware import _build, compile_options, play_primitive_seed
    from calflab.evolve.lie_rise import play_seed
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins

    load_plugins()
    p = job["payload"]
    if job["kind"] == "screen":  # the screen's own play (InterpretSettings: cut at max_play_s)
        design, lib = _build(p)
        copts = compile_options(p.get("compile", {}), EvaluationSettings.model_validate(p["evaluation"]))
        rec = play_primitive_seed({"key": "lie_rise", "primitive": "lie_rise", "params": {}}, design.spec, lib, copts,
                                  job["seed"], job["margin"])
        return {"body": job["body"], "seed": job["seed"], "kind": "screen", "margin": rec["margin"],
                "within": rec["within"], "closest": rec["closest"]}
    rec = play_seed(p, job["params"], job["seed"], job["margin"], job["settle_s"])
    return {"body": job["body"], "seed": job["seed"], "kind": "full", **rec}


def diagnose(lab: Any, bodies: list[str], opts: dict[str, str]) -> None:
    from calflab.evolve.lie_rise import LieRiseSearch

    pays, ev = body_payloads(lab, bodies)
    s = LieRiseSearch()
    jobs = []
    for body in bodies:
        for seed in ev["seeds"]:
            for kind in ("full", "screen"):
                jobs.append({"body": body, "seed": seed, "kind": kind, "payload": pays[body], "params": {},
                             "margin": _margin(ev), "settle_s": s.settle_s})
    t0 = time.time()
    with ProcessPoolExecutor(int(opts.get("workers", 7))) as pool:
        res = list(pool.map(_diag_job, jobs))
    print(f"{len(jobs)} plays in {time.time() - t0:.0f} s", flush=True)
    data = {"settle_s": s.settle_s, "margin": _margin(ev), "bodies": {}}
    for body in bodies:
        mine = [r for r in res if r["body"] == body]
        data["bodies"][body] = {
            "stage_c_run": pays[body]["stage_c_run"],
            "screen": [{k: r[k] for k in ("seed", "margin", "within", "closest")} for r in mine if r["kind"] == "screen"],
            "full": [{k: r.get(k) for k in ("seed", "within", "fell", "sim_fell", "tipped", "risen", "lying_height_mm", "margin", "closest", "violations", "moves",
                                            "length_s", "wall_s")} for r in mine if r["kind"] == "full"]}
    DIAG.write_bytes(json.dumps(data, indent=1, default=float).encode())
    print("wrote", DIAG)


#: the extension (``--lying``): the lying pose searched too, within the joint ranges less 2 deg (ADR-107)
LYING_DIMS = [("lie_stifle", 30.0, 78.0), ("lie_hock", 30.0, 78.0), ("lie_shoulder", -58.0, 0.0),
              ("lie_carpus", 60.0, 128.0)]


def optimise(lab: Any, bodies: list[str], opts: dict[str, str]) -> None:
    from calflab.evolve.lie_rise import LieRiseSearch, play_seed
    from calflab.evolve.lie_rise import optimise as opt

    pays, ev = body_payloads(lab, bodies)
    lying = "lying" in opts
    s = LieRiseSearch(popsize=int(opts.get("popsize", 12)), generations=int(opts.get("generations", 10)),
                      seed=int(opts.get("seed", 0)), extra_dims=LYING_DIMS if lying else [])
    cache = str(Path(lab.project.path) / ".cache" / "lie_rise")
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {"bodies": {}}
    section = "bodies_lying" if lying else "bodies"
    data.setdefault(section, {})
    with ProcessPoolExecutor(int(opts.get("workers", 7))) as pool:
        def pmap(fn: Any, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return list(pool.map(fn, jobs))

        for body in bodies:
            t0 = time.time()
            print(time.strftime("%H:%M:%S"), body, flush=True)
            sb = s
            if lying and (data.get("bodies") or {}).get(body):  # warm start: this body's Stage 2 best
                sb = s.model_copy(update={"starts": [data["bodies"][body]["best"]["params"]]})
            r = opt(pays[body], list(ev["seeds"]), _margin(ev), sb, pmap, cache,
                    lambda m, b=body: print(time.strftime("%H:%M:%S"), b, m, flush=True))
            best = r["best"]
            # the best version, played again with stop_on_fall off and per-move detail (as stored runs play it)
            again = list(pool.map(_full, [{"payload": pays[body], "params": best["params"], "seed": sd,
                                           "margin": _margin(ev), "settle_s": s.settle_s} for sd in ev["seeds"]]))
            data[section][body] = {"stage_c_run": pays[body]["stage_c_run"], "search": r["search"],
                                    "plays": r["plays"], "new_plays": r["new_plays"], "wall_s": r["wall_s"],
                                    "start": _slim(r["start"]), "best": _slim(best), "best_seeds": again,
                                    "history": r["history"]}
            OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
            print(time.strftime("%H:%M:%S"), body, f"best {best['worst']:+.3f} held={best['held']}",
                  f"{time.time() - t0:.0f} s", flush=True)
    _ = play_seed  # imported for workers' module import order
    print("wrote", OUT)


def _full(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.lie_rise import play_seed

    rec = play_seed(job["payload"], job["params"], job["seed"], job["margin"], job["settle_s"])
    return {"seed": job["seed"], **{k: rec.get(k) for k in ("within", "fell", "sim_fell", "tipped", "risen", "lying_height_mm", "margin", "closest", "violations",
                                                              "moves", "length_s", "controller")}}


def _slim(e: dict[str, Any]) -> dict[str, Any]:
    return {"params": e["params"], "worst": e["worst"], "rank": e["rank"], "held": e["held"],
            "complete": e["complete"],
            "seeds": [{k: r.get(k) for k in ("seed", "within", "fell", "margin", "excess", "closest", "violations",
                                             "moves")} for r in e["seeds"]]}


# ---------------------------------------------------------------------------------------------- Stage 3
STAGE3_SEEDS = ["g012-009", "g020-008-r01", "g009-000"]
PRESET = Path("config/fitness/hardware_r13.yaml")
#: gate budgets offered (popsize, generations); each body's search also plays today's motion and the starts
BUDGETS = {"S": (8, 8), "M": (12, 15), "L": (12, 30)}
#: measured in Stage 2: about 1070 plays per body in 15-23 min on 7 workers = 7.5 CPU-s per play (whole motion,
#: three seeds each, while other work shared the machine)
CPU_S_PER_PLAY = 7.5
#: Stage B (ADR-104): a generation of 15 bodies took about 34 min (screen + 11 behaviours x 3 seeds for those passing)
STAGE_B_MIN_PER_15 = 34.0


def write_preset(lab: Any, opts: dict[str, str]) -> dict[str, Any]:
    """config/fitness/hardware_r13.yaml: hardware_r11c (judging, space, budgets) + the lie_rise gate + the three
    seed bodies; the old lie_rise screen play is dropped (the gate judges lying down and rising)."""
    import yaml
    from calflab.design import genome_definition

    d = yaml.safe_load(Path("config/fitness/hardware_r11c.yaml").read_text(encoding="utf-8"))
    budget = opts.get("budget", "M")
    pop, gens = BUDGETS[budget]
    o = json.loads(OUT.read_text(encoding="utf-8"))
    lying = "lying" in opts
    section = "bodies_lying" if lying and o.get("bodies_lying") else "bodies"
    gdef = genome_definition("feral_calf")
    brun = lab.registry.get_run("20261107-043030-evolve-c02e")
    base = gdef.complete(brun.genome["values"])  # Stage B started from the working body, as Stage 3 will
    cands = lab.registry.list_candidates(brun.id)
    seeds, starts = [], []
    for body in STAGE3_SEEDS:
        c = next(x for x in cands if x["id"].endswith(body))
        vals = gdef.complete(c["genome"]["values"])
        seeds.append({"label": body, "note": f"Stage B candidate {c['id']} (ADR-104)",
                      "values": {k: v for k, v in vals.items() if base.get(k) != v}})
        if body in o.get(section, {}):
            starts.append(o[section][body]["best"]["params"])
    hw = d["evaluation"]["hardware"]
    hw["screen_extra"] = [k for k in hw["screen_extra"] if k != "lie_rise"]
    hw["seeds_bodies"] = seeds
    from calflab.evolve.lie_rise import LieRiseSearch

    hw["lie_rise_gate"] = LieRiseSearch(popsize=pop, generations=gens, starts=starts,
                                        extra_dims=LYING_DIMS if lying else []).model_dump(mode="json")
    d["name"], d["version"] = "hardware_r13", 1
    d["description"] = (f"R13 (ADR-107): hardware_r11c with lying down and rising as a constraint: each body's "
                        f"lie_rise is optimised (CMA-ES {pop} x {gens}, three seeds, whole motion, warm-started from "
                        f"the seed bodies' R13 versions{', lying pose searched' if lying else ''}); a body passes "
                        "only if it holds on all three seeds, then the trot grid, walk, turn and the 11 shared "
                        "behaviours are judged as in Stage B. Seeded with g012-009, g020-008-r01, g009-000.")
    head = ("# Fitness preset R13 (ADR-107): written by docs/studies/lierise_r13.py preset. Use with the optimizer\n"
            "# map_elites_hardware. Bump `version` whenever you change it.\n")
    PRESET.write_bytes((head + yaml.safe_dump(d, sort_keys=False, width=118, allow_unicode=True)).encode("utf-8"))
    print("wrote", PRESET, "budget", budget, (pop, gens), "starts", len(starts), "seeds", [s["label"] for s in seeds])
    return d


def estimate(opts: dict[str, str]) -> None:
    """Cost of Stage 3 per generation and for N generations, per gate budget (an upper bound: cached plays and the
    seed bodies' searches cost less)."""
    workers, batch = int(opts.get("workers", 7)), int(opts.get("batch", 14))
    n_starts, n_seeds = 4, 3
    waves = -(-batch // workers)
    print(f"| gate budget | plays per body | CPU min per body | wall per generation of {batch} ({workers} workers, "
          f"{waves} waves) | + judging if all pass | 10 generations | 20 generations |")
    print("|---|---|---|---|---|---|---|")
    for name, (pop, gens) in BUDGETS.items():
        plays = n_seeds * (n_starts + pop * gens)
        cpu_min = plays * CPU_S_PER_PLAY / 60.0
        gen_min = waves * cpu_min
        judge = STAGE_B_MIN_PER_15 * batch / 15.0
        print(f"| {name} ({pop} x {gens}) | {plays} | {cpu_min:.0f} | {gen_min / 60:.1f} h | +{judge:.0f} min | "
              f"{10 * gen_min / 60:.0f}-{10 * (gen_min + judge) / 60:.0f} h | "
              f"{20 * gen_min / 60:.0f}-{20 * (gen_min + judge) / 60:.0f} h |")


def stage3(lab: Any, opts: dict[str, str]) -> None:
    """The body search with lie_rise as a constraint (preset hardware_r13 must exist: run ``preset`` first)."""
    params: dict[str, Any] = {"generations": int(opts.get("generations", 1)), "batch_size": int(opts.get("batch", 14)),
                              "vary_geometry": True, "what_if_pulleys": False, "seed_bodies": True,
                              "sigma_init": 0.1, "sigma_iso": 0.05, "hardware_flip": 0.05,
                              "seed": int(opts.get("seed", 0))}
    t0 = time.time()
    job = lab.run_evolve("map_elites_hardware", params, None, None, None, "hardware_r13")
    print("run", (job.result or {}).get("run_id"), params, flush=True)
    while True:
        j = lab.jobs.get(job.id) if hasattr(lab.jobs, "get") else job
        if j.status in ("done", "failed", "cancelled"):
            break
        time.sleep(30)
    print(j.status, getattr(j, "error", None), j.result, f"{time.time() - t0:.0f} s", flush=True)


# ---------------------------------------------------------------------------------------------- report
LIM = {"speed": "joint speed", "torque": "sustained torque", "belt": "sustained belt", "envelope": "envelope",
       "stall": "stall"}


def _cell(m: dict[str, Any]) -> str:
    if m.get("joint") is None:
        return "-"
    return f"{m['joint']} {LIM.get(m['limit'], m['limit'])} {m['margin']:+.2f}"


def move_table(seeds: list[dict[str, Any]]) -> list[str]:
    """One row per move: per seed the closest joint and limit with its margin (1 - use)."""
    names = [m["move"] for m in seeds[0]["moves"]]
    out = ["| move | t (s) | " + " | ".join(f"seed {r['seed']}" for r in seeds) + " |",
           "|---|---|" + "---|" * len(seeds)]
    for k, name in enumerate(names):
        m0 = seeds[0]["moves"][k]
        out.append(f"| {name} | {m0['t0']:.1f}-{m0['t1']:.1f} | "
                   + " | ".join(_cell(r["moves"][k]) if k < len(r["moves"]) else "-" for r in seeds) + " |")
    return out


def report() -> None:
    if DIAG.is_file():
        d = json.loads(DIAG.read_text(encoding="utf-8"))
        print("## Stage 1: today's lie_rise, per move\n")
        print("| body | screen (cut at 10 s), seeds 0/1/2 | whole motion + 1 s, seeds 0/1/2 | binds (whole) |")
        print("|---|---|---|---|")
        for body, b in d["bodies"].items():
            sc = " / ".join(f"{r['margin']:+.2f}" for r in b["screen"])
            fu = " / ".join(f"{r['margin']:+.2f}{' fell' if r['fell'] else ''}" for r in b["full"])
            print(f"| {body} | {sc} | {fu} | {b['full'][0]['closest']} |")
        for body, b in d["bodies"].items():
            print(f"\n### {body}\n")
            print("\n".join(move_table(b["full"])))
    if not OUT.is_file():
        return
    o = json.loads(OUT.read_text(encoding="utf-8"))
    for section, title in (("bodies", "Stage 2: the primitive's dims, per body"),
                           ("bodies_lying", "Extension: the lying pose searched too (--lying)")):
        if not o.get(section):
            continue
        print(f"\n## {title}\n")
        print("| body | today (whole) worst | best worst-seed | holds 3/3 | plays (new) | wall min | best version |")
        print("|---|---|---|---|---|---|---|")
        for body, b in o[section].items():
            p = b["best"]["params"]
            order = "front first" if p["front_first"] >= 0.5 else "hind first"
            desc = (f"{order}; kneel {p['kneel_shoulder']:.0f}/{p['kneel_carpus']:.0f}, reach {p['reach_shoulder']:.0f}/"
                    f"{p['reach_carpus']:.0f}; moves {p['kneel_s']:.1f}/{p['lie_s']:.1f}/{p['rise_hind_s']:.1f}/"
                    f"{p['reach_s']:.1f}/{p['rise_front_s']:.1f} s; hold {p['hold_s']:.1f}; rock {p['rock_back_deg']:.0f} "
                    f"deg/{p['rock_s']:.1f} s; pauses {p['pause_mid_s']:.1f}/{p['pause_reach_s']:.1f} s")
            if "lie_stifle" in p:
                desc += (f"; lying stifle/hock {p['lie_stifle']:.0f}/{p['lie_hock']:.0f}, shoulder/carpus "
                         f"{p['lie_shoulder']:.0f}/{p['lie_carpus']:.0f}")
            print(f"| {body} | {b['start']['worst']:+.3f} | {b['best']['worst']:+.3f} | "
                  f"{'yes' if b['best']['held'] else 'no'} | {b['plays']} ({b['new_plays']}) | {b['wall_s'] / 60:.0f} | "
                  f"{desc} |")
        for body, b in o[section].items():
            print(f"\n### {body}: best version, per move\n")
            print("\n".join(move_table(b["best_seeds"])))


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj, stage = Path(sys.argv[1]), sys.argv[2]
    args = [a for a in sys.argv[3:] if not a.startswith("--")]
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
        if stage == "diagnose":
            diagnose(lab, args or DIAG_BODIES, opts)
        elif stage == "optimise":
            optimise(lab, args or ALL_BODIES, opts)
        elif stage == "preset":
            write_preset(lab, opts)
        elif stage == "stage3":
            stage3(lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
