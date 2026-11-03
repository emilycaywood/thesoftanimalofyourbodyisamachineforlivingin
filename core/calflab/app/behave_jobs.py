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
