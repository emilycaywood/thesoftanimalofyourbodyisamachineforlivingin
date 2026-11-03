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

Settings (tracker, map, segmentation, 2D or 3D mode) are the project's, in
``<project>/footage/settings.json``, not the undoable document, like the
motion library itself.

**3D mode** (ADR-080): instead of measuring angles in the image (a side view,
ADR-073), the robot's own skeleton and a camera are fitted to every frame
(:mod:`calflab.behave.lift`); segmentation runs on those angles, with
unreliable frames as gaps, and clips carry the animal's turning. New projects
start in 3D; a project that processed videos before keeps 2D until switched.

**Frames for the review** come from :class:`FrameCache`: one open reader per
video and recently decoded frames, read ahead, so Play does not reopen and
seek the file for every frame (ADR-081).
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from calflab import units as u
from calflab.behave import inbox
from calflab.behave.clips import cut, near_angles, settle_side, standing_frame
from calflab.behave.keypoints import clean
from calflab.behave.lift import LiftMap, LiftSettings, cut_lift, lift, lift_clip, load_lift_map
from calflab.behave.retarget import RetargetMap, load_map
from calflab.behave.segment import SegmentSettings, segment
from calflab.behave.smoothing import ClipSmoothing, provenance, smooth_clip
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
    #: "2d": angles measured in the image (a side view, ADR-076); "3d": the body's skeleton lifted (ADR-080)
    mode: Literal["2d", "3d"] = "3d"
    map: str = "ap10k_side"  # the 2D map
    map_3d: str = "ap10k_3d"  # the 3D lift map
    #: decide the near side from the footage (overrides the map's near_side; 2D)
    auto_side: bool = True
    segmentation: SegmentSettings = Field(default_factory=SegmentSettings)
    lift: LiftSettings = Field(default_factory=LiftSettings)
    #: how clips cut from a video are smoothed (ADR-082); settings saved before it existed load as "none"
    smoothing: ClipSmoothing = Field(default_factory=ClipSmoothing)
    poll_s: float = 2.0


def settings_path(project_dir: Path) -> Path:
    return Path(project_dir) / "footage" / "settings.json"


def load_settings(project_dir: Path) -> FootageSettings:
    """The project's settings. 3D is the default only for a new project: settings saved before the mode existed,
    or a project that processed videos without saving settings, stay 2D (ADR-080). Clip smoothing likewise
    (ADR-082): on for a new project, off for settings saved before it existed."""
    p = settings_path(project_dir)
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("mode", "2d")
        data.setdefault("smoothing", {"method": "none"})  # clips of an older project are cut as they were
        return FootageSettings.model_validate(data)
    used = (Path(project_dir) / "footage" / "inbox.json").is_file()
    return FootageSettings(mode="2d" if used else "3d", smoothing=ClipSmoothing(method="none") if used else ClipSmoothing())


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
        self.frames = FrameCache()  # decoded frames for the review (ADR-081)
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
        self.frames.close()

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
        return _analyse_and_store(lab, file, sha, tracks, s, path.stem, job, 0.85)
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


def _analyse_and_store(lab: Any, file: str, sha: str, tracks: Any, s: FootageSettings, stem: str, job: Any,
                       p0: float) -> dict[str, Any]:
    """Analyse tracked footage in the project's mode and store the result in the record."""
    pdir = Path(lab.project.path)
    if s.mode == "3d":
        def report(frac: float, msg: str) -> None:
            job.report(p0 + (0.99 - p0) * frac, msg)

        out = analyse_3d(lab, tracks, s, stem, sha, report, job.cancelled)
    else:
        out = analyse(lab, tracks, _map_for(lab, s), s.segmentation, stem)
        inbox.lift_path(pdir, sha).unlink(missing_ok=True)
    _set(lab, file, sha, status="needs_review", progress=1.0, map=out["map"], near_side=out["near_side"],
         view=out["view"], standing_frame=out["standing_frame"], segmentation=out["segmentation"],
         candidates=out["candidates"], mode=s.mode, lift=out.get("lift", {}), reference=out.get("reference", ""),
         reason="" if out["candidates"] else "No stretch long enough was found (see the segmentation settings)")
    return {"file": file, "mode": s.mode, "candidates": len(out["candidates"]), "view": out["view"].get("verdict")}


