"""Element parameters and explicit overrides (ADR-007).

A part generator first produces, for every element, a table of parametric
values (:class:`ParamValue`) that records which gene drives each value. Direct
edits (gumball drags, Rhino-sculpted geometry) are stored as named
:class:`Override` records and applied to that table before geometry is built.
They are never silent mutations: each can be listed, toggled, removed or
internalized into the driving gene.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ParamValue(BaseModel):
    """One parametric value of one element."""

    value: float
    unit: str | None = "mm"
    gene: str | None = None  # gene that drives this value (value = gene * scale + offset)
    scale: float = 1.0
    offset: float = 0.0
    min: float | None = None
    max: float | None = None
    label: str | None = None
    # filled in by apply_overrides
    parametric: float | None = None  # value before the override
    override: str | None = None  # id of the active override

    def gene_value_for(self, value: float) -> float:
        """Gene value that would produce ``value`` (used by 'internalize')."""
        return (value - self.offset) / (self.scale or 1.0)


ElementParams = dict[str, dict[str, ParamValue]]


class Override(BaseModel):
    """An explicit edit layered over the parametric result."""

    id: str
    name: str
    target: str  # element id
    kind: Literal["param", "geometry"] = "param"
    param: str | None = None  # for kind == "param"
    value: float | None = None
    asset: str | None = None  # for kind == "geometry": project-relative mesh path
    enabled: bool = True
    source: str = "web"  # client that created it (web, rhino, blender, cli)
    note: str = ""
    created: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


def apply_overrides(params: ElementParams, overrides: list[Override]) -> tuple[ElementParams, list[str]]:
    """Return a copy of ``params`` with enabled param overrides applied.

    Later overrides win. Returns ``(params, warnings)``; an override whose
    target or param no longer exists yields a warning, not an error, so a
    design never becomes unloadable.
    """
    out: ElementParams = {
        el: {k: v.model_copy() for k, v in table.items()} for el, table in params.items()
    }
    warnings: list[str] = []
    for ov in overrides:
        if not ov.enabled or ov.kind != "param":
            continue
        table = out.get(ov.target)
        if table is None or ov.param is None or ov.param not in table:
            warnings.append(f"Override {ov.name!r} targets missing {ov.target}.{ov.param}")
            continue
        if ov.value is None:
            continue
        pv = table[ov.param]
        if pv.parametric is None:
            pv.parametric = pv.value
        value = ov.value
        if pv.min is not None:
            value = max(value, pv.min)
        if pv.max is not None:
            value = min(value, pv.max)
        pv.value = value
        pv.override = ov.id
    return out, warnings


def geometry_overrides(overrides: list[Override]) -> dict[str, Override]:
    """Active geometry overrides by target element id (last one wins)."""
    return {o.target: o for o in overrides if o.enabled and o.kind == "geometry" and o.asset}
