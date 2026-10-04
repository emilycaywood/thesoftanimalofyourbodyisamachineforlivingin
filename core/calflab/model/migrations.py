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


def migration(definition: str, from_version: int) -> Callable[[Migration], Migration]:
    def deco(fn: Migration) -> Migration:
        key = (definition, from_version)
        if key in _MIGRATIONS:
            raise ValueError(f"Duplicate migration for {key}")
        _MIGRATIONS[key] = fn
        return fn

    return deco


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
