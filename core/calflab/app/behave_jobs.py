"""Lab side of behaviors from footage (ADR-073): importing keypoint tracks as
clips, previewing a clip on the body, and the data of the Behave panel.

Footage files live in ``<project>/footage/`` (copy the tracker's CSV there);
clips in ``<project>/motions/``; the project's own retarget maps in
``<project>/motions/maps/``. The motion library is not the document: an
import adds a file and is not an undo step.
"""

from __future__ import annotations

import time
from typing import Any

from calflab.app.footage import footage_view
from calflab.app.scene import build_scene
from calflab.behave.feasibility import clip_report
from calflab.behave.keypoints import read_tracks
from calflab.behave.preview import preview_rollout
from calflab.behave.retarget import list_maps, load_map, retarget
from calflab.components import library
from calflab.project import RunRecord
from calflab.project.store import write_json


class BehaveError(Exception):
    """Shown to the user as is."""


def footage_files(lab: Any) -> list[str]:
    d = lab.project.dir("footage")
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".txt"))


def import_footage(lab: Any, file: str, map_name: str, name: str, fps: float, standing: str = "",
                   fmt: str = "auto") -> dict[str, Any]:
    """Keypoint tracks (a file in ``<project>/footage``) -> a motion clip, with its retarget and body reports."""
    path = lab.project.dir("footage") / file
    if not path.is_file():
        raise BehaveError(f"No file {file!r} in {lab.project.dir('footage')}. Copy your tracker's CSV there first.")
    try:
        m = load_map(map_name, lab.project.path)
    except KeyError as exc:
        raise BehaveError(str(exc)) from exc
    design = lab.design()
    try:
        tracks = read_tracks(path, fps, fmt)  # type: ignore[arg-type]
        clip = retarget(tracks, m, name or path.stem, standing or None, robot_height_mm=design.spec.root.pos[2])
    except (ValueError, KeyError, IndexError) as exc:
        raise BehaveError(f"{file}: {exc}") from exc
    if not clip.joints:
        raise BehaveError(f"{file}: no joint could be retargeted ({clip.meta['retarget']['omitted']}); check the map's "
                          "landmark names against the file's")
    clip.meta["imported"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    clip = lab.motions.save(clip)
    lab.bus.emit("motions.changed", clip=clip.id)
    return {"clip": clip.id, "retarget": clip.meta["retarget"], "body": clip_report(clip, design.spec, library())}


def preview_clip(lab: Any, clip_id: str, speed: float = 1.0) -> dict[str, Any]:
    """The clip posed on the body frame by frame (no physics), stored as a run that replays in the viewport."""
    try:
        clip = lab.motions.get(clip_id)
    except KeyError as exc:
        raise BehaveError(str(exc)) from exc
    return preview_run(lab, clip, speed, f"Clip preview: {clip.name}", {"clip": clip.id})


def preview_run(lab: Any, clip: Any, speed: float, title: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Pose the body with ``clip`` (saved or not) and store it as a run of kind ``clip``."""
    design = lab.design()
    rollout = preview_rollout(clip, design.spec, speed)
    run_id = lab.registry.new_run_id("clip")
    run_dir = lab.registry.run_dir(run_id)
    rollout.save(run_dir / "rollout.npz")
    state = lab.state
    write_json(run_dir / "scene.json", build_scene(design, state.layers, state.settings))
    report = clip_report(clip, design.spec, library())
    lab.registry.save_run(RunRecord(
        id=run_id, kind="clip", title=title, duration_s=0.0, backend="local",
        inputs={**inputs, "speed": speed, "kinematic": True, "report": report},
        genome=design.genome.model_dump(mode="json"),
        metrics={"verdict": report["verdict"], "duration_s": round(rollout.meta["duration_s"], 3)},
        artifacts={"rollout": f"runs/{run_id}/rollout.npz", "scene": f"runs/{run_id}/scene.json"},
    ))
    lab.bus.emit("runs.changed", run_id=run_id)
    return {"run_id": run_id, "report": report}


def clip_filter(f: dict[str, Any] | None) -> dict[str, Any] | None:
    """Affect-tag conditions from the analysis params, or None when nothing narrows the list."""
    f = f or {}
    words = [w.strip() for w in str(f.get("words", "")).split(",") if w.strip()]
    val = (float(f.get("valence_min", -1.0)), float(f.get("valence_max", 1.0)))
    aro = (float(f.get("arousal_min", 0.0)), float(f.get("arousal_max", 1.0)))
    if not words and val == (-1.0, 1.0) and aro == (0.0, 1.0):
        return None
    return {"words": words or None, "valence": None if val == (-1.0, 1.0) else val,
            "arousal": None if aro == (0.0, 1.0) else aro}


def behave_view(lab: Any, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the Behave panel shows: clips with their reports for this body (only those whose affect tags
    match ``filters``, if any), maps, footage files, the inbox, controller."""
    from calflab.project.motions import AffectTags

    design = lab.design()
    lib = library()
    cond = clip_filter(filters)
    clips = []
    words: set[str] = set()
    for row in lab.motions.list():
        tags = AffectTags.model_validate(row["affect"]) if row.get("affect") else None
        if tags:
            words.update(w.strip().lower() for w in tags.words)
        if cond is not None and (tags is None or not tags.matches(**cond)):
            continue
        try:
            c = lab.motions.get(row["id"])
            clips.append({**row, "report": clip_report(c, design.spec, lib), "retarget": c.meta.get("retarget"),
                          "footage": c.meta.get("footage")})
        except Exception as exc:  # a bad file must not hide the others
            clips.append({**row, "error": str(exc)})
    ctrl = lab.state.graph.role("controller")
    return {
        "clips": clips,
        "maps": list_maps(lab.project.path),
        "footage": footage_files(lab),
        "footage_dir": str(lab.project.dir("footage")),
        "controller": {"type": ctrl.type, "params": ctrl.params},
        "inbox": footage_view(lab),
        "tag_words": sorted(words),
        "filtered": cond is not None,
    }


# ---------------------------------------------------------------------- composition study (ADR-078)
def behaviors_params(lab: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """The behaviors controller's parameters as the document has them (active, or kept from before), with
    ``extra`` over them and the project's clips resolved, so workers away from the project play the same clips."""
    from calflab.plugins import registry

    cls = registry.get("controller", "behaviors")
    node = lab.state.graph.role("controller")
    if node.type == "controller:behaviors":
        base = dict(node.params)
    else:
        base = dict((lab.state.settings.get("controller_params") or {}).get("controller:behaviors") or {})
    params = {**cls.Params().model_dump(mode="json"), **base, **(extra or {})}
    params.pop("clips", None)
    params.pop("pools", None)
    try:
        cls.Params.model_validate(params)
        return cls.resolve_params(params, lab.project.path)  # type: ignore[attr-defined]
    except Exception as exc:
        raise BehaveError(f"Behaviors: {exc}") from exc


def run_composition_study(lab: Any, settings: dict[str, Any] | None = None) -> Any:
    """Play each composition with each seed on the document's body; table of features, tracking and safety."""
    from calflab.behave.study import CompositionStudySettings, randomization, summarize, table_csv
    from calflab.evolve.safety import SafetyPolicy
    from calflab.plugins import Task, registry

    try:
        cfg = CompositionStudySettings.model_validate(settings or {})
    except Exception as exc:
        raise BehaveError(f"Composition study: invalid settings: {exc}") from exc
    if not cfg.compositions or not cfg.seeds:
        raise BehaveError("Give at least one composition and one seed")
    g = lab.state.graph.model_copy(deep=True)
    design = lab.design()
    from calflab.app.loads_jobs import FeralError, refuse_invalid_belts

    try:
        refuse_invalid_belts(design)
    except FeralError as exc:
        raise BehaveError(str(exc)) from exc
    params = [behaviors_params(lab, c.params) for c in cfg.compositions]
    overrides = [o.model_dump(mode="json") for o in lab.state.overrides if o.enabled]
    compile_params = {**g.role("model").params, "torque_derating": 1.0,
                      "randomization": randomization(cfg.randomize, cfg.friction, cfg.mass_scale)}
    common = {"genome": design.genome.model_dump(mode="json"), "overrides": overrides,
              "generator": g.role("design").type.split(":", 1)[1], "generator_params": lab.job_generator_params(g),
              "compile": compile_params, "safety": SafetyPolicy().model_dump(mode="json")}
    bkey = lab.backend_key
    backend = registry.get("compute_backend", bkey)()
    run_id = lab.registry.new_run_id("composition")

    def work(job: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        tasks = []
        for ci, prm in enumerate(params):
            for seed in cfg.seeds:
                sim = {**g.role("simulation").params, "duration_s": cfg.duration_s, "seed": seed}
                tasks.append(Task(fn="calflab.behave.study:evaluate_composition",
                                  payload={**common, "compile": {**compile_params}, "sim": sim,
                                           "controller": {"key": "behaviors", "params": prm}},
                                  id=f"{run_id}-c{ci}-s{seed}"))
        done = [0]

        def on_result(_i: int, _r: Any) -> None:
            done[0] += 1
            job.report(done[0] / len(tasks), f"{done[0]} of {len(tasks)} rollouts")

        results = backend.map(tasks, on_result=on_result, cancelled=job.cancelled)  # type: ignore[attr-defined]
        n = len(cfg.seeds)
        per = [results[i * n:(i + 1) * n] for i in range(len(params))]
        rows = summarize(cfg.compositions, list(cfg.seeds), per)
        run_dir = lab.registry.run_dir(run_id)
        from calflab.behave.descriptors import NOTE
        from calflab.behave.study import feature_columns

        write_json(run_dir / "composition_study.json", {
            "run_id": run_id, "settings": cfg.model_dump(mode="json"), "rows": rows, "features": feature_columns(),
            "note": NOTE, "compile": compile_params, "safety_policy": common["safety"],
            "runs": [{"composition": cfg.compositions[i].name, "seed": cfg.seeds[k], **(r if isinstance(r, dict) else {"error": str(r)})}
                     for i, rs in enumerate(per) for k, r in enumerate(rs)],
        })
        (run_dir / "composition_study.csv").write_bytes(table_csv(rows).encode("utf-8"))
        lab.registry.save_run(RunRecord(
            id=run_id, kind="composition", title="Composition study", duration_s=time.perf_counter() - t0, backend=bkey,
            status="cancelled" if job.cancelled() else "done",
            inputs={"settings": cfg.model_dump(mode="json"), "compile": compile_params, "safety_policy": common["safety"],
                    "controllers": params, "mass": lab._mass_record(design)},
            genome=design.genome.model_dump(mode="json"), overrides=overrides,
            metrics={"compositions": len(rows), "rollouts": len(tasks),
                     "falls": sum(r["falls"] for r in rows)},
            artifacts={"study": f"runs/{run_id}/composition_study.json", "csv": f"runs/{run_id}/composition_study.csv"},
        ))
        lab.bus.emit("runs.changed", run_id=run_id)
        return {"run_id": run_id, "rows": len(rows)}

    job = lab.jobs.submit("composition", "Composition study", work, backend=bkey)
    job.result = {"run_id": run_id}
    return job
