"""Project folder: the document, its sub-folders and atomic saving.

    <project>/
      project.calflab.json   the document (graph, overrides, layers, ...)
      commands.jsonl         append-only command log (undo/redo, research record)
      index.sqlite           registry index (rebuildable from the text files)
      runs/<id>/run.json     one folder per sim / evolution / bake / export
      designs/<id>/          baked, immutable designs
      journal/*.md           research journal
      assets/                reference images, captures, sculpted geometry
      motions/               reference-motion clips (from Blender)
      exports/               fabrication and wiring outputs
      .cache/                node-output cache (safe to delete)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from calflab import __version__
from calflab.graph.model import Graph
from calflab.model.overrides import Override
from calflab.model.spec import LAYER_COLORS, LAYERS

PROJECT_FILE = "project.calflab.json"
PROJECT_SCHEMA_VERSION = 1
SUBDIRS = ("runs", "designs", "journal", "assets", "motions", "exports", ".cache")


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, fallback: str = "item") -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or fallback


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file + replace so a crash never leaves a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(5):  # cloud-synced folders briefly lock files
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def write_json(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=False, default=str) + "\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class LayerState(BaseModel):
    visible: bool = True
    locked: bool = False
    color: str = "#cccccc"


class ReferenceImage(BaseModel):
    """A calf photo/drawing placed on a view plane (Form workspace)."""

    id: str
    asset: str  # project-relative path under assets/
    plane: str = "right"  # front | right | top
    center: tuple[float, float, float] = (0.0, 0.0, 300.0)  # mm
    width_mm: float = 700.0
    opacity: float = 0.5
    visible: bool = True


def default_layers() -> dict[str, LayerState]:
    return {name: LayerState(color=LAYER_COLORS[name]) for name in LAYERS}


class DocumentState(BaseModel):
    """Everything undo/redo covers."""

    graph: Graph = Field(default_factory=Graph)
    overrides: list[Override] = Field(default_factory=list)
    layers: dict[str, LayerState] = Field(default_factory=default_layers)
    references: list[ReferenceImage] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectFile(BaseModel):
    schema_version: int = PROJECT_SCHEMA_VERSION
    name: str
    created: str
    modified: str
    calflab_version: str = __version__
    state: DocumentState


class Project:
    """A project folder on disk."""

    def __init__(self, path: Path, file: ProjectFile):
        self.path = path
        self.file = file

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, path: Path, name: str | None = None, state: DocumentState | None = None) -> Project:
        path = Path(path)
        if (path / PROJECT_FILE).exists():
            raise FileExistsError(f"{path} already contains a CALFLAB project")
        path.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRS:
            (path / sub).mkdir(exist_ok=True)
        if state is None:
            from calflab.config import default
            from calflab.graph import default_graph

            state = DocumentState(graph=default_graph(default("simulation", {})))
        t = now_iso()
        project = cls(path, ProjectFile(name=name or path.name, created=t, modified=t, state=state))
        project.save()
        return project

    @classmethod
    def open(cls, path: Path) -> Project:
        path = Path(path)
        f = path / PROJECT_FILE
        if not f.is_file():
            raise FileNotFoundError(f"No {PROJECT_FILE} in {path}. Create one with: calflab setup")
        data = read_json(f)
        version = int(data.get("schema_version", 1))
        if version > PROJECT_SCHEMA_VERSION:
            raise ValueError(
                f"Project was saved by a newer CALFLAB (schema {version} > {PROJECT_SCHEMA_VERSION})"
            )
        project = cls(path, ProjectFile.model_validate(data))
        for sub in SUBDIRS:
            (path / sub).mkdir(exist_ok=True)
        return project

    def save(self, state: DocumentState | None = None) -> None:
        if state is not None:
            self.file.state = state
        self.file.modified = now_iso()
        write_json(self.path / PROJECT_FILE, self.file.model_dump(mode="json"))

    # ------------------------------------------------------------------ paths
    @property
    def name(self) -> str:
        return self.file.name

    @property
    def state(self) -> DocumentState:
        return self.file.state

    def dir(self, name: str) -> Path:
        p = self.path / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def rel(self, path: Path) -> str:
        """Project-relative POSIX path (used in records so projects are movable)."""
        return Path(path).resolve().relative_to(self.path.resolve()).as_posix()

    def resolve(self, rel: str) -> Path:
        """Resolve a project-relative path, refusing to escape the project."""
        p = (self.path / rel).resolve()
        if not p.is_relative_to(self.path.resolve()):
            raise ValueError(f"Path {rel!r} escapes the project folder")
        return p
