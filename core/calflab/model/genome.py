"""Genomes: data-defined, versioned gene definitions and their values.

Gene definitions live in YAML (``config/genes/*.yaml``) or come from
``GeneDefinition`` plugins; they are never hard-coded fields. A stored
:class:`Genome` carries the definition name and version it was written with,
and :func:`calflab.model.migrations.migrate` brings old genomes forward so old
runs always reload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, Field, model_validator

from calflab.schema import dynamic_schema

GeneValue = float | int | bool | str


class GeneDef(BaseModel):
    id: str
    type: Literal["float", "int", "bool", "enum"] = "float"
    default: GeneValue
    #: What a stored genome that does not mention this gene had (None = ``default``).
    #: Set it when a gene is added, or its default changed, after genomes were
    #: already saved, so that old documents, runs, candidates and designs keep
    #: the body they were made with while new projects get the new default.
    absent: GeneValue | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    group: str = "General"
    label: str | None = None
    description: str = ""
    choices: list[str] | None = None
    #: component kind whose library keys are also choices (e.g. ``actuator``), so a
    #: component added to config/components is selectable without editing the genes
    choices_from: str | None = None
    evolvable: bool = True

    @model_validator(mode="after")
    def _check(self) -> GeneDef:
        if self.type in ("float", "int"):
            if self.min is None or self.max is None:
                raise ValueError(f"Gene {self.id!r}: numeric genes need min and max")
            if not (self.min <= float(self.default) <= self.max):  # type: ignore[arg-type]
                raise ValueError(f"Gene {self.id!r}: default outside [min, max]")
        if self.type == "enum":
            if not self.choices:
                raise ValueError(f"Gene {self.id!r}: enum genes need choices")
            if self.default not in self.choices:
                raise ValueError(f"Gene {self.id!r}: default not in choices")
        if self.absent is not None and self.coerce(self.absent) != self.absent:
            raise ValueError(f"Gene {self.id!r}: 'absent' is not a valid value for this gene")
        return self

    def coerce(self, value: Any) -> GeneValue:
        """Validate and clamp a value for this gene."""
        if self.type == "float":
            v = float(value)
            return min(max(v, float(self.min)), float(self.max))  # type: ignore[arg-type]
        if self.type == "int":
            vi = int(round(float(value)))
            return int(min(max(vi, int(self.min)), int(self.max)))  # type: ignore[arg-type]
        if self.type == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if value not in (self.choices or []):
            raise ValueError(f"Gene {self.id!r}: {value!r} not in {self.choices}")
        return str(value)


class GenomeDefinition(BaseModel):
    name: str
    version: int = 1
    description: str = ""
    genes: list[GeneDef]

    @model_validator(mode="after")
    def _unique(self) -> GenomeDefinition:
        seen: set[str] = set()
        for g in self.genes:
            if g.id in seen:
                raise ValueError(f"Duplicate gene id {g.id!r}")
            seen.add(g.id)
        return self

    def gene(self, gene_id: str) -> GeneDef:
        for g in self.genes:
            if g.id == gene_id:
                return g
        raise KeyError(gene_id)

    def has(self, gene_id: str) -> bool:
        return any(g.id == gene_id for g in self.genes)

    def defaults(self) -> dict[str, GeneValue]:
        return {g.id: g.default for g in self.genes}

    def complete(self, values: dict[str, Any]) -> dict[str, GeneValue]:
        """Complete stored values: fill in genes they do not mention (with the
        gene's ``absent`` value if it has one, else its default), drop unknown
        genes, coerce and clamp."""
        out: dict[str, GeneValue] = {g.id: g.default if g.absent is None else g.absent for g in self.genes}
        for k, v in values.items():
            if self.has(k):
                out[k] = self.gene(k).coerce(v)
        return out

    def default_genome(self) -> Genome:
        return Genome(definition=self.name, version=self.version, values=self.defaults())

    # ---- vector encoding for optimizers (numeric evolvable genes, normalised to [0, 1])
    def evolvable(self, only: list[str] | None = None) -> list[GeneDef]:
        genes = [g for g in self.genes if g.evolvable and g.type in ("float", "int")]
        if only:
            genes = [g for g in genes if g.id in only]
        return genes

    def encode(self, values: dict[str, GeneValue], only: list[str] | None = None) -> np.ndarray:
        genes = self.evolvable(only)
        return np.array(
            [(float(values[g.id]) - g.min) / ((g.max - g.min) or 1.0) for g in genes],  # type: ignore[operator,arg-type]
            dtype=float,
        )

    def decode(
        self, vector: np.ndarray, base: dict[str, GeneValue], only: list[str] | None = None
    ) -> dict[str, GeneValue]:
        genes = self.evolvable(only)
        out = dict(base)
        for g, x in zip(genes, np.clip(vector, 0.0, 1.0), strict=True):
            out[g.id] = g.coerce(g.min + float(x) * (g.max - g.min))  # type: ignore[operator]
        return out

    def ui_schema(self) -> dict[str, Any]:
        fields = []
        for g in self.genes:
            ftype = {"float": "number", "int": "integer", "bool": "boolean", "enum": "enum"}[g.type]
            f: dict[str, Any] = {
                "name": g.id,
                "type": ftype,
                "default": g.default,
                "unit": g.unit,
                "min": g.min,
                "max": g.max,
                "step": g.step,
                "description": g.description,
                "group": g.group,
            }
            if g.label:
                f["label"] = g.label
            if g.choices:
                f["choices"] = g.choices
            fields.append(f)
        return dynamic_schema(f"{self.name} v{self.version}", fields, self.description)


class Genome(BaseModel):
    definition: str
    version: int
    values: dict[str, GeneValue] = Field(default_factory=dict)


def load_definition_file(path: Path) -> GenomeDefinition:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return GenomeDefinition.model_validate(data)
