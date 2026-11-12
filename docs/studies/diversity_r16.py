"""Session R16 (ADR-112): what can g020-008-r01 do? A quality-diversity search on one body, and probes.

The body is fixed: g020-008-r01 at mass_model explicit_v2 (2074 g), built as ``outcomes_r15.py`` builds it (its
Stage C run's genome, Stage B's generator and compile settings). Nothing of the body, the catalogs or the library
changes.

Stages:

* ``smoke``: version 2 of ``outcome_motion`` with its defaults plays R15's trot exactly; one free play.
* ``pilot``: MAP-Elites (``calflab.evolve.qd``) from the starting points (``starts``), ``--iters`` batches of
  ``--batch``; then every elite re-judged at 30 s on seeds 0-2. Writes ``diversity_r16.json`` (``pilot``).
* ``probe_trot``, ``probe_gaits``: the same search on the rhythm alone, from trots / from other gaits.
* ``probe_lie``: lying down searched by outcome (R15's ``lie``) with the wider controller; ``lie_grid``: the lying
  posture swept to see what loads the hind stifle.
* ``store``: each distinct elite (and each probe's findings) played on seed 0 at the judging length and saved as a
  ``sim`` run; ``compare.html?set=r16`` reads them.
* ``report``: markdown tables (``diversity_r16_tables.md``); ``estimate``: the full search at three budgets.

Run:  python docs/studies/diversity_r16.py <project dir> <stage> [--workers=14] [--iters=30] [--batch=28]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path("docs/studies/diversity_r16.json")
TABLES = Path("docs/studies/diversity_r16_tables.md")
R15 = Path("docs/studies/outcomes_r15.json")
BODY = "g020-008-r01"
MODEL = "explicit_v2"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save(data: dict[str, Any]) -> None:
    OUT.write_bytes(json.dumps(data, indent=1, default=float).encode())


def payload(lab: Any) -> tuple[dict[str, Any], float]:
    from outcomes_r15 import payloads

    pl, ev = payloads(lab, [BODY], MODEL)
    return pl[BODY], float(ev["hardware"]["margin"])


def r15_best() -> dict[str, dict[str, Any]]:
    """R15's best version of each behaviour on this body (its own space's fixed numbers included)."""
    from calflab.evolve.outcomes import BehaviourSpace, controller_params

    d = _load(R15)["pilot"][BODY]
    return {b: controller_params(BehaviourSpace.model_validate(r["space"]), r["best"]["params"]) for b, r in d.items()}


def starts() -> tuple[list[dict[str, Any]], list[str]]:
    """The starting points (ADR-112): R15's four versions on this body; R13's evolved lie_rise for it; the primitives
    the R7 / Stage C generators play (stand, weight shifts, the walk, turning, the trot at R11c's grid corners)."""
    from calflab.control.outcome import from_feral_trot, from_feral_walk
    from calflab.evolve.outcomes import warm_starts
    from outcomes_r15 import lie_versions

    out: list[dict[str, Any]] = []
    names: list[str] = []
    for b, p in r15_best().items():
        out.append(p)
        names.append(f"R15 {b}")
    for i, p in enumerate(warm_starts("lie", lie_versions(BODY))[1:]):
        out.append(p)
        names.append(f"R13 lie_rise {i + 1}")
    out.append({})
    names.append("stand")
    for sign, side in ((1, "left"), (-1, "right")):  # Stage C's shift_hl / shift_hr: the hind end over one side
        out.append({"side_abd": 6.0 * sign, "side_from_s": 1.0, "side_s": 1.5})
        names.append(f"weight shift {side}")
    out.append(from_feral_walk())
    names.append("walk (feral)")
    out.append(from_feral_walk(cycle_s=4.0, stride=0.0, turn=1.0))
    names.append("turn in place (feral walk)")
    for c, st in ((0.4, 2.0), (0.4, 0.5), (0.6, 1.0), (0.6, 2.0), (0.5, 1.5)):
        out.append(from_feral_trot(cycle_s=c, stride=st, lift=0.6))
        names.append(f"trot {c}/{st}")
    return out, names


def _pool(workers: int) -> tuple[ProcessPoolExecutor, Any]:
    pool = ProcessPoolExecutor(max_workers=workers)

    def map_fn(fn: Any, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(pool.map(fn, jobs))

    return pool, map_fn


def smoke(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.outcomes import BehaviourSpace, play_seed
    from calflab.evolve.qd import free_space

    pl, margin = payload(lab)
    r = _load(R15)["pilot"][BODY]["trot"]
    sp = BehaviourSpace.model_validate(r["space"])
    rec = play_seed(pl, sp, r["best"]["params"], 0, margin, judging=True)
    want = next(s for s in r["best"]["seeds"] if s["seed"] == 0)
    print("trot v2:", rec["outcome"]["speed_mm_s"], rec["margin"], "R15:", want["outcome"]["speed_mm_s"], want["margin"])
    t = time.perf_counter()
    f = play_seed(pl, free_space(), {}, 0, margin)
    o = f["outcome"]
    print("free stand:", {k: o.get(k) for k in ("d_class", "d_speed_mm_s", "d_turn_deg_s", "height_low", "kneel_bw",
                                              "score", "gates")}, f["within"], f["rank"],
          round(time.perf_counter() - t, 1), "s")
    f = play_seed(pl, free_space(), r15_best()["trot"], 0, margin)
    o = f["outcome"]
    print("free trot:", {k: o.get(k) for k in ("d_class", "d_speed_mm_s", "d_turn_deg_s", "height_low", "gait",
                                             "score")}, f["within"], f["rank"])


def _qd(lab: Any, opts: dict[str, str], key: str, space: Any, grid: Any, st: list[dict[str, Any]],
        names: list[str]) -> None:
    """One MAP-Elites run and the judging of its elites, stored under ``key`` in the JSON."""
    from calflab.evolve.qd import QDSettings, judge, run

    pl, margin = payload(lab)
    s = QDSettings(iterations=int(opts.get("iters", 30)), batch=int(opts.get("batch", 28)),
                   seed=int(opts.get("seed", 0)), confirm="confirm" in opts,
                   p_posture=float(opts.get("posture", 0.0)))
    cache = str(Path(sys.argv[1]) / ".cache" / "outcomes")
    t0 = time.time()
    pool, map_fn = _pool(int(opts.get("workers", 14)))
    with pool:
        if "judge_only" in opts:  # the search is stored; judge its elites again
            r = _load(OUT)[key]
        else:
            def checkpoint(res: dict[str, Any]) -> None:
                if len(res["history"]) % 5 == 1:  # every 5 batches
                    d = _load(OUT)
                    d[key] = {**res, "partial": True}
                    _save(d)

            r = run(pl, space, grid, s, st, margin, map_fn, cache, names,
                    report=lambda m: print(f"[{key}] {m}", flush=True), checkpoint=checkpoint)
            data = _load(OUT)
            data[key] = r
            _save(data)
        t1 = time.time()
        j = judge(pl, space, grid, r["archive"], s.judge_seeds, margin, map_fn, cache)
    for c, v in j.items():
        r["archive"][c]["judged"] = v
    r["judge_wall_s"] = round(time.time() - t1, 1)
    r["total_wall_s"] = round(time.time() - t0, 1)
    r["workers"] = int(opts.get("workers", 14))
    data = _load(OUT)
    data[key] = r
    data["body"] = BODY
    data["model"] = MODEL
    _save(data)
    held = sum(1 for v in j.values() if v["holds"])
    print(f"[{key}] DONE {r['cells']} cells, judged at {space.judge_s} s: {held} hold, "
          f"{sum(1 for v in j.values() if v['holds'] and v['same_cell'])} in the same cell; wall {r['total_wall_s']} s",
          flush=True)


def pilot(lab: Any, opts: dict[str, str]) -> None:
    from calflab.evolve.qd import Grid, free_space

    st, names = starts()
    _qd(lab, opts, "pilot", free_space(), Grid(), st, names)


def full(lab: Any, opts: dict[str, str]) -> None:
    """The full search (ADR-113): as the pilot, with every would-be elite confirmed at 30 s (it must hold and stay
    in its cell) and half of each batch from the posture emitter. Stored under ``full``."""
    from calflab.evolve.qd import Grid, free_space

    st, names = starts()
    opts = {"seed": "1", "posture": "0.5", "confirm": "", **opts}
    _qd(lab, opts, opts.get("key", "full"), free_space(), Grid(still_by_posture=True), st, names)


def _names(edges: list[float], unit: str) -> list[str]:
    e = [f"{x:g}" for x in edges]
    return [f"under {e[0]} {unit}", *(f"{a}-{b} {unit}" for a, b in zip(e, e[1:], strict=False)), f"over {e[-1]} {unit}"]


def _trot_starts() -> tuple[list[dict[str, Any]], list[str]]:
    """R15's trot on this body and today's trot at R11c's grid corners plus three faster corners (cycle 0.35 s,
    stride 2.5) the grid never had."""
    from calflab.control.outcome import from_feral_trot

    out, names = [r15_best()["trot"]], ["R15 trot (0.4 s, stride 2)"]
    for c, st in ((0.4, 2.0), (0.45, 2.0), (0.5, 2.0), (0.6, 2.0), (0.4, 1.5), (0.35, 2.0), (0.4, 2.5), (0.35, 2.5)):
        out.append(from_feral_trot(cycle_s=c, stride=st, lift=0.6))
        names.append(f"trot {c}/{st}")
    return out, names


def probe_trot(lab: Any, opts: dict[str, str]) -> None:
    """Is there a trot faster or more economical than the warm start? The rhythm, reflexes and a posture searched
    with fine speed bins; least effort per bin."""
    from calflab.evolve.qd import Grid, free_space

    edges = [100.0, 200.0, 300.0, 400.0, 450.0, 500.0, 550.0, 600.0, 650.0, 700.0]
    grid = Grid(classes=["walk", "trot", "pace", "bound", "irregular"], speed_edges=edges,
                speed_names=_names(edges, "mm/s"), turn_edges=[-2.5, 2.5],
                turn_names=["turning right", "straight", "turning left"])
    st, names = _trot_starts()
    _qd(lab, opts, "probe_trot", free_space(blocks=["p1", "rhythm", "reflex"]), grid, st, names)


def _gait_starts() -> tuple[list[dict[str, Any]], list[str]]:
    """Gaits other than the trot, written as the rhythm's leg phases (hind-left at 0) with the trot's leg numbers:
    starting points only; whether they hold is the question."""
    from calflab.control.outcome import from_feral_trot, from_feral_walk

    def trot(**kw: float) -> dict[str, Any]:
        return {**from_feral_trot(cycle_s=0.5, stride=1.5, lift=0.6), **kw}

    out = [trot(phase_fl=0.0, phase_hr=0.5, phase_fr=0.5), trot(phase_fl=0.5, phase_hr=0.0, phase_fr=0.5),
           trot(phase_fl=0.0, phase_hr=0.0, phase_fr=0.0, stride=0.5), trot(phase_fl=0.6, phase_hr=0.1, phase_fr=0.5),
           trot(phase_fl=0.75, phase_hr=0.5, phase_fr=0.25, cycle_s=0.8, swing=0.3),
           from_feral_walk(cycle_s=1.2), from_feral_walk(cycle_s=2.0), from_feral_walk(cycle_s=4.0),
           trot(stride=0.0, turn=1.0), trot(stride=0.0, turn=-1.0), from_feral_walk(cycle_s=2.0, stride=0.0, turn=1.0),
           trot(stride=-1.0), trot(stride=1.0, turn=0.6), from_feral_walk(cycle_s=2.0, stride=-1.0),
           trot(bout_s=2.0, pause_s=1.5)]
    names = ["pace", "bound", "pronk (in place)", "rotary gallop phases", "diagonal-sequence walk", "walk 1.2 s",
             "walk 2 s", "walk 4 s (feral)", "trot turning on the spot left", "trot turning on the spot right",
             "walk turning on the spot", "trot backward", "trot curving left", "walk backward",
             "trot in bouts (2 s on, 1.5 s off)"]
    return out, names


def probe_gaits(lab: Any, opts: dict[str, str]) -> None:
    """Is there a gait other than a trot that holds (walk, pace, bound, turning on the spot)? The rhythm and reflexes
    searched on the main grid, from the gaits above."""
    from calflab.evolve.qd import Grid, free_space

    st, names = _gait_starts()
    _qd(lab, opts, "probe_gaits", free_space(blocks=["rhythm", "reflex"]), Grid(), st, names)


#: lying down (R15's outcome ``lie``) with the wider controller: three keyframes, pauses, a left/right offset
LIE_POSE = {"abd": (-10.0, 10.0), "stifle": (-20.0, 78.0), "hock": (-20.0, 78.0), "shoulder": (-58.0, 20.0),
            "carpus": (-5.0, 128.0)}


def _lie_space() -> Any:
    from calflab.evolve.outcomes import BehaviourSpace

    dims: list[tuple[str, float, float]] = []
    for k in ("p1", "p2", "p3"):
        dims += [(f"{k}_{g}", lo, hi) for g, (lo, hi) in LIE_POSE.items()]
        dims += [(f"{k}_s", 0.8, 6.0)]
        if k != "p3":
            dims += [(f"{k}_hold_s", 0.0, 3.0)]
    dims += [("side_abd", -15.0, 15.0), ("side_stifle", -30.0, 30.0), ("side_hock", -30.0, 30.0),
             ("side_shoulder", -30.0, 30.0), ("side_carpus", -30.0, 30.0), ("side_from_s", 0.0, 8.0),
             ("side_s", 0.5, 4.0), ("pitch_gain", -1.0, 1.0), ("pitch_gain_hind", -1.0, 1.0), ("roll_gain", -1.0, 1.0)]
    return BehaviourSpace(behaviour="lie", dims=dims, fixed={}, one_shot_extra_s=3.5)


def _lie_starts() -> tuple[list[dict[str, Any]], list[str]]:
    from calflab.evolve.outcomes import warm_starts
    from outcomes_r15 import lie_versions

    kneel = {"shoulder": -30.0, "carpus": 115.0}
    front_lie = {"shoulder": -45.0, "carpus": 125.0}
    hind = {"stifle": 75.0, "hock": 75.0}

    def kf(k: str, pose: dict[str, float], s: float, hold: float = 0.0) -> dict[str, float]:
        return {**{f"{k}_{g}": v for g, v in pose.items()}, f"{k}_s": s, **({f"{k}_hold_s": hold} if hold else {})}

    def p3_as_p2(p: dict[str, Any]) -> dict[str, Any]:  # a two-keyframe version: keyframe 3 holds keyframe 2
        return {**p, **{k.replace("p2_", "p3_"): v for k, v in p.items() if k.startswith("p2_") and k != "p2_hold_s"},
                "p3_s": 0.8}

    out = [p3_as_p2(r15_best()["lie"]), *(p3_as_p2(p) for p in warm_starts("lie", lie_versions(BODY)))]
    names = ["R15 lie (this body)", *(f"R13 lie_rise {i}" for i in range(len(out) - 1))]
    out += [
        {**kf("p1", kneel, 3.0, 1.0), **kf("p2", {**front_lie, "stifle": 45.0, "hock": 45.0}, 3.0, 1.0),
         **kf("p3", {**front_lie, **hind}, 3.0)},
        {**kf("p1", {"stifle": 60.0, "hock": 60.0}, 3.0, 1.0), **kf("p2", {**kneel, **hind}, 3.0, 1.0),
         **kf("p3", {**front_lie, **hind}, 2.0)},
        {**kf("p1", kneel, 2.5), **kf("p2", {**front_lie, **hind}, 4.0), **kf("p3", {**front_lie, **hind}, 0.8),
         "side_stifle": 15.0, "side_hock": -15.0, "side_abd": 8.0, "side_from_s": 3.0, "side_s": 2.0},
        {**kf("p1", {**kneel, "abd": 8.0}, 3.0), **kf("p2", {**front_lie, **hind, "abd": 8.0}, 5.0),
         **kf("p3", {**front_lie, **hind, "abd": 8.0}, 0.8)},
        {**kf("p1", kneel, 5.0, 2.0), **kf("p2", {**front_lie, "stifle": 60.0, "hock": 60.0}, 5.0, 2.0),
         **kf("p3", {**front_lie, **hind}, 5.0)},
    ]
    names += ["front first (kneel, half fold, fold)", "hind first (sit, kneel, fold)", "front first, folded to one side",
              "front first, hips out", "front first, slow with pauses"]
    return out, names


def probe_lie(lab: Any, opts: dict[str, str]) -> None:
    """Is there any lying down within the limits? R15's lie outcome, the wider controller, front-first, hind-first,
    one-sided and slow starts."""
    from calflab.evolve.outcomes import OutcomeSearch, optimise

    pl, margin = payload(lab)
    st, names = _lie_starts()
    s = OutcomeSearch(popsize=int(opts.get("pop", 12)), generations=int(opts.get("gens", 20)))
    cache = str(Path(sys.argv[1]) / ".cache" / "outcomes")
    pool, map_fn = _pool(int(opts.get("workers", 14)))
    with pool:
        r = optimise(pl, _lie_space(), margin, s, st, map_fn, cache, report=lambda m: print(f"[lie] {m}", flush=True))
    r["start_names"] = names
    data = _load(OUT)
    data.setdefault("probes", {})["lie"] = r
    _save(data)
    print("[lie] DONE holds", r["best"]["holds"], "rank", r["best"]["rank"], "wall", r["wall_s"], flush=True)


def _grid_job(job: dict[str, Any]) -> dict[str, Any]:
    """One lying posture held: the outcome, the limits, and at the end (last 2 s) each servo's effort, the hind and
    front hooves' share of body weight and the body's share on the floor."""
    import numpy as np
    from calflab.evolve.hardware import _build
    from calflab.evolve.outcomes import play_seed
    from calflab.fitness.outcomes import probe, servo_effort, weight_n
    from calflab.plugins import load_plugins
    from calflab.sim.rollout import Rollout

    load_plugins()
    path = Path(job["tmp"]) / f"lie_grid_{job['i']}.npz"
    rec = play_seed(job["payload"], _lie_space(), job["params"], 0, job["margin"], rollout_path=str(path))
    ro = Rollout.load(path)
    path.unlink(missing_ok=True)
    design, _lib = _build(job["payload"])
    spec = design.spec
    t_end = float(ro.t[-1])
    m = ro.t >= t_end - 2.0
    bw = weight_n(ro)
    names = [g.split(".")[1] for g in ro.foot_geoms]
    ff = np.asarray(ro.foot_force[m], float).mean(axis=0) / bw
    share = {n: round(float(v), 3) for n, v in zip(names, ff, strict=True)}
    body = float(np.linalg.norm(probe(ro, "body_floor")[ro.t[ro.t >= 0] >= t_end - 2.0], axis=-1).mean()) / bw
    eff = servo_effort(ro, spec, t_end - 2.0)
    return {"i": job["i"], "pose": job["pose"], "within": rec["within"], "binding": rec["binding"],
            "stifle": {k: v for k, v in (rec["joints"].get("hl.stifle") or {}).items()},
            "lying_min": rec["outcome"].get("lying_min"), "lay_down": (rec["outcome"].get("gates") or {}).get("lay_down"),
            "resting_bw": rec["outcome"].get("resting_bw"), "holds": rec["holds"], "end_hooves_bw": share,
            "end_body_bw": round(body, 3), "end_effort": eff}


def lie_grid(lab: Any, opts: dict[str, str]) -> None:
    """Why lying binds: the front kneels and lies (carpus 125, shoulder -45), then the hind legs fold to a stifle and
    hock pair from a grid; held 3.5 s. Seed 0. Reports the hind stifle's load at the end against the floor's share."""
    pl, margin = payload(lab)
    tmp = Path(sys.argv[1]) / ".cache" / "outcomes_rollouts"
    tmp.mkdir(parents=True, exist_ok=True)
    jobs = []
    for st in (20.0, 40.0, 55.0, 65.0, 78.0):
        for hk in (20.0, 40.0, 55.0, 65.0, 78.0):
            pose = {"stifle": st, "hock": hk}
            params = {"p1_shoulder": -30.0, "p1_carpus": 115.0, "p1_s": 3.0,
                      "p2_shoulder": -45.0, "p2_carpus": 125.0, "p2_stifle": st, "p2_hock": hk, "p2_s": 4.0}
            jobs.append({"i": len(jobs), "pose": pose, "params": params, "payload": pl, "margin": margin,
                         "tmp": str(tmp)})
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 14))) as pool:
        res = list(pool.map(_grid_job, jobs))
    data = _load(OUT)
    data["lie_grid"] = res
    _save(data)
    for r in res:
        st = r["stifle"]
        print(r["pose"], "min", r["lying_min"], "rest", r["resting_bw"], "hooves", r["end_hooves_bw"], "body",
              r["end_body_bw"], "stifle use", {k: st.get(k) for k in ("torque", "envelope", "speed")},
              "eff hl.stifle", r["end_effort"].get("hl.stifle"), "binds", r["binding"], flush=True)