def reanalyse_video(lab: Any, file: str) -> dict[str, Any]:
    """Analyse a tracked video again with the current settings (mode, map, segmentation), keeping its tracks.
    A job; tracking is not repeated."""
    rec = _record(lab, file)
    if rec.status in ("tracking", "retargeting", "queued", "waiting"):
        raise FootageError(f"{file} is being processed; wait for it or cancel it first")
    pdir = Path(lab.project.path)
    try:
        tracks = inbox.load_tracks(pdir, rec.sha256)
    except FileNotFoundError as exc:
        raise FootageError(f"{file} has no stored tracks; use Retry to track it") from exc
    sha = rec.sha256
    s = load_settings(pdir)

    def work(job: Any) -> dict[str, Any]:
        _set(lab, file, sha, status="retargeting", reason="", progress=0.0, job=job.job.id, candidates=[])
        try:
            return _analyse_and_store(lab, file, sha, tracks, s, Path(file).stem, job, 0.0)
        except Exception as exc:
            if job.cancelled():
                _set(lab, file, sha, status="cancelled", reason="cancelled")
                raise
            _set(lab, file, sha, status="failed", reason=str(exc) if isinstance(exc, FootageError | ValueError)
                 else f"{type(exc).__name__}: {exc}")
            raise

    return {"job": lab.jobs.submit("footage", f"Analyse video {file} ({s.mode.upper()})", work).id}


def _lift_map_for(lab: Any, s: FootageSettings) -> LiftMap:
    try:
        return load_lift_map(s.map_3d, lab.project.path)
    except KeyError as exc:
        raise FootageError(str(exc)) from exc


