"""Session R9 (ADR-100): up to four STS3250 C002 servos in place of STS3215 C018s, in simulation only.

Every what-if is an in-memory copy of the working body's spec (as ``joints_r8.py``): the project document, belts,
catalogs and component values are not changed. On top of R8's levers (``ratio``, ``d1``) a case may name joints
whose left/right pair gets the new servo (``new``): the actuator's component and the servo geom's mass (74.5 g
against 55 g) change; nothing else does (same case, same mount, same belt).

Cases:
* ``now``: the working body (ten C018s, 2:1 belts at stifle, hock and carpus);
* ``new: <joint>``: one pair new (hip_abd, stifle, hock, shoulder, carpus);
* ``new: <joint>+<joint>``: two pairs new (four servos, the most allowed);
* ``... | <pulley what-if>``: combined with R8's pulley what-ifs on joints that keep the old servo;
* ``... @11.1V``: every servo's stall torque, rated torque, no-load speed and stall current x 11.1 / 12 (ADR-086's
  linear assumption; torque per amp unchanged).

Plays per case and seed: the trot grid (cycle 0.5-1.2 s x stride 0.5-1.5, lift 0.6), the walk and the turn at the
primitives' defaults; margin 0.2, judged as everywhere else; seeds with the diversity preset's randomisation.

Per play, besides R8's per-joint table: the peak belt tension per belted joint (N, against the allowable working
tension and breaking strength), and the current the new servos draw (A at the servo: |servo torque| / (stall
torque / stall current) + idle current; the C018 has no stall current, so its share is unknown).

Session R10 (ADR-101): the new servos are now built through the genome's per-pair servo genes (``servo_<joint>``),
not patched into the spec; the model is the same bit for bit (``tests/test_feral_calf.py``), only the servo geoms'
labels lose R9's "[what-if: ...]". R8's pulley what-ifs may now be combined with a new servo on the same joint (R10
asked for a new carpus servo on 1:1 and 1.5:1). Grid ``r10`` = the quick grid + walk + turn + ``lie_rise``.

Run:  python docs/studies/servos_r9.py <project dir> <out.json> [--cases=a;b;...] [--seeds=0,1,2] [--workers=7]
          [--grid=wide|quick|r10]
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

NEW = "sts3250_c002"
OLD = "sts3215_c018"
PAIRS = ["hip_abd", "stifle", "hock", "shoulder", "carpus"]
MARGIN = 0.2

#: R8's pulley what-ifs (ADR-099), applicable to a belted joint that keeps the old servo
PULLEYS: dict[str, dict[str, Any]] = {
    "carpus 1:1 45T": {"ratio": {"carpus": 1.0}, "d1": {"carpus": 1.5}},
    "carpus 1.5:1": {"ratio": {"carpus": 1.5}},
    "hock 1.5:1": {"ratio": {"hock": 1.5}},
    "carpus 1:1 45T + hock 1.5:1": {"ratio": {"carpus": 1.0, "hock": 1.5}, "d1": {"carpus": 1.5}},
}
#: pairs already in the project's catalog (2:1, larger driver: less belt tension per servo torque), built through the
#: belt genes so C, the servo's place and every belt check are the real ones; the belt length is the stocked one
#: whose derived C is nearest today's (``belts_r9.py``). Allowed on any belted joint, new servo or old.
CATALOG: dict[str, dict[str, Any]] = {
    "carpus 36T-72T": {"belts": {"carpus": ["36T-72T", "GT2-2mm-640-C"]}},  # C 265.8 (today 274.8)
    "carpus 40T-80T": {"belts": {"carpus": ["40T-80T", "GT2-2mm-640-C"]}},  # C 259.7
    "hock 36T-72T": {"belts": {"hock": ["36T-72T", "GT2-2mm-400-C"]}},      # C 145.5 (today 154.7)
    "hock 40T-80T": {"belts": {"hock": ["40T-80T", "GT2-2mm-444-C"]}},      # C 161.5
    "hock 40T-80T 400": {"belts": {"hock": ["40T-80T", "GT2-2mm-400-C"]}},  # C 139.4
    "stifle 40T-80T": {"belts": {"stifle": ["40T-80T", "GT2-2mm-444-C"]}},  # checked by the build
}


def assignments() -> dict[str, dict[str, Any]]:
    """``now``, every single pair and every two pairs out of the five (at most four new servos)."""
    out: dict[str, dict[str, Any]] = {"now": {}}
    for k in (1, 2):
        for combo in itertools.combinations(PAIRS, k):
            out["new: " + "+".join(combo)] = {"new": list(combo)}
    return out


def parse_case(name: str) -> dict[str, Any]:
    """``new: a+b | <pulley what-if> @11.1V`` -> case dict."""
    volt = None
    if "@" in name:
        name, v = name.rsplit("@", 1)
        volt = float(v.strip().rstrip("V"))
        name = name.strip()
    head, *puls = (p.strip() for p in name.split("|"))
    if head.startswith("new:"):  # any order of the joints
        head = "new: " + "+".join(sorted(head[4:].strip().split("+"), key=PAIRS.index))
    if head.startswith("new: ") and head not in assignments():  # R10: three pairs, as an out-of-budget reference
        joints = head[5:].split("+")
        if not set(joints) <= set(PAIRS):
            raise KeyError(f"unknown assignment {head!r}")
        case: dict[str, Any] = {"new": joints}
    elif head in assignments():
        case = dict(assignments()[head])
    else:
        raise KeyError(f"unknown assignment {head!r}")
    for pul in puls:
        # R9 kept R8's pulley what-ifs to joints with the old servo, as its request put it; R10 lifts that
        p = PULLEYS[pul] if pul in PULLEYS else CATALOG[pul]
        for k, v in p.items():
            case[k] = {**case.get(k, {}), **v}
    if volt is not None:
        case["volt"] = volt
    return case


def swapped(spec: Any, new: list[str], lib: Any) -> Any:
    """The new servo on every actuator of the named joints (both sides): component and servo geom mass. R9's in-memory
    swap; since R10 ``what_if`` sets the servo genes instead (the same model, ``tests/test_feral_calf.py``)."""
    servo = lib.actuator(NEW)
    ids = set()
    for a in spec.actuators:
        if a.joint.split(".")[-1] in new:
            a.component = NEW
            ids.add(f"{a.id}.motor")
    hit = 0
    for b in spec.bodies:
        for g in b.geoms:
            if g.id in ids:
                g.mass_g, g.component, hit = servo.mass_g, NEW, hit + 1
                g.label = f"{g.label} [what-if: {servo.name}]"
    if hit != len(ids) or len(ids) != 2 * len(new):
        raise RuntimeError(f"swap of {new}: {len(ids)} actuators, {hit} servo geoms (expected {2 * len(new)} each)")
    return spec


def case_genome(genome: Any, case: dict[str, Any]) -> Any:
    """The genome with the case's catalog belt choices and new servos set through the genes (R10, ADR-101). R8's
    ratio and driver what-ifs (45T, 30T/45T) are not in any catalog, so no gene holds them: ``body`` applies them."""
    from calflab.design import genome_definition
    from calflab.model.migrations import migrate

    genome = migrate(genome, genome_definition(genome.definition))
    vals = dict(genome.values)
    for drive, (pair, length) in (case.get("belts") or {}).items():
        vals[f"belt_{drive}_pulleys"], vals[f"belt_{drive}_length"] = pair, length
    for joint in case.get("new", []):
        vals[f"servo_{joint}"] = NEW
    return genome.model_copy(update={"values": vals})


def what_if(design: Any, overrides: list[Any], generator: str, gen_params: dict[str, Any], case: dict[str, Any],
            lib: Any) -> Any:
    """The case's in-memory spec: catalog belt choices through the genes (real C and checks), R8's levers, then the
    new servos. Refuses a body whose belts fail a check (it would not be simulated in the lab either)."""
    import dataclasses

    from joints_r8 import body

    design = dataclasses.replace(design, genome=case_genome(design.genome, case))
    spec = body(design, overrides, generator, gen_params, case)
    fer = spec.metadata.get("feral") or {}
    if fer.get("infeasible"):
        raise ValueError(f"{case}: the body cannot be built as asked: {fer['infeasible']}")
    return spec


def lib_at(volt: float | None) -> Any:
    """The library, with every actuator's figures x volt / 12 (ADR-086: linear in voltage, torque per amp kept)."""
    from calflab.components.library import Library, library

    lib0 = library()
    if volt is None:
        return lib0
    s = volt / 12.0
    comps = []
    for c in lib0.all():
        if c.key in (NEW, OLD):
            upd: dict[str, Any] = {"stall_torque_nm": c.stall_torque_nm * s, "no_load_speed_rpm": c.no_load_speed_rpm * s}  # type: ignore[attr-defined]
            if c.rated_torque_nm is not None:  # type: ignore[attr-defined]
                upd["rated_torque_nm"] = c.rated_torque_nm * s  # type: ignore[attr-defined]
            if c.stall_current_a is not None:  # type: ignore[attr-defined]
                upd["stall_current_a"] = c.stall_current_a * s  # type: ignore[attr-defined]
            c = c.model_copy(update=upd)
        comps.append(c)
    return Library(comps, lib0.incomplete)