# ---------------------------------------------------------------------------------------------------- store
def _worst(summ: dict[str, Any]) -> dict[str, Any]:
    return min(summ["seeds"], key=lambda r: r["rank"])


def _shown_from_archive(key: str, source: str, keep: Any) -> list[dict[str, Any]]:
    """One record per elite of a stored QD run (``keep(cell, elite)`` filters), described by its judged worst seed."""
    data = _load(OUT)
    r = data.get(key) or {}
    out = []
    for cell, e in sorted((r.get("archive") or {}).items()):
        if not keep(cell, e):
            continue
        j = e.get("judged") or {}
        summ = j.get("summary") or e["summary"]
        w = _worst(summ)
        d = j.get("descriptor") or e["descriptor"]
        out.append({"key": f"{key}:{cell}", "group": cell.split("|")[0], "source": source, "cell": cell,
                    "cell_label": e["label"], "descriptor": d, "search_descriptor": e["descriptor"],
                    "outcome": w.get("outcome"), "holds": j.get("holds", False), "within": j.get("within", False),
                    "same_cell": j.get("same_cell", False), "agree": d.get("agree", 1.0),
                    "binding": w.get("binding"), "margin": w.get("margin"), "judged_s": r["space"]["judge_s"],
                    "params": summ["params"], "space": r["space"], "found": e.get("op"),
                    "iteration": e.get("iteration")})
    return out


