"""Fitness presets: named, versioned, explicit weighted sums of fitness terms.

A preset is stored in full (terms, weights, params) with every run, so results
stay interpretable after the preset file changes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from calflab.config import fitness_preset_files
from calflab.plugins import load_plugins, registry


class TermRef(BaseModel):
    term: str
    weight: float = 1.0
    params: dict[str, Any] = Field(default_factory=dict)


class EvaluationSettings(BaseModel):
    """How a candidate is evaluated under this preset (ADR-079): over several seeds with mild domain randomisation,
    a pessimistic aggregate, and safety constraints. A preset without it evaluates once, as before."""

    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])
    randomize: bool = True
    friction: tuple[float, float] = (0.7, 1.1)
    mass_scale: tuple[float, float] = (0.95, 1.05)
    aggregate: Literal["mean_minus_sd", "worst"] = "mean_minus_sd"
    spread_k: float = 1.0
    #: safety constraints (calflab.evolve.safety.SafetyPolicy); None = not applied
    safety: dict[str, Any] | None = Field(default_factory=dict)
    #: compile with this torque derating (1.0 = a servo can reach stall, as the load analysis); None = the document's
    torque_derating: float | None = 1.0
    #: compile with this servo model; torque_speed = torque falling to zero at no-load speed, as the physics review
    #: of clips (ADR-084); None = the document's
    servo_model: Literal["torque", "torque_speed"] | None = "torque_speed"
    #: the behaviors controller plays every required clip once before choosing freely
    play_required_first: bool = True
    #: score a body on a suite of motions, each tuned for it, instead of one controller
    #: (calflab.evolve.vigour.SuiteSettings; ADR-090); None = not used
    suite: dict[str, Any] | None = None
    #: judge a body and its hardware (servo per pair, belt drives) by the loads of a behaviour suite
    #: (calflab.evolve.hardware.HardwareSettings; ADR-102); None = not used
    hardware: dict[str, Any] | None = None


class FitnessPreset(BaseModel):
    name: str
    version: int = 1
    description: str = ""
    terms: list[TermRef]
    evaluation: EvaluationSettings | None = None

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return ``{"total": float, "preset": ref, "terms": {key: {value, weight, weighted}}}``."""
        load_plugins()
        total = 0.0
        terms: dict[str, Any] = {}
        for ref in self.terms:
            cls = registry.get("fitness_term", ref.term)
            value = float(cls(ref.params).evaluate(metrics, context or {}))  # type: ignore[attr-defined]
            weighted = value * ref.weight
            total += weighted
            terms[ref.term] = {"value": value, "weight": ref.weight, "weighted": weighted}
        return {"total": total, "preset": self.ref, "terms": terms}


def presets() -> dict[str, FitnessPreset]:
    """All presets from ``config/fitness/*.yaml`` keyed by name."""
    return {name: FitnessPreset.model_validate(data) for name, data in fitness_preset_files().items()}


def preset(name: str) -> FitnessPreset:
    table = presets()
    if name not in table:
        raise KeyError(f"No fitness preset {name!r}. Known: {', '.join(sorted(table)) or 'none'}")
    return table[name]
