"""The footage inbox: videos dropped into ``<project>/footage/videos/`` (ADR-076).

Each video gets a status record, kept in ``<project>/footage/inbox.json``,
keyed by file name:

``waiting`` (the file is still growing) -> ``queued`` -> ``tracking`` ->
``retargeting`` -> ``needs_review`` -> ``ready`` (every candidate accepted or
rejected), or ``failed`` with the reason, or ``cancelled``.

The record holds the file's SHA-256, so a video is processed once; a file
whose content changes gets a new hash and is processed again (its old
candidates are dropped, clips already accepted stay in the motion library
with the old hash). The hash is only recomputed when the size or modification
time changes, so polling a folder of large videos stays cheap. A file is
queued only once its size is the same on two scans (still being copied
otherwise). Tracks are stored per hash in ``footage/tracks/<sha16>.npz``.

Pure file operations; the lab runs the polling and the processing jobs.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab.behave.keypoints import KeypointTracks
from calflab.behave.video import VIDEO_SUFFIXES

Status = Literal["waiting", "queued", "tracking", "retargeting", "needs_review", "ready", "failed", "cancelled",
                 "missing"]
_LOCK = threading.RLock()


class Candidate(BaseModel):
    """A stretch of the video proposed as a clip, and what the researcher decided."""

    id: str
    start: int
    end: int
    kind: str  # idle | gait | other
    name: str = ""
    period_s: float | None = None
    far_side: str = "copy"
    seconds: float = 0.0
    periodicity: float = 0.0
    trunk_bl_s: float = 0.0
    activity_deg_s: float = 0.0
    turned_fraction: float | None = None
    view_ok: bool | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"
    clip: str = ""  # motion-library id once accepted
    #: the cut as the researcher trimmed it (frames), when different from start/end
    trim: tuple[int, int] | None = None
    # 3D lift (ADR-080); None for 2D candidates
    reliable_fraction: float | None = None
    ambiguous_fraction: float | None = None
    view_yaw_range_deg: tuple[float, float] | None = None
    turn_deg: float | None = None  # heading change over the stretch (+ = turning left)
    reference: str = ""  # what the angles are relative to
    legs_seen: dict[str, float] | None = None  # share of the frames where each leg is tracked


class VideoRecord(BaseModel):
    file: str
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    status: Status = "waiting"
    reason: str = ""
    progress: float = 0.0
    job: str = ""
    info: dict[str, Any] = Field(default_factory=dict)  # fps, frames, width, height, codec, reader
    tracker: dict[str, Any] = Field(default_factory=dict)  # provenance of the tracks
    map: dict[str, Any] = Field(default_factory=dict)  # the retarget map used, side settled
    near_side: dict[str, Any] = Field(default_factory=dict)
    view: dict[str, Any] = Field(default_factory=dict)  # verdict, note, median yaw (per-frame arrays not kept here)
    #: "2d" (side view, ADR-076) or "3d" (lift, ADR-080); records written before the lift are 2D
    mode: str = "2d"
    #: the 3D lift's summary, camera and proportions (per-frame arrays are in footage/lift/<sha16>.json)
    lift: dict[str, Any] = Field(default_factory=dict)
    reference: str = ""  # what the angles are relative to
    standing_frame: int | None = None
    segmentation: dict[str, Any] = Field(default_factory=dict)  # settings, body_px
    candidates: list[Candidate] = Field(default_factory=list)
    updated: str = ""

    @property
    def key(self) -> str:
        return self.sha256[:16]


def videos_dir(project_dir: Path) -> Path:
    d = Path(project_dir) / "footage" / "videos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(project_dir: Path) -> Path:
    return Path(project_dir) / "footage" / "inbox.json"


def tracks_path(project_dir: Path, sha: str) -> Path:
    d = Path(project_dir) / "footage" / "tracks"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha[:16]}.npz"


def load(project_dir: Path) -> dict[str, VideoRecord]:
    p = _index_path(project_dir)
    if not p.is_file():
        return {}
    with _LOCK:
        data = json.loads(p.read_text(encoding="utf-8"))
    return {k: VideoRecord.model_validate(v) for k, v in data.items()}


def save(project_dir: Path, records: dict[str, VideoRecord]) -> None:
    p = _index_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({k: v.model_dump(mode="json") for k, v in sorted(records.items())}, indent=1)
    with _LOCK:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(p)


def update(project_dir: Path, file: str, **fields: Any) -> VideoRecord:
    """Change one record (read-modify-write under a lock)."""
    with _LOCK:
        recs = load(project_dir)
        rec = recs[file]
        for k, v in fields.items():
            setattr(rec, k, v)
        rec.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
        save(project_dir, recs)
        return rec


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan(project_dir: Path) -> dict[str, list[str]]:
    """Look at the videos folder once. Returns the files that became ``queued`` (new or changed), and those gone."""
    d = videos_dir(project_dir)
    queued: list[str] = []
    gone: list[str] = []
    with _LOCK:
        recs = load(project_dir)
        present = {p.name: p for p in d.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES}
        for name, path in present.items():
            st = path.stat()
            rec = recs.get(name)
            if rec is None:
                recs[name] = VideoRecord(file=name, size=st.st_size, mtime_ns=st.st_mtime_ns, status="waiting",
                                         updated=time.strftime("%Y-%m-%dT%H:%M:%S"))
                continue
            if rec.status == "waiting":
                if st.st_size == rec.size and st.st_mtime_ns == rec.mtime_ns:  # unchanged since the last scan
                    rec.sha256 = sha256_file(path)
                    rec.status, rec.reason, rec.progress = "queued", "", 0.0
                    queued.append(name)
                else:
                    rec.size, rec.mtime_ns = st.st_size, st.st_mtime_ns
                continue
            if rec.status == "missing" or st.st_size != rec.size or st.st_mtime_ns != rec.mtime_ns:
                digest = sha256_file(path)
                rec.size, rec.mtime_ns = st.st_size, st.st_mtime_ns
                if digest != rec.sha256 or rec.status == "missing":
                    # changed content: start over (accepted clips stay in the library with the old hash)
                    recs[name] = VideoRecord(file=name, size=st.st_size, mtime_ns=st.st_mtime_ns, sha256=digest,
                                             status="queued", updated=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                             reason="the file changed" if rec.sha256 else "")
                    queued.append(name)
        for name, rec in recs.items():
            if name not in present and rec.status != "missing":
                rec.status, rec.reason = "missing", "the file is no longer in the videos folder"
                gone.append(name)
        save(project_dir, recs)
    return {"queued": queued, "gone": gone}


def lift_path(project_dir: Path, sha: str) -> Path:
    d = Path(project_dir) / "footage" / "lift"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha[:16]}.json"


def save_lift(project_dir: Path, sha: str, result: Any) -> Path:
    p = lift_path(project_dir, sha)
    p.write_bytes(result.model_dump_json().encode())
    return p


def load_lift(project_dir: Path, sha: str) -> Any:
    from calflab.behave.lift import LiftResult

    p = lift_path(project_dir, sha)
    if not p.is_file():
        raise FileNotFoundError(f"No 3D lift stored for {sha[:16]}: analyse the video again")
    return LiftResult.model_validate_json(p.read_bytes())


def save_tracks(project_dir: Path, sha: str, tracks: KeypointTracks) -> Path:
    p = tracks_path(project_dir, sha)
    np.savez_compressed(p, xy=tracks.xy, likelihood=tracks.likelihood,
                        meta=np.array(json.dumps({"fps": tracks.fps, "names": tracks.names, "source": tracks.source,
                                                  "model": tracks.model, "image_size": tracks.image_size})))
    return p


def load_tracks(project_dir: Path, sha: str) -> KeypointTracks:
    p = tracks_path(project_dir, sha)
    if not p.is_file():
        raise FileNotFoundError(f"No tracks stored for {sha[:16]}: process the video again")
    with np.load(p) as z:
        meta = json.loads(str(z["meta"]))
        return KeypointTracks(fps=meta["fps"], names=meta["names"], xy=z["xy"], likelihood=z["likelihood"],
                              source=meta["source"], model=meta["model"],
                              image_size=tuple(meta["image_size"]) if meta["image_size"] else None)
