"""Genome migrations.

A migration is a pure function ``values -> values`` registered for
``(definition name, from_version)``; it upgrades a genome by exactly one
version. :func:`migrate` chains them up to the current definition version so
that genomes stored in old runs and designs always reload.

When you change ``config/genes/<name>.yaml`` in a way that renames, removes or
re-scales a gene: bump ``version`` there, add a migration here, and add a case
to ``tests/test_genome.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from calflab.model.genome import Genome, GenomeDefinition

Migration = Callable[[dict[str, Any]], dict[str, Any]]
_MIGRATIONS: dict[tuple[str, int], Migration] = {}
#: per migration, the genes it removes: only a genome older than the migration has them (ADR-101)
_REMOVES: dict[tuple[str, int], tuple[str, ...]] = {}


def migration(definition: str, from_version: int, removes: tuple[str, ...] = ()) -> Callable[[Migration], Migration]:
    """Register ``fn`` as the upgrade of ``definition`` from ``from_version`` to the next.

    ``removes``: the genes this step removes. Name them when a step removes or renames a gene and is harmless on
    values that are already past it: params stored without a version (a document's genome node, ADR-101) are then
    recognised as older than this step by the presence of one of them, and upgraded by :func:`upgrade_unversioned`
    wherever they are completed. (The calf's v1 -> v2 step also re-measures ``neck_angle``, so it is not marked.)
    """

    def deco(fn: Migration) -> Migration:
        key = (definition, from_version)
        if key in _MIGRATIONS:
            raise ValueError(f"Duplicate migration for {key}")
        _MIGRATIONS[key] = fn
        if removes:
            _REMOVES[key] = tuple(removes)
        return fn

    return deco


def upgrade_unversioned(definition: GenomeDefinition, values: dict[str, Any]) -> dict[str, Any]:
    """Upgrade genome values that carry no version (a document's genome node params, ADR-101).

    A step is applied when the values still hold a gene it removes; steps that remove nothing cannot be recognised
    and are skipped. A value already at the installed version holds none of them and comes back unchanged (the same
    dict), so this is safe to call on every completion.
    """
    out = values
    for (name, _v), removed in sorted(_REMOVES.items()):
        if name != definition.name or _v >= definition.version:
            continue
        if any(k in out and not definition.has(k) for k in removed):
            out = _MIGRATIONS[(name, _v)](dict(out))
    return out


def migrate(genome: Genome, definition: GenomeDefinition) -> Genome:
    """Upgrade ``genome`` to ``definition.version`` and complete missing genes."""
    if genome.definition != definition.name:
        raise ValueError(
            f"Genome is for definition {genome.definition!r}, not {definition.name!r}"
        )
    if genome.version > definition.version:
        raise ValueError(
            f"Genome version {genome.version} is newer than the installed definition "
            f"{definition.name} v{definition.version}. Update CALFLAB."
        )
    values = dict(genome.values)
    version = genome.version
    while version < definition.version:
        fn = _MIGRATIONS.get((definition.name, version))
        if fn is None:
            raise ValueError(f"No migration registered for {definition.name} v{version} -> v{version + 1}")
        values = fn(dict(values))
        version += 1
    return Genome(
        definition=definition.name, version=definition.version, values=definition.complete(values)
    )


# --------------------------------------------------------------------------- calf
@migration("calf", 1)
def _calf_v1_to_v2(v: dict[str, Any]) -> dict[str, Any]:
    """v1 had a single ``leg_length``; v2 splits it into thigh and shank.

    v1 also stored ``neck_angle`` as an angle from vertical; v2 measures it
    from horizontal.
    """
    if "leg_length" in v:
        leg = float(v.pop("leg_length"))
        v.setdefault("thigh_length", leg / 2.0)
        v.setdefault("shank_length", leg / 2.0)
    if "neck_angle" in v:
        v["neck_angle"] = 90.0 - float(v["neck_angle"])
    return v


# --------------------------------------------------------------------------- feral calf
SERVO_PAIRS = ("hip_abd", "stifle", "hock", "shoulder", "carpus")


@migration("feral_calf", 1, removes=("actuator",))
def _feral_v1_to_v2(v: dict[str, Any]) -> dict[str, Any]:
    """v1 had one ``actuator`` gene for all ten servos; v2 has one per joint pair, ``servo_<joint>`` (ADR-101).

    A v1 genome without ``actuator`` had the gene's default then, which is the pair genes' default now.
    """
    if "actuator" in v:
        servo = v.pop("actuator")
        for pair in SERVO_PAIRS:
            v.setdefault(f"servo_{pair}", servo)
    return v
