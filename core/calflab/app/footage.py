"""Lab side of the footage inbox (ADR-076, ADR-077): watching the videos
folder, processing each new video as a job, and reviewing its candidates.

* :class:`FootageInbox` polls ``<project>/footage/videos/`` on a background
  thread (never the UI's), and submits one processing job at a time for
  queued videos: track (the chosen pose tracker) -> retarget (map, side
  settled from the footage, camera view checked) -> segment -> candidates ->
  ``needs_review``.
* Review: a candidate is cut from the retargeted video on demand
  (:func:`candidate_clip`), previewed on the body (a kinematic run), and
  accepted as a motion clip with full provenance and the researcher's affect
  tags, or rejected.
* The server serves frames (:func:`frame_image`) and tracked points
  (:func:`frame_points`); the browser only draws them.

Settings (tracker, map, segmentation) are the project's, in
``<project>/footage/settings.json``, not the undoable document, like the
motion library itself.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from calflab.behave import inbox
from calflab.behave.clips import cut, near_angles, settle_side, standing_frame
from calflab.behave.keypoints import clean
from calflab.behave.retarget import RetargetMap, load_map
from calflab.behave.segment import SegmentSettings, segment
from calflab.behave.video import VideoError, encode_image, open_video
from calflab.behave.view import view_report
from calflab.plugins import TrackerCancelled, registry
from calflab.project.motions import AffectTags, MotionClip

log = logging.getLogger(__name__)


class FootageError(Exception):
    """Shown to the user as is."""


class FootageSettings(BaseModel):
    tracker: str = "rtmpose_ap10k"
    tracker_params: dict[str, Any] = Field(default_factory=dict)
    map: str = "ap10k_side"
    #: decide the near side from the footage (overrides the map's near_side)
    auto_side: bool = True
    segmentation: SegmentSettings = Field(default_factory=SegmentSettings)
    poll_s: float = 2.0


def settings_path(project_dir: Path) -> Path:
    return Path(project_dir) / "footage" / "settings.json"


def load_settings(project_dir: Path) -> FootageSettings:
    p = settings_path(project_dir)
    if p.is_file():
        return FootageSettings.model_validate(json.loads(p.read_text(encoding="utf-8")))
    return FootageSettings()


def save_settings(project_dir: Path, s: FootageSettings) -> None:
    p = settings_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s.model_dump(mode="json"), indent=1), encoding="utf-8")


# ---------------------------------------------------------------------- watcher
class FootageInbox:
    """Polls the videos folder and runs one processing job at a time."""

    def __init__(self, lab: Any):
        self.lab = lab
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._busy: str | None = None  # file being processed
        self._lock = threading.Lock()
        inbox.videos_dir(self.project_dir)  # the folder the researcher drops videos into exists from the start

    @property
    def project_dir(self) -> Path:
        return Path(self.lab.project.path)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="calflab-footage", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:  # the watcher must survive a bad file
                log.exception("Footage inbox poll failed")
            self._stop.wait(load_settings(self.project_dir).poll_s)

    def poll(self) -> dict[str, Any]:
        """One scan; starts the next queued video if nothing is processing. Returns what changed."""
        changes = inbox.scan(self.project_dir)
        if changes["queued"] or changes["gone"]:
            self.lab.bus.emit("footage.changed", **changes)
        started = None
        with self._lock:
            if self._busy is None:
                queued = [r.file for r in inbox.load(self.project_dir).values() if r.status == "queued"]
                if queued:
                    started = queued[0]
                    self._busy = started
        if started:
            self.lab.jobs.submit("footage", f"Process video {started}", lambda job: self._process(job, started))
        return {**changes, "started": started}

    def _process(self, job: Any, file: str) -> dict[str, Any]:
        try:
            return process_video(self.lab, file, job)
        finally:
            with self._lock:
                self._busy = None
            self.lab.bus.emit("footage.changed", file=file)


# ---------------------------------------------------------------------- processing
def _set(lab: Any, file: str, sha: str, **fields: Any) -> None:
    """Update a record unless the file changed meanwhile (then the new content's record must not be touched)."""
    recs = inbox.load(lab.project.path)
    if file in recs and recs[file].sha256 == sha:
        inbox.update(lab.project.path, file, **fields)
        lab.bus.emit("footage.changed", file=file, status=fields.get("status"))


def _map_for(lab: Any, s: FootageSettings) -> RetargetMap:
    try:
        m = load_map(s.map, lab.project.path)
    except KeyError as exc:
        raise FootageError(str(exc)) from exc
    return m.model_copy(update={"near_side": "auto"}) if s.auto_side else m


def process_video(lab: Any, file: str, job: Any) -> dict[str, Any]:
    """Track, retarget, check the view and segment one video (a job)."""
    pdir = Path(lab.project.path)
    rec = inbox.load(pdir)[file]
    sha = rec.sha256
    s = load_settings(pdir)
    path = inbox.videos_dir(pdir) / file
    _set(lab, file, sha, status="tracking", reason="", progress=0.0, job=job.job.id)
    try:
        with open_video(path) as r:
            info = r.info
        _set(lab, file, sha, info=info.model_dump(mode="json") | {"duration_s": round(info.duration_s, 3)})
        tracker = registry.get("pose_tracker", s.tracker)(s.tracker_params)
        ok, why = tracker.available()  # type: ignore[attr-defined]
        if not ok:
            raise FootageError(f"Tracker {s.tracker}: {why}")
        last = [0.0]

        def report(frac: float, msg: str) -> None:
            job.report(0.8 * frac, msg)
            if frac - last[0] >= 0.05 or frac >= 1.0:
                last[0] = frac
                _set(lab, file, sha, progress=round(0.8 * frac, 3))

        t0 = time.perf_counter()
        tracks = tracker.track(path, report, job.cancelled)  # type: ignore[attr-defined]
        job.log(f"Tracked {tracks.frames} frames with {s.tracker} in {time.perf_counter() - t0:.1f} s")
        inbox.save_tracks(pdir, sha, tracks)
        _set(lab, file, sha, status="retargeting", progress=0.85, tracker=tracks.model)
        out = analyse(lab, tracks, _map_for(lab, s), s.segmentation, path.stem)
        _set(lab, file, sha, status="needs_review", progress=1.0, map=out["map"], near_side=out["near_side"],
             view=out["view"], standing_frame=out["standing_frame"], segmentation=out["segmentation"],
             candidates=out["candidates"],
             reason="" if out["candidates"] else "No stretch long enough was found (see the segmentation settings)")
        return {"file": file, "candidates": len(out["candidates"]), "view": out["view"]["verdict"]}
    except TrackerCancelled:
        _set(lab, file, sha, status="cancelled", reason="cancelled")
        raise
    except Exception as exc:
        if job.cancelled():
            _set(lab, file, sha, status="cancelled", reason="cancelled")
            raise
        _set(lab, file, sha, status="failed", reason=f"{type(exc).__name__}: {exc}" if not isinstance(
            exc, FootageError | VideoError) else str(exc))
        raise


def analyse(lab: Any, tracks: Any, m: RetargetMap, seg: SegmentSettings, stem: str) -> dict[str, Any]:
    """Side, view, segmentation and candidates of tracked footage."""
    m2, side = settle_side(tracks, m)
    view = view_report(tracks, m2)
    height = lab.design().spec.root.pos[2]
    first = near_angles(tracks, m2, None, height)
    if not first.joints:
        raise FootageError(f"No joint could be retargeted with map {m.name} "
                           f"({first.meta['retarget']['omitted']}); the tracker's names: {', '.join(tracks.names)}")
    cleaned, _ = clean(tracks, m2.min_likelihood, m2.max_gap_frames, m2.smooth_frames)
    from calflab.behave.retarget import _pick

    rear = _pick(cleaned, m2.trunk[0]) if len(m2.trunk) == 2 else None
    front = _pick(cleaned, m2.trunk[1]) if len(m2.trunk) == 2 else None
    import numpy as np

    joints = {k: np.asarray(v) for k, v in first.joints.items()}
    segs = segment(cleaned, rear, front, joints, seg, view["turned"])
    stand = standing_frame(segs["candidates"])
    counts: dict[str, int] = {}
    cands: list[inbox.Candidate] = []
    for c in segs["candidates"]:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
        cands.append(inbox.Candidate(id=f"c{len(cands) + 1}", name=f"{stem} {c['kind']} {counts[c['kind']]}",
                                     **{k: v for k, v in c.items() if k in inbox.Candidate.model_fields}))
    return {
        "map": m2.model_dump(mode="json"), "near_side": side or {"near_side": m2.near_side, "method": "map"},
        "view": {k: v for k, v in view.items() if k not in ("yaw_deg", "turned")},
        "standing_frame": stand,
        "segmentation": {"settings": segs["settings"], "body_px": segs["body_px"],
                         "standing_frame": stand, "signals": segs["signals"]},
        "candidates": cands,
    }


# ---------------------------------------------------------------------- review
def _record(lab: Any, file: str) -> inbox.VideoRecord:
    recs = inbox.load(lab.project.path)
    if file not in recs:
        raise FootageError(f"No video {file!r} in the inbox")
    return recs[file]


def _candidate(rec: inbox.VideoRecord, cid: str) -> inbox.Candidate:
    for c in rec.candidates:
        if c.id == cid:
            return c
    raise FootageError(f"{rec.file} has no candidate {cid!r}")


def candidate_clip(lab: Any, file: str, cid: str, start: int | None = None, end: int | None = None,
                   name: str = "", far_side: str = "") -> MotionClip:
    """The candidate cut from the retargeted video (trimmed to [start, end) if given), with its provenance."""
    rec = _record(lab, file)
    if not rec.map:
        raise FootageError(f"{file} has not been processed yet ({rec.status})")
    c = _candidate(rec, cid)
    tracks = inbox.load_tracks(lab.project.path, rec.sha256)
    m = RetargetMap.model_validate(rec.map)
    height = lab.design().spec.root.pos[2]
    full = near_angles(tracks, m, rec.standing_frame if rec.standing_frame is not None else None, height)
    a = c.start if start is None else int(start)
    b = c.end if end is None else int(end)
    fs = far_side or c.far_side
    period = c.period_s
    if fs == "half_cycle" and (a, b) != (c.start, c.end) and period:
        cycles = max(1, int((b - a) / (period * tracks.fps)))  # a trimmed gait keeps whole cycles
        b = a + int(round(cycles * period * tracks.fps))
    try:
        clip = cut(full, a, b, name or c.name, fs, period, m.near_side)
    except ValueError as exc:
        raise FootageError(str(exc)) from exc
    clip.meta.update({
        "footage": file, "video_sha256": rec.sha256, "video": rec.info, "candidate": cid, "kind": c.kind,
        "tracker": rec.tracker, "map": rec.map, "near_side_detected": rec.near_side, "view": rec.view,
        "standing_frame": rec.standing_frame, "cleaning": {"min_likelihood": m.min_likelihood,
                                                          "max_gap_frames": m.max_gap_frames,
                                                          "smooth_frames": m.smooth_frames},
        "segmentation": rec.segmentation.get("settings"), "retarget": full.meta.get("retarget"),
    })
    return clip


def preview_candidate(lab: Any, file: str, cid: str, start: int | None = None, end: int | None = None,
                      far_side: str = "") -> dict[str, Any]:
    from calflab.app.behave_jobs import preview_run

    clip = candidate_clip(lab, file, cid, start, end, far_side=far_side)
    clip.id = f"{Path(file).stem}-{cid}"
    return preview_run(lab, clip, 1.0, f"Candidate preview: {file} {cid}",
                       {"footage": file, "candidate": cid, "frame_range": clip.meta["frame_range"]})


def accept_candidate(lab: Any, file: str, cid: str, name: str = "", start: int | None = None, end: int | None = None,
                     far_side: str = "", affect: dict[str, Any] | None = None) -> dict[str, Any]:
    """Store the candidate as a motion clip (provenance + affect tags) and mark it accepted."""
    from calflab.behave.feasibility import clip_report
    from calflab.components import library

    clip = candidate_clip(lab, file, cid, start, end, name, far_side)
    tags = AffectTags.model_validate({**(affect or {}), "tagged": time.strftime("%Y-%m-%dT%H:%M:%S")}) \
        if affect and any(v not in (None, "", []) for v in affect.values()) else None
    clip.affect = tags
    clip.meta["accepted"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    clip = lab.motions.save(clip)
    rec = _record(lab, file)
    for c in rec.candidates:
        if c.id == cid:
            c.status, c.clip, c.name = "accepted", clip.id, clip.name
            fr = clip.meta["frame_range"]
            c.trim = (fr[0], fr[1]) if (fr[0], fr[1]) != (c.start, c.end) else None
    status = "ready" if all(c.status != "pending" for c in rec.candidates) else rec.status
    inbox.update(lab.project.path, file, candidates=rec.candidates, status=status)
    lab.bus.emit("motions.changed", clip=clip.id)
    lab.bus.emit("footage.changed", file=file)
    return {"clip": clip.id, "report": clip_report(clip, lab.design().spec, library()), "status": status}


def reject_candidate(lab: Any, file: str, cid: str) -> dict[str, Any]:
    rec = _record(lab, file)
    _candidate(rec, cid).status = "rejected"
    status = "ready" if all(c.status != "pending" for c in rec.candidates) else rec.status
    inbox.update(lab.project.path, file, candidates=rec.candidates, status=status)
    lab.bus.emit("footage.changed", file=file)
    return {"status": status}


def retry_video(lab: Any, file: str) -> dict[str, Any]:
    rec = _record(lab, file)
    if rec.status in ("tracking", "retargeting"):
        raise FootageError(f"{file} is being processed; cancel it first")
    inbox.update(lab.project.path, file, status="queued", reason="", progress=0.0, candidates=[])
    lab.bus.emit("footage.changed", file=file)
    return lab.footage.poll()


def cancel_video(lab: Any, file: str) -> dict[str, Any]:
    rec = _record(lab, file)
    if rec.status in ("tracking", "retargeting") and rec.job:
        with contextlib.suppress(KeyError):  # the job is gone (lab restarted): just mark the record
            lab.jobs.cancel(rec.job)
    if rec.status in ("queued", "waiting", "tracking", "retargeting"):
        inbox.update(lab.project.path, file, status="cancelled", reason="cancelled")
    lab.bus.emit("footage.changed", file=file)
    return {"status": "cancelled"}


# ---------------------------------------------------------------------- frames and points for the browser
def frame_image(lab: Any, file: str, index: int, max_width: int = 640) -> tuple[bytes, str]:
    path = inbox.videos_dir(lab.project.path) / Path(file).name
    try:
        with open_video(path) as r:
            return encode_image(r.frame(int(index)), max_width)
    except VideoError as exc:
        raise FootageError(str(exc)) from exc


def frame_points(lab: Any, file: str, start: int = 0, end: int | None = None) -> dict[str, Any]:
    """Tracked points in image pixels (y down) per frame of [start, end), with confidences, the skeleton, and the
    landmarks the retarget map uses."""
    rec = _record(lab, file)
    tracks = inbox.load_tracks(lab.project.path, rec.sha256)
    end = tracks.frames if end is None else min(int(end), tracks.frames)
    xy = tracks.xy[start:end].copy()
    xy[:, :, 1] = -xy[:, :, 1]
    from calflab.behave.synthetic import STICKS
    from calflab.behave.trackers import AP10K_SKELETON

    names = set(tracks.names)
    links = [list(link) for link in (*AP10K_SKELETON, *STICKS) if link[0] in names and link[1] in names]
    used: set[str] = set()
    if rec.map:
        m = rec.map
        for r in m.get("joints", {}).values():
            for lm in (r.get("flexion") or []) + (r.get("swing") or []):
                used.update([lm] if isinstance(lm, str) else lm)
        for lm in m.get("trunk", []):
            used.update([lm] if isinstance(lm, str) else lm)
    rows = []
    for f in range(xy.shape[0]):
        rows.append([[None if v != v else round(float(v), 1) for v in xy[f, k]] + [round(float(tracks.likelihood[start + f, k]), 3)]
                     for k in range(len(tracks.names))])
    thr = RetargetMap.model_validate(rec.map).min_likelihood if rec.map else 0.5
    return {"names": tracks.names, "links": links, "used": sorted(used & names), "start": start, "end": end,
            "image_size": tracks.image_size, "fps": tracks.fps, "min_likelihood": thr, "frames": rows}


def footage_view(lab: Any) -> dict[str, Any]:
    """The inbox for the Behave panel: records (no per-frame arrays), settings, trackers, model downloads."""
    from calflab.behave import models

    pdir = Path(lab.project.path)
    recs = inbox.load(pdir)
    rows = []
    for r in recs.values():
        d = r.model_dump(mode="json")
        d["segmentation"] = {k: v for k, v in r.segmentation.items() if k != "signals"}
        d["map"] = {"name": r.map.get("name"), "near_side": r.map.get("near_side")} if r.map else {}
        rows.append(d)
    trackers = [{"key": k, "label": c.label, **c.extra()} for k, c in sorted(registry.all("pose_tracker").items())]
    return {
        "dir": str(inbox.videos_dir(pdir)), "videos": rows, "settings": load_settings(pdir).model_dump(mode="json"),
        "trackers": trackers, "models": [models.status(k) for k in models.PACKAGES],
        "watching": lab.footage._thread is not None,
    }
