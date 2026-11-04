"""Lab side of judging clips in physics (ADR-084): play a clip once in MuJoCo, or search for a feasible version
of it, as jobs that leave runs.

* ``physics`` runs: one play (:mod:`calflab.behave.physics`). ``physics.json`` holds the report; the rollout and
  scene replay in the viewport like any run.
* ``adapt`` runs: the search of :mod:`calflab.behave.adapt`. ``adapt.json`` holds both reports, the steps, the
  operations, the character kept and a side-by-side comparison; ``adapted_clip.json`` the adapted clip; the
  rollout is the adapted version's. The clip as retargeted is played in a ``physics`` run of its own (``parent`` =
  the adapt run), so both replay.

The source is a motion-library clip or a candidate stretch of a video in the inbox. An adapted library clip is
saved as a new clip ``<id>-feasible`` (the clip itself is never changed); a candidate's stays in the run until
``keep_adapted_clip``.

Every run records what its numbers rest on (``basis``): the masses as entered and the parts with no mass, the
servo's library entry (verified or not, missing and defaulted values, armature), the PROVISIONAL values, and the
compile and controller settings used.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from calflab.app.scene import build_scene
from calflab.components import library
from calflab.project import RunRecord
from calflab.project.motions import MotionClip
from calflab.project.store import read_json, write_json


class PhysicsError(Exception):
    """Shown to the user as is."""


# ---------------------------------------------------------------------- source and context
def source_clip(lab: Any, clip: str = "", file: str = "", candidate: str = "", start: int | None = None,
                end: int | None = None, far_side: str = "") -> tuple[MotionClip, dict[str, Any], dict[str, Any]]:
    """The clip to judge, what it is (``source``) and how its frames map to video frames (``frame_map``)."""
    if clip:
        try:
            c = lab.motions.get(clip)
        except KeyError as exc:
            raise PhysicsError(str(exc)) from exc
        src = {"kind": "clip", "clip": c.id, "name": c.name, "accepted": bool(c.meta.get("accepted")),
               "adapted_from": c.meta.get("adapted_from")}
    elif file and candidate:
        from calflab.app.footage import FootageError, candidate_clip

        try:
            c = candidate_clip(lab, file, candidate, start, end, far_side=far_side)
        except FootageError as exc:
            raise PhysicsError(str(exc)) from exc
        c.id = f"{Path(file).stem}-{candidate}"
        src = {"kind": "candidate", "file": file, "candidate": candidate, "name": c.name,
               "frame_range": c.meta.get("frame_range"), "far_side": far_side or None}
    else:
        raise PhysicsError("Give a clip id, or a video file and a candidate")
    return c, src, frame_map(c)


def frame_map(clip: MotionClip) -> dict[str, Any]:
    """Clip frame -> video frame: the clip's first video frame, and video frames per clip frame (1 when the clip
    keeps the video's rate). Empty for clips not cut from a video."""
    fr = clip.meta.get("frame_range")
    if not fr:
        return {}
    video_fps = float((clip.meta.get("video") or {}).get("fps") or clip.fps)
    raw_fps = float(clip.meta.get("source_fps") or clip.fps)
    return {"start": int(fr[0]), "end": int(fr[1]), "frames_per_clip_frame": video_fps / raw_fps if raw_fps else 1.0,
            "file": clip.meta.get("footage")}