def _store_job(job: dict[str, Any]) -> dict[str, Any]:
    from calflab.evolve.outcomes import BehaviourSpace, play_seed
    from calflab.plugins import load_plugins

    load_plugins()
    rec = play_seed(job["payload"], BehaviourSpace.model_validate(job["space"]), job["params"], 0, job["margin"],
                    judging=True, rollout_path=job["path"])
    return {k: v for k, v in rec.items() if k != "joints"} | {"joints": rec["joints"]}


def store(lab: Any, opts: dict[str, str]) -> None:
    """Each distinct elite (the pilot's archive; the trot probe's trots; the gait probe's elites that are not trots
    going straight; the lying probe's best) played on seed 0 at its judging length and saved as a ``sim`` run."""
    from calflab.evolve.outcomes import BehaviourSpace, controller_params, play_length

    pl, margin = payload(lab)
    shown = _shown_from_archive("pilot", "pilot", lambda c, e: True)
    shown += _shown_from_archive("full", "full search", lambda c, e: True)
    shown += _shown_from_archive("probe_trot", "probe: trot", lambda c, e: c.startswith("trot|"))
    shown += _shown_from_archive("probe_gaits", "probe: gaits",
                                 lambda c, e: not (c.startswith("trot|") and c.endswith("|2")))
    lie = ((_load(OUT).get("probes") or {}).get("lie")) or {}
    if lie:
        b = lie["best"]
        w = _worst(b)
        o = w.get("outcome") or {}
        shown.append({"key": "probe_lie:best", "group": "probe", "source": "probe: lie",
                      "title": "lies down (probe: the best try)", "descriptor": {"class": "down", "speed": 0.0,
                                                                                  "turn": 0.0},
                      "outcome": {**o, "height_mean": None, "height_low": o.get("lying_min")},
                      "holds": b["holds"], "within": b["within"], "same_cell": True, "binding": w.get("binding"),
                      "margin": w.get("margin"), "judged_s": "own length", "params": b["params"],
                      "space": lie["space"]})
    tmp = Path(sys.argv[1]) / ".cache" / "outcomes_rollouts"
    tmp.mkdir(parents=True, exist_ok=True)
    jobs = [{"payload": pl, "space": s["space"], "params": s["params"], "margin": margin,
             "path": str(tmp / f"r16_{i}.npz")} for i, s in enumerate(shown)]
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 14))) as pool:
        recs = list(pool.map(_store_job, jobs))
    data = _load(OUT)
    old = {s["key"]: s.get("run") for s in data.get("shown") or []}
    for s, job, rec in zip(shown, jobs, recs, strict=True):
        sp = BehaviourSpace.model_validate(s["space"])
        title = s.get("title") or s["cell_label"]
        s["run"] = _store_run(lab, pl, f"R16 {BODY} {title} [{s['source']}]: seed 0", Path(job["path"]),
                              {"key": "outcome_motion", "params": controller_params(sp, s["params"])},
                              play_length(sp, s["params"], True), rec)
        s["replaced_run"] = old.get(s["key"])
        print("STORED", s["key"], s["run"], "holds", s["holds"], flush=True)
    data["shown"] = shown
    data["mass_g"] = _mass(pl)
    _save(data)