def analyse_3d(lab: Any, tracks: Any, s: FootageSettings, stem: str, sha: str, report: Any = None,
               cancelled: Any = None) -> dict[str, Any]:
    """3D lift, segmentation on its angles (unreliable stretches are gaps), standing reference, candidates."""
    import numpy as np

    from calflab.behave.keypoints import KeypointTracks

    m = _lift_map_for(lab, s)
    spec = lab.design().spec
    try:
        res = lift(tracks, m, spec, s.lift, report, cancelled)
    except ValueError as exc:
        raise FootageError(f"3D lift with map {m.name}: {exc}; the tracker's names: {', '.join(tracks.names)}") from exc
    inbox.save_lift(lab.project.path, sha, res)
    full = lift_clip(res, spec, None, stem)
    joints = {k: np.asarray(v) for k, v in full.joints.items()}
    # trunk motion: travel on the ground and turning, in robot body lengths per second
    sk_len = _robot_length(spec) * float(res.proportions.get("trunk_length", 1.0))
    xy = np.array([p[:2] for p in full.root_pos])
    fps = tracks.fps
    speed = np.hypot(*np.gradient(xy, axis=0).T) * fps / max(sk_len, 1e-9) if len(xy) > 1 else np.zeros(len(xy))
    turn = np.abs(np.gradient(u.deg_to_rad(np.asarray(full.meta["lift"]["heading_deg"])))) * fps / 2.0 if len(xy) > 1 else 0.0
    trunk = np.hypot(speed, turn)
    bad = ~res.reliable()
    gaps = np.zeros(len(bad), dtype=bool)
    run = 0
    for i in range(len(bad) + 1):  # unreliable stretches longer than a short gap are not candidates
        if i < len(bad) and bad[i]:
            run += 1
            continue
        if run > s.lift.max_gap_frames:
            gaps[i - run:i] = True
        run = 0
    stub = KeypointTracks(fps=fps, names=[], xy=np.zeros((tracks.frames, 0, 2)), likelihood=np.zeros((tracks.frames, 0)))
    segs = segment(stub, None, None, joints, s.segmentation, None, trunk_bl_s=trunk, gaps=gaps)
    stand = standing_frame(segs["candidates"])
    ref_clip = lift_clip(res, spec, stand, stem) if stand is not None else full
    reference = ref_clip.meta["reference"]
    counts: dict[str, int] = {}
    cands: list[inbox.Candidate] = []
    rel = res.reliable()
    vy = np.asarray(res.view_yaw_deg)
    hd = np.asarray(ref_clip.meta["lift"]["heading_deg"])
    for c in segs["candidates"]:
        a, b = c["start"], c["end"]
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
        frac = float(np.mean(rel[a:b]))
        seen = {leg: round(float(np.mean(v[a:b])), 3) for leg, v in res.legs_seen.items()}
        row = {k: v for k, v in c.items() if k in inbox.Candidate.model_fields}
        row.update(far_side="tracked", reliable_fraction=round(frac, 3),
                   ambiguous_fraction=round(float(np.mean([st == "ambiguous" for st in res.state[a:b]])), 3),
                   view_yaw_range_deg=(round(float(vy[a:b].min()), 1), round(float(vy[a:b].max()), 1)),
                   turn_deg=round(float(hd[b - 1] - hd[a]), 1), reference=reference, legs_seen=seen,
                   view_ok=frac >= 0.8)
        cands.append(inbox.Candidate(id=f"c{len(cands) + 1}", name=f"{stem} {c['kind']} {counts[c['kind']]}", **row))
    summary = res.summary
    verdict = (f"3D lift: {summary['reliable_fraction']:.0%} of frames reliable, median yaw "
               f"{summary['median_view_yaw_deg']} deg" if summary.get("median_view_yaw_deg") is not None else
               "3D lift: no reliable frame")
    return {
        "map": m.model_dump(mode="json"),
        "near_side": {"near_side": summary.get("near_side"), "method": "3d lift"},
        "view": {"verdict": verdict, "note": res.camera["note"], "median_yaw_deg": summary.get("median_view_yaw_deg")},
        "standing_frame": stand,
        "reference": reference,
        "segmentation": {"settings": segs["settings"], "standing_frame": stand, "signals": segs["signals"],
                         "gaps": int(gaps.sum())},
        "candidates": cands,
        "lift": {"map": m.name, "summary": summary, "camera": res.camera, "proportions": res.proportions,
                 "settings": res.settings},
    }


def _robot_length(spec: Any) -> float:
    """Hip-to-shoulder distance of the robot (mm), the body length of the 3D signals."""
    root = spec.root.id
    hind = [b.pos[0] for b in spec.bodies if b.parent == root and b.id.startswith("leg.h")]
    front = [b.pos[0] for b in spec.bodies if b.parent == root and b.id.startswith("leg.f")]
    return abs(sum(front) / len(front) - sum(hind) / len(hind)) if hind and front else 500.0


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
    if rec.mode == "3d":
        return _candidate_clip_3d(lab, rec, c, start, end, name, far_side)
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
    sm = load_settings(lab.project.path).smoothing
    try:
        raw = cut(full, a, b, name or c.name, fs, period, m.near_side)
        smoothed, how = smooth_clip(full, sm)
        clip = cut(smoothed, a, b, name or c.name, fs, period, m.near_side)
    except ValueError as exc:
        raise FootageError(str(exc)) from exc
    clip.meta.update({
        "footage": file, "video_sha256": rec.sha256, "video": rec.info, "candidate": cid, "kind": c.kind,
        "tracker": rec.tracker, "map": rec.map, "near_side_detected": rec.near_side, "view": rec.view,
        "standing_frame": rec.standing_frame, "cleaning": {"min_likelihood": m.min_likelihood,
                                                          "max_gap_frames": m.max_gap_frames,
                                                          "smooth_frames": m.smooth_frames},
        "segmentation": rec.segmentation.get("settings"), "retarget": full.meta.get("retarget"),
        "smoothing": provenance(sm, full.fps, how, raw, clip),
    })
    return clip


