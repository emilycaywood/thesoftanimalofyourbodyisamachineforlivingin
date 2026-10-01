"""Evaluate a design: genome + overrides -> element parameters -> RobotSpec."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calflab.components import library
from calflab.config import robot_defaults
from calflab.model.genome import Genome, GenomeDefinition
from calflab.model.migrations import migrate
from calflab.model.overrides import ElementParams, Override, apply_overrides, geometry_overrides
from calflab.model.spec import RobotSpec
from calflab.plugins import BuildContext, PartGenerator, load_plugins, registry


@dataclass
class EvaluatedDesign:
    genome: Genome
    element_params: ElementParams
    spec: RobotSpec
    warnings: list[str] = field(default_factory=list)


def genome_definition(name: str) -> GenomeDefinition:
    load_plugins()
    cls = registry.get("gene_definition", name)
    return cls().definition()  # type: ignore[attr-defined]


def build_design(
    genome: Genome,
    overrides: list[Override] | None = None,
    generator: str = "calf",
    generator_params: dict[str, Any] | None = None,
) -> EvaluatedDesign:
    """Run the two-stage part generator with overrides applied in between."""
    load_plugins()
    gen_cls = registry.get("part_generator", generator)
    gen: PartGenerator = gen_cls(generator_params or {})  # type: ignore[assignment]
    gdef = genome_definition(gen.genome_definition or genome.definition)
    genome = migrate(genome, gdef)
    params = gen.element_params(genome.values)
    params, warnings = apply_overrides(params, overrides or [])
    ctx = BuildContext(
        library=library(),
        defaults=robot_defaults(),
        geometry_overrides=geometry_overrides(overrides or []),
    )
    spec = gen.build(genome.values, params, ctx)
    for target, ov in ctx.geometry_overrides.items():
        _apply_geometry_override(spec, target, ov, warnings)
    spec.metadata.update({"genome_definition": gdef.name, "genome_version": gdef.version})
    return EvaluatedDesign(genome=genome, element_params=params, spec=spec, warnings=warnings)


def _apply_geometry_override(
    spec: RobotSpec, target: str, ov: Override, warnings: list[str]
) -> None:
    """Replace a body's visible skin/shell with a sculpted mesh asset."""
    from calflab.model.spec import Geom

    try:
        body = spec.body(target)
    except KeyError:
        warnings.append(f"Geometry override {ov.name!r} targets missing body {target}")
        return
    layer = str(ov.meta.get("layer", "Skin"))
    replaced_mass = 0.0
    kept = []
    for g in body.geoms:
        if g.layer == layer and g.role == "visual":
            replaced_mass += g.mass_g
        else:
            kept.append(g)
    kept.append(
        Geom(
            id=f"{target}.override.{ov.id}",
            shape="mesh",
            size=(0.0, 0.0, 0.0),
            mesh=ov.asset,
            layer=layer,
            role="visual",
            mass_g=replaced_mass,
            label=ov.name,
        )
    )
    body.geoms = kept
