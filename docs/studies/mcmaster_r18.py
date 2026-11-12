"""Session R18 (ADR-115..): g020-008-r01 on McMaster-Carr timing belt parts only (1/4 in bore pulleys).

Every pulley and belt comes from the two McMaster systems in the catalog (``MM-2MGT-6``, ``MM-3MGT-9``; see
``catalog_r18.py``). Their breaking strength is the researcher's assumption (``guessed``); their allowable working
tension is unknown, so the sustained belt-tension check is unknown and every "within limits" here means "within limits
excluding sustained belt tension". Each play reports every drive's peak and mean belt tension and the largest fraction
of any 2 s window spent above the reference levels ``LEVELS`` (the statistic the sustained check would use), so the
researcher can choose an allowable later.

Stages (``python docs/studies/mcmaster_r18.py <project> <stage> [--opts]``):

* ``fits``     every McMaster pair x length that passes every check on each belted drive of g020-008-r01;
* ``swap``     the closest swap ``g020-008-r01-mc``: each drive moved to the fitting choice nearest its ratio;
* ``mass``     mass_breakdown of every body against the baseline;
* ``loads``    statics in the standing pose and three plays (stand, the R16 lowest stand, the walk) per body;
* ``replay``   the R16 repertoire on seeds 0-2 at its judging length (30 s), judged at margin 0.2 (``--bodies=``);
* ``summary``  the tables (``mcmaster_r18_tables.md``).

Bodies are payloads (genome + generator params) held in ``mcmaster_r18.json``; nothing is stored in the document.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path("docs/studies").resolve()))

OUT = Path("docs/studies/mcmaster_r18.json")
TABLES = Path("docs/studies/mcmaster_r18_tables.md")
BASE = "g020-008-r01"
SWAP = "g020-008-r01-mc"
SYSTEMS = ["MM-2MGT-6", "MM-3MGT-9"]
LEVELS = (20.0, 30.0, 40.0, 50.0)  # N, reference belt tensions (not limits)
WINDOW_S = 2.0
DRIVES = ("stifle", "hock", "carpus", "shoulder")
#: the plays of the loads table: R16's level stand, its lowest stand that holds, and its 256 mm/s walk
LOAD_PLAYS = {"stand": "full:stand|3|3", "lowest stand": "full:stand|0|2", "walk": "full:walk|4|2"}


def _load() -> dict[str, Any]:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}


def _save(d: dict[str, Any]) -> None:
    OUT.write_text(json.dumps(d, indent=1, default=float), encoding="utf-8")


# --------------------------------------------------------------------- bodies
def base_payload(lab: Any) -> tuple[dict[str, Any], float]:
    """R16's payload for g020-008-r01 (explicit_v2), with the project's current belt catalog inlined (the R16 payload
    carries the catalog of its Stage B run, which has no McMaster entries)."""
    from calflab.mech.belts import catalog_files
    from diversity_r16 import payload

    pl, margin = payload(lab)
    pl = copy.deepcopy(pl)
    pl["generator_params"]["belt_catalog"] = catalog_files(lab.project.path)
    return pl, margin


def with_genes(pl: dict[str, Any], genes: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(pl)
    out["genome"]["values"] = {**out["genome"]["values"], **genes}
    return out


def bodies(lab: Any) -> dict[str, dict[str, Any]]:
    """Every body of the study by name: the baseline, the swap and the reformulated bodies (``best``)."""
    pl, _m = base_payload(lab)
    d = _load()
    out = {BASE: pl}
    for name, genes in (d.get("bodies") or {}).items():
        out[name] = with_genes(pl, genes)
    return out


def _cat(pl: dict[str, Any]) -> Any:
    from calflab.mech.belts import BeltCatalog

    return BeltCatalog.from_dict(pl["generator_params"]["belt_catalog"], origin="inlined")


def _drive_row(rep: Any, cat: Any) -> dict[str, Any]:
    """One fitting choice: derived C, pulley gap, teeth in mesh, servo span, clearance, ratio, part numbers."""
    sing = cat.singles(rep.choice.pulleys)
    entry = cat.length(rep.choice.length)
    ch = {c.id: c for c in rep.checks}
    clr = ch.get("stifle_belt_clearance")
    return {"system": rep.choice.system, "pulleys": rep.choice.pulleys, "length": rep.choice.length,
            "driver_teeth": rep.driver_teeth, "driven_teeth": rep.driven_teeth, "ratio": round(rep.ratio, 4),
            "length_mm": rep.length_mm, "belt_teeth": rep.belt_teeth, "belt_part": entry.part_number,
            "pulley_parts": [p.part_number for p in sing] if sing else None,
            "d1_mm": round(rep.d1_mm, 3), "d2_mm": round(rep.d2_mm, 3), "c_mm": round(float(rep.c_mm or 0), 2),
            "pulley_gap_mm": round(float(rep.c_mm or 0) - (rep.d1_mm + rep.d2_mm) / 2.0, 2),
            "teeth_in_mesh": round(float(rep.teeth_in_mesh or 0), 1), "wrap_deg": round(float(rep.wrap_deg or 0), 1),
            "servo_span_mm": [round(x, 1) for x in rep.servo_span_mm] if rep.servo_span_mm else None,
            "servo_check": ch["servo_on_segment"].status, "servo_detail": ch["servo_on_segment"].detail,
            "clearance": clr.status if clr else None, "clearance_detail": clr.detail if clr else "",
            "unknown": rep.unknown, "breaking_n": rep.breaking_strength_n}


def fits(lab: Any, opts: dict[str, str]) -> None:
    """Every McMaster pair x length that passes every check on each belted drive of the baseline (the hock against
    the baseline's own stifle belt; the swap re-checks it against the swapped stifle)."""
    from calflab.evolve.hardware import _build
    from calflab.mech.belts import fitting_choices
    from calflab.morphology.feral import belt_context

    pl, _m = base_payload(lab)
    design, _lib = _build(pl)
    cat = _cat(pl)
    _c, layouts, extra = belt_context(design.spec, None, catalog=cat)
    fer = design.spec.metadata["feral"]
    out: dict[str, Any] = {}
    for d, r in fer["belt_drives"].items():
        t = time.perf_counter()
        ok, fails = fitting_choices(cat, layouts[d], SYSTEMS, extra.get(d))
        lay = layouts[d]
        out[d] = {"current": {"choice": r["choice"], "ratio": r["ratio"], "c_mm": r["c_mm"], "d1_mm": r["d1_mm"]},
                  "layout": {"segment": lay.segment, "segment_length_mm": lay.segment_length_mm,
                             "window_mm": [lay.near_limit_mm, lay.far_limit_mm], "servo_length_mm": lay.servo_length_mm,
                             "pulley_clearance_mm": lay.pulley_clearance_mm, "min_teeth_in_mesh": lay.min_teeth_in_mesh},
                  "fits": [_drive_row(x, cat) for x in ok], "failed_checks": fails,
                  "seconds": round(time.perf_counter() - t, 1)}
        print(d, len(ok), "fit;", fails, flush=True)
    data = _load()
    data["fits"] = out
    _save(data)


def closest(rows: list[dict[str, Any]], ratio0: float, c0: float) -> dict[str, Any]:
    """The swap rule (ADR-116): the ratio nearest the current one; then the most belt margin per unit of servo torque
    (driver pitch radius x the assumed breaking strength, the one belt limit that is checked); then C nearest the
    current C (the servo stays where it was)."""
    return min(rows, key=lambda r: (round(abs(r["ratio"] - ratio0), 6), -round(r["d1_mm"] / 2 * (r["breaking_n"] or 0), 3),
                                    abs(r["c_mm"] - c0)))


def swap(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.hardware import _build
    from calflab.mech.belts import BeltChoice, fitting_choices
    from calflab.morphology.feral import belt_context, belt_genes

    pl, _m = base_payload(lab)
    design, _lib = _build(pl)
    cat = _cat(pl)
    fer = design.spec.metadata["feral"]
    genes: dict[str, Any] = {}
    picks: dict[str, Any] = {}
    stifle_choice = None
    for d in ("stifle", "hock", "carpus", "shoulder"):
        if d not in fer["belt_drives"]:
            continue
        r = fer["belt_drives"][d]
        _c, layouts, extra = belt_context(design.spec, None, catalog=cat, stifle_choice=stifle_choice)
        ok, _f = fitting_choices(cat, layouts[d], SYSTEMS, extra.get(d))
        rows = [_drive_row(x, cat) for x in ok]
        best = closest(rows, float(r["ratio"]), float(r["c_mm"]))
        picks[d] = {"from": r["choice"], "from_ratio": r["ratio"], "from_c_mm": r["c_mm"], "to": best,
                    "candidates_at_ratio": sum(1 for x in rows if abs(x["ratio"] - best["ratio"]) < 1e-9)}
        ch = BeltChoice(system=best["system"], pulleys=best["pulleys"], length=best["length"])
        genes.update(belt_genes(ch, d))
        if d == "stifle":
            stifle_choice = ch
        print(d, r["choice"]["pulleys"], r["ratio"], "->", best["pulleys"], best["ratio"], best["length"],
              "C", best["c_mm"], flush=True)
    d2, _ = _build(with_genes(pl, genes))
    drives = d2.spec.metadata["feral"]["belt_drives"]
    bad = [k for k, v in drives.items() if not v["ok"]]
    if bad:
        raise SystemExit(f"swap fails its own checks at {bad}")
    data = _load()
    data.setdefault("bodies", {})[SWAP] = genes
    data["swap"] = picks
    _save(data)
    print("swap stored as", SWAP)


# --------------------------------------------------------------------- mass and loads
def mass(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.hardware import _build
    from calflab.model.mass import mass_breakdown

    out = {}
    for name, pl in bodies(lab).items():
        design, lib = _build(pl)
        mb = mass_breakdown(design.spec, lib)
        out[name] = {"total_g": round(design.spec.total_mass_g(), 1), "breakdown": mb}
        print(name, out[name]["total_g"], flush=True)
    data = _load()
    data["mass"] = out
    _save(data)


def _belt_stats(ro: Any, spec: Any, lib: Any) -> dict[str, Any]:
    """Per belted joint: servo torque peak / mean |.|, joint torque peak, belt tension peak / mean (N), peak as a
    fraction of the (assumed) breaking strength, and the largest fraction of any 2 s window above each level."""
    import numpy as np
    from calflab.behave.interpret import _checks
    from calflab.mech.loads import analyse, windowed_fraction

    belts = (spec.metadata.get("feral") or {}).get("belt_drives") or {}
    res = analyse(ro, spec, lib, WINDOW_S, _checks(spec), belts)
    cols, t = res["columns"], res["columns"]["t_s"]
    out: dict[str, Any] = {}
    for row in res["summary"]:
        short = row["joint"].replace("joint.", "")
        if f"{short}.belt_n" not in cols:
            continue
        ten = np.asarray(cols[f"{short}.belt_n"], float)
        brk = row.get("breaking_n")
        out[short] = {"servo_peak_nm": round(row["servo_torque_peak_nm"], 3),
                      "servo_mean_nm": round(row["servo_torque_mean_abs_nm"], 3),
                      "joint_peak_nm": round(row["joint_torque_peak_nm"], 3),
                      "belt_peak_n": round(float(np.max(ten)), 1), "belt_mean_n": round(float(np.mean(ten)), 1),
                      "peak_of_breaking": None if brk is None else round(float(np.max(ten)) / float(brk), 4),
                      "above": {f"{lv:g}": round(windowed_fraction(ten > lv, t, WINDOW_S), 3) for lv in LEVELS}}
    return out


def _play(job: dict[str, Any]) -> dict[str, Any]:
    """One R16 behaviour on one seed on one body, judged at the margin; belt statistics per drive."""
    import dataclasses

    from calflab.behave.interpret import judge
    from calflab.evolve.hardware import _build, per_joint
    from calflab.evolve.outcomes import BehaviourSpace, play_seed
    from calflab.plugins import load_plugins
    from calflab.sim.rollout import Rollout

    load_plugins()
    t0 = time.perf_counter()
    sp = BehaviourSpace.model_validate(job["space"])
    rec = play_seed(job["payload"], sp, job["params"], job["seed"], job["margin"], judging=True,
                    rollout_path=job["path"])
    ro = Rollout.load(Path(job["path"]))
    Path(job["path"]).unlink(missing_ok=True)
    design, lib = _build(job["payload"])
    spec = design.spec
    if sp.behaviour in ("lie", "free"):  # as R16 judged them (its own gates; the simulator's fall check off)
        ro = dataclasses.replace(ro, meta={**ro.meta, "fell": False, "fall_time": None})
    j = judge(ro, spec, lib, job["margin"])
    cons = j["constraints"]
    known = {k: v["margin"] for k, v in cons.items() if v.get("margin") is not None}
    excl = {k: v for k, v in known.items() if k != "belt_sustained"}
    viol = list(j["violations"])
    pj = per_joint(ro, spec, lib, job["margin"])
    worst = max(((jn, r) for jn, r in pj.items() if r.get("binds")),
                key=lambda kv: kv[1][kv[1]["binds"]] or 0.0, default=(None, {}))
    return {"body": job["body"], "key": job["key"], "seed": job["seed"], "holds": bool(rec.get("holds")),
            "fell": bool(j["fell"]), "violations": viol,
            "within": bool(j["within_limits"]),
            "within_excl": (not j["fell"]) and not [v for v in viol if v != "belt_sustained"],
            "margin": round(min(known.values()), 4) if known else None,
            "margin_excl": round(min(excl.values()), 4) if excl else None,
            "closest_excl": min(excl, key=lambda k: excl[k]) if excl else None,
            "belt_sustained": cons.get("belt_sustained", {}).get("margin"),
            "binding": {"joint": worst[0], "limit": worst[1].get("binds"),
                        "use": worst[1].get(worst[1].get("binds") or "", None)} if worst[0] else None,
            "belts": _belt_stats(ro, spec, lib), "seconds": round(time.perf_counter() - t0, 1)}


def _jobs(lab: Any, names: list[str], keys: list[str] | None, seeds: list[int], margin: float) -> list[dict[str, Any]]:
    from diversity_r16 import OUT as R16
    from diversity_r16 import _load as r16load

    shown = r16load(R16)["shown"]
    if keys:
        shown = [s for s in shown if s["key"] in keys]
    tmp = Path(sys.argv[1]) / ".cache" / "mcmaster_r18_rollouts"
    tmp.mkdir(parents=True, exist_ok=True)
    bs = bodies(lab)
    return [{"payload": bs[n], "body": n, "space": s["space"], "params": s["params"], "seed": seed, "margin": margin,
             "key": s["key"], "path": str(tmp / f"{n}_{i}_{seed}.npz")}
            for n in names for i, s in enumerate(shown) for seed in seeds]


def _run(jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    res = []
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, r in enumerate(pool.map(_play, jobs)):
            res.append(r)
            if i % 25 == 0:
                print(f"done {i + 1}/{len(jobs)} in {time.perf_counter() - t:.0f} s", flush=True)
    return res


def loads(lab: Any, opts: dict[str, str]) -> None:
    """Statics in the standing pose, and the three load plays on seed 0, per body."""
    from calflab.evolve.hardware import _build
    from calflab.mech.statics import static_loads

    _pl, margin = base_payload(lab)
    names = (opts.get("bodies") or ",".join(bodies(lab))).split(",")
    data = _load()
    stat: dict[str, Any] = {}
    for n in names:
        design, _lib = _build(bodies(lab)[n])
        spec = design.spec
        sl = static_loads(spec)
        trans = {tr.id: tr for tr in spec.transmissions}
        drives = spec.metadata["feral"]["belt_drives"]
        rows = {}
        for a in spec.actuators:
            short = a.joint.replace("joint.", "")
            tr = trans.get(a.transmission) if a.transmission else None
            ratio, eff = (tr.ratio, tr.efficiency) if tr else (1.0, 1.0)
            joint_nm = -sl[a.joint]["net_nm"]
            servo_nm = joint_nm / (ratio * eff)
            drv = drives.get(short.split(".")[-1]) if tr else None
            belt = abs(servo_nm) / (float(drv["d1_mm"]) / 2000.0) if drv else None
            rows[short] = {"joint_nm": round(joint_nm, 3), "servo_nm": round(servo_nm, 3), "ratio": ratio,
                           "belt_n": None if belt is None else round(belt, 1),
                           "peak_of_breaking": None if belt is None or not drv.get("breaking_strength_n")
                           else round(belt / float(drv["breaking_strength_n"]), 4)}
        stat[n] = rows
    jobs = _jobs(lab, names, list(LOAD_PLAYS.values()), [0], margin)
    res = _run(jobs, int(opts.get("workers", 14)))
    data["loads"] = {"statics": stat, "plays": res, "which": LOAD_PLAYS}
    _save(data)


def replay(lab: Any, opts: dict[str, str]) -> None:
    """The R16 repertoire (``diversity_r16.json`` shown, 107 behaviours) on seeds 0-2 per body; results are merged
    into ``replay`` by body, so bodies can be added later."""
    _pl, margin = base_payload(lab)
    names = (opts.get("bodies") or f"{BASE},{SWAP}").split(",")
    keys = opts["keys"].split(",") if opts.get("keys") else None
    seeds = [int(s) for s in opts.get("seeds", "0,1,2").split(",")]
    jobs = _jobs(lab, names, keys, seeds, margin)
    print(len(jobs), "plays", flush=True)
    t = time.perf_counter()
    res = _run(jobs, int(opts.get("workers", 14)))
    data = _load()
    rp = data.setdefault("replay", {})
    for n in names:
        old = [r for r in rp.get(n, []) if (r["key"], r["seed"]) not in {(x["key"], x["seed"]) for x in res
                                                                         if x["body"] == n}]
        rp[n] = old + [r for r in res if r["body"] == n]
    data.setdefault("timing", {})[f"replay {','.join(names)}"] = {"plays": len(jobs),
                                                                   "seconds": round(time.perf_counter() - t, 1)}
    _save(data)


# --------------------------------------------------------------------- the reformulation search (step 3)
PRESET = Path("config/fitness/hardware_r18.yaml")
B_CANDIDATE_BODY = BASE  # the search starts from Stage B's candidate g020-008-r01 (run_evolve(candidate=...))


def _swap_genes() -> dict[str, Any]:
    return dict((_load().get("bodies") or {})[SWAP])


def preset(lab: Any, opts: dict[str, str]) -> None:
    """hardware_r18 (ADR-117): hardware_r14 v2 (explicit_v2, the R11c suite at margin 0.2, bounded geometry, springs,
    shoulder drive) with the belts restricted to the two McMaster systems (sourceable only), the carpus drive belted
    or direct, and the suite played on seed 0 only (the researcher's choice of a lighter judge; front-runners are
    confirmed on seeds 0-2 by ``confirm``). Seeded with the closest swap and three variants of it."""
    import yaml

    p = yaml.safe_load(Path("config/fitness/hardware_r14.yaml").read_text(encoding="utf-8"))
    sw = _swap_genes()
    fits_c = (_load().get("fits") or {}).get("carpus", {}).get("fits") or []
    c72 = min((r for r in fits_c if r["pulleys"] == "MM-2MGT-72T+MM-2MGT-72T"),
              key=lambda r: abs(r["c_mm"] - 232.5), default=None)
    seeds = [{"label": "g020-008-r01-mc (closest swap)", "note": "R18 step 2", "values": sw}]
    if c72:
        seeds.append({"label": "swap + carpus 2MGT 72T/72T", "note": "the 6 mm 1:1 option",
                      "values": {**sw, "belt_carpus_system": c72["system"], "belt_carpus_pulleys": c72["pulleys"],
                                 "belt_carpus_length": c72["length"]}})
    seeds.append({"label": "swap + carpus direct", "note": "C002 carpus on the joint", "values": {**sw, "carpus_belt": False}})
    seeds.append({"label": "swap + shoulder belted 3MGT 30T/45T", "note": "a length feasible on the body is chosen",
                  "values": {**sw, "shoulder_belt": True, "belt_shoulder_system": "MM-3MGT-9",
                             "belt_shoulder_pulleys": "MM-3MGT-30T+MM-3MGT-45T", "belt_shoulder_length": "MM-3MGT-450"}})
    hw = p["evaluation"]["hardware"]
    hw["belt_systems"] = list(SYSTEMS)
    hw["production"]["sourceable_only"] = True
    hw["production"]["carpus_drive"] = True
    hw["seeds_bodies"] = seeds
    p["evaluation"]["seeds"] = [0]
    p["name"], p["version"] = "hardware_r18", 1
    p["description"] = ("R18 (ADR-117): g020-008-r01 reformulated on McMaster-Carr belt parts only. hardware_r14 v2 "
                        "(explicit_v2) with belt systems MM-2MGT-6 / MM-3MGT-9 (sourceable only), carpus belted or "
                        "direct, the R11c suite on seed 0 (front-runners confirmed on seeds 0-2). Breaking strength "
                        "assumed; sustained belt tension unknown.")
    head = ("# Fitness preset R18 (ADR-117): written by docs/studies/mcmaster_r18.py preset. Use with the optimizer\n"
            "# map_elites_hardware, starting from Stage B's candidate g020-008-r01. Bump `version` when you change it.\n")
    PRESET.write_text(head + yaml.safe_dump(p, sort_keys=False, width=120), encoding="utf-8")
    print("wrote", PRESET, len(seeds), "seed bodies")


def _b_candidate(lab: Any) -> str:
    from stagec_r12 import b_candidate

    c = b_candidate(lab, B_CANDIDATE_BODY)
    assert c is not None
    return str(c["id"])


def search(lab: Any, opts: dict[str, str]) -> None:
    """One map_elites_hardware run with hardware_r18 (settings as R14's search). ``--generations``, ``--batch``."""
    params: dict[str, Any] = {"generations": int(opts.get("generations", 1)), "batch_size": int(opts.get("batch", 15)),
                              "vary_geometry": True, "what_if_pulleys": False, "seed_bodies": True,
                              "sigma_init": 0.1, "sigma_iso": 0.05, "hardware_flip": 0.05,
                              "seed": int(opts.get("seed", 0))}
    t0 = time.time()
    job = lab.run_evolve("map_elites_hardware", params, None, None, None, "hardware_r18", candidate=_b_candidate(lab))
    run_id = (job.result or {}).get("run_id")
    print("run", run_id, params, flush=True)
    while True:
        j = lab.jobs.get(job.id) if hasattr(lab.jobs, "get") else job
        if j.status in ("done", "failed", "cancelled"):
            break
        time.sleep(20)
    secs = round(time.time() - t0)
    print(j.status, getattr(j, "error", None), j.result, f"{secs} s", flush=True)
    data = _load()
    data.setdefault("searches", []).append({"label": opts.get("label", ""), "params": params,
                                            "result": j.result, "status": j.status, "seconds": secs})
    _save(data)


def _cands(lab: Any, run_id: str) -> list[dict[str, Any]]:
    return [c for c in lab.registry.list_candidates(run_id) if c.get("status") not in ("infeasible", "failed")]


def _perform(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.hardware import perform_task, screen_task

    if job["kind"] == "screen":
        return screen_task(job["payload"])
    return perform_task(job["payload"])


def confirm(lab: Any, opts: dict[str, str]) -> None:
    """The top ``--top`` bodies of the searches (by their seed-0 fitness) played on seeds 0-2 with the same suite and
    cache (seed 0 is a cache hit), summarised as Stage B summarises a body."""
    from calflab.evolve.hardware import HardwareSettings, summarise
    from calflab.fitness.preset import EvaluationSettings

    data = _load()
    runs = [s["result"]["run_id"] for s in data.get("searches", []) if (s.get("result") or {}).get("run_id")]
    allc = [c for r in runs for c in _cands(lab, r)]
    seen: dict[str, dict[str, Any]] = {}
    for c in sorted(allc, key=lambda c: -float(c.get("fitness") or -1e9)):
        k = json.dumps(c["genome"]["values"], sort_keys=True)
        seen.setdefault(k, c)
    top = list(seen.values())[: int(opts.get("top", 6))]
    run = lab.registry.get_run(runs[-1])
    pre = run.fitness["preset"]
    ev = EvaluationSettings.model_validate({**pre["evaluation"], "seeds": [0, 1, 2]})
    hw = HardwareSettings.model_validate(ev.hardware)
    hw.cache_dir = str(Path(lab.project.path) / ".cache" / "hardware")  # as the run had it: seed 0 is a cache hit
    jobs, index = [], []
    base_pl, _m = base_payload(lab)
    for c in top:
        payload = {"genome": c["genome"], "overrides": run.overrides, "generator": "feral_calf",
                   "generator_params": base_pl["generator_params"], "compile": run.inputs["compile"],
                   "evaluation": ev.model_dump(mode="json"), "hardware": hw.model_dump(mode="json")}
        jobs.append({"kind": "screen", "payload": payload})
        index.append((c["id"], "screen", None))
        for j in range(len(hw.performances)):
            jobs.append({"kind": "perf", "payload": {**payload, "performance": j}})
            index.append((c["id"], "perf", j))
    print(len(top), "bodies,", len(jobs), "tasks", flush=True)
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 15))) as pool:
        outs = list(pool.map(_perform, jobs))
    res: dict[str, Any] = {}
    for c in top:
        scr = next(o for (cid, kind, _j), o in zip(index, outs, strict=True) if cid == c["id"] and kind == "screen")
        perfs = [o for (cid, kind, _j), o in zip(index, outs, strict=True) if cid == c["id"] and kind == "perf"]
        if "plays" not in scr:
            res[c["id"]] = {"error": scr.get("infeasible") or scr.get("error")}
            continue
        s0 = summarise(scr, None, hw, 3)
        s = summarise(scr, perfs if s0["passed_screen"] else None, hw, 3)
        res[c["id"]] = {"seed0_fitness": c.get("fitness"), "seed0_summary": (c.get("metrics") or {}),
                        "summary": s, "genome": c["genome"]["values"]}
        print(c["id"], round(float(c.get("fitness") or 0), 3), "->", s.get("fitness"), s.get("minutes_held"),
              flush=True)
    data["confirm"] = {"bodies": res, "seconds": round(time.perf_counter() - t, 1), "runs": runs}
    _save(data)


# --------------------------------------------------------------------- compare set r18 (step 5)
def _store_one(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.outcomes import BehaviourSpace, play_seed
    from calflab.plugins import load_plugins

    load_plugins()
    rec = play_seed(job["payload"], BehaviourSpace.model_validate(job["space"]), job["params"], 0, job["margin"],
                    judging=True, rollout_path=job["path"])
    return rec


def _store_run(lab: Any, pl: dict[str, Any], title: str, rollout: Path, controller: dict[str, Any], length: float,
               rec: dict[str, Any]) -> str:
    """A ``sim`` run holding a saved rollout (as R16's), tagged ``mcmaster_r18``."""
    import shutil

    from calflab.app.scene import build_scene
    from calflab.evolve.hardware import _build
    from calflab.project.registry import RunRecord

    design, _lib = _build(pl)
    sim_id = lab.registry.new_run_id("sim")
    rdir = lab.registry.run_dir(sim_id)
    rdir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(rollout), rdir / "rollout.npz")
    (rdir / "scene.json").write_text(json.dumps(build_scene(design, lab.state.layers, lab.state.settings)),
                                     encoding="utf-8")
    lab.registry.save_run(RunRecord(
        id=sim_id, kind="sim", title=title, duration_s=rec["wall_s"], seed=0, backend="local",
        inputs={"mcmaster_r18": {"length_s": length, "outcome": rec["outcome"]}, "margin": 0.2,
                "report": {k: v for k, v in rec.items() if k not in ("joints", "outcome")}, "joints": rec["joints"]},
        genome=pl["genome"], overrides=pl["overrides"], controller=controller,
        metrics={"within_limits": rec["within"], "safety_margin": rec["margin"], "closest": rec["closest"],
                 "holds": rec["holds"], "score": rec["outcome"].get("score")},
        artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
        parent=pl.get("stage_c_run"), tags=["mcmaster_r18"]))
    return sim_id


def store(lab: Any, opts: dict[str, str]) -> None:
    """Seed-0 runs of every R16 behaviour per body for ``compare.html?set=r18``. The baseline uses R16's own runs;
    other bodies (``--bodies=``) are played and stored as ``R18 <body> <behaviour>: seed 0``."""
    from calflab.evolve.outcomes import BehaviourSpace, controller_params, play_length
    from diversity_r16 import OUT as R16
    from diversity_r16 import _load as r16load

    _pl, margin = base_payload(lab)
    shown = r16load(R16)["shown"]
    data = _load()
    st = data.setdefault("store", {})
    st[BASE] = {s["key"]: s["run"] for s in shown if s.get("run")}
    names = [n for n in (opts.get("bodies") or "").split(",") if n and n != BASE]
    bs = bodies(lab)
    tmp = Path(sys.argv[1]) / ".cache" / "mcmaster_r18_store"
    tmp.mkdir(parents=True, exist_ok=True)
    for n in names:
        have = st.setdefault(n, {})
        todo = [s for s in shown if s["key"] not in have]
        jobs = [{"payload": bs[n], "space": s["space"], "params": s["params"], "margin": margin,
                 "path": str(tmp / f"{n}_{i}.npz")} for i, s in enumerate(todo)]
        with ProcessPoolExecutor(max_workers=int(opts.get("workers", 15))) as pool:
            recs = list(pool.map(_store_one, jobs))
        for s, job, rec in zip(todo, jobs, recs, strict=True):
            sp = BehaviourSpace.model_validate(s["space"])
            title = s.get("title") or s["cell_label"]
            have[s["key"]] = _store_run(lab, bs[n], f"R18 {n} {title} [{s['source']}]: seed 0", Path(job["path"]),
                                        {"key": "outcome_motion", "params": controller_params(sp, s["params"])},
                                        play_length(sp, s["params"], True), rec)
        print(n, len(todo), "stored", flush=True)
        _save(data)
    _save(data)


# --------------------------------------------------------------------- tables
def _f(v: Any, nd: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def fits_csv(data: dict[str, Any]) -> list[Path]:
    """Every fitting pair x length per drive, one CSV each (``mcmaster_r18_fits_<drive>.csv``)."""
    import csv

    out = []
    cols = ["system", "driver_teeth", "driven_teeth", "ratio", "length_mm", "belt_teeth", "belt_part", "pulley_parts",
            "c_mm", "pulley_gap_mm", "teeth_in_mesh", "wrap_deg", "servo_span_mm", "servo_check", "clearance",
            "unknown"]
    for d, r in (data.get("fits") or {}).items():
        p = OUT.with_name(f"mcmaster_r18_fits_{d}.csv")
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for row in r["fits"]:
                w.writerow([("/".join(row[c]) if isinstance(row[c], list) and c != "servo_span_mm" else
                             ("-".join(f"{x:g}" for x in row[c]) if c == "servo_span_mm" and row[c] else
                              ("; ".join(row[c]) if c == "unknown" else row[c]))) for c in cols])
        out.append(p)
    return out


def _cell_rows(data: dict[str, Any], a: str, b: str) -> list[str]:
    """Per R16 behaviour: holds / within (excl. sustained belt tension) on all seeds, worst margin, binding limit, and
    per drive the highest belt peak / mean and time above the levels, for body a vs body b."""
    from collections import defaultdict

    rp = data.get("replay") or {}
    by: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for body in (a, b):
        for r in rp.get(body, []):
            by[r["key"]][body].append(r)
    lines = [f"| behaviour | {a}: holds / within* 3 seeds | margin* | binds | {b}: holds / within* | margin* | binds | "
             + " | ".join(f"{d} peak/mean N ({a} -> {b})" for d in ("stifle", "hock", "carpus"))
             + f" | most time >{LEVELS[0]:g}/{LEVELS[1]:g}/{LEVELS[2]:g}/{LEVELS[3]:g} N ({b}) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]

    def agg(rs: list[dict[str, Any]]) -> tuple[str, str, str]:
        if not rs:
            return "-", "-", "-"
        h = all(r["holds"] for r in rs)
        w = all(r["within_excl"] for r in rs)
        m = min((r["margin_excl"] for r in rs if r["margin_excl"] is not None), default=None)
        worst = min(rs, key=lambda r: r["margin_excl"] if r["margin_excl"] is not None else 9)
        bnd = worst.get("binding") or {}
        return (f"{'yes' if h else 'no'} / {'yes' if w else 'no'}", _f(m),
                f"{bnd.get('joint') or '-'} {bnd.get('limit') or ''}".strip())

    def belt(rs: list[dict[str, Any]], drive: str) -> tuple[float | None, float | None]:
        vals = [(v["belt_peak_n"], v["belt_mean_n"]) for r in rs for j, v in (r.get("belts") or {}).items()
                if j.endswith(drive)]
        return (max(v[0] for v in vals), max(v[1] for v in vals)) if vals else (None, None)

    for key in sorted(by):
        ra, rb = by[key][a], by[key][b]
        ca, cb = agg(ra), agg(rb)
        cells = []
        for d in ("stifle", "hock", "carpus"):
            pa, ma = belt(ra, d)
            pb, mb = belt(rb, d)
            cells.append(f"{_f(pa, 0)}/{_f(ma, 0)} -> {_f(pb, 0)}/{_f(mb, 0)}")
        above = [max((v["above"][f"{lv:g}"] for r in rb for v in (r.get("belts") or {}).values()), default=None)
                 for lv in LEVELS]
        lines.append(f"| {key} | {ca[0]} | {ca[1]} | {ca[2]} | {cb[0]} | {cb[1]} | {cb[2]} | " + " | ".join(cells)
                     + " | " + "/".join(_f(x) for x in above) + " |")
    return lines


def counts(data: dict[str, Any], body: str) -> dict[str, int]:
    """Behaviours (of the R16 repertoire) that hold, are within limits (all, and excluding sustained belt tension) on
    every seed."""
    from collections import defaultdict

    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in (data.get("replay") or {}).get(body, []):
        by[r["key"]].append(r)
    return {"behaviours": len(by), "holds": sum(all(r["holds"] for r in v) for v in by.values()),
            "within": sum(all(r["within"] for r in v) for v in by.values()),
            "within_excl": sum(all(r["within_excl"] for r in v) for v in by.values()),
            "holds_and_within_excl": sum(all(r["holds"] and r["within_excl"] for r in v) for v in by.values()),
            "full_cells_within_excl": sum(all(r["holds"] and r["within_excl"] for r in v) for k, v in by.items()
                                          if k.startswith("full:"))}


def summary(lab: Any, opts: dict[str, str]) -> None:
    data = _load()
    paths = fits_csv(data)
    L = ["# R18 tables (generated by `docs/studies/mcmaster_r18.py summary`)", "",
         "Breaking strength assumed (researcher's assumption, 51 lbf per 1/8 in of width); sustained belt tension "
         "unknown (no allowable working tension). *within\\** = within every limit at margin 0.2 **excluding sustained "
         "belt tension**.", ""]
    L += ["## 1. McMaster choices that fit each drive of g020-008-r01", ""]
    for d, r in (data.get("fits") or {}).items():
        rows = r["fits"]
        L.append(f"### {d} ({r['layout']['segment']}, {r['layout']['segment_length_mm']:g} mm; servo window "
                 f"{r['layout']['window_mm'][0]:g}-{r['layout']['window_mm'][1]:g} mm; now "
                 f"{r['current']['choice']['pulleys']}, {r['current']['ratio']:g}:1, C {r['current']['c_mm']:.1f} mm)")
        L.append("")
        L.append(f"{len(rows)} pair x length choices pass every check (all in `{paths[0].name.replace('stifle', d)}`); "
                 "failed: " + ", ".join(f"{k} {v}" for k, v in r["failed_checks"].items()) + ".")
        L.append("")
        L.append("| system | pair (driver/driven T) | ratio | lengths that fit | C range mm | min teeth in mesh | "
                 "clearance unknown |")
        L.append("|---|---|---|---|---|---|---|")
        groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        for x in rows:
            groups.setdefault((x["system"], x["driver_teeth"], x["driven_teeth"]), []).append(x)
        for (s, a, b), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[1][0]["ratio"], kv[0][1])):
            if opts.get("all") or abs(g[0]["ratio"] - r["current"]["ratio"]) <= 0.35:
                L.append(f"| {s} | {a}/{b} | {g[0]['ratio']:.3f} | {len(g)} | {min(x['c_mm'] for x in g):.1f}-"
                         f"{max(x['c_mm'] for x in g):.1f} | {min(x['teeth_in_mesh'] for x in g):.1f} | "
                         f"{sum(1 for x in g if x['clearance'] == 'unknown' or x['servo_check'] == 'unknown')} |")
        L.append(f"\n(pairs within 0.35 of the current ratio shown; {len(groups)} pairs fit in all.)\n")
    sw = data.get("swap") or {}
    if sw:
        L += ["## 2. The closest swap g020-008-r01-mc", "",
              "| drive | from | ratio | C mm | to | ratio | belt | C mm | gap mm | teeth in mesh | parts |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for d, p in sw.items():
            t = p["to"]
            L.append(f"| {d} | {p['from']['pulleys']} on {p['from']['length']} | {p['from_ratio']:g} | "
                     f"{p['from_c_mm']:.1f} | {t['pulleys']} | {t['ratio']:g} | {t['length_mm']:g} mm ({t['belt_teeth']} "
                     f"T) | {t['c_mm']:.1f} | {t['pulley_gap_mm']:.1f} | {t['teeth_in_mesh']:.1f} | "
                     f"{t['belt_part']}, {'/'.join(t['pulley_parts'] or [])} |")
        L.append("")
    ms = data.get("mass") or {}
    if ms:
        L += ["## 3. Mass", "", "| body | total g | vs baseline | parts g | headroom g | missing masses |",
              "|---|---|---|---|---|---|"]
        b0 = ms.get(BASE, {}).get("total_g")
        for n, m in ms.items():
            mb = m["breakdown"]
            miss = mb.get("missing") or mb.get("missing_items") or []
            L.append(f"| {n} | {m['total_g']:.1f} | {m['total_g'] - b0:+.1f} | {_f(mb.get('parts_g'), 1)} | "
                     f"{_f(mb.get('headroom_g'), 1)} | {len(miss) if isinstance(miss, list) else miss} |")
        L.append("")
    ld = data.get("loads") or {}
    if ld:
        L += ["## 4. Statics and loads", "", "Standing pose (statics): servo torque, joint torque and belt tension per "
              "belted joint (left side).", "", "| body | joint | joint N*m | servo N*m | ratio | belt N | of breaking |",
              "|---|---|---|---|---|---|---|"]
        for n, rows in ld["statics"].items():
            for j, r in rows.items():
                if r["belt_n"] is not None and (j.startswith("hl.") or j.startswith("fl.")):
                    L.append(f"| {n} | {j} | {r['joint_nm']:.3f} | {r['servo_nm']:.3f} | {r['ratio']:g} | "
                             f"{r['belt_n']:.1f} | {_f(r['peak_of_breaking'], 3)} |")
        L += ["", "Plays (seed 0): per belted drive, both sides, the larger.", "",
              "| play | body | within* | margin* | drive | servo peak / mean N*m | joint peak N*m | belt peak / mean N | "
              f"peak of breaking | most of 2 s above {'/'.join(f'{x:g}' for x in LEVELS)} N |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        names = {v: k for k, v in ld["which"].items()}
        for r in sorted(ld["plays"], key=lambda r: (r["key"], r["body"])):
            for d in ("stifle", "hock", "carpus", "shoulder"):
                vs = [v for j, v in r["belts"].items() if j.endswith(d)]
                if not vs:
                    continue
                v = max(vs, key=lambda v: v["belt_peak_n"])
                L.append(f"| {names.get(r['key'], r['key'])} | {r['body']} | {_f(r['within_excl'])} | "
                         f"{_f(r['margin_excl'])} | {d} | {v['servo_peak_nm']:.2f} / {v['servo_mean_nm']:.2f} | "
                         f"{v['joint_peak_nm']:.2f} | {v['belt_peak_n']:.0f} / {v['belt_mean_n']:.0f} | "
                         f"{_f(v['peak_of_breaking'], 3)} | {'/'.join(_f(v['above'][f'{x:g}']) for x in LEVELS)} |")
        L.append("")
    rp = data.get("replay") or {}
    if rp:
        L += ["## 5. The R16 repertoire replayed (seeds 0-2, 30 s, margin 0.2)", "",
              "| body | behaviours | hold (all seeds) | within, all limits | within* | hold and within* | full-search "
              "cells hold and within* |", "|---|---|---|---|---|---|---|"]
        for n in rp:
            c = counts(data, n)
            L.append(f"| {n} | {c['behaviours']} | {c['holds']} | {c['within']} | {c['within_excl']} | "
                     f"{c['holds_and_within_excl']} | {c['full_cells_within_excl']} |")
        L.append("")
        for other in [n for n in rp if n != BASE]:
            L += [f"### {BASE} vs {other}", ""] + _cell_rows(data, BASE, other) + [""]
    cf = data.get("confirm") or {}
    if cf:
        L += ["## 6. Reformulation search: front-runners confirmed on seeds 0-2", "",
              "| candidate | seed-0 fitness | fitness (3 seeds) | minutes held* | trot mm/s | screen held | cost | "
              "stoppers |", "|---|---|---|---|---|---|---|---|"]
        for cid, r in cf["bodies"].items():
            s = r.get("summary") or {}
            L.append(f"| {cid} | {_f(r.get('seed0_fitness'), 3)} | {_f(s.get('fitness'), 3)} | "
                     f"{s.get('minutes_held')}/{s.get('minutes_of')} | {_f(s.get('trot_speed_mm_s'), 0)} | "
                     f"{s.get('screen_held')}/{s.get('screen_plays')} | {_f((s.get('costs') or {}).get('cost_index'), 2)}"
                     f" | {', '.join(f'{a} {b} ({c})' for a, b, c in (s.get('stoppers') or [])[:3])} |")
        L.append("")
    TABLES.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", TABLES, *[p.name for p in paths])


# --------------------------------------------------------------------- main
def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj, stage = Path(sys.argv[1]), sys.argv[2]
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    load_plugins()
    lab = Lab.open(proj, create=False)
    try:
        globals()[stage](lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