def _candidate_clip_3d(lab: Any, rec: inbox.VideoRecord, c: inbox.Candidate, start: int | None, end: int | None,
                       name: str, far_side: str) -> MotionClip:
    try:
        res = inbox.load_lift(lab.project.path, rec.sha256)
    except FileNotFoundError as exc:
        raise FootageError(str(exc)) from exc
    full = lift_clip(res, lab.design().spec, rec.standing_frame, Path(rec.file).stem)
    a = c.start if start is None else int(start)
    b = c.end if end is None else int(end)
    fs = far_side or c.far_side or "tracked"
    period = c.period_s
    if fs == "half_cycle" and (a, b) != (c.start, c.end) and period:
        cycles = max(1, int((b - a) / (period * res.fps)))
        b = a + int(round(cycles * period * res.fps))
    sm = load_settings(lab.project.path).smoothing
    try:
        raw = cut_lift(full, a, b, name or c.name, fs, period)
        smoothed, how = smooth_clip(full, sm)
        clip = cut_lift(smoothed, a, b, name or c.name, fs, period)
    except ValueError as exc:
        raise FootageError(str(exc)) from exc
    clip.meta.update({
        "footage": rec.file, "video_sha256": rec.sha256, "video": rec.info, "candidate": c.id, "kind": c.kind,
        "tracker": rec.tracker, "map": rec.map, "near_side_detected": rec.near_side, "view": rec.view,
        "lift": rec.lift, "standing_frame": rec.standing_frame,
        "segmentation": rec.segmentation.get("settings"), "smoothing": provenance(sm, full.fps, how, raw, clip),
    })
    return clip


