"""Fitness presets: named, versioned, explicit weighted sums of fitness terms.

A preset is stored in full (terms, weights, params) with every run, so results
stay interpretable after the preset file changes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from calflab.config import fitness_preset_files
from calflab.plugins import load_plugins, registry


class TermRef(BaseModel):
    term: str
    weight: float = 1.0
    params: dict[str, Any] = Field(default_factory=dict)


class FitnessPreset(BaseModel):
    name: str
    version: int = 1
    description: str = ""
    terms: list[TermRef]

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
