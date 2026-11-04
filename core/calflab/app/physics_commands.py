"""Commands for judging clips in physics (ADR-084). None edits the document: runs and motion-library clips are
files beside it, as with the footage inbox (ADR-076)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from calflab.plugins import Command, register
from calflab.schema import P


def _err(msg: str) -> Exception:
    from calflab.app.lab import LabError

    return LabError(msg)


def _call(fn: Any, *args: Any, **kw: Any) -> Any:
    from calflab.app.physics_jobs import PhysicsError

    try:
        return fn(*args, **kw)
    except PhysicsError as exc:
        raise _err(str(exc)) from exc


class _Source(BaseModel):
    clip: str = P("", desc="Motion-library clip id (or leave empty and give a video and candidate).")
    file: str = P("", desc="Video file name in the inbox (for a candidate).")
    candidate: str = P("", desc="Candidate id (c1, c2, ...).")
    start: int = P(-1, ge=-1, desc="First frame (-1 = the candidate's).")
    end: int = P(-1, ge=-1, desc="Frame after the last (-1 = the candidate's).")
    far_side: str = P("", choices=["", "tracked", "copy", "half_cycle", "hold"], desc="Far legs (empty = suggested).")


def _source(p: Any) -> dict[str, Any]:
    return {"clip": p.clip, "file": p.file, "candidate": p.candidate, "start": None if p.start < 0 else p.start,
            "end": None if p.end < 0 else p.end, "far_side": p.far_side}


@register
class PlayInPhysics(Command):
    key = "play_in_physics"
    label = "Play in physics"
    description = ("Play a clip or a candidate once on the body in MuJoCo, with servos limited in torque and speed "
                   "(their torque-speed envelope), belts and springs; report tracking, torque against rated and stall, "
                   "speed, envelope, belt tension, hooves, battery current and falls, every limit with your margin. "
                   "A job; a run of kind physics that replays.")
    category = "Behave"

    class Params(_Source):
        margin: float = P(0.2, ge=0.0, le=0.9, step=0.05, desc="Safety margin on every limit (0.2 = keep 20 % in hand).")
        settings: dict[str, Any] = P(default_factory=dict, ui="json",
                                     desc="Physics settings (partial): lead_in_s, return_s, hold_s, command_speed_fraction, seed.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.physics_jobs import play_in_physics

        p = self.params
        job = _call(play_in_physics, lab, _source(p), {**p.settings, "margin": p.margin})  # type: ignore[attr-defined]
        return {"job": job.id}


@register
class AdaptClip(Command):
    key = "adapt_clip"
    label = "Make feasible"
    description = ("Search for a version of a clip or candidate that stays within every limit with your margin: "
                   "hooves planted, slower, smaller, smoother, inside the ranges, then as much given back as holds. "
                   "A job (a few minutes); a run of kind adapt with both versions. A library clip's version is saved "
                   "as a new clip <id>-feasible; a candidate's stays in the run (Keep adapted clip).")
    category = "Behave"

    class Params(_Source):
        margin: float = P(0.2, ge=0.0, le=0.9, step=0.05, desc="Safety margin on every limit.")
        settings: dict[str, Any] = P(default_factory=dict, ui="json",
                                     desc="Search settings (partial): max_rounds, max_slowdown, min_amplitude, plant, "
                                          "min_support, stability_margin_mm, range_margin_deg...")
        physics: dict[str, Any] = P(default_factory=dict, ui="json", desc="Physics settings (partial).")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.physics_jobs import adapt_clip

        p = self.params
        job = _call(adapt_clip, lab, _source(p), {**p.settings, "margin": p.margin}, dict(p.physics))  # type: ignore[attr-defined]
        return {"job": job.id, "run_id": job.result["run_id"]}


@register
class KeepAdaptedClip(Command):
    key = "keep_adapted_clip"
    label = "Keep adapted clip"
    description = "Save the feasible version found by a Make feasible run into the motion library as a new clip."
    category = "Behave"

    class Params(BaseModel):
        run: str = P("", desc="The adapt run id.")
        name: str = P("", desc="Clip name (empty = the suggested one).")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.physics_jobs import keep_adapted_clip

        return _call(keep_adapted_clip, lab, self.params.run, self.params.name)  # type: ignore[attr-defined]


@register
class PhysicsReport(Command):
    key = "physics_report"
    label = "Physics report"
    description = "The stored report of a physics or Make feasible run (what the Behave panel shows)."
    category = "Behave"

    class Params(BaseModel):
        run: str = P("", desc="Run id; empty = list the latest physics and adapt runs.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.physics_jobs import physics_run_view, physics_runs

        if not self.params.run:  # type: ignore[attr-defined]
            return {"runs": physics_runs(lab)}
        return _call(physics_run_view, lab, self.params.run)  # type: ignore[attr-defined]
