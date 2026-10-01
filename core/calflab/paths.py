"""Filesystem locations: repo root, config, user plugins, local work directory."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Root of the CALFLAB checkout (contains ``pyproject.toml`` and ``config/``)."""
    env = os.environ.get("CALFLAB_REPO")
    if env and (Path(env) / "config").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "robot_defaults.yaml").is_file():
            return parent
    return here.parents[2]


def config_dir() -> Path:
    return repo_root() / "config"


def plugins_dir() -> Path:
    return repo_root() / "plugins"


def projects_dir() -> Path:
    return repo_root() / "projects"


def web_dir() -> Path:
    return repo_root() / "web"


def home_dir() -> Path:
    """Local (non-synced) work directory: venv, node_modules, caches. ADR-003."""
    env = os.environ.get("CALFLAB_HOME")
    if env:
        p = Path(env)
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        p = Path(base) / "calflab"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_project() -> Path:
    env = os.environ.get("CALFLAB_PROJECT")
    return Path(env) if env else projects_dir() / "sample-calf"