def belts_and_current(ro: Any, spec: Any, lib: Any) -> dict[str, Any]:
    """Peak belt tension per belted joint, and the new servos' current (A at 12 V or the case's voltage)."""
    from calflab.behave.interpret import _checks
    from calflab.mech.loads import analyse

    belts = {d: dict(r) for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items()}
    rows = analyse(ro, spec, lib, 2.0, _checks(spec), belts)["summary"]
    belt = {}
    for r in rows:
        if "belt_tension_peak_n" in r:
            belt[r["joint"].replace("joint.", "")] = {
                "servo": r["servo"], "peak_n": round(r["belt_tension_peak_n"], 1),
                "allowable_n": r.get("allowable_n"), "breaking_n": r.get("breaking_n"),
                "peak_over_breaking": None if r.get("peak_over_breaking") is None else round(r["peak_over_breaking"], 3)}
    trans = {tr.id: tr for tr in spec.transmissions}
    act = {a.id: a for a in spec.actuators}
    m = ro.t >= 0
    per: dict[str, Any] = {}
    total = np.zeros(int(m.sum()))
    for i, aid in enumerate(ro.actuator_ids):
        a = act[aid]
        c = lib.actuator(a.component)
        if c.stall_current_a is None:
            continue
        tr = trans.get(a.transmission) if a.transmission else None
        g = (tr.ratio * tr.efficiency) if tr else 1.0
        cur = np.abs(ro.torque[m, i].astype(float)) / g / (c.stall_torque_nm / c.stall_current_a) + c.idle_current_a
        total += cur
        per[a.joint.replace("joint.", "")] = {"peak_a": round(float(cur.max()), 2), "mean_a": round(float(cur.mean()), 2)}
    cur_out = {"per_servo": per, "known_servos": len(per), "unknown_servos": len(ro.actuator_ids) - len(per),
               "new_total_peak_a": round(float(total.max()), 2) if per else None,
               "new_total_mean_a": round(float(total.mean()), 2) if per else None}
    return {"belts": belt, "current": cur_out}


