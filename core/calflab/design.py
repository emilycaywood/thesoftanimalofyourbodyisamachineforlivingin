"""Evaluate a design: genome + overrides -> element parameters -> RobotSpec."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calflab.components import Library, MaterialSpec, library
from calflab.config import robot_defaults
from calflab.model.genome import Genome, GenomeDefinition
from calflab.model.migrations import migrate
from calflab.model.overrides import (
    ElementParams,
    Override,
    apply_overrides,
    geometry_override_list,
    geometry_overrides,
    mass_overrides,
    material_overrides,
)
from calflab.model.spec import Body, Geom, RobotSpec
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


def structure_material(lib: Library, key: str | None) -> MaterialSpec | None:
    """The structure material ``key`` names, or None if it is not one."""
    if not key or not lib.has(key):
        return None
    c = lib.get(key)
    return c if isinstance(c, MaterialSpec) and c.role == "structure" else None


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
    lib = library()
    defaults = robot_defaults()
    materials: dict[str, str] = {}
    for target, key in material_overrides(overrides or []).items():
        if structure_material(lib, key) is None:
            warnings.append(f"Material override on {target}: {key!r} is not a structure material; the default is used")
        else:
            materials[target] = key
    ctx = BuildContext(
        library=lib,
        defaults=defaults,
        geometry_overrides=geometry_overrides(overrides or []),
        materials=materials,
    )
    spec = gen.build(genome.values, params, ctx)
    default_key = str(defaults.get("structure", {}).get("material", "petg"))
    for ov in geometry_override_list(overrides or []):
        _apply_geometry_override(spec, ov.target, ov, warnings, lib, materials.get(ov.target, default_key))
    for target, ov in mass_overrides(overrides or []).items():
        _apply_measured_mass(spec, target, ov, warnings)
    spec.metadata.update({"genome_definition": gdef.name, "genome_version": gdef.version})
    return EvaluatedDesign(genome=genome, element_params=params, spec=spec, warnings=warnings)


def structure_geoms(body: Body) -> list[Geom]:
    """The geoms that make up a body's fabricated structure: what a pushed
    solid replaces and what a weighed part's mass stands for. Components and
    the cast hoof are separate parts."""
    return [g for g in body.geoms if g.layer == "Structure" and g.component is None and not g.foot]


def _apply_geometry_override(
    spec: RobotSpec, target: str, ov: Override, warnings: list[str], lib: Library, body_material: str
) -> None:
    """Put a pushed mesh in place of a body's geometry on one layer.

    *Structure* (ADR-050): a closed solid gives the part's mass, centre of mass
    and inertia as volume x density of its material; the envelope primitives
    stay as massless collision shapes. An open or invalid solid is shown but
    not used for mass: the envelope estimate stays, with a warning. A push of
    several solids (``meta["solids"]``, ADR-053) gives one mass geom per solid,
    each with its own material; the simulator composes them.

    *Any other layer* (a skin sculpt): the mesh replaces the visible surface
    and keeps the mass the envelope estimate gave it.
    """
    from calflab.model.solid import SolidInfo, scaled_inertia

    try:
        body = spec.body(target)
    except KeyError:
        warnings.append(f"Geometry override {ov.name!r} targets missing body {target}")
        return
    layer = str(ov.meta.get("layer", "Skin"))
    mesh = Geom(
        id=f"{target}.override.{ov.id}",
        shape="mesh",
        size=(0.0, 0.0, 0.0),
        mesh=ov.asset,
        layer=layer,
        role="visual",
        label=ov.name,
    )
    if layer != "Structure":
        kept = []
        for g in body.geoms:
            if g.layer == layer and g.role == "visual":
                mesh.mass_g += g.mass_g
                mesh.material = mesh.material or g.material
            else:
                kept.append(g)
        body.geoms = [*kept, mesh]
        return

    replaced = structure_geoms(body)
    estimate = sum(g.mass_g for g in replaced)
    # one entry per pushed solid; a push of a single solid has no list (ADR-053)
    entries: list[dict[str, Any]] = list(ov.meta.get("solids") or []) or [
        {"asset": ov.asset, "material": ov.meta.get("material"), "solid": ov.meta.get("solid")}
    ]
    several = len(entries) > 1
    meshes: list[Geom] = []
    measured: list[tuple[SolidInfo, MaterialSpec | None]] = []
    problems: list[str] = []
    for n, entry in enumerate(entries, start=1):
        label = str(entry.get("name") or f"solid {n}")
        solid = SolidInfo.model_validate(entry.get("solid") or {})
        key = str(entry.get("material") or ov.meta.get("material") or body_material)
        mat = structure_material(lib, key)
        problem = ""
        if not entry.get("solid"):
            problem = "it was pushed before solids were measured (push it again)"
        elif not solid.closed:
            problem = solid.problem or "it is not a closed solid"
        elif mat is None:
            problem = f"{key!r} is not a structure material in the library"
        if problem:
            problems.append(f"{label}: {problem}" if several else problem)
        measured.append((solid, mat))
        meshes.append(
            mesh.model_copy(update={"id": f"{mesh.id}.{n}", "mesh": entry.get("asset") or ov.asset, "label": f"{ov.name}: {label}"})
            if several
            else mesh
        )
    for g in replaced:  # the envelope stays as the collision shape only
        g.role = "collision"
        g.label = f"{g.label or g.id} (envelope)"
    if problems:
        # one unusable solid leaves the whole part on its estimate: a part-mass that lacks a solid would be wrong silently
        note = (
            f"The solids pushed onto {target} are not used for mass: {'; '.join(problems)}. The parametric estimate is kept."
            if several
            else f"The solid pushed onto {target} is not used for mass: {problems[0]}. The parametric estimate is kept."
        )
        warnings.append(note)
        for g in [*meshes, *replaced]:
            g.mass_note = note
    else:
        for g, (solid, mat) in zip(meshes, measured, strict=True):
            assert mat is not None
            density = mat.density_g_cm3 / 1000.0  # g/mm^3: each solid with its own material
            g.mass_g = solid.volume_mm3 * density
            g.mass_source = "geometry"
            g.material = mat.key
            g.com = solid.com_mm
            g.inertia = scaled_inertia(solid.inertia_mm5, density)
        meshes[0].mass_replaced_g = estimate
        for g in replaced:
            g.mass_g = 0.0
    body.geoms.extend(meshes)


def _apply_measured_mass(spec: RobotSpec, target: str, ov: Override, warnings: list[str]) -> None:
    """A weighed part: its structure mass becomes the measured value. Centre of
    mass and inertia keep the shape the geometry gave them, scaled to the mass."""
    from calflab.model.solid import scaled_inertia

    try:
        body = spec.body(target)
    except KeyError:
        warnings.append(f"Measured mass {ov.name!r} targets missing body {target}")
        return
    geoms = [g for g in structure_geoms(body) if g.mass_g > 0]
    computed = sum(g.mass_g for g in geoms)
    measured = float(ov.value or 0.0)
    if computed <= 0 or measured <= 0:
        warnings.append(f"Measured mass on {target} is not used: the part has no structure mass to replace")
        return
    factor = measured / computed
    for g in geoms:
        g.mass_computed_g = g.mass_g
        g.mass_g *= factor
        if g.inertia is not None:
            g.inertia = scaled_inertia(g.inertia, factor)
        g.mass_source = "measured"