def basis(lab: Any, design: Any, compile_params: dict[str, Any]) -> dict[str, Any]:
    """What a physics result rests on, from the library and the design (nothing is filled in)."""
    lib = library()
    servos: dict[str, Any] = {}
    for a in design.spec.actuators:
        if a.component in servos:
            servos[a.component]["count"] += 1
            continue
        try:
            comp = lib.actuator(a.component)
        except (KeyError, TypeError) as exc:
            servos[a.component] = {"error": str(exc), "count": 1}
            continue
        given = comp.model_fields_set
        servos[a.component] = {
            "count": 1, "name": comp.name, "verified": comp.verified, "source": comp.source,
            "stall_torque_nm": comp.stall_torque_nm, "rated_torque_nm": comp.rated_torque_nm,
            "no_load_speed_rpm": comp.no_load_speed_rpm, "voltage_v": comp.voltage_v,
            "stall_current_a": comp.stall_current_a,
            "armature_kgm2": comp.armature_kgm2, "armature_default": "armature_kgm2" not in given,
            "guessed": list(getattr(comp, "guessed", []) or []),
            "missing": [f for f in ("stall_current_a", "rated_torque_nm") if getattr(comp, f) is None],
        }
    feral = design.spec.metadata.get("feral") or {}
    ratios = {d: r.get("ratio") for d, r in (feral.get("belt_drives") or {}).items()}
    return {
        "mass": lab._mass_record(design),
        "total_mass_g": round(design.spec.total_mass_g(), 1),
        "missing_masses": design.spec.metadata.get("missing_masses", []),
        "servos": servos,
        "belt_ratios": ratios,
        "provisional": feral.get("provisional", []),
        "compile": compile_params,
        "armature_scale": compile_params.get("armature_scale", 1.0),
    }


def _context(lab: Any) -> dict[str, Any]:
    from calflab.app.behave_jobs import BehaveError, behaviors_params
    from calflab.app.loads_jobs import FeralError, refuse_invalid_belts
    from calflab.behave.physics import compile_params

    design = lab.design()
    try:
        refuse_invalid_belts(design)
    except FeralError as exc:
        raise PhysicsError(str(exc)) from exc
    try:
        base = behaviors_params(lab)
    except BehaveError as exc:
        raise PhysicsError(str(exc)) from exc
    g = lab.state.graph
    doc = dict(g.role("model").params)
    return {"design": design, "base": base, "doc_compile": doc, "compile": compile_params(doc),
            "overrides": [o.model_dump(mode="json") for o in lab.state.overrides if o.enabled]}


def _player(ctx: dict[str, Any], s: Any, fm: dict[str, Any], cancelled: Any) -> Any:
    from calflab.behave import physics

    spec = ctx["design"].spec
    lib = library()

    def play(clip: MotionClip) -> tuple[Any, dict[str, Any]]:
        rollout, timing, _params = physics.play(clip, spec, lib, ctx["base"], ctx["doc_compile"], s, cancelled)
        return rollout, physics.report(rollout, clip, spec, lib, timing, s.margin, fm)
    return play


def _store_play(lab: Any, ctx: dict[str, Any], clip: MotionClip, src: dict[str, Any], s: Any, rollout: Any,
                rep: dict[str, Any], title: str, parent: str | None = None, extra: dict[str, Any] | None = None) -> str:
    """One physics play as a run of kind ``physics``."""
    design = ctx["design"]
    run_id = lab.registry.new_run_id("physics")
    run_dir = lab.registry.run_dir(run_id)
    rollout.save(run_dir / "rollout.npz")
    write_json(run_dir / "scene.json", build_scene(design, lab.state.layers, lab.state.settings))
    b = basis(lab, design, ctx["compile"])
    write_json(run_dir / "physics.json", {"run_id": run_id, "source": src, "settings": s.model_dump(mode="json"),
                                          "report": rep, "basis": b, **(extra or {})})
    lab.registry.save_run(RunRecord(
        id=run_id, kind="physics", title=title, duration_s=float(rep.get("wall_s") or 0.0), seed=s.seed,
        backend="local", parent=parent,
        inputs={"source": src, "clip_meta": _clip_provenance(clip), "settings": s.model_dump(mode="json"),
                "compile": ctx["compile"], "basis": b},
        genome=design.genome.model_dump(mode="json"), overrides=ctx["overrides"],
        controller={"key": "behaviors", "params": {k: v for k, v in ctx["base"].items() if k not in ("clips", "pools")}},
        metrics=_metrics(rep),
        artifacts={"rollout": f"runs/{run_id}/rollout.npz", "scene": f"runs/{run_id}/scene.json",
                   "report": f"runs/{run_id}/physics.json"},
    ))
    lab.bus.emit("runs.changed", run_id=run_id)
    return run_id


