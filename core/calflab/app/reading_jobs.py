"""Lab side of reading footage (ADR-085): every video of the inbox read into behaviours and a semi-Markov model,
stored as ``<project>/footage/readings/<id>.json`` (versioned, schema-validated, with provenance)."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from calflab.behave import reading as rd
from calflab.project.store import read_json, write_json

log = logging.getLogger(__name__)


class ReadingError(Exception):
    """Shown to the user as is."""


def readings_dir(lab: Any) -> Path:
    return Path(lab.project.path) / "footage" / "readings"


def _lift_path(pdir: Path, sha: str, map_name: str, bend_choice: str) -> Path | None:
    base = pdir / "footage" / "lift"
    for name in ([f"{sha[:16]}.{map_name}.window.json"] if bend_choice == "window" else []) + [
            f"{sha[:16]}.{map_name}.json", f"{sha[:16]}.json"]:
        if (base / name).is_file():
            return base / name
    return None


def _unreliable_reasons(res: Any) -> list[str]:
    counts: dict[str, int] = {}
    for st, why in zip(res.state, res.reasons, strict=False):
        if st in ("unreliable", "missing"):
            for w in why or ["no confident point"]:
                key = w.split(":")[0].split(" (")[0]
                key = "".join(ch for ch in key if not ch.isdigit()).replace(". ", " ").strip()
                counts[key] = counts.get(key, 0) + 1
    return [f"{k} ({n} frames)" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])[:4]]


def _affect(pdir: Path) -> list[dict[str, Any]]:
    """Accepted clips that carry the researcher's affect tags, with the frames they were cut from."""
    from calflab.project.motions import MotionClip

    out = []
    d = pdir / "motions"
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            c = MotionClip.model_validate(read_json(f))
        except Exception:  # noqa: BLE001 - a broken clip file is not the reading's business
            continue
        fr = c.meta.get("frame_range")
        if c.affect is None or not fr or not c.meta.get("footage"):
            continue
        out.append({"clip": c.id, "file": c.meta["footage"], "start": int(fr[0]), "end": int(fr[1]),
                    "affect": c.affect.model_dump(mode="json")})
    return out


def expressive_gaps(spec: Any, beh: dict[str, dict[str, Any]], usable_any: bool) -> list[dict[str, Any]]:
    """What the calf does that this body cannot express, from the body's joints and the reading. Listed, never
    approximated."""
    joints = {j.id for j in spec.joints if j.type == "hinge"}
    has = lambda part: any(j.endswith(part) for j in joints)  # noqa: E731
    out: list[dict[str, Any]] = []
    head = [(b, d["features"]["head_motion_bl_s"]["mean"]) for b, d in beh.items()
            if d["n"] and "head_motion_bl_s" in d["features"]]
    if not any("neck" in j or "head" in j for j in joints):
        out.append({"what": "head and neck", "why": "the body has no neck or head joint (the head is a fixed lump)",
                    "seen": {b: f"nose moves {v:.2f} body lengths/s against the shoulders" for b, v in head},
                    "handling": "dropped: no primitive moves a head; not turned into trunk or leg motion"})
    out.append({"what": "tail", "why": "the body has no tail joint, and AP-10K tracks only the tail's root",
                "seen": {}, "handling": "not measured, not expressed"})
    if not any(j.endswith(".hip_flex") for j in joints):
        out.append({"what": "hind hip swing (thigh fore and aft)",
                    "why": "the femur is fixed: no hind hip pitch; the lift follows a calf's thigh with the stifle "
                           "and hock only",
                    "seen": {}, "handling": "the stifle and hock carry what they can; the rest is not expressed"})
    if not (has("fl.shoulder_abd") or any(j.startswith("joint.f") and j.endswith("abd") for j in joints)):
        out.append({"what": "front legs out to the side (abduction)", "why": "the front legs have no ab/adduction",
                    "seen": {}, "handling": "lateral weight shifts use the hind ab/ad only"})
    out.append({"what": "spine (back arching, bending sideways)", "why": "the trunk is one rigid body",
                "seen": {}, "handling": "trunk pitch and roll as a whole only"})
    out.append({"what": "fetlock and pastern", "why": "the cannon ends in a hoof pad (no joint below the carpus/hock)",
                "seen": {}, "handling": "not expressed"})
    fast = beh.get("other", {})
    if fast.get("n"):
        f = fast.get("features", {})
        out.append({"what": "fast, airborne movement (canter, bucking, leaps)",
                    "why": "judged per body in the interpretation: whether a gait of this body reaches it within "
                           "the limits",
                    "seen": {"other": f"two or more hooves up {f.get('two_up_fraction', {}).get('mean', 0):.0%} of "
                                      f"the time, {fast['seconds']:.1f} s in {fast['n']} stretches"},
                    "handling": "see the interpretation of 'other'"})
    if not usable_any:
        out.append({"what": "everything", "why": "no usable video", "seen": {}, "handling": "nothing read"})
    return out


