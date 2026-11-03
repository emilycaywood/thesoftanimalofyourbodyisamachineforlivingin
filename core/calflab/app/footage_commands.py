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
class ReanalyseVideo(Command):
    key = "reanalyse_video"
    label = "Analyse video again"
    description = ("Analyse a tracked video again with the current footage settings (2D or 3D, map, segmentation), "
                   "keeping its tracks: nothing is tracked again. A job; the video's candidates are replaced.")
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name in <project>/footage/videos.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import reanalyse_video

        return _call(reanalyse_video, lab, self.params.file)  # type: ignore[attr-defined]


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
        far_side: str = P("", choices=["", "tracked", "copy", "half_cycle", "hold"],
                          desc="Far legs (empty = suggested; tracked = as the 3D lift fitted them).")

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
        far_side: str = P("", choices=["", "tracked", "copy", "half_cycle", "hold"],
                          desc="Far legs (empty = suggested; tracked = as the 3D lift fitted them).")
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
    description = ("Which pose tracker the inbox uses, 2D side view or 3D lift and their maps, whether it decides the "
                   "near side from the footage (2D), the lift's and the segmentation's thresholds (lift.bend_choice: "
                   "window or frame), and how clips cut from a video are smoothed and re-timed. Applies to videos processed from now on (Analyse again for older "
                   "ones); smoothing applies to every candidate previewed or accepted from now on.")
    category = "Behave"

    class Params(BaseModel):
        tracker: str = P("rtmpose_ap10k", desc="Pose tracker plugin key.")
        tracker_params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Its parameters (partial).")
        mode: str = P("", choices=["", "2d", "3d"],
                      desc="2d: angles measured in the image (side views only). 3d: the body's skeleton and a camera "
                           "fitted to every frame (turning, ab/adduction, far legs). Empty = unchanged.")
        map: str = P("ap10k_side", desc="2D retarget map name.")
        map_3d: str = P("", desc="3D lift map name (empty = unchanged).")
        auto_side: bool = P(True, desc="Decide the near side from which way the animal faces.")
        segmentation: dict[str, Any] = P(default_factory=dict, ui="json",
                                         desc="Segmentation thresholds (partial; see the user guide).")
        lift: dict[str, Any] = P(default_factory=dict, ui="json",
                                 desc="3D lift settings (partial: max_view_yaw_deg, max_residual_bl, camera_hfov_deg...).")
        clip_smoothing: str = P("", choices=["", "auto", "lowpass", "none"],
                                desc="Clips cut from a video: a zero-lag low-pass on the joint angles and the trunk's "
                                     "path, so peak speeds are the animal's and not the tracker's jitter. auto = the "
                                     "cutoff found from the video (Winter's residual analysis); lowpass = at the "
                                     "cutoff below; none = as retargeted. Empty = unchanged.")
        clip_smoothing_hz: float = P(0.0, unit="Hz", ge=0.0, le=15.0, step=0.5,
                                     desc="Cutoff for lowpass (6 Hz is the walking-kinematics convention; "
                                          "PROVISIONAL). 0 = unchanged.")
        repeated_frames: str = P("", choices=["", "interpolate", "keep"],
                                 desc="Frames the recording repeated (a screen recording, dropped frames): interpolate "
                                      "= clips re-timed across them, so a step is not played twice as fast; keep = "
                                      "every frame as it is. Found when a video is analysed. Empty = unchanged.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import FootageSettings, load_settings, save_settings
        from calflab.plugins import registry

        p = self.params
        if not registry.has("pose_tracker", p.tracker):  # type: ignore[attr-defined]
            raise _err(f"No pose tracker {p.tracker!r}; known: {', '.join(sorted(registry.all('pose_tracker')))}")  # type: ignore[attr-defined]
        cur = load_settings(lab.project.path)
        new = FootageSettings.model_validate({
            **cur.model_dump(), "tracker": p.tracker, "tracker_params": p.tracker_params, "map": p.map,  # type: ignore[attr-defined]
            "auto_side": p.auto_side, "mode": p.mode or cur.mode,  # type: ignore[attr-defined]
            "map_3d": p.map_3d or cur.map_3d,  # type: ignore[attr-defined]
            "segmentation": {**cur.segmentation.model_dump(), **p.segmentation},  # type: ignore[attr-defined]
            "lift": {**cur.lift.model_dump(), **p.lift},  # type: ignore[attr-defined]
            "smoothing": {**cur.smoothing.model_dump(),
                          **({"method": p.clip_smoothing} if p.clip_smoothing else {}),  # type: ignore[attr-defined]
                          **({"cutoff_hz": p.clip_smoothing_hz} if p.clip_smoothing_hz > 0 else {})},  # type: ignore[attr-defined]
            "repeated": {**cur.repeated.model_dump(),
                         **({"method": p.repeated_frames} if p.repeated_frames else {})},  # type: ignore[attr-defined]
        })
        save_settings(lab.project.path, new)
        lab.bus.emit("footage.changed")
        return new.model_dump(mode="json")


@register
class CompareLiftMaps(Command):
    key = "compare_lift_maps"
    label = "Compare 3D lifts"
    description = ("Side by side for one video, from the last lift with each map and bend choice: reliable and "
                   "ambiguous shares per leg, jumps per frame, the residual per landmark, the hind angles, and the "
                   "playable speed of the candidates raw and smoothed. Analyse the video again with another map or "
                   "bend choice first.")
    category = "Behave"

    class Params(BaseModel):
        file: str = P("", desc="Video file name.")
        maps: list[str] = P(default_factory=list, ui="json",
                            desc="Lifts: a map name (bends chosen frame by frame) or <map>.window (over the window). "
                                 "Empty = every lift kept for the video.")
        ranges: list[list[int]] = P(default_factory=list, ui="json",
                                    desc="Frame ranges [start, end) for the playable speed (empty = the candidates).")
        jump_deg: float = P(12.0, unit="deg", ge=1.0, le=90.0, desc="A jump: a joint moving more than this in one frame.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.footage import compare_lift_maps

        p = self.params
        return _call(compare_lift_maps, lab, p.file, list(p.maps), [list(r) for r in p.ranges] or None,  # type: ignore[attr-defined]
                     p.jump_deg)  # type: ignore[attr-defined]


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


@register
class RunCompositionStudy(Command):
    key = "run_composition_study"
    label = "Composition study"
    description = ("Play the stochastic behaviors on this body in several compositions (tempo, amplitude, stillness, "
                   "smoothness, phrasing, affect curve...), each with several seeds; tabulate movement features, clip "
                   "tracking and safety. A job; the document is not changed.")
    category = "Behave"

    class Params(BaseModel):
        compositions: list[dict[str, Any]] = P(
            default_factory=lambda: [c.model_dump() for c in _default_compositions()], ui="json",
            desc="[{name, params}]: behaviors parameters over the document's, e.g. {\"tempo\": 0.7, \"idle_share\": 0.6}.")
        seeds: list[int] = P(default_factory=lambda: [0, 1, 2], ui="json", desc="Seeds; every composition plays each.")
        duration_s: float = P(20.0, unit="s", ge=2.0, le=300.0, step=1.0, desc="Simulated time per rollout.")
        randomize: bool = P(False, desc="Mildly randomise floor friction (0.7-1.1) and mass (x0.95-1.05) per seed.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.behave_jobs import BehaveError, run_composition_study

        try:
            job = run_composition_study(lab, self.params.model_dump())
        except BehaveError as exc:
            raise _err(str(exc)) from exc
        return {"job": job.id, "run_id": job.result["run_id"]}


def _default_compositions() -> list[Any]:
    from calflab.behave.study import _default_compositions as d

    return d()


@register
class EstimateEvolve(Command):
    key = "estimate_evolve"
    label = "Estimate evolution cost"
    description = ("Time one short rollout and estimate the CPU and wall-clock time of an evolution with these settings "
                   "(and of a small budget to try first) before starting it.")
    category = "Evolve"

    class Params(BaseModel):
        optimizer: str = P("map_elites_cma", desc="Optimizer plugin key.")
        params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Optimizer parameters (partial).")
        sim: dict[str, Any] = P(default_factory=dict, ui="json", desc="Simulation settings (partial).")

    def run(self, lab: Any, state: Any) -> Any:
        p = self.params
        try:
            return lab.estimate_evolve(p.optimizer, dict(p.params), dict(p.sim))  # type: ignore[attr-defined]
        except Exception as exc:
            raise _err(f"estimate_evolve: {exc}") from exc