def _mass(pl: dict[str, Any]) -> float:
    from calflab.evolve.hardware import _build

    d, _ = _build(pl)
    return round(d.spec.total_mass_g(), 1)


def _store_run(lab: Any, pl: dict[str, Any], title: str, rollout: Path, controller: dict[str, Any], length: float,
               rec: dict[str, Any]) -> str:
    """A ``sim`` run holding a saved rollout (as ``outcomes_r15._store_run``), tagged ``diversity_r16``."""
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
        inputs={"diversity_r16": {"length_s": length, "outcome": rec["outcome"]}, "margin": 0.2,
                "report": {k: v for k, v in rec.items() if k not in ("joints", "outcome")}, "joints": rec["joints"]},
        genome=pl["genome"], overrides=pl["overrides"], controller=controller,
        metrics={"within_limits": rec["within"], "safety_margin": rec["margin"], "closest": rec["closest"],
                 "holds": rec["holds"], "score": rec["outcome"].get("score")},
        artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
        parent=pl.get("stage_c_run"), tags=["diversity_r16"]))
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


def _qd_tables(key: str, r: dict[str, Any]) -> list[str]:
    from calflab.evolve.qd import Grid

    grid = Grid.model_validate(r["grid"])
    arch = r["archive"]
    lines = [f"## {key}", "", f"{r['cells']} of {r['grid_size']} cells ({100 * r['coverage']:.1f} %), {r['plays']} "
             f"plays, search {r['wall_s']:.0f} s, judging {r.get('judge_wall_s', 0):.0f} s on {r.get('workers')} "
             f"workers; space {len(r['space']['dims'])} dims; judged at {r['space']['judge_s']} s.", "",
             "Cells filled per class (speed bins x turn bins):", "",
             "| class | cells | tried (seed 0) | held 3 seeds | judged: hold / same cell | most common reasons it failed |",
             "|---|---|---|---|---|---|"]
    for cls in grid.classes:
        cs = [c for c in arch if c.startswith(cls + "|")]
        t = r["tried"].get(cls, {})
        reasons = sorted(((k, v) for k, v in t.items() if k not in ("tried", "held")), key=lambda kv: -kv[1])[:4]
        jh = sum(1 for c in cs if (arch[c].get("judged") or {}).get("holds"))
        js = sum(1 for c in cs if (arch[c].get("judged") or {}).get("holds") and arch[c]["judged"].get("same_cell"))
        lines.append(f"| {cls} | {len(cs)} | {t.get('tried', 0)} | {t.get('held', 0)} | {jh} / {js} | "
                     + "; ".join(f"{k} {v}" for k, v in reasons) + " |")
    none = r["tried"].get("none")
    if none:
        lines.append(f"| (no class: early stop) | – | {none.get('tried')} | – | – | "
                     + "; ".join(f"{k} {v}" for k, v in sorted(none.items(), key=lambda kv: -kv[1])[1:5]) + " |")
    lines += ["", "Elites (search descriptor; judged worst seed):", "",
              "| cell | found by | speed mm/s | turn deg/s | trunk mean / lowest | footfall (lag) | effort mean / worst "
              "(servo) | judged: holds, same cell, margin, binds |", "|---|---|---|---|---|---|---|---|"]
    for c in sorted(arch, key=lambda c: (grid.classes.index(c.split("|")[0]), c)):
        e = arch[c]
        j = e.get("judged") or {}
        w = _worst(j["summary"]) if j else _worst(e["summary"])
        o = w.get("outcome") or {}
        d = e["descriptor"]
        b = w.get("binding") or {}
        lines.append(f"| {e['label']} | {e.get('op')} (batch {e.get('iteration')}) | {_f(d['speed'], 0)} | "
                     f"{_f(d['turn'], 1)} | {_f(o.get('height_mean'))} / {_f(o.get('height_low'))} | {o.get('gait')} "
                     f"({_f(o.get('diagonal_lag'))}) | {_f(o.get('effort_mean'))} / {_f(o.get('effort_max'))} "
                     f"({o.get('worst')}) | {_f(j.get('holds'))}, {_f(j.get('same_cell'))}, {_f(w.get('margin'))}, "
                     f"{b.get('joint')} {b.get('limit')} {_f(b.get('use'))} |")
    curve = " ".join(str(h["cells"]) for h in r["history"])
    lines += ["", f"Cells after the starts and each batch: {curve}", ""]
    return lines