def read_footage(lab: Any, settings: dict[str, Any] | None = None, exclude: dict[str, str] | None = None,
                 camera: bool = True, report: Any = None) -> rd.Reading:
    """Read every lifted video of the inbox (or not, with the reason) into a stored :class:`Reading`."""
    from calflab.app.footage import load_settings
    from calflab.behave import inbox
    from calflab.behave.camera_motion import background_shift, camera_motion
    from calflab.behave.lift import LiftResult, load_lift_map
    from calflab.behave.signals import from_lift

    try:
        s = rd.ReadingSettings.model_validate(settings or {})
    except Exception as exc:
        raise ReadingError(f"Reading settings: {exc}") from exc
    pdir = Path(lab.project.path)
    fs = load_settings(pdir)
    ib_path = pdir / "footage" / "inbox.json"
    if not ib_path.is_file():
        raise ReadingError("The video inbox is empty: drop videos into footage/videos first")
    records = json.loads(ib_path.read_text(encoding="utf-8"))
    spec = lab.design().spec
    exclude = dict(exclude or {})
    videos: list[rd.VideoReading] = []
    stretches: list[rd.Stretch] = []
    tags = _affect(pdir)
    lift_files: dict[str, str] = {}
    for k, (file, rec) in enumerate(sorted(records.items())):
        if report is not None:
            report(k / max(1, len(records)), f"reading {file}")
        info = rec.get("info") or {}
        vr = rd.VideoReading(file=file, sha256=rec.get("sha256", ""), usable=False, frames=int(info.get("frames") or 0),
                             fps=float(info.get("fps") or 0.0), seconds=float(info.get("duration_s") or 0.0))
        videos.append(vr)
        if file in exclude:
            vr.reasons.append(f"excluded by you: {exclude[file]}")
            continue
        if rec.get("mode") != "3d":
            vr.reasons.append("not lifted in 3D (the reading needs the 3D lift)")
            continue
        lp = _lift_path(pdir, rec.get("sha256", ""), fs.map_3d, fs.lift.bend_choice)
        if lp is None:
            vr.reasons.append("no stored lift; press Analyse again")
            continue
        res = LiftResult.model_validate_json(lp.read_text(encoding="utf-8"))
        lift_files[file] = lp.name
        rel = float(np.mean(res.reliable()))
        body_px = float(res.summary.get("body_px_median") or 0.0)
        vr.lift = {"file": lp.name, "map": res.map, "reliable_fraction": round(rel, 3), "body_px": body_px,
                   "median_view_yaw_deg": res.summary.get("median_view_yaw_deg"),
                   "labels_exchanged_fraction": res.summary.get("labels_exchanged_fraction"),
                   "repeated_fraction": res.summary.get("repeated_fraction")}
        vr.proportions = {k2: res.proportions.get(k2) for k2 in ("trunk_length", "front_leg", "width_over_length",
                                                                  "width_source")}
        vr.fps = res.fps
        vr.frames = res.frames
        vr.seconds = round(res.frames / res.fps, 3)
        if rel < s.min_reliable:
            vr.reasons.append(f"only {rel:.0%} of frames reliable (need {s.min_reliable:.0%}): "
                              + "; ".join(_unreliable_reasons(res)))
        if body_px and body_px < s.min_body_px:
            vr.reasons.append(f"the calf is {body_px:.0f} px long in the image (need {s.min_body_px:.0f}): the "
                              "tracker's noise is a large share of every movement")
        tracks = None
        with contextlib.suppress(FileNotFoundError, KeyError):
            tracks = inbox.load_tracks(pdir, rec["sha256"])
        video = pdir / "footage" / "videos" / file
        moves = False
        shift = None
        if camera and tracks is not None and video.is_file():
            try:
                shift = background_shift(video, tracks)
                cm = camera_motion(video, tracks, body_px, res.fps, s.camera_moves_bl_s, shift)
                vr.camera = {**res.camera, "motion": cm}
                moves = bool(cm["moves"])
            except Exception as exc:  # noqa: BLE001 - an unreadable video only loses the camera check
                vr.camera = {**res.camera, "motion": {"error": str(exc)}}
        else:
            vr.camera = dict(res.camera)
        if vr.reasons:
            continue
        try:
            lmap = load_lift_map(res.map, pdir)
        except KeyError:
            lmap = None
        sig = from_lift(res, spec, tracks, s.cutoff_hz, background=shift["vector_px"] if shift else None, lmap=lmap)
        up, how = rd.lifted(sig, s)
        vr.lift["contact"] = how
        sts = rd.label(sig, up, s, camera_moves=moves, video=file)
        for st in sts:
            st.affect = [t for t in tags if t["file"] == file and t["start"] < st.end and st.start < t["end"]]
        vr.usable = True
        vr.stretches = len(sts)
        vr.seconds_read = round(sum(st.t1 - st.t0 for st in sts), 3)
        if moves:
            vr.reasons.append("the camera moves: the trunk's travel is not read here (turns are)")
        stretches.extend(sts)
    model = rd.fit_model(stretches, s)
    beh = rd.behaviour_summary(stretches)
    notes = []
    ratios = [v.proportions.get("trunk_length") for v in videos if v.usable and v.proportions.get("trunk_length")]
    if ratios:
        notes.append(f"Trunk length fits {min(ratios):.2f}-{max(ratios):.2f} times the robot's in the usable videos; "
                     "the footage itself does not say whether it is one calf.")
    if not tags:
        notes.append("No accepted clip carries your affect tags yet, so no stretch has any.")
    rid = rd.new_id()
    try:
        import calflab

        code = getattr(calflab, "__version__", "")
    except Exception:  # noqa: BLE001
        code = ""
    out = rd.Reading(
        id=rid, created=rid, settings=s,
        provenance={"project": str(pdir.name), "lift_map": fs.map_3d, "bend_choice": fs.lift.bend_choice,
                    "repeated_frames": fs.repeated.method, "lift_files": lift_files, "code_version": code,
                    "body": spec.metadata.get("generator") or getattr(spec, "name", ""), "excluded": exclude,
                    "signals": "calflab.behave.signals.from_lift (low-pass at cutoff_hz)"},
        videos=videos, stretches=stretches, behaviours=beh, model=model,
        support=rd.support_statement(videos, stretches, model, notes),
        gaps=expressive_gaps(spec, beh, any(v.usable for v in videos)),
    )
    d = readings_dir(lab)
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / f"{rid}.json", out.model_dump(mode="json"))
    lab.bus.emit("readings.changed", reading=rid)
    return out


def list_readings(lab: Any) -> list[dict[str, Any]]:
    d = readings_dir(lab)
    out = []
    for f in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        try:
            r = read_json(f)
        except Exception:  # noqa: BLE001
            continue
        out.append({"id": r.get("id"), "created": r.get("created"), "stretches": len(r.get("stretches") or []),
                    "videos_usable": (r.get("support") or {}).get("videos_usable")})
    return out


def load_reading(lab: Any, rid: str = "") -> rd.Reading:
    d = readings_dir(lab)
    if not rid:
        files = sorted(d.glob("*.json")) if d.is_dir() else []
        if not files:
            raise ReadingError("No reading yet: run Read footage first")
        path = files[-1]
    else:
        path = d / f"{rid}.json"
        if not path.is_file():
            raise ReadingError(f"No reading {rid!r}")
    data = read_json(path)
    if int(data.get("schema_version", 0)) != rd.SCHEMA_VERSION:
        raise ReadingError(f"Reading {path.stem} has schema version {data.get('schema_version')}; this lab reads "
                           f"{rd.SCHEMA_VERSION}. Read the footage again.")
    return rd.Reading.model_validate(data)
