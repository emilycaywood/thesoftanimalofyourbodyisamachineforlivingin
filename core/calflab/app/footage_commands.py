"""Commands of the footage inbox and its review (ADR-076, ADR-077, ADR-078).

None of them edits the document: videos, tracks, candidates and clips live in
the project's footage folder and motion library, as imports did before
(ADR-073). Every UI button calls one of these.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from calflab.plugins import Command, register
from calflab.schema import P


def _err(msg: str) -> Exception:
    from calflab.app.lab import LabError

    return LabError(msg)


def _call(fn: Any, *args: Any, **kw: Any) -> Any:
    from calflab.app.footage import FootageError

    try:
        return fn(*args, **kw)
    except FootageError as exc:
        raise _err(str(exc)) from exc


@register
class ScanFootage(Command):
    key = "scan_footage"
    label = "Scan the video inbox"
    description = ("Look at <project>/footage/videos now (the lab also does every few seconds) and start processing the "
                   "next new or changed video.")
    category = "Behave"

    def run(self, lab: Any, state: Any) -> Any:
        return lab.footage.poll()


@register
class RetryVideo(Command):
    key = "retry_video"
    label = "Process video again"
    description = "Queue a video of the inbox again (after a failure, a cancel, or new settings)."
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name in <project>/footage/videos.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import retry_video

        return _call(retry_video, lab, self.params.file)  # type: ignore[attr-defined]


@register
class CancelVideo(Command):
    key = "cancel_video"
    label = "Cancel video processing"
    description = "Stop tracking a video of the inbox (it can be processed again later)."
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import cancel_video

        return _call(cancel_video, lab, self.params.file)  # type: ignore[attr-defined]


@register
class PreviewCandidate(Command):
    key = "preview_candidate"
    label = "Preview candidate on the body"
    description = "Pose the body with a candidate stretch of a video (no physics) and replay it, with its body report."
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name.")
        candidate: str = P("", desc="Candidate id (c1, c2, ...).")
        start: int = P(-1, ge=-1, desc="First frame (-1 = the candidate's).")
        end: int = P(-1, ge=-1, desc="Frame after the last (-1 = the candidate's).")
        far_side: str = P("", choices=["", "copy", "half_cycle", "hold"], desc="Far legs (empty = suggested).")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import preview_candidate

        p = self.params
        return _call(preview_candidate, lab, p.file, p.candidate, None if p.start < 0 else p.start,  # type: ignore[attr-defined]
                     None if p.end < 0 else p.end, p.far_side)  # type: ignore[attr-defined]


def _words(text: str | list[str]) -> list[str]:
    items = text.split(",") if isinstance(text, str) else text
    return [w.strip() for w in items if w.strip()]


@register
class AcceptCandidate(Command):
    key = "accept_candidate"
    label = "Accept candidate as a clip"
    description = ("Store a candidate stretch of a video as a motion clip, trimmed and named as you choose, with your "
                   "affect tags and its provenance (video hash, frames, tracker, map, cleaning).")
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name.")
        candidate: str = P("", desc="Candidate id.")
        name: str = P("", desc="Clip name (empty = the suggested one).")
        start: int = P(-1, ge=-1, desc="First frame (-1 = the candidate's).")
        end: int = P(-1, ge=-1, desc="Frame after the last (-1 = the candidate's).")
        far_side: str = P("", choices=["", "copy", "half_cycle", "hold"], desc="Far legs (empty = suggested).")
        valence: float | None = P(None, ge=-1.0, le=1.0, step=0.1, desc="Your reading: -1 unpleasant .. +1 pleasant.")
        arousal: float | None = P(None, ge=0.0, le=1.0, step=0.1, desc="Your reading: 0 calm .. 1 agitated.")
        words: str = P("", desc="Free words, separated by commas (wary, curious, ...).")
        note: str = P("", desc="Anything else about this clip.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import accept_candidate

        p = self.params
        affect = {"valence": p.valence, "arousal": p.arousal, "words": _words(p.words), "note": p.note}  # type: ignore[attr-defined]
        return _call(accept_candidate, lab, p.file, p.candidate, p.name,  # type: ignore[attr-defined]
                     None if p.start < 0 else p.start, None if p.end < 0 else p.end, p.far_side, affect)  # type: ignore[attr-defined]


@register
class RejectCandidate(Command):
    key = "reject_candidate"
    label = "Reject candidate"
    description = "Mark a candidate stretch of a video as not wanted."
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name.")
        candidate: str = P("", desc="Candidate id.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import reject_candidate

        return _call(reject_candidate, lab, self.params.file, self.params.candidate)  # type: ignore[attr-defined]


@register
class TagClip(Command):
    key = "tag_clip"
    label = "Rename or tag a clip"
    description = "Change a motion clip's name and your affect tags (valence, arousal, words). The lab never sets these."
    category = "Behave"

    class Params(BaseModel):
        clip: str = P("", desc="Motion-library clip id.")
        name: str = P("", desc="New name (empty = unchanged).")
        valence: float | None = P(None, ge=-1.0, le=1.0, step=0.1, desc="-1 unpleasant .. +1 pleasant (empty = none).")
        arousal: float | None = P(None, ge=0.0, le=1.0, step=0.1, desc="0 calm .. 1 agitated (empty = none).")
        words: str = P("", desc="Free words, separated by commas.")
        note: str = P("", desc="Anything else.")

    def run(self, lab: Any, state: Any) -> Any:
        import time

        from calflab.project.motions import AffectTags

        p = self.params
        try:
            clip = lab.motions.get(p.clip)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise _err(str(exc)) from exc
        if p.name:  # type: ignore[attr-defined]
            clip.name = p.name  # type: ignore[attr-defined]
        vals = {"valence": p.valence, "arousal": p.arousal, "words": _words(p.words),  # type: ignore[attr-defined]
                "note": p.note}  # type: ignore[attr-defined]
        clip.affect = (AffectTags.model_validate({**vals, "tagged": time.strftime("%Y-%m-%dT%H:%M:%S")})
                       if any(v not in (None, "", []) for v in vals.values()) else None)
        lab.motions.save(clip)
        lab.bus.emit("motions.changed", clip=clip.id)
        return {"clip": clip.id, "name": clip.name, "affect": clip.affect.model_dump(mode="json") if clip.affect else None}


@register
class SetFootageSettings(Command):
    key = "set_footage_settings"
    label = "Footage settings"
    description = ("Which pose tracker and retarget map the inbox uses, whether it decides the near side from the "
                   "footage, and the segmentation thresholds. Applies to videos processed from now on (Retry for "
                   "older ones).")
    category = "Behave"

    class Params(BaseModel):
        tracker: str = P("rtmpose_ap10k", desc="Pose tracker plugin key.")
        tracker_params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Its parameters (partial).")
        map: str = P("ap10k_side", desc="Retarget map name.")
        auto_side: bool = P(True, desc="Decide the near side from which way the animal faces.")
        segmentation: dict[str, Any] = P(default_factory=dict, ui="json",
                                         desc="Segmentation thresholds (partial; see the user guide).")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import FootageSettings, load_settings, save_settings
        from calflab.plugins import registry

        p = self.params
        if not registry.has("pose_tracker", p.tracker):  # type: ignore[attr-defined]
            raise _err(f"No pose tracker {p.tracker!r}; known: {', '.join(sorted(registry.all('pose_tracker')))}")  # type: ignore[attr-defined]
        cur = load_settings(lab.project.path)
        new = FootageSettings.model_validate({
            **cur.model_dump(), "tracker": p.tracker, "tracker_params": p.tracker_params, "map": p.map,  # type: ignore[attr-defined]
            "auto_side": p.auto_side,  # type: ignore[attr-defined]
            "segmentation": {**cur.segmentation.model_dump(), **p.segmentation},  # type: ignore[attr-defined]
        })
        save_settings(lab.project.path, new)
        lab.bus.emit("footage.changed")
        return new.model_dump(mode="json")


@register
class DownloadTrackerModel(Command):
    key = "download_tracker_model"
    label = "Download tracker model"
    description = ("Download a pose tracker's model weights (listed with source, size and licence in the Behave panel) "
                   "into <repo>/models, checking each file's SHA-256. A job.")
    category = "Behave"

    class Params(BaseModel):
        package: str = P("rtmpose_ap10k", desc="Model package key.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.behave import models

        key = self.params.package  # type: ignore[attr-defined]
        if key not in models.PACKAGES:
            raise _err(f"No model package {key!r}; known: {', '.join(models.PACKAGES)}")

        def work(job: Any) -> dict[str, Any]:
            man = models.download(key, job.report, job.cancelled)
            lab.bus.emit("footage.changed")
            return {"package": key, "files": [f["name"] for f in man["files"]]}

        return {"job": lab.jobs.submit("download", f"Download {key}", work).id}