def preview_candidate(lab: Any, file: str, cid: str, start: int | None = None, end: int | None = None,
                      far_side: str = "") -> dict[str, Any]:
    from calflab.app.behave_jobs import preview_run

    clip = candidate_clip(lab, file, cid, start, end, far_side=far_side)
    clip.id = f"{Path(file).stem}-{cid}"
    out = preview_run(lab, clip, 1.0, f"Candidate preview: {file} {cid}",
                      {"footage": file, "candidate": cid, "frame_range": clip.meta["frame_range"]})
    if clip.meta.get("mode") == "3d":
        out["motion"] = {k: clip.meta.get(k) for k in ("turn_deg", "heading_range_deg", "travel_mm", "legs",
                                                         "reference", "unreliable_frames")}
    out["smoothing"] = clip.meta.get("smoothing")
    return out


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
class FrameCache:
    """Frames for the review (ADR-081). Keeps readers open per video (one for requests, one for reading ahead; at
    most ``readers`` in all), the most recent encoded frames (at most ``frames``), and reads ahead from a
    requested frame on a thread, sequentially, which is fast; reopening and seeking an H.264 file for every frame
    took 300-500 ms. A request for a frame the read-ahead is about to reach waits for it instead of seeking."""

    def __init__(self, frames: int = 600, readers: int = 4, ahead: int = 45):
        self._readers: OrderedDict[tuple[str, int, int, str], tuple[Any, threading.Lock]] = OrderedDict()
        self._frames: OrderedDict[tuple[str, int, int, int, int], tuple[bytes, str]] = OrderedDict()
        self._lock = threading.Lock()
        self._added = threading.Condition(self._lock)
        self._ahead: dict[tuple[str, int, int], tuple[int, int]] = {}  # video -> (next frame, end) being read
        self._jump: dict[tuple[str, int, int], int] = {}  # video -> where the read-ahead should go on from
        self.max_frames, self.max_readers, self.ahead = frames, readers, ahead

    @staticmethod
    def _key(path: Path) -> tuple[str, int, int]:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size)

    def _reader(self, key: tuple[str, int, int], role: str = "serve") -> tuple[Any, threading.Lock]:
        rk = (*key, role)
        with self._lock:
            if rk in self._readers:
                self._readers.move_to_end(rk)
                return self._readers[rk]
        r = open_video(Path(key[0]))
        with self._lock:
            if rk in self._readers:  # opened by another thread meanwhile
                r.close()
                return self._readers[rk]
            self._readers[rk] = (r, threading.Lock())
            while len(self._readers) > self.max_readers:
                _, (old, olock) = self._readers.popitem(last=False)
                with olock:
                    old.close()
            return self._readers[rk]

    def _decode(self, key: tuple[str, int, int], index: int, width: int, role: str = "serve") -> tuple[bytes, str]:
        fk = (*key, index, width)
        with self._lock:
            hit = self._frames.get(fk)
            if hit is not None:
                self._frames.move_to_end(fk)
                return hit
            if role == "serve" and key in self._ahead:
                nxt, end = self._ahead[key]
                if nxt <= index < min(end, nxt + 60):  # the read-ahead gets there sooner than a seek would
                    self._added.wait_for(lambda: fk in self._frames or key not in self._ahead, timeout=2.0)
                    hit = self._frames.get(fk)
                    if hit is not None:
                        return hit
        r, rlock = self._reader(key, role)
        with rlock:
            with self._lock:
                hit = self._frames.get(fk)
            if hit is not None:
                return hit
            out = encode_image(r.frame(int(index)), width)
        with self._lock:
            self._frames[fk] = out
            while len(self._frames) > self.max_frames:
                self._frames.popitem(last=False)
            self._added.notify_all()
        return out

    def get(self, path: Path, index: int, width: int = 640) -> tuple[bytes, str]:
        key = self._key(path)
        out = self._decode(key, index, width)
        self.read_ahead(path, index + 1, index + 1 + self.ahead, width)
        return out

    def cached(self, path: Path, index: int, width: int = 640) -> bool:
        with self._lock:
            return (*self._key(path), index, width) in self._frames

    def read_ahead(self, path: Path, start: int, end: int, width: int = 640) -> None:
        """Decode [start, end) in order on a thread (one per video at a time), skipping frames already cached."""
        key = self._key(path)
        with self._lock:
            if key in self._ahead:
                nxt, cur_end = self._ahead[key]
                if nxt <= start <= cur_end + 30:  # already reading there: just read further
                    self._ahead[key] = (nxt, max(cur_end, end))
                else:  # elsewhere (a scrub): the running thread jumps there
                    self._jump[key] = max(0, start)
                    self._ahead[key] = (nxt, end)
                return
            self._ahead[key] = (max(0, start), end)

        def run() -> None:
            try:
                r, _ = self._reader(key, "ahead")
                i = max(0, start)
                while True:
                    with self._lock:
                        if key in self._jump:
                            i = self._jump.pop(key)
                        stop = self._ahead[key][1]
                        if r.info.frames:
                            stop = min(stop, r.info.frames)
                        if i >= stop:
                            break
                        self._ahead[key] = (i, self._ahead[key][1])
                        have = (*key, i, width) in self._frames
                    if not have:
                        self._decode(key, i, width, "ahead")
                    i += 1
            except Exception:  # the end of a file whose frame count was approximate, or a closed reader
                log.debug("read-ahead stopped", exc_info=True)
            finally:
                with self._lock:
                    self._ahead.pop(key, None)
                    self._jump.pop(key, None)
                    self._added.notify_all()

        threading.Thread(target=run, name="calflab-frames", daemon=True).start()

    def close(self) -> None:
        with self._lock:
            for r, rlock in self._readers.values():
                with rlock:
                    r.close()
            self._readers.clear()
            self._frames.clear()


def frame_image(lab: Any, file: str, index: int, max_width: int = 640) -> tuple[bytes, str]:
    path = inbox.videos_dir(lab.project.path) / Path(file).name
    if not path.is_file():
        raise FootageError(f"No video {file!r} in the videos folder")
    try:
        return lab.footage.frames.get(path, int(index), max_width)
    except VideoError as exc:
        raise FootageError(str(exc)) from exc


