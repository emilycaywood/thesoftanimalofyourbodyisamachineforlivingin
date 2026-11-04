"""Commands for reading footage and interpreting it as the robot's own movement (ADR-085). None edits the
document: readings are files in ``footage/readings``, interpretations runs of kind ``interpret``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from calflab.plugins import Command, register
from calflab.schema import P


def _err(msg: str) -> Exception:
    from calflab.app.lab import LabError

    return LabError(msg)


@register
class ReadFootage(Command):
    key = "read_footage"
    label = "Read footage"
    description = ("Read every lifted video of the inbox into behaviours (stand, weight shift, step, walk, turn, "
                   "other), their character and a semi-Markov model, with the evidence for each stretch; videos that "
                   "cannot be read are listed with the reason. A job; stored in footage/readings.")
    category = "Behave"

    class Params(BaseModel):
        settings: dict[str, Any] = P(default_factory=dict, ui="json",
                                     desc="Reading thresholds (partial): swing_bl_s, still_qom_deg_s, join_s, "
                                          "turn_min_deg, fast_two_up, min_reliable, min_body_px...")
        exclude: dict[str, str] = P(default_factory=dict, ui="json",
                                    desc="Videos to leave out: file name -> your reason.")
        synthetic: list[tuple[str, float]] = P(default_factory=list, ui="json", advanced=True,
                                               desc="Instead of the footage: a known sequence [[behaviour, seconds], "
                                                    "...] posed on the robot's skeleton (for trying it out).")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.reading_jobs import ReadingError, read_footage, read_synthetic

        p = self.params
        if p.synthetic:  # type: ignore[attr-defined]
            try:
                r = read_synthetic(lab, list(p.synthetic), dict(p.settings))  # type: ignore[attr-defined]
            except ReadingError as exc:
                raise _err(str(exc)) from exc
            return {"reading": r.id, "stretches": len(r.stretches)}

        def work(job: Any) -> dict[str, Any]:
            r = read_footage(lab, dict(p.settings), dict(p.exclude), report=lambda f, m: job.report(f, m))  # type: ignore[attr-defined]
            job.log(" ".join(r.support["lines"][:2]))
            return {"reading": r.id}

        try:
            job = lab.jobs.submit("reading", "Read footage", work)
        except ReadingError as exc:
            raise _err(str(exc)) from exc
        return {"job": job.id}


@register
class ReadingReport(Command):
    key = "reading_report"
    label = "Reading"
    description = "A stored reading (the latest when no id is given), or the list of readings."
    category = "Behave"

    class Params(BaseModel):
        reading: str = P("", desc="Reading id; empty = the latest.")
        list_all: bool = P(False, desc="List the readings instead.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.reading_jobs import ReadingError, list_readings, load_reading

        p = self.params
        if p.list_all:  # type: ignore[attr-defined]
            return {"readings": list_readings(lab)}
        try:
            return load_reading(lab, p.reading).model_dump(mode="json")  # type: ignore[attr-defined]
        except ReadingError as exc:
            raise _err(str(exc)) from exc


@register
class InterpretFootage(Command):
    key = "interpret_footage"
    label = "Interpret footage"
    description = ("Interpret a reading as the robot's own movements: per behaviour, the motion primitive and "
                   "parameters whose features come closest to the calf's within every limit with your margin (a "
                   "small CMA-ES, cached per body); then a performance drawn from the reading's model, played for a "
                   "minute with three seeds and judged; all compared side by side. A job; a run of kind interpret.")
    category = "Behave"

    class Params(BaseModel):
        reading: str = P("", desc="Reading id; empty = the latest.")
        margin: float = P(0.2, ge=0.0, le=0.9, step=0.05, desc="Safety margin on every limit.")
        seconds: float = P(60.0, unit="s", ge=5.0, le=600.0, desc="Length of each performance.")
        seeds: list[int] = P(default_factory=lambda: [0, 1, 2], ui="json", desc="Seeds of the performances.")
        settings: dict[str, Any] = P(default_factory=dict, ui="json",
                                     desc="Search settings (partial): popsize, generations, sigma, seed, cycles, "
                                          "primitives (behaviour -> keys), behaviours.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.interpret_jobs import InterpretError, interpret_job

        p = self.params
        try:
            job = interpret_job(lab, p.reading, {**p.settings, "margin": p.margin}, p.seconds, list(p.seeds))  # type: ignore[attr-defined]
        except InterpretError as exc:
            raise _err(str(exc)) from exc
        return {"job": job.id}


@register
class InterpretationReport(Command):
    key = "interpretation_report"
    label = "Interpretation"
    description = "The stored interpretation report (the latest when no run is given): what the Behave panel shows."
    category = "Behave"

    class Params(BaseModel):
        run: str = P("", desc="Run id of kind interpret; empty = the latest.")

    def run(self, lab: Any, state: Any) -> Any:
        from calflab.app.interpret_jobs import InterpretError, interpretation_view

        try:
            return interpretation_view(lab, self.params.run)  # type: ignore[attr-defined]
        except InterpretError as exc:
            raise _err(str(exc)) from exc
