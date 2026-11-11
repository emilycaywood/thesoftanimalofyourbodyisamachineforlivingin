"""Session R14 (ADR-108): the five candidate bodies at their real weight.

Every body so far was evolved and judged with ADR-068's counting (unentered parts 0 g), 1.30-1.42 kg as simulated.
The gene ``mass_model`` = ``explicit_v1`` adds the researcher's masses of 2026-11-11 (pulley axles, servo horns,
16 x 12 mm CF leg tubes at 1.65 g/cm3 in place of the tube-gene estimate, 270 g of packs, 300 g PROVISIONAL headroom).

Stages:

* ``breakdown``: each body built both ways; totals and the breakdown by kind of part -> ``mass_r14.json``.
* ``judge``: the R11c suite at explicit_v1 (Stage B's preset ``hardware_r11c``: seeds 0-2, friction 0.7-1.1,
  mass x0.95-1.05, margin 0.2, torque-speed servos): the screen (trot grid, walk, turn, the 10 s lie_rise), each
  body's own Stage C behaviours for 60 s on every seed, and both stored lie_rise versions of R13
  (``lierise_r13.json`` ``bodies`` = the compare page's "lie_rise (evolved)", and ``bodies_lying``) over the whole
  motion plus settle. Same workers as ``stagec_r12.py`` and ``calflab.evolve.lie_rise``; nothing is re-evolved.
* ``report``: markdown tables against the stored as_entered numbers (``stagec_r12.json``, ``lierise_r13.json``).
* ``preset``: ``config/fitness/hardware_r14.yaml`` = hardware_r11c v2 seeded with the ``--top`` best-holding bodies.
* ``estimate``: wall time per generation from the measured rates. ``search``: start it (``--generations``,
  ``--batch``); only with the researcher's budget.

Run:  python docs/studies/mass_r14.py <project dir> breakdown|judge|report|preset|estimate|search [--workers=12]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

BODIES = ["working", "g007-002", "g009-000", "g012-009", "g020-008-r01"]
MODEL = "explicit_v1"
OUT = Path("docs/studies/mass_r14.json")
STAGEC = Path("docs/studies/stagec_r12.json")
LIERISE = Path("docs/studies/lierise_r13.json")

#: how a breakdown item is grouped (first match on the geom id)
KINDS = [("servos", lambda i: i.startswith("act.") and i.endswith(".motor")),
         ("servo horns", lambda i: i.startswith("act.") and i.endswith(".horn")),
         ("pulley axles", lambda i: i.startswith("belt.") and i.endswith(".axle")),
         ("leg tubes", lambda i: i.startswith("leg.") and i.endswith(".tube")),
         ("batteries", lambda i: i.startswith("elec.battery")),
         ("headroom (PROVISIONAL)", lambda i: i == "trunk.headroom"),
         ("head + neck", lambda i: i.startswith("head.")),
         ("rails", lambda i: i.startswith("trunk.rail")),
         ("pulleys", lambda i: i.startswith("belt.") and (i.endswith(".driver") or i.endswith(".driven")))]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _kind(gid: str) -> str:
    return next((k for k, f in KINDS if f(gid)), "other")


def payloads(lab: Any, model: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per body the worker payload of R13 (Stage C run's genome, Stage B's generator and compile settings), with
    ``mass_model`` set to ``model``."""
    from lierise_r13 import body_payloads

    out, ev = body_payloads(lab, BODIES)
    for p in out.values():
        p["genome"]["values"] = {**p["genome"]["values"], "mass_model": model}
    return out, ev