def plays(grid: str) -> list[tuple[str, dict[str, Any]]]:
    quick = grid in ("quick", "r10")
    cycles = (0.4, 0.45, 0.5, 0.6, 0.8) if quick else (0.5, 0.6, 0.8, 1.0, 1.2)
    strides = (0.5, 1.0, 1.5, 2.0) if quick else (0.5, 1.0, 1.5)
    out = [("trot", {"cycle_s": c, "stride": st, "lift": 0.6, "turn": 0.0}) for c in cycles for st in strides]
    return out + [("walk", {}), ("turn", {})] + ([("lie_rise", {})] if grid == "r10" else [])


def task(name: str, case: dict[str, Any], spec_json: str, doc: dict[str, Any], seed: int, grid: str) -> dict[str, Any]:
    """One case on one seed: every play (runs in a worker process)."""
    import calflab.behave.physics as phys
    from calflab.behave.interpret import InterpretSettings, judge, play_primitive
    from calflab.behave.study import randomization
    from calflab.model.spec import RobotSpec
    from calflab.plugins import load_plugins, registry
    from joints_r8 import per_joint

    load_plugins()
    strip = phys.compile_params
    rand = randomization(True, (0.7, 1.1), (0.95, 1.05))  # the diversity preset's, as R8's three seeds
    phys.compile_params = lambda d: {**strip(d), "randomization": rand}  # type: ignore[assignment]
    lib = lib_at(case.get("volt"))
    spec = RobotSpec.model_validate_json(spec_json)
    s = InterpretSettings(margin=MARGIN, seed=seed)
    rows = []
    t = time.perf_counter()
    for key, prm in plays(grid):
        prim = registry.get("motion_primitive", key)(prm)  # type: ignore[call-arg]
        ro, t0, t1, _c = play_primitive(prim, spec, lib, doc, s)
        j = judge(ro, spec, lib, MARGIN)
        trunk = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
        mm = (ro.t >= t0) & (ro.t < t1)
        dist = float(np.linalg.norm(ro.body_pos[mm, trunk, :2][-1] - ro.body_pos[mm, trunk, :2][0])) * 1000.0
        speed = dist / max(1e-6, float(ro.t[mm][-1] - ro.t[mm][0]))
        worst = sorted(((k, v["margin"]) for k, v in j["constraints"].items() if v.get("margin") is not None),
                       key=lambda kv: kv[1])[:2]
        rows.append({"primitive": key, "params": prim.params.model_dump(mode="json"), "within": j["within_limits"],
                     "fell": j["fell"], "margin": j["margin"], "worst": worst, "speed_mm_s": round(speed, 1),
                     "joints": per_joint(ro, spec, lib, MARGIN), **belts_and_current(ro, spec, lib)})
    return {"name": name, "seed": seed, "rows": rows, "wall_s": round(time.perf_counter() - t, 1)}