def prefetch_frames(lab: Any, file: str, start: int, end: int, max_width: int = 640) -> dict[str, Any]:
    """Start decoding [start, end) into the frame cache (a candidate's range, when the review opens it)."""
    path = inbox.videos_dir(lab.project.path) / Path(file).name
    if not path.is_file():
        raise FootageError(f"No video {file!r} in the videos folder")
    lab.footage.frames.read_ahead(path, int(start), int(end), max_width)
    return {"file": file, "start": start, "end": end}


def footage_lift(lab: Any, file: str) -> dict[str, Any]:
    """Per-frame reliability of a 3D lift for the review's strip: state, estimated yaw and heading, residual."""
    rec = _record(lab, file)
    if rec.mode != "3d":
        return {"mode": rec.mode, "frames": 0}
    try:
        res = inbox.load_lift(lab.project.path, rec.sha256)
    except FileNotFoundError as exc:
        raise FootageError(str(exc)) from exc
    return {
        "mode": "3d", "frames": res.frames, "fps": res.fps, "state": res.state,
        "view_yaw_deg": res.view_yaw_deg, "heading_deg": [round(v - res.heading_deg[0], 1) for v in res.heading_deg],
        "residual_px": res.residual_px, "residual_bl": res.residual_bl, "reasons": res.reasons,
        "ambiguous": res.ambiguous, "unobservable": res.unobservable, "near_side": res.near_side,
        "summary": res.summary, "camera": res.camera, "proportions": res.proportions,
        "maps": inbox.lift_maps(lab.project.path, rec.sha256),
    }


def compare_lift_maps(lab: Any, file: str, maps: list[str] | None = None) -> dict[str, Any]:
    """The video's last lift with each map, side by side (:func:`calflab.behave.lift.compare_lifts`)."""
    from calflab.behave.lift import compare_lifts

    rec = _record(lab, file)
    have = inbox.lift_maps(lab.project.path, rec.sha256)
    names = maps or have
    missing = [m for m in names if m not in have]
    if missing:
        raise FootageError(f"{file} has no lift with {', '.join(missing)}; lifted with: {', '.join(have) or 'none'}. "
                           "Choose the map in Settings and Analyse again.")
    if len(names) < 2:
        raise FootageError(f"{file} was lifted with {', '.join(names) or 'no map'} only: analyse it again with another "
                           "map to compare")
    out = compare_lifts({m: inbox.load_lift(lab.project.path, rec.sha256, m) for m in names})
    return {"file": file, **out}


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
    if rec.map and rec.mode == "3d":
        used.update(LiftMap.model_validate(rec.map).expanded()[0])
    elif rec.map:
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
    thr = float(rec.map.get("min_likelihood", 0.5)) if rec.map else 0.5
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
        if r.lift:
            d["lift"] = {k: r.lift.get(k) for k in ("map", "camera", "proportions")} | {
                "summary": {k: v for k, v in r.lift.get("summary", {}).items()
                            if k not in ("unobservable_fraction", "landmark_residual_px")},
                "landmark_residual_px": r.lift.get("summary", {}).get("landmark_residual_px"),
                "unobservable_fraction": r.lift.get("summary", {}).get("unobservable_fraction")}
        rows.append(d)
    trackers = [{"key": k, "label": c.label, **c.extra()} for k, c in sorted(registry.all("pose_tracker").items())]
    s = load_settings(pdir)
    return {
        "dir": str(inbox.videos_dir(pdir)), "videos": rows,
        # the smoothing also as the settings command's flat fields, so its form shows the current values
        "settings": s.model_dump(mode="json") | {"clip_smoothing": s.smoothing.method,
                                                 "clip_smoothing_hz": s.smoothing.cutoff_hz},
        "trackers": trackers, "models": [models.status(k) for k in models.PACKAGES],
        "watching": lab.footage._thread is not None,
    }