def breakdown_of(payload: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.hardware import _build
    from calflab.model.mass import mass_breakdown

    design, lib = _build(payload)
    spec = design.spec
    mb = mass_breakdown(spec, lib)
    kinds: dict[str, float] = {}
    count: dict[str, int] = {}
    for r in mb["bodies"]:
        for it in r["items"]:
            k = _kind(it["id"])
            kinds[k] = round(kinds.get(k, 0.0) + it["mass_g"], 2)
            count[k] = count.get(k, 0) + 1
    com = spec.center_of_mass()
    tubes = {r["body"]: next((it["mass_g"] for it in r["items"] if it["id"].endswith(".tube")), None)
             for r in mb["bodies"] if r["body"].startswith("leg.")}
    return {"total_g": round(spec.total_mass_g(), 2), "breakdown_total_g": mb["total_g"],
            "parts_g": mb.get("parts_g"), "headroom_g": mb.get("headroom_g"), "by_source_g": mb["by_source_g"],
            "by_kind_g": kinds, "count": count, "com_mm": [round(v, 1) for v in com], "tubes_g": tubes,
            "servos": {k: v["component"] for k, v in spec.metadata["feral"]["servos"].items()},
            "belted": spec.metadata["feral"]["belted"],
            "missing": [f"{m['label']} x{m['qty']}" for m in mb["missing"]]}


def breakdown(lab: Any) -> None:
    old, _ = payloads(lab, "as_entered")
    new, _ = payloads(lab, MODEL)
    data = _load(OUT) if OUT.is_file() else {}
    data["breakdown"] = {b: {"as_entered": breakdown_of(old[b]), MODEL: breakdown_of(new[b]),
                             "stage_c_run": old[b]["stage_c_run"]} for b in BODIES}
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
    for b, v in data["breakdown"].items():
        print(b, v["as_entered"]["total_g"], "->", v[MODEL]["total_g"], v[MODEL]["by_kind_g"], flush=True)


# ---------------------------------------------------------------------------------------------------- judging
def lie_task(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.lie_rise import task

    r = task(job)
    keep = ("within", "fell", "margin", "closest", "violations", "lying_fraction", "risen", "tipped", "excess",
            "length_s", "cached", "moves")
    return {"body": job["body"], "version": job["version"], "seed": job["seed"], **{k: r.get(k) for k in keep}}


def judge(lab: Any, opts: dict[str, str]) -> None:
    from calflab.design import genome_definition
    from calflab.evolve.hardware import HardwareSettings, Performance, baseline_of, summarise
    from calflab.evolve.lie_rise import LieRiseSearch, body_keys, job_key, lay_down
    from stagec_r12 import B_RUN, perform, screen

    model = opts.get("model", MODEL)
    pls, ev = payloads(lab, model)
    stagec = _load(STAGEC)["bodies"]
    lr = _load(LIERISE)
    brun = lab.registry.get_run(B_RUN)
    gdef = genome_definition("feral_calf")
    hw0 = HardwareSettings.model_validate(ev["hardware"])
    hw0.cache_dir = str(Path(lab.project.path) / ".cache" / "hardware")
    # the cost baseline: Stage B's start (the working body) at the same mass model, as the optimizer would set it
    start = {**gdef.complete(brun.genome["values"]), "mass_model": model}
    base_payload = {**next(iter(pls.values())), "genome": {"definition": gdef.name, "version": gdef.version,
                                                           "values": start}}
    from calflab.evolve.hardware import _build
    hw0.baseline = baseline_of(_build(base_payload)[0].spec, start)
    screens, perfs, lies = [], [], []
    margin = float(ev["hardware"]["margin"])
    lie_cache = str(Path(lab.project.path) / ".cache" / "lie_rise")
    for body in BODIES:
        p = pls[body]
        sc_entry = stagec[body]
        hw = hw0.model_copy(deep=True)
        hw.performances = []
        new_perfs = []
        cands = {c["id"]: c for c in lab.registry.list_candidates(p["stage_c_run"])}
        for ref in sc_entry["perf_refs"]:
            cid = f"{p['stage_c_run']}-{ref['ref'].split(':', 1)[1]}"
            new_perfs.append({"label": ref["label"], "ref": ref["ref"], "controller": cands[cid]["controller"]})
        hw.performances = [Performance(**x) for x in new_perfs]
        payload_hw = hw.model_dump(mode="json")
        common = {**{k: v for k, v in p.items() if k != "stage_c_run"}, "body": body}
        screens.append({**common, "hardware": payload_hw})
        perfs += [{**common, "hardware": payload_hw, "perf": x} for x in new_perfs]
        keys = body_keys(common)
        for version in ("bodies", "bodies_lying"):
            ent = (lr.get(version) or {}).get(body)
            if not ent:
                continue
            s = LieRiseSearch.model_validate(ent["search"])
            params = ent["best"]["params"]
            for seed in ev["seeds"]:
                lies.append({"payload": common, "params": params, "seed": seed, "margin": margin,
                             "settle_s": s.settle_s, "cache": lie_cache, "body": body, "version": version,
                             "depth": s.lying_depth,
                             "key": job_key(keys[0], params, seed, keys[1], margin, s.settle_s)})
    print(f"{len(screens)} screens, {len(perfs)} behaviours x {len(ev['seeds'])} seeds, {len(lies)} lie_rise plays",
          flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(int(opts.get("workers", 12))) as pool:
        lf = [pool.submit(lie_task, j) for j in lies]
        sf = [pool.submit(screen, s) for s in screens]
        pf = [pool.submit(perform, x) for x in perfs]
        sc = [f.result() for f in sf]
        print(f"screens done {time.time() - t0:.0f} s", flush=True)
        li = [f.result() for f in lf]
        print(f"lie_rise done {time.time() - t0:.0f} s", flush=True)
        pr = [f.result() for f in pf]
    print(f"behaviours done {time.time() - t0:.0f} s", flush=True)
    out: dict[str, Any] = {}
    for s in sc:
        body = s["body"]
        mine = [x for x in pr if x["body"] == body]
        hw = HardwareSettings.model_validate(next(x["hardware"] for x in screens if x["body"] == body))
        summ = summarise(s, mine, hw, len(ev["seeds"]))
        lie = {}
        for version in ("bodies", "bodies_lying"):
            rows = [r for r in li if r["body"] == body and r["version"] == version]
            if not rows:
                continue
            depth = next(j["depth"] for j in lies if j["body"] == body and j["version"] == version)
            lie[version] = {"worst": round(min(-1.0 if r["margin"] is None else r["margin"] for r in rows), 4),
                            "held": all(r["within"] and lay_down(r, depth) for r in rows),
                            "seeds": rows}
        out[body] = {"summary": summ, "lie_rise": lie,
                     "behaviours": [{"label": x["label"], "seeds": [
                         {k: y.get(k) for k in ("seed", "within", "fell", "margin", "closest", "violations",
                                                "played_s", "states")}
                         | {"qom": y["movement"].get("quantity_of_motion_deg_s")} for y in x["seeds"]]}
                         for x in mine]}
    data = _load(OUT) if OUT.is_file() else {}
    data["judge" if model == MODEL else f"judge_{model}"] = {"model": model, "stage_b_run": B_RUN, "wall_s": round(time.time() - t0, 1), "bodies": out}
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())
    print("wrote", OUT, flush=True)


# ---------------------------------------------------------------------------------------------------- report
def _m(x: Any) -> str:
    return "-" if x is None else f"{x:+.2f}"


def _held3(s: dict[str, Any]) -> int:
    return sum(1 for r in s["performances"] if r["held"] == r["of"])


def _scr(s: dict[str, Any], play: str) -> float | None:
    return (s["screen"].get(play) or {}).get("worst_margin")


def report() -> None:
    data = _load(OUT)
    stagec = _load(STAGEC)["bodies"]
    lr = _load(LIERISE)
    bd = data.get("breakdown") or {}
    if bd:
        kinds = [k for k, _ in KINDS] + ["other"]
        print("| body | as simulated g | " + " | ".join(kinds) + f" | {MODEL} total g | of it real parts | CoM x/z mm |")
        print("|---|" + "---|" * (len(kinds) + 4))
        for b, v in bd.items():
            o, n = v["as_entered"], v[MODEL]
            cells = []
            for k in kinds:
                a, c = o["by_kind_g"].get(k, 0.0), n["by_kind_g"].get(k, 0.0)
                cells.append(f"{c:.0f}" if abs(a - c) < 0.05 else f"{a:.0f} -> {c:.0f}")
            print(f"| {b} | {o['total_g']:.0f} | " + " | ".join(cells)
                  + f" | **{n['total_g']:.0f}** | {n['parts_g']:.0f} | {o['com_mm'][0]:.0f}/{o['com_mm'][2]:.0f}"
                  f" -> {n['com_mm'][0]:.0f}/{n['com_mm'][2]:.0f} |")
    j = (data.get("judge") or {}).get("bodies") or {}
    if not j:
        return
    print("\n| body | behaviours held 3/3 | minutes | trot mm/s (fastest held) | trots held | walk | turn | "
          "lie_rise 10 s screen | lie_rise evolved (R13) | lie_rise evolved, lying pose | stoppers |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for b in BODIES:
        if b not in j:
            continue
        s0, s1 = stagec[b]["summary"], j[b]["summary"]
        lie0 = {v: ((lr.get(v) or {}).get(b) or {}).get("best") or {} for v in ("bodies", "bodies_lying")}
        lie1 = j[b]["lie_rise"]

        def pair(a: Any, c: Any, f: Any = _m) -> str:
            return f"{f(a)} -> **{f(c)}**"

        def lie(v: str, lie0: dict[str, Any] = lie0, lie1: dict[str, Any] = lie1) -> str:
            a = lie0[v].get("worst")
            c = (lie1.get(v) or {}).get("worst")
            return pair(a, c) + (" holds" if (lie1.get(v) or {}).get("held") else "")

        print(f"| {b} | {_held3(s0)} -> **{_held3(s1)}** of {len(s1['performances'])} | "
              f"{s0['minutes_held']}/{s0['minutes_of']} -> **{s1['minutes_held']}/{s1['minutes_of']}** | "
              f"{s0['trot_speed_mm_s']:.0f} -> **{s1['trot_speed_mm_s']:.0f}** ({s1['fastest_trot'] or '-'}) | "
              f"{len(s0.get('trots_held') or [])} -> **{len(s1.get('trots_held') or [])}** | "
              f"{pair(_scr(s0, 'walk'), _scr(s1, 'walk'))} | {pair(_scr(s0, 'turn'), _scr(s1, 'turn'))} | "
              f"{pair(_scr(s0, 'lie_rise'), _scr(s1, 'lie_rise'))} | {lie('bodies')} | {lie('bodies_lying')} | "
              + "; ".join(f"{jn} {lim} ({n})" for jn, lim, n in s1["stoppers"][:3]) + " |")
    for b in BODIES:
        if b not in j:
            continue
        s0, s1 = stagec[b]["summary"], j[b]["summary"]
        print(f"\n#### {b}\n")
        print("| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |")
        print("|---|---|---|---|")
        for a, c in zip(s0["performances"], s1["performances"], strict=True):
            print(f"| {c['label']} | {a['held']}/{a['of']} {_m(a['worst_margin'])} | **{c['held']}/{c['of']} "
                  f"{_m(c['worst_margin'])}** | {', '.join(str(x) for x in c['closest'])} |")
        for v, name in (("bodies", "lie_rise evolved"), ("bodies_lying", "lie_rise evolved, lying pose")):
            rows = (j[b]["lie_rise"].get(v) or {}).get("seeds") or []
            if rows:
                print(f"\n{name}: " + "; ".join(
                    f"seed {r['seed']} {_m(r['margin'])} {'fell' if r.get('fell') else ''} closest {r.get('closest')}"
                    for r in rows))


# ---------------------------------------------------------------------------------------------------- next search
PRESET = Path("config/fitness/hardware_r14.yaml")
#: measured: Stage B (ADR-104) 10.8 h for 19 generations of 15 on 7 workers = 34 min per generation (screen + 11
#: behaviours x 3 seeds for those passing); R13 Stage 3 (budget S gate) about 50 min per generation of 14
MIN_PER_15 = {"hardware_r11c": 34.0, "hardware_r13": 50.0 * 15 / 14}


def _rank(data: dict[str, Any]) -> list[tuple[str, int, int, float]]:
    """Bodies by how well they hold at explicit_v1: behaviours held 3/3, minutes, trot."""
    j = data["judge"]["bodies"]
    rows = [(b, _held3(j[b]["summary"]), j[b]["summary"]["minutes_held"], j[b]["summary"]["trot_speed_mm_s"])
            for b in j]
    return sorted(rows, key=lambda r: (-r[1], -r[2], -r[3]))


def write_preset(lab: Any, opts: dict[str, str]) -> dict[str, Any]:
    """config/fitness/hardware_r14.yaml: hardware_r11c v2 (explicit_v1, Stage B's judging and space) seeded with the
    ``--top`` (3) bodies that hold best at explicit_v1, each as is plus its shoulder-spring, belted-shoulder and
    carpus-spring variants (as Stage A / R13 seeded generation 0)."""
    import yaml
    from calflab.design import genome_definition
    from stagec_r12 import B_RUN, b_candidate

    data = _load(OUT)
    top = [r[0] for r in _rank(data)][: int(opts.get("top", 3))]
    d = yaml.safe_load(Path("config/fitness/hardware_r11c.yaml").read_text(encoding="utf-8"))
    gdef = genome_definition("feral_calf")
    base = gdef.complete(lab.registry.get_run(B_RUN).genome["values"])
    seeds = []
    for body in top:
        c = b_candidate(lab, body)
        vals = gdef.complete(c["genome"]["values"]) if c else dict(base)
        own = {k: v for k, v in vals.items() if base.get(k) != v and k != "mass_model"}
        sh = bool(vals.get("spring_shoulder"))
        for suffix, extra in (("", {}), (f" + shoulder spring {'off' if sh else 'on'}", {"spring_shoulder": not sh}),
                              (" + belted shoulder", {"shoulder_belt": True}), (" + carpus spring",
                                                                                {"spring_carpus": True})):
            if extra and all(vals.get(k) == v for k, v in extra.items()):
                continue
            seeds.append({"label": body + suffix, "note": f"held best at explicit_v1 (R14, ADR-108){suffix}",
                          "values": {**own, **extra}})
    hw = d["evaluation"]["hardware"]
    hw["seeds_bodies"] = seeds
    model = opts.get("model", "explicit_v2")  # ADR-109: the Flywoo pack
    hw["mass_model"] = model
    d["name"], d["version"] = "hardware_r14", int(opts.get("version", 2))
    d["description"] = (f"R14 (ADR-108): hardware_r11c v2 (bodies at their real weight, mass_model {model}) seeded "
                        f"with the bodies that hold best at that weight: {', '.join(top)}, each with its shoulder "
                        "spring switched, its shoulder belted and its carpus spring on.")
    head = ("# Fitness preset R14 (ADR-108): written by docs/studies/mass_r14.py preset. Use with the optimizer\n"
            "# map_elites_hardware. Bump `version` whenever you change it.\n")
    PRESET.write_bytes((head + yaml.safe_dump(d, sort_keys=False, width=118, allow_unicode=True)).encode("utf-8"))
    print("wrote", PRESET, "seeds", [s["label"] for s in seeds])
    return d


def estimate(opts: dict[str, str]) -> None:
    """Wall time per generation and for N generations, from the measured rates (an upper bound: heavier bodies that
    fail the screen play nothing else)."""
    batch = int(opts.get("batch", 15))
    print("| preset | per generation of", batch, "| 5 generations | 10 generations | 20 generations |")
    print("|---|---|---|---|---|")
    for name, m15 in MIN_PER_15.items():
        g = m15 * batch / 15.0
        print(f"| {name} v2 | {g:.0f} min | {5 * g / 60:.1f} h | {10 * g / 60:.1f} h | {20 * g / 60:.1f} h |")


def search(lab: Any, opts: dict[str, str]) -> None:
    """The seeded search with preset hardware_r14 (run ``preset`` first). Settings as R11c's Stage B."""
    params: dict[str, Any] = {"generations": int(opts.get("generations", 1)), "batch_size": int(opts.get("batch", 15)),
                              "vary_geometry": True, "what_if_pulleys": False, "seed_bodies": True,
                              "sigma_init": 0.1, "sigma_iso": 0.05, "hardware_flip": 0.05,
                              "seed": int(opts.get("seed", 0))}
    t0 = time.time()
    job = lab.run_evolve("map_elites_hardware", params, None, None, None, opts.get("preset", "hardware_r14"))
    print("run", (job.result or {}).get("run_id"), params, flush=True)
    while True:
        j = lab.jobs.get(job.id) if hasattr(lab.jobs, "get") else job
        if j.status in ("done", "failed", "cancelled"):
            break
        time.sleep(30)
    print(j.status, getattr(j, "error", None), j.result, f"{time.time() - t0:.0f} s", flush=True)


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
        if stage == "breakdown":
            breakdown(lab)
        elif stage == "judge":
            judge(lab, opts)
        elif stage == "preset":
            write_preset(lab, opts)
        elif stage == "search":
            search(lab, opts)
    finally:
        close = getattr(lab, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
