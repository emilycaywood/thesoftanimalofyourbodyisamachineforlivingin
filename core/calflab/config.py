"""Access to ``config/robot_defaults.yaml`` and gene-definition files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from calflab.model.genome import GenomeDefinition, load_definition_file
from calflab.paths import config_dir


@lru_cache(maxsize=4)
def _load_yaml(path: str, mtime: float) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def robot_defaults() -> dict[str, Any]:
    """Parsed ``config/robot_defaults.yaml`` (reloaded when the file changes)."""
    p = config_dir() / "robot_defaults.yaml"
    return _load_yaml(str(p), p.stat().st_mtime)


def default(path: str, fallback: Any = None) -> Any:
    """Dotted lookup into robot defaults, e.g. ``default('simulation.torque_derating')``."""
    node: Any = robot_defaults()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return fallback
        node = node[part]
    return node


@lru_cache(maxsize=16)
def _load_def(path: str, mtime: float) -> GenomeDefinition:
    return load_definition_file(Path(path))


def gene_definition_files() -> dict[str, GenomeDefinition]:
    out: dict[str, GenomeDefinition] = {}
    for p in sorted((config_dir() / "genes").glob("*.yaml")):
        d = _load_def(str(p), p.stat().st_mtime)
        out[d.name] = d
    return out


def fitness_preset_files() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((config_dir() / "fitness").glob("*.yaml")):
        data = _load_yaml(str(p), p.stat().st_mtime)
        out[str(data.get("name", p.stem))] = data
    return out
