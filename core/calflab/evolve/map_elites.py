"""MAP-Elites over morphology with a CMA-ES inner loop over the controller.

Outer loop (this module): a pyribs ``GridArchive`` indexed by two behavior
descriptors; children are produced by iso+line variation from elites so every
candidate knows its parents (lineage). Inner loop
(:func:`calflab.evolve.tasks.evaluate_candidate`): CMA-ES tunes the controller
for each candidate morphology, warm-started from the first parent's controller.
The unit of parallel work is one outer candidate (ADR-012).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.design import genome_definition
from calflab.plugins import ComputeBackend, Optimizer, Task, register, registry
from calflab.schema import P


class Candidate(BaseModel):
    """One evaluated design. Stored in the registry with its lineage."""

    id: str
    run_id: str = ""
    generation: int
    parents: list[str] = Field(default_factory=list)
    genome: dict[str, Any]
    controller: dict[str, Any]
    controller_x: list[float] = Field(default_factory=list)
    fitness: float
    fitness_terms: dict[str, Any] = Field(default_factory=dict)
    descriptors: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    cell: tuple[int, int] | None = None
    status: str = "rejected"  # new | improved | rejected | failed
    mass_g: float = 0.0
    error: str | None = None


@dataclass
class EvolveProblem:
    """Everything needed to evaluate candidates, all JSON-able."""

    genome: dict[str, Any]  # Genome dump (the starting design)
    overrides: list[dict[str, Any]]
    generator: str
    generator_params: dict[str, Any]
    compile: dict[str, Any]
    sim: dict[str, Any]
    controller: dict[str, Any]  # {key, params}
    fitness: dict[str, Any]  # FitnessPreset dump
    run_id: str = "run"
    cancelled: Callable[[], bool] | None = None


@dataclass
class EvolveResult:
    candidates: list[Candidate] = field(default_factory=list)
    cells: dict[str, str] = field(default_factory=dict)  # "i,j" -> candidate id
    history: list[dict[str, Any]] = field(default_factory=list)
    archive: dict[str, Any] = field(default_factory=dict)
    evals: int = 0


@register
class MapElitesCMA(Optimizer):
    """MAP-Elites (pyribs) outer loop + CMA-ES controller inner loop."""

    key = "map_elites_cma"
    label = "MAP-Elites + CMA-ES"
    description = "Illuminates morphology space (MAP-Elites) while CMA-ES tunes the gait for each body."
    version = "1"

    class Params(BaseModel):
        generations: int = P(6, ge=1, le=500, desc="Outer-loop generations.", group="Budget")
        batch_size: int = P(8, ge=2, le=256, desc="Candidate morphologies per generation.", group="Budget")
        inner_iterations: int = P(3, ge=0, le=50, desc="CMA-ES iterations per candidate (0 = keep the controller).", group="Budget")
        inner_popsize: int = P(6, ge=2, le=64, desc="CMA-ES population size.", group="Budget")
        descriptor_x: str = P("leg_length", desc="Behavior descriptor on the archive's X axis.", group="Archive")
        descriptor_y: str = P("gait_frequency", desc="Behavior descriptor on the archive's Y axis.", group="Archive")
        grid_x: int = P(10, ge=2, le=50, desc="Archive cells along X.", group="Archive")
        grid_y: int = P(10, ge=2, le=50, desc="Archive cells along Y.", group="Archive")
        genes: list[str] = P(default_factory=list, ui="json", desc="Genes to evolve (empty = all evolvable genes).", group="Variation")
        sigma_init: float = P(0.15, ge=0.01, le=0.5, step=0.01, desc="Spread of the initial population (fraction of gene range).", group="Variation")
        sigma_iso: float = P(0.05, ge=0.0, le=0.5, step=0.01, desc="Isotropic mutation (fraction of gene range).", group="Variation")
        sigma_line: float = P(0.2, ge=0.0, le=1.0, step=0.01, desc="Mutation along the line between two elites.", group="Variation")
        inner_sigma: float = P(0.15, ge=0.01, le=0.5, step=0.01, desc="CMA-ES initial step size.", group="Variation")
        seed: int = P(0, ge=0, le=2**31 - 1, ui="number", desc="Random seed.", group="Budget")

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        schema = super().params_schema()
        choices = sorted(registry.all("behavior_descriptor"))
        for f in schema["fields"]:
            if f["name"] in ("descriptor_x", "descriptor_y"):
                f.update({"type": "enum", "ui": "enum", "choices": choices})
        return schema

    def run(
        self, problem: EvolveProblem, backend: ComputeBackend, report: Callable[..., None]
    ) -> EvolveResult:
        from ribs.archives import GridArchive

        p = self.params
        rng = np.random.default_rng(p.seed)  # type: ignore[attr-defined]
        gdef = genome_definition(problem.genome["definition"])
        base_values = gdef.complete(problem.genome["values"])
        only = list(p.genes) or None  # type: ignore[attr-defined]
        genes = gdef.evolvable(only)
        if not genes:
            raise ValueError("No evolvable genes selected")
        dkeys = [p.descriptor_x, p.descriptor_y]  # type: ignore[attr-defined]
        ranges = [registry.get("behavior_descriptor", k).range for k in dkeys]  # type: ignore[attr-defined]
        archive = GridArchive(
            solution_dim=len(genes),
            dims=[p.grid_x, p.grid_y],  # type: ignore[attr-defined]
            ranges=ranges,
            qd_score_offset=-2.0,
        )
        result = EvolveResult()
        by_id: dict[str, Candidate] = {}
        vec: dict[str, np.ndarray] = {}
        x_base = gdef.encode(base_values, only)

        def payload(x: np.ndarray, warm: list[float] | None, seed: int) -> dict[str, Any]:
            values = gdef.decode(x, base_values, only)
            return {
                "genome": {"definition": gdef.name, "version": gdef.version, "values": values},
                "overrides": problem.overrides,
                "generator": problem.generator,
                "generator_params": problem.generator_params,
                "compile": problem.compile,
                "sim": problem.sim,
                "controller": {**problem.controller, "x0": warm},
                "fitness": problem.fitness,
                "descriptors": dkeys,
                "inner": {
                    "iterations": p.inner_iterations,  # type: ignore[attr-defined]
                    "popsize": p.inner_popsize,  # type: ignore[attr-defined]
                    "sigma": p.inner_sigma,  # type: ignore[attr-defined]
                },
                "seed": seed,
            }

        def cancelled() -> bool:
            return bool(problem.cancelled and problem.cancelled())

        for gen in range(p.generations):  # type: ignore[attr-defined]
            if cancelled():
                break
            # ---- variation
            xs: list[np.ndarray] = []
            parents: list[list[str]] = []
            warm: list[list[float] | None] = []
            elites = list(result.cells.values())
            for i in range(p.batch_size):  # type: ignore[attr-defined]
                if not elites:
                    x = x_base if i == 0 else x_base + rng.normal(0, p.sigma_init, len(genes))  # type: ignore[attr-defined]
                    parents.append([])
                    warm.append(None)
                else:
                    a = by_id[elites[int(rng.integers(len(elites)))]]
                    b = by_id[elites[int(rng.integers(len(elites)))]]
                    x = (
                        vec[a.id]
                        + rng.normal(0, p.sigma_iso, len(genes))  # type: ignore[attr-defined]
                        + rng.normal(0, p.sigma_line) * (vec[b.id] - vec[a.id])  # type: ignore[attr-defined]
                    )
                    parents.append([a.id] if a.id == b.id else [a.id, b.id])
                    warm.append(a.controller_x or None)
                xs.append(np.clip(x, 0.0, 1.0))

            # ---- evaluation (parallel over candidates)
            tasks = [
                Task(
                    fn="calflab.evolve.tasks:evaluate_candidate",
                    payload=payload(x, w, p.seed + gen * 1000 + i),  # type: ignore[attr-defined]
                    id=f"{problem.run_id}-g{gen:03d}-{i:03d}",
                )
                for i, (x, w) in enumerate(zip(xs, warm, strict=True))
            ]
            done = [0]

            def on_result(
                _i: int, _r: Any, gen: int = gen, done: list[int] = done, n: int = len(tasks)
            ) -> None:
                done[0] += 1
                report(
                    kind="progress",
                    generation=gen,
                    fraction=(gen + done[0] / n) / p.generations,  # type: ignore[attr-defined]
                )

            outs = backend.map(tasks, on_result=on_result, cancelled=cancelled)

            # ---- insertion
            new_cands: list[Candidate] = []
            for i, (task, out) in enumerate(zip(tasks, outs, strict=True)):
                genome = task.payload["genome"]
                if not isinstance(out, dict) or out.get("error"):
                    cand = Candidate(
                        id=task.id,
                        run_id=problem.run_id,
                        generation=gen,
                        parents=parents[i],
                        genome=genome,
                        controller=problem.controller,
                        fitness=-1e9,
                        status="failed",
                        error=str(out.get("error") if isinstance(out, dict) else out),
                    )
                    new_cands.append(cand)
                    continue
                result.evals += int(out["evals"])
                measures = np.array([[out["descriptors"][k] for k in dkeys]])
                info = archive.add(xs[i][None, :], np.array([out["fitness"]]), measures)
                status = int(info["status"][0])
                gi = archive.int_to_grid_index(archive.index_of(measures))[0]
                cand = Candidate(
                    id=task.id,
                    run_id=problem.run_id,
                    generation=gen,
                    parents=parents[i],
                    genome=genome,
                    controller={"key": problem.controller["key"], "params": out["controller_params"]},
                    controller_x=out["controller_x"],
                    fitness=float(out["fitness"]),
                    fitness_terms=out["fitness_terms"],
                    descriptors=out["descriptors"],
                    metrics=out["metrics"],
                    cell=(int(gi[0]), int(gi[1])),
                    status={0: "rejected", 1: "improved", 2: "new"}[status],
                    mass_g=float(out.get("mass_g", 0.0)),
                )
                by_id[cand.id] = cand
                vec[cand.id] = xs[i]
                if status > 0:
                    result.cells[f"{gi[0]},{gi[1]}"] = cand.id
                new_cands.append(cand)
            result.candidates += new_cands

            ok = [c for c in new_cands if c.status != "failed"]
            stats = archive.stats
            entry = {
                "generation": gen,
                "best": float(stats.obj_max) if stats.num_elites else None,  # type: ignore[arg-type]
                "mean": float(stats.obj_mean) if stats.num_elites else None,  # type: ignore[arg-type]
                "gen_best": max((c.fitness for c in ok), default=None),
                "gen_mean": float(np.mean([c.fitness for c in ok])) if ok else None,
                "coverage": float(stats.coverage),
                "qd_score": float(stats.qd_score),
                "elites": int(stats.num_elites),
                "evals": result.evals,
                "failed": len(new_cands) - len(ok),
            }
            result.history.append(entry)
            result.archive = self.archive_view(result, by_id, dkeys, ranges)
            report(kind="generation", generation=gen, entry=entry, candidates=new_cands, result=result)
        if not result.archive:
            result.archive = self.archive_view(result, by_id, dkeys, ranges)
        return result

    def archive_view(
        self,
        result: EvolveResult,
        by_id: dict[str, Candidate],
        dkeys: list[str],
        ranges: list[tuple[float, float]],
    ) -> dict[str, Any]:
        """JSON view of the archive for the heatmap."""
        p = self.params
        axes = []
        for key, rng_, n in zip(dkeys, ranges, (p.grid_x, p.grid_y), strict=True):  # type: ignore[attr-defined]
            cls = registry.get("behavior_descriptor", key)
            axes.append(
                {"key": key, "label": cls.label, "unit": cls.unit, "range": list(rng_), "cells": n}  # type: ignore[attr-defined]
            )
        cells = []
        for key, cid in result.cells.items():
            i, j = (int(v) for v in key.split(","))
            c = by_id[cid]
            cells.append(
                {
                    "i": i,
                    "j": j,
                    "candidate": cid,
                    "fitness": c.fitness,
                    "generation": c.generation,
                    "descriptors": c.descriptors,
                    "speed_mps": c.metrics.get("speed_mps"),
                }
            )
        return {"axes": axes, "cells": cells}