def report(lab: Any, opts: dict[str, str]) -> None:
    data = _load(OUT)
    lines = ["# R16 tables (generated by `diversity_r16.py report`)", "",
             f"Body {data.get('body')} at {data.get('model')}, {data.get('mass_g')} g.", ""]
    for key in ("pilot", "full", "probe_trot", "probe_gaits"):
        if data.get(key):
            lines += _qd_tables(key, data[key])
    lie = (data.get("probes") or {}).get("lie")
    if lie:
        lines += ["## probe_lie", "", f"{lie['plays']} plays, {lie['wall_s']:.0f} s. Starts (worst seed):", "",
                  "| start | rank | down to | held s | resting bw | descent mm/s | impact bw | tilt | binds |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for name, s in zip(lie["start_names"], lie["starts"], strict=False):
            w = _worst(s)
            o = w["outcome"]
            b = w.get("binding") or {}
            lines.append(f"| {name} | {_f(s['rank'])} | {_f(o.get('lying_min'))} | {_f(o.get('lying_held_s'), 1)} | "
                         f"{_f(o.get('resting_bw'))} | {_f(o.get('descent_peak_mm_s'), 0)} | "
                         f"{_f(o.get('impact_peak_bw'))} | {_f(o.get('tilt_max_deg'), 0)} | {b.get('joint')} "
                         f"{b.get('limit')} {_f(b.get('use'))} |")
        for tag in ("search_best", "best"):
            w = _worst(lie[tag])
            lines.append(f"\n**{tag}** holds {lie[tag]['holds']}, rank {lie[tag]['rank']}: "
                         f"`{json.dumps(w['outcome'], default=str)[:600]}`; binds {w.get('binding')}; "
                         f"params `{json.dumps(lie[tag]['params'])}`")
        lines.append("")
    grid = data.get("lie_grid")
    if grid:
        lines += ["## lie_grid (front kneels and lies; hind stifle / hock folded; seed 0; last 2 s)", "",
                  "| stifle | hock | down to | resting bw | hind hooves bw | front hooves bw | body on floor bw | "
                  "hl.stifle effort | hl.stifle sustained use | binds |", "|---|---|---|---|---|---|---|---|---|---|"]
        for g in grid:
            h = g["end_hooves_bw"]
            lines.append(f"| {g['pose']['stifle']:.0f} | {g['pose']['hock']:.0f} | {_f(g['lying_min'])} | "
                         f"{_f(g['resting_bw'])} | {_f(h.get('hl', 0) + h.get('hr', 0))} | "
                         f"{_f(h.get('fl', 0) + h.get('fr', 0))} | {_f(g['end_body_bw'])} | "
                         f"{_f(g['end_effort'].get('hl.stifle'))} | {_f(g['stifle'].get('torque'))} | "
                         f"{(g['binding'] or {}).get('joint')} {(g['binding'] or {}).get('limit')} "
                         f"{_f((g['binding'] or {}).get('use'))} |")
        lines.append("")
    if data.get("trot_judged"):
        lines += ["## Trots judged as R15 judges a trot (60 s, seeds 0-2)", "",
                  "| source | cell | holds | slowest 5 s mm/s | mean mm/s | lag | effort mean / worst (16 s) | "
                  "binds |", "|---|---|---|---|---|---|---|---|"]
        for t in data["trot_judged"]:
            lines.append(f"| {t['source']} | {t['cell']} | {_f(t['holds'])} | {_f(t['speed_min'], 0)} | "
                         f"{_f(t['speed'], 0)} | {_f(t['lag'])} | {_f(t['effort_mean'])} / {_f(t['effort_max'])} | "
                         f"{t['binding']} |")
        lines.append("")
    if data.get("estimate"):
        lines += ["## Full search estimate", "", *data["estimate"]["lines"], ""]
    TABLES.write_bytes(("\n".join(lines) + "\n").encode())
    print("\n".join(lines))


def judge_trots(lab: Any, opts: dict[str, str]) -> None:
    """Every straight trot elite of the pilot and the trot probe at 300 mm/s or more, judged as R15 judges its trot
    (60 s, every gate, seeds 0-2): is it faster or cheaper than R15's?"""
    from calflab.evolve.outcomes import BehaviourSpace, OutcomeSearch, body_key, evaluate

    pl, margin = payload(lab)
    data = _load(OUT)
    sp = BehaviourSpace.model_validate(_load(R15)["pilot"][BODY]["trot"]["space"])
    sp = sp.model_copy(update={"fixed": {}})
    rows: list[dict[str, Any]] = []
    for key in ("pilot", "probe_trot"):
        for c, e in sorted(((data.get(key) or {}).get("archive") or {}).items()):
            if not c.startswith("trot|") or float(e["descriptor"]["speed"]) < 300.0:
                continue
            if c.split("|")[2] != ("2" if key == "pilot" else "1"):
                continue
            w = _worst(e["summary"])
            rows.append({"source": key, "cell": e["label"], "params": e["summary"]["params"],
                         "effort_mean": w["outcome"].get("effort_mean"), "effort_max": w["outcome"].get("effort_max")})
    r15 = r15_best()["trot"]
    rows.append({"source": "R15", "cell": "R15 trot", "params": r15, "effort_mean": None, "effort_max": None})
    cache = str(Path(sys.argv[1]) / ".cache" / "outcomes")
    pool, map_fn = _pool(int(opts.get("workers", 14)))
    with pool:
        res = evaluate(pl, body_key(pl), sp, [r["params"] for r in rows], [0, 1, 2], margin,
                       OutcomeSearch().model_copy(update={"early_stop": -1e9}), map_fn, cache, judging=True)
    out = []
    for r, e in zip(rows, res, strict=True):
        w = min(e["seeds"], key=lambda s: s["rank"])
        o = w["outcome"]
        b = w.get("binding") or {}
        out.append({"source": r["source"], "cell": r["cell"], "holds": e["holds"], "speed_min": o.get("speed_min_mm_s"),
                    "speed": o.get("speed_mm_s"), "lag": (o.get("footfall") or {}).get("diagonal_lag"),
                    "effort_mean": r["effort_mean"], "effort_max": r["effort_max"],
                    "failed": [k for k, v in (o.get("gates") or {}).items() if not v],
                    "binding": f"{b.get('joint')} {b.get('limit')} {b.get('use')}", "margin": w.get("margin")})
        print(out[-1], flush=True)
    data = _load(OUT)
    data["trot_judged"] = out
    _save(data)


#: the full search (ADR-112): batches of 28 after the starts, then every elite judged at 30 s
BUDGETS = {"S": 200, "M": 500, "L": 1200}


def estimate(lab: Any, opts: dict[str, str]) -> None:
    data = _load(OUT)
    r = data["pilot"]
    h = r["history"]
    per_batch = (h[-1]["wall_s"] - h[0]["wall_s"]) / max(1, len(h) - 1)
    plays_per_cand = (h[-1]["plays"] - h[0]["plays"]) / max(1, (len(h) - 1) * r["settings"]["batch"])
    judge_per_elite = float(r.get("judge_wall_s") or 0) / max(1, r["cells"])
    lines = [f"Measured in the pilot: {per_batch:.1f} s per batch of {r['settings']['batch']} on {r.get('workers')} "
             f"workers, {plays_per_cand:.2f} plays per candidate (early stop), {judge_per_elite:.1f} s wall per "
             f"elite judged at 30 s; {r['cells']} cells after {len(h) - 1} batches.", "",
             "| budget | batches | candidates | search wall | judging (cells x 2, guess) | total |", "|---|---|---|---|---|---|"]
    rows = {}
    for name, n in BUDGETS.items():
        search = per_batch * n
        cells = min(r["grid_size"], r["cells"] * 2)
        judging = judge_per_elite * cells
        rows[name] = {"batches": n, "search_h": round(search / 3600, 2), "total_h": round((search + judging) / 3600, 2)}
        lines.append(f"| {name} | {n} | {n * r['settings']['batch']} | {search / 3600:.1f} h | "
                     f"{judging / 60:.0f} min | {(search + judging) / 3600:.1f} h |")
    data["estimate"] = {"per_batch_s": round(per_batch, 1), "plays_per_candidate": round(plays_per_cand, 2),
                        "judge_s_per_elite": round(judge_per_elite, 1), "rows": rows, "lines": lines}
    _save(data)
    print("\n".join(lines))


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
