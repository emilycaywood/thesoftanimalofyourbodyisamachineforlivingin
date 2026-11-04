"""Lab side of interpretation and performance (ADR-085): a job that interprets a reading on the working design,
plays the result for a minute with three seeds, and stores everything as a run of kind ``interpret``
(``interpretation.json``; the seed-0 rollout and scene replay like any run). The Behave panel shows the stored
report; nothing is computed in the UI."""

from __future__ import annotations

import contextlib
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from calflab.app.scene import build_scene
from calflab.components import library
from calflab.project import RunRecord
from calflab.project.motions import MotionClip
from calflab.project.store import read_json, write_json


class InterpretError(Exception):
    """Shown to the user as is."""


def _calf_features(beh: dict[str, Any], stretches: list[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The calf's features of one behaviour (means) and a detail record (the longest stretch's footfall)."""
    feats = {k: v["mean"] for k, v in beh["features"].items()}
    longest = max(stretches, key=lambda s: s.t1 - s.t0) if stretches else None
    detail = dict(feats)
    if longest is not None:
        detail["footfall"] = longest.features.get("footfall")
    return feats, detail


def build_states(reading: Any, records: list[dict[str, Any]], spec: Any) -> dict[str, Any]:
    """Controller parameters of ``interpreted`` from the reading's model and the interpretation records."""
    from calflab.plugins import registry

    states = []
    for rec in records:
        b = rec["behaviour"]
        if not rec["within_limits"]:
            continue
        prim = registry.get("motion_primitive", rec["primitive"])(rec["params"])
        key, params = prim.controller(spec, library())
        dur = reading.model.durations.get(b)
        values = dur.values_s if dur else []
        d = {"log_mean": dur.log_mean if dur and dur.log_mean is not None else 0.7,
             "log_sd": dur.log_sd if dur and dur.log_sd is not None else 0.5,
             "min_s": round(max(0.5, 0.5 * min(values)), 3) if values else 0.5,
             "max_s": round(max(2.0, 2.0 * max(values)), 3) if values else 10.0}
        feats = reading.behaviours[b]["features"]

        def cv(k: str, f: dict[str, Any] = feats) -> float:
            v = f.get(k) or {}
            if not v or not v.get("mean") or v.get("sd") is None:
                return 0.1
            return float(min(0.5, abs(v["sd"] / v["mean"])))

        vary: dict[str, tuple[float, float]] = {}
        # timing only slower than interpreted, sizes only smaller: the spread never leaves what was found within
        # the limits (PROVISIONAL rule, ADR-085)
        for p in ("cycle_s", "trot_cycle_s", "shift_s", "hold_s", "back_s", "phase_s"):
            if p in params:
                vary[p] = (1.0, round(math.exp(cv("tempo_s")), 4))
        for p in ("stride", "trot_sweep_scale", "offsets", "lift"):
            if p in params and params[p]:
                vary[p] = (round(math.exp(-cv("amplitude_mean_deg")), 4), 1.0)
        states.append({"name": b, "primitive": rec["primitive"], "controller": {"key": key, "params": params},
                       "period_s": prim.period_s(), "offset_s": prim.phase_offset_s(),
                       "safe": [list(x) for x in prim.safe_phases()], "one_shot": prim.one_shot, "duration": d,
                       "vary": {k: list(v) for k, v in vary.items()}})
    names = {s["name"] for s in states}

    def norm(row: dict[str, float]) -> dict[str, float]:
        tot = sum(row.values())
        return {k: round(v / tot, 4) for k, v in row.items()} if tot > 0 else {}

    # only the behaviours performed, renormalised (a behaviour left out moves its share to the others)
    trans = {a: norm({b: p for b, p in row.items() if b in names and b != a}) for a, row in
             reading.model.probabilities.items() if a in names}
    init = norm({b: p for b, p in reading.model.initial.items() if b in names})
    return {"states": states, "transitions": trans, "initial": init}


def commanded_clip(ro: Any, spec: Any) -> MotionClip:
    """What the controller commanded (deg, relative to standing), as a clip, so the physics report can judge a
    performance (tracking = how far the body was from its commands)."""
    from calflab import units as u

    rest = spec.rest_angles()
    aj = list(ro.meta.get("actuator_joint") or [])
    m = ro.t >= 0
    joints = {j: [round(float(u.rad_to_deg(v)) - rest.get(j, 0.0), 4) for v in ro.ctrl[m, i]] for i, j in enumerate(aj)}
    fps = 1.0 / float(np.median(np.diff(ro.t[m]))) if m.sum() > 1 else 50.0
    return MotionClip(id="performance", name="performance", fps=fps, joints=joints, source="performance")


def _adr084_scores(lab: Any) -> dict[str, Any]:
    """Character kept by Make feasible (ADR-084), from adapt runs of this project, else of the scratch project the
    ADR's numbers come from, if present."""
    rows = []
    dirs = [Path(lab.project.path) / "runs", Path(lab.project.path).parent / "_scratch-physics" / "runs"]
    for d in dirs:
        for f in sorted(d.glob("*-adapt-*/adapt.json")) if d.is_dir() else []:
            try:
                a = read_json(f)
            except Exception:  # noqa: BLE001
                continue
            comp = a.get("comparison") or {}
            ch = (comp.get("adapted") or {}).get("character") or a.get("character") or {}
            rows.append({"run": f.parent.name, "project": f.parent.parent.parent.name,
                         "clip": (a.get("source") or {}).get("name") or (a.get("source") or {}).get("candidate"),
                         "character_kept": ch.get("kept", ch.get("score")),
                         "verdict": (comp.get("adapted") or {}).get("verdict")})
        if rows:
            break
    return {"source": "adapt runs (Make feasible, ADR-084)", "runs": rows,
            "note": "Character kept is ADR-084's movement measure of a replayed clip; interpretation keeps or drops "
                    "features by name instead (the comparison table)."}


def perform(lab: Any, spec: Any, doc: dict[str, Any], ctrl_params: dict[str, Any], seconds: float, seed: int,
            margin: float, cancelled: Any = None) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Play the interpreted controller for ``seconds``; the physics report and the robot read back."""
    from calflab.behave import physics
    from calflab.behave import reading as rd
    from calflab.behave.interpret import robot_features
    from calflab.behave.signals import _feet, from_rollout
    from calflab.plugins import registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    lib = library()
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(physics.compile_params(doc)), seed)
    st = SimSettings(duration_s=seconds, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                     stop_on_fall=True, seed=seed)
    ro = run_rollout(cm, registry.get("controller", "interpreted")(ctrl_params), st, lib, cancelled=cancelled)
    clip = commanded_clip(ro, spec)
    end = float(ro.t[-1])
    rep = physics.report(ro, clip, spec, lib, {"clip_t0": 0.0, "clip_t1": end + 1e-6, "end_t": end}, margin)
    sig = from_rollout(ro, spec, 0.0)
    legs = [leg for leg, *_r in _feet(spec)]
    order = [next((lg for lg in legs if f".{lg}." in g or g.startswith(f"leg.{lg}") or f"{lg}." in g), g)
             for g in ro.foot_geoms]
    m = ro.t >= 0
    up = rd.lifted_from_contact(ro.foot_force[m].astype(float), order, sig.fps)
    read = rd.label(sig, up, rd.ReadingSettings(), video=f"seed {seed}")
    log = (ro.meta.get("controller_log") or {}).get("episodes") or []
    for e in log:
        e.setdefault("t1", round(end, 4))
    per_episode = []
    for e in log:
        if e["t1"] - e["t0"] >= 0.6:
            with contextlib.suppress(ValueError):
                per_episode.append({"name": e["name"], "features": robot_features(ro, spec, e["t0"], e["t1"])})
    return ro, rep, {"episodes": log, "read": [s.model_dump(mode="json") for s in read], "per_episode": per_episode}


def _shares(items: list[tuple[str, float]], names: list[str]) -> dict[str, float]:
    tot = sum(d for _n, d in items) or 1.0
    return {n: round(sum(d for m, d in items if m == n) / tot, 4) for n in names}


def _transitions(seq: list[str], names: list[str]) -> dict[str, dict[str, int]]:
    out = {a: dict.fromkeys(names, 0) for a in names}
    for a, b in zip(seq, seq[1:], strict=False):
        if a in out and b in out[a] and a != b:
            out[a][b] += 1
    return out


def comparison(reading: Any, records: list[dict[str, Any]], plays: list[dict[str, Any]]) -> dict[str, Any]:
    """The calf and the robot side by side: shares, transitions, durations, features per behaviour, falls, margins."""
    from calflab.behave.reading import BEHAVIOURS, behaviour_summary
    from calflab.behave.reading import Stretch as St

    names = list(BEHAVIOURS)
    calf_items = [(s.behaviour, s.t1 - s.t0) for s in reading.stretches]
    robot_int = [(e["name"], e["t1"] - e["t0"]) for p in plays for e in p["perf"]["episodes"]]
    robot_read = [St.model_validate(s) for p in plays for s in p["perf"]["read"]]
    seq_int: dict[str, dict[str, int]] = {a: dict.fromkeys(names, 0) for a in names}
    for p in plays:
        t = _transitions([e["name"] for e in p["perf"]["episodes"]], names)
        for a in names:
            for b in names:
                seq_int[a][b] += t[a][b]
    durations = {}
    for b in names:
        rv = [e["t1"] - e["t0"] for p in plays for e in p["perf"]["episodes"] if e["name"] == b]
        cd = reading.model.durations.get(b)
        durations[b] = {"calf_median_s": cd.median_s if cd else None, "calf_n": cd.n if cd else 0,
                        "robot_median_s": round(float(np.median(rv)), 3) if rv else None, "robot_n": len(rv)}
    rb = behaviour_summary(robot_read)
    feats = {}
    for b in names:
        cf = reading.behaviours[b]["features"]
        rf = rb[b]["features"]
        if not cf and not rf:
            continue
        feats[b] = {k: {"calf": (cf.get(k) or {}).get("mean"), "robot": (rf.get(k) or {}).get("mean")}
                    for k in sorted(set(cf) | set(rf))}
    return {
        "behaviours": names,
        "shares": {"calf": _shares(calf_items, names), "robot_intended": _shares(robot_int, names),
                   "robot_read": _shares([(s.behaviour, s.t1 - s.t0) for s in robot_read], names)},
        "transitions": {"calf": reading.model.counts, "robot_intended": seq_int},
        "durations": durations,
        "features": feats,
        "robot_read_summary": {b: {"n": rb[b]["n"], "seconds": rb[b]["seconds"]} for b in names},
        "falls": [{"seed": p["seed"], "fell": p["report"]["fell"], "fall_time_s": p["report"]["fall_time_s"]}
                  for p in plays],
        "margins": [{"seed": p["seed"], "margin": p["report"]["safety"]["margin"],
                     "violations": p["report"]["safety"]["violations"], "verdict": p["report"]["verdict"]}
                    for p in plays],
    }


def interpret_job(lab: Any, reading_id: str = "", settings: dict[str, Any] | None = None, seconds: float = 60.0,
                  seeds: list[int] | None = None) -> Any:
    from calflab.app.physics_jobs import _context
    from calflab.app.reading_jobs import ReadingError, load_reading
    from calflab.behave.interpret import InterpretSettings

    try:
        s = InterpretSettings.model_validate(settings or {})
    except Exception as exc:
        raise InterpretError(f"Interpretation settings: {exc}") from exc
    try:
        reading = load_reading(lab, reading_id)
    except ReadingError as exc:
        raise InterpretError(str(exc)) from exc
    try:
        ctx = _context(lab)
    except Exception as exc:
        raise InterpretError(str(exc)) from exc
    seeds = list(seeds if seeds is not None else [0, 1, 2])

    def work(job: Any) -> dict[str, Any]:
        out = run_interpretation(lab, reading, s, ctx, seconds, seeds, job.cancelled,
                                 lambda f, m: job.report(f, m))
        job.log(f"interpretation: {len(out['records'])} behaviours, {out['cost']['plays']} plays, "
                f"{out['cost']['seconds']:.0f} s")
        return {"run_id": out["run_id"]}

    return lab.jobs.submit("interpret", f"Interpret reading {reading.id}", work)


def run_interpretation(lab: Any, reading: Any, s: Any, ctx: dict[str, Any], seconds: float, seeds: list[int],
                       cancelled: Any = None, report: Any = None) -> dict[str, Any]:
    """The whole chain, synchronously: interpret, perform, compare, store. Returns the stored payload."""
    from calflab.app.physics_jobs import basis
    from calflab.behave.interpret import Interpreter, candidates_for, interpret_behaviour

    design = ctx["design"]
    spec = design.spec
    lib = library()
    t_start = time.perf_counter()
    cache = Path(lab.project.path) / ".cache" / "interpret"
    say = report or (lambda f, m: None)
    it = Interpreter(spec, lib, ctx["doc_compile"], s, cache, cancelled, lambda m: say(0.1, m))
    todo = [b for b, d in reading.behaviours.items() if d["n"] and (not s.behaviours or b in s.behaviours)]
    records = []
    for k, b in enumerate(todo):
        say(0.05 + 0.6 * k / max(1, len(todo)), f"interpreting {b}")
        sts = [st for st in reading.stretches if st.behaviour == b]
        feats, detail = _calf_features(reading.behaviours[b], sts)
        cands = candidates_for(b, spec, s)
        rec = interpret_behaviour(it, b, feats, cands, detail)
        rec["read"] = {"n": reading.behaviours[b]["n"], "seconds": reading.behaviours[b]["seconds"],
                       "features": reading.behaviours[b]["features"],
                       "footfall_patterns": reading.behaviours[b]["footfall_patterns"],
                       "videos": reading.behaviours[b]["videos"]}
        records.append(rec)
    # the gaits as they are, judged the same way (they go over joint speed and the envelope at margin 0.2)
    defaults = []
    for key in ("walk", "trot"):
        e = it.evaluate(key, {}, {}, {})
        after = next((r for r in records if r["primitive"] == key and r["within_limits"]), None)
        defaults.append({"primitive": key, "default": {"within_limits": e.within_limits, "violations": e.violations,
                                                      "margin": e.margin, "fell": e.fell,
                                                      "constraints": e.constraints},
                         "interpreted": None if after is None else
                         {"behaviour": after["behaviour"], "params": after["params"], "margin": after["margin"],
                          "within_limits": after["within_limits"], "constraints": after["constraints"]}})
    interp_cost = {"plays": it.plays, "cache_hits": it.cache_hits, "play_seconds": round(it.wall_s, 1),
                   "seconds": round(time.perf_counter() - t_start, 1)}
    ctrl = build_states(reading, records, spec)
    plays = []
    first_ro = None
    if ctrl["states"]:
        for k, seed in enumerate(seeds):
            say(0.7 + 0.25 * k / max(1, len(seeds)), f"performing {seconds:.0f} s, seed {seed}")
            ro, rep, perf = perform(lab, spec, ctx["doc_compile"], {**ctrl}, seconds, seed, s.margin, cancelled)
            plays.append({"seed": seed, "report": rep, "perf": perf})
            if first_ro is None:
                first_ro = ro
    comp = comparison(reading, records, plays) if plays else None
    from calflab.behave.reading import LABELS

    run_id = lab.registry.new_run_id("interpret")
    run_dir = lab.registry.run_dir(run_id)
    b = basis(lab, design, ctx["compile"])
    payload = {
        "run_id": run_id, "reading_id": reading.id, "labels": LABELS, "settings": s.model_dump(mode="json"),
        "records": records, "defaults": defaults, "controller": ctrl, "seconds": seconds, "seeds": seeds,
        "plays": [{"seed": p["seed"], "report": {k: p["report"][k] for k in (
            "verdict", "within_limits", "fell", "fall_time_s", "first_limit", "tracking_rms_deg", "constraints",
            "safety", "hooves_down_fewer_than_3_fraction", "strip", "events", "battery", "joints", "mass_kg")},
            "episodes": p["perf"]["episodes"], "read": p["perf"]["read"], "per_episode": p["perf"]["per_episode"]}
            for p in plays],
        "comparison": comp,
        "calf": {"stretches": [st.model_dump(mode="json") for st in reading.stretches],
                 "videos": [v.model_dump(mode="json") for v in reading.videos],
                 "behaviours": reading.behaviours, "model": reading.model.model_dump(mode="json"),
                 "support": reading.support},
        "gaps": reading.gaps,
        "adr084": _adr084_scores(lab),
        "cost": {**interp_cost, "total_seconds": round(time.perf_counter() - t_start, 1),
                 "note": "Plays are cached per body: a second interpretation of the same body costs only what changed."},
        "basis": b,
    }
    if first_ro is not None:
        first_ro.save(run_dir / "rollout.npz")
        write_json(run_dir / "scene.json", build_scene(design, lab.state.layers, lab.state.settings))
    write_json(run_dir / "interpretation.json", payload)
    arts = {"report": f"runs/{run_id}/interpretation.json"}
    if first_ro is not None:
        arts.update(rollout=f"runs/{run_id}/rollout.npz", scene=f"runs/{run_id}/scene.json")
    lab.registry.save_run(RunRecord(
        id=run_id, kind="interpret", title=f"Interpretation of reading {reading.id}",
        duration_s=payload["cost"]["total_seconds"], seed=seeds[0] if seeds else 0, backend="local",
        inputs={"reading": reading.id, "settings": s.model_dump(mode="json"), "compile": ctx["compile"], "basis": b,
                "seconds": seconds, "seeds": seeds},
        genome=design.genome.model_dump(mode="json"), overrides=ctx["overrides"],
        controller={"key": "interpreted", "params": ctrl},
        metrics={"behaviours": len(records), "within_limits": sum(1 for r in records if r["within_limits"]),
                 "falls": sum(1 for p in plays if p["report"]["fell"]), "plays": it.plays},
        artifacts=arts,
    ))
    lab.bus.emit("runs.changed", run_id=run_id)
    return payload


def interpretation_view(lab: Any, run: str = "") -> dict[str, Any]:
    """The stored interpretation (the latest when ``run`` is empty)."""
    d = Path(lab.project.path) / "runs"
    if not run:
        found = sorted(d.glob("*-interpret-*/interpretation.json")) if d.is_dir() else []
        if not found:
            raise InterpretError("No interpretation yet: run Interpret footage first")
        path = found[-1]
    else:
        path = d / run / "interpretation.json"
        if not path.is_file():
            raise InterpretError(f"No interpretation in run {run!r}")
    return read_json(path)