def _clip_provenance(clip: MotionClip) -> dict[str, Any]:
    keep = ("footage", "video_sha256", "candidate", "frame_range", "tracker", "lift", "smoothing", "repeated_frames",
            "accepted", "adapted_from", "adapted_operations", "feasible", "margin")
    return {"id": clip.id, "name": clip.name, "fps": clip.fps, "frames": clip.frames, "source": clip.source,
            **{k: clip.meta.get(k) for k in keep if k in clip.meta}}


def _metrics(rep: dict[str, Any]) -> dict[str, Any]:
    fl = rep.get("first_limit") or {}
    return {"verdict": rep["verdict"], "within_limits": rep["within_limits"], "fell": rep["fell"],
            "fall_time_s": rep["fall_time_s"], "tracking_rms_deg": rep["tracking_rms_deg"],
            "first_limit": fl.get("key"), "first_joint": fl.get("joint"),
            "violations": rep["safety"]["violations"], "margin": rep["safety"]["margin"]}


# ---------------------------------------------------------------------- play once
def play_in_physics(lab: Any, source: dict[str, Any], settings: dict[str, Any] | None = None) -> Any:
    """Play a clip (or candidate) once in physics as a job; the run (kind ``physics``) holds the report."""
    from calflab.behave.physics import PhysicsSettings

    try:
        s = PhysicsSettings.model_validate(settings or {})
    except Exception as exc:
        raise PhysicsError(f"Physics settings: {exc}") from exc
    clip, src, fm = source_clip(lab, **source)
    ctx = _context(lab)

    def work(job: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        job.report(0.1, f"playing {clip.name} in physics")
        rollout, rep = _player(ctx, s, fm, job.cancelled)(clip)
        rep["wall_s"] = round(time.perf_counter() - t0, 2)
        run_id = _store_play(lab, ctx, clip, src, s, rollout, rep, f"Physics: {clip.name}")
        job.log(f"{clip.name}: {rep['verdict']}" + (f" (falls at {rep['fall_time_s']:.2f} s)" if rep["fell"] else ""))
        return {"run_id": run_id, "verdict": rep["verdict"]}

    return lab.jobs.submit("physics", f"Play in physics: {clip.name}", work)


# ---------------------------------------------------------------------- feasible version
def compare(raw: dict[str, Any], adapted: dict[str, Any], raw_character: dict[str, Any],
            adapted_character: dict[str, Any]) -> dict[str, Any]:
    """Raw and adapted side by side: what limits each first, tracking, features kept, margins per constraint."""
    def side(rep: dict[str, Any], ch: dict[str, Any]) -> dict[str, Any]:
        cons = {c["key"]: {"value": c["value"], "limit": c["limit"], "violated": c["violated"], "margin": c.get("margin"),
                           "label": c.get("label"), "detail": c.get("detail")} for c in rep["constraints"]}
        worst_joint = max((r for r in rep["joints"] if r["in_clip"]), key=lambda r: r["envelope_peak"], default=None)
        return {"verdict": rep["verdict"], "within_limits": rep["within_limits"], "fell": rep["fell"],
                "fall_time_s": rep["fall_time_s"], "first_limit": rep["first_limit"],
                "tracking_rms_deg": rep["tracking_rms_deg"], "tracking_peak_deg": rep["tracking_peak_deg"],
                "margin": rep["safety"]["margin"], "violations": rep["safety"]["violations"],
                "duration_s": rep["duration_s"], "constraints": cons,
                "busiest_joint": None if worst_joint is None else
                {"joint": worst_joint["joint"], "envelope_peak": worst_joint["envelope_peak"],
                 "pct_stall_peak": worst_joint["pct_stall_peak"]},
                "character": ch}
    return {"raw": side(raw, raw_character), "adapted": side(adapted, adapted_character)}


def _feasible_id(lab: Any, base: str) -> str:
    d = lab.project.dir("motions")
    cid, n = f"{base}-feasible", 2
    while (d / f"{cid}.json").exists():
        cid = f"{base}-feasible-{n}"
        n += 1
    return cid


def adapt_clip(lab: Any, source: dict[str, Any], settings: dict[str, Any] | None = None,
               physics: dict[str, Any] | None = None) -> Any:
    """Search for a version of the clip within every limit with the margin, as a job (run kind ``adapt``)."""
    from calflab.behave import adapt
    from calflab.behave.physics import PhysicsSettings

    try:
        s = adapt.AdaptSettings.model_validate(settings or {})
        ps = PhysicsSettings.model_validate({**(physics or {}), "margin": s.margin})
    except Exception as exc:
        raise PhysicsError(f"Adapt settings: {exc}") from exc
    clip, src, fm = source_clip(lab, **source)
    ctx = _context(lab)
    run_id = lab.registry.new_run_id("adapt")

    def work(job: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        n = [0]

        def progress(msg: str) -> None:
            n[0] += 1
            job.report(min(0.95, n[0] / (s.max_rounds + s.give_back_rounds + 2)), msg)
            job.log(msg)

        spec = ctx["design"].spec
        res = adapt.adapt(clip, spec, library(), _player(ctx, ps, fm, job.cancelled), s, progress, job.cancelled)
        raw, best = res["raw"], res["adapted"]
        raw_char = adapt.character(res["raw_features"], res["raw_features"], 0.0, s)
        cmp_ = compare(raw["report"], best["report"], raw_char, best["character"])
        raw_run = _store_play(lab, ctx, raw["clip"], {**src, "as": "retargeted"}, ps, raw["rollout"], raw["report"],
                              f"Physics (as retargeted): {clip.name}", parent=run_id)
        run_dir = lab.registry.run_dir(run_id)
        best["rollout"].save(run_dir / "rollout.npz")
        write_json(run_dir / "scene.json", build_scene(ctx["design"], lab.state.layers, lab.state.settings))
        adapted = best["clip"]
        adapted.meta.update({"adapted_from": clip.id if src["kind"] == "clip" else None,
                             "adapted_from_source": src, "adapted_run": run_id,
                             "frame_range": clip.meta.get("frame_range"), "footage": clip.meta.get("footage"),
                             "video": clip.meta.get("video"), "source_fps": clip.fps,
                             "adapted": time.strftime("%Y-%m-%dT%H:%M:%S")})
        adapted.affect = clip.affect
        saved = None
        if src["kind"] == "clip" and not job.cancelled():
            adapted.id = _feasible_id(lab, clip.id)
            adapted.name = f"{clip.name} (feasible)" if res["feasible"] else f"{clip.name} (best found, over a limit)"
            adapted = lab.motions.save(adapted)
            saved = adapted.id
            lab.bus.emit("motions.changed", clip=adapted.id)
        else:
            adapted.id = f"{clip.id}-feasible"
        write_json(run_dir / "adapted_clip.json", adapted.model_dump(mode="json"))
        b = basis(lab, ctx["design"], ctx["compile"])
        stance = best["clip"].meta.get("stance") or {}
        doc = {
            "run_id": run_id, "source": src, "feasible": res["feasible"], "plays": res["plays"],
            "settings": s.model_dump(mode="json"), "physics_settings": ps.model_dump(mode="json"),
            "operations": best["ops"].model_dump(mode="json"), "operations_text": best["ops"].describe(),
            "steps": res["steps"], "character": best["character"], "raw_features": res["raw_features"],
            "compare": cmp_, "stance": {k: v for k, v in stance.items() if k != "support"},
            "stance_support": stance.get("support"),
            "raw_run": raw_run, "saved_clip": saved, "adapted_clip": adapted.id,
            "raw": raw["report"], "adapted": best["report"], "basis": b,
            "cancelled": bool(job.cancelled()),
        }
        write_json(run_dir / "adapt.json", doc)
        lab.registry.save_run(RunRecord(
            id=run_id, kind="adapt", title=f"Feasible version: {clip.name}", duration_s=time.perf_counter() - t0,
            seed=ps.seed, backend="local", status="cancelled" if job.cancelled() else "done",
            inputs={"source": src, "clip_meta": _clip_provenance(clip), "settings": s.model_dump(mode="json"),
                    "physics_settings": ps.model_dump(mode="json"), "compile": ctx["compile"], "basis": b},
            genome=ctx["design"].genome.model_dump(mode="json"), overrides=ctx["overrides"],
            controller={"key": "behaviors", "params": {k: v for k, v in ctx["base"].items() if k not in ("clips", "pools")}},
            metrics={**_metrics(best["report"]), "feasible": res["feasible"], "plays": res["plays"],
                     "character": round(best["character"]["score"], 3), "operations": best["ops"].describe(),
                     "raw_verdict": raw["report"]["verdict"]},
            artifacts={"rollout": f"runs/{run_id}/rollout.npz", "scene": f"runs/{run_id}/scene.json",
                       "report": f"runs/{run_id}/adapt.json", "clip": f"runs/{run_id}/adapted_clip.json"},
            tags=["feasible"] if res["feasible"] else [],
        ))
        lab.bus.emit("runs.changed", run_id=run_id)
        job.log(f"{clip.name}: {'feasible' if res['feasible'] else 'no feasible version found'} after {res['plays']} "
                f"plays: {best['ops'].describe()}; character kept {best['character']['score']:.2f}")
        return {"run_id": run_id, "feasible": res["feasible"], "clip": saved, "raw_run": raw_run}

    job = lab.jobs.submit("adapt", f"Make feasible: {clip.name}", work)
    job.result = {"run_id": run_id}
    return job


def keep_adapted_clip(lab: Any, run_id: str, name: str = "") -> dict[str, Any]:
    """Save an adapt run's clip into the motion library as a new clip (never over an existing one)."""
    try:
        rec = lab.registry.get_run(run_id)
    except Exception as exc:
        raise PhysicsError(f"No run {run_id!r}") from exc
    if rec.kind != "adapt" or "clip" not in rec.artifacts:
        raise PhysicsError(f"Run {run_id} is not a feasible-version (adapt) run")
    clip = MotionClip.model_validate(read_json(lab.project.resolve(rec.artifacts["clip"])))
    doc = read_json(lab.project.resolve(rec.artifacts["report"]))
    if doc.get("saved_clip"):
        raise PhysicsError(f"Run {run_id}'s clip is already in the library as {doc['saved_clip']!r}")
    base = clip.id.removesuffix("-feasible") or "clip"
    clip.id = _feasible_id(lab, base)
    if name:
        clip.name = name
    clip.meta["kept_from_run"] = run_id
    clip = lab.motions.save(clip)
    doc["saved_clip"] = clip.id
    write_json(lab.project.resolve(rec.artifacts["report"]), doc)
    lab.bus.emit("motions.changed", clip=clip.id)
    lab.bus.emit("runs.changed", run_id=run_id)
    return {"clip": clip.id, "name": clip.name, "feasible": doc.get("feasible")}


def physics_run_view(lab: Any, run_id: str) -> dict[str, Any]:
    """The stored report of a physics or adapt run, for the Behave panel."""
    try:
        rec = lab.registry.get_run(run_id)
    except Exception as exc:
        raise PhysicsError(f"No run {run_id!r}") from exc
    if rec.kind not in ("physics", "adapt") or "report" not in rec.artifacts:
        raise PhysicsError(f"Run {run_id} is not a physics or feasible-version run")
    return {"kind": rec.kind, "status": rec.status, "title": rec.title,
            **read_json(lab.project.resolve(rec.artifacts["report"]))}


def physics_runs(lab: Any, limit: int = 30, clip: str = "", file: str = "", candidate: str = "") -> list[dict[str, Any]]:
    """The latest physics and adapt runs, newest first, with their source and metrics; only those of one clip or
    one candidate if given. The as-retargeted plays inside an adapt run are left out (their adapt run lists them)."""
    out: list[dict[str, Any]] = []
    for kind in ("adapt", "physics"):
        for r in lab.registry.list_runs(kind, 500):
            try:
                rec = lab.registry.get_run(r["id"])
            except Exception:
                continue
            src = rec.inputs.get("source") or {}
            if src.get("as") == "retargeted":
                continue
            if clip and not (src.get("kind") == "clip" and src.get("clip") == clip):
                continue
            if (file or candidate) and not (src.get("kind") == "candidate" and src.get("file") == file
                                            and src.get("candidate") == candidate):
                continue
            out.append({**r, "source": src, "metrics": rec.metrics})
    out.sort(key=lambda r: (r["created"], r["id"]), reverse=True)
    return out[:limit]
