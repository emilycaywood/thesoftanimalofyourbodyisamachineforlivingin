"""Constraints on what evolution may change (ADR-070).

A part generator may list, in ``spec.metadata["infeasible"]``, why a body
cannot be built as it is (the feral calf: a belt drive that fails a check,
front legs that cannot reach the ground). Evolution never repairs such a
body: the candidate is rejected before it is simulated, with the reasons.

Genes marked ``belt_bound`` feed the belt drives' checks. Before a run their
search range is narrowed to the stretch around the starting value where every
belt still passes (``spec.metadata["infeasible_by"]["belt"]`` empty), scanned
one gene at a time with the others at their starting values. Other reasons
(the feral calf's front legs too short for a level back) do not narrow a
range, since other evolved genes can fix them. Genes interact, so a
candidate can still fail; the rejection above catches it. The belts
themselves are catalog ids and never evolve, so their dimensions are the
same in every candidate.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from calflab.model.genome import GeneDef, Genome
from calflab.model.overrides import Override


def infeasible(spec: Any) -> list[str]:
    """Why a built body cannot be used (empty = it can)."""
    return [str(r) for r in (spec.metadata.get("infeasible") or [])]


def feasible_bounds(
    genome: Genome,
    overrides: list[Override],
    generator: str,
    generator_params: dict[str, Any],
    project_dir: Path | None,
    genes: list[GeneDef],
    samples: int = 33,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per ``belt_bound`` gene: the contiguous range around the starting value
    in which the body stays feasible (others at their starting values)."""
    from calflab.design import build_design

    def ok(values: dict[str, Any]) -> bool:
        try:
            d = build_design(Genome(definition=genome.definition, version=genome.version, values=values), overrides,
                             generator, generator_params, project_dir)
        except Exception:
            return False
        by = d.spec.metadata.get("infeasible_by")
        return not (by["belt"] if isinstance(by, dict) and "belt" in by else infeasible(d.spec))

    out: dict[str, dict[str, Any]] = {}
    for g in genes:
        if not g.belt_bound or g.min is None or g.max is None:
            continue
        start = float(genome.values[g.id])  # type: ignore[arg-type]
        grid = sorted({g.min + (g.max - g.min) * i / (samples - 1) for i in range(samples)} | {start})
        flags = []
        for v in grid:
            if cancelled is not None and cancelled():
                return out
            flags.append(ok({**genome.values, g.id: g.coerce(v)}))
        k = grid.index(start)
        if not flags[k]:
            raise ValueError(f"The starting body is not feasible (gene {g.id} = {start:g}); fix it before evolving")
        lo = k
        while lo > 0 and flags[lo - 1]:
            lo -= 1
        hi = k
        while hi < len(grid) - 1 and flags[hi + 1]:
            hi += 1
        out[g.id] = {"min": grid[lo], "max": grid[hi], "start": start, "gene_min": g.min, "gene_max": g.max,
                     "narrowed": grid[lo] > g.min or grid[hi] < g.max, "samples": len(grid)}
    return out