def main() -> None:
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    load_plugins()
    proj, outp = Path(sys.argv[1]), Path(sys.argv[2])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[3:] if a.startswith("--"))
    names = [c.strip() for c in opts["cases"].split(";")] if "cases" in opts else list(assignments())
    seeds = [int(v) for v in opts.get("seeds", "0,1,2").split(",")]
    grid = opts.get("grid", "")
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    design = lab.design()
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    overrides = [o for o in lab.state.overrides if o.enabled]
    doc = dict(g.role("model").params)
    lab.close()
    lib = lib_at(None)
    out: dict[str, Any] = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() and "append" in opts else {}
    jobs = []
    for name in names:
        case = parse_case(name)
        spec = what_if(design, overrides, generator, gen_params, case, lib)
        out[name] ={"case": case, "mass_g": round(spec.total_mass_g(), 1), "grid": grid, "seeds": {}}
        jobs.append((name, case, spec.model_dump_json(), doc))
    t = time.perf_counter()
    with ProcessPoolExecutor(max_workers=int(opts.get("workers", 7))) as ex:
        futs = [ex.submit(task, n, c, sj, d, sd, grid) for n, c, sj, d in jobs for sd in seeds]
        for f in as_completed(futs):
            r = f.result()
            out[r["name"]]["seeds"][str(r["seed"])] = {"rows": r["rows"], "wall_s": r["wall_s"]}
            ok = [f"{x['params'].get('cycle_s', '')}/{x['params'].get('stride', '')}" for x in r["rows"]
                  if x["primitive"] == "trot" and x["within"]]
            wt = {x["primitive"]: x["margin"] for x in r["rows"] if x["primitive"] != "trot"}
            print(f"{r['name']:44s} seed {r['seed']}: trots within {ok}; walk {wt.get('walk')}, turn {wt.get('turn')}, "
                  f"lie_rise {wt.get('lie_rise')} "
                  f"({r['wall_s']:.0f} s; {time.perf_counter() - t:.0f} s total)", flush=True)
            outp.write_text(json.dumps(out, separators=(",", ":"), default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
