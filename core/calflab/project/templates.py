"""Project templates: a new project for a body other than the reference calf.

``feral_calf`` (ADR-066): the final feral calf. The project gets its own copy
of the belt catalog (``catalog/belt_systems.json``, ``belt_lengths.json``,
``pulleys.json``) from ``config/belts``, which the researcher then edits there
(e.g. ``purchase_confirmed``); the default belt choices are worked out with
that catalog and stored explicitly in the document.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from calflab.mech.belts import CATALOG_FILES
from calflab.paths import config_dir
from calflab.project.store import DocumentState, Project

TEMPLATE_NAMES = ("calf", "feral_calf")


def create_project(path: Path, template: str = "calf", name: str | None = None) -> Project:
    """Create a project folder from a template. Refuses an existing project."""
    from calflab.config import default
    from calflab.graph import default_graph
    from calflab.plugins import load_plugins

    if template not in TEMPLATE_NAMES:
        raise ValueError(f"Unknown template {template!r}; choose one of {', '.join(TEMPLATE_NAMES)}")
    load_plugins()
    path = Path(path)
    if template == "calf":
        return Project.create(path, name)
    if (path / "project.calflab.json").exists():
        raise FileExistsError(f"{path} already contains a CALFLAB project")
    catalog = path / "catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    for f in CATALOG_FILES:
        if not (catalog / f).exists():
            shutil.copyfile(config_dir() / "belts" / f, catalog / f)
    graph = default_graph(default("simulation", {}), template="feral_calf")
    # load runs use the servos up to stall (derating 1); F5 does the same so both agree (ADR-069). No skin model yet.
    graph.node("mjcf").params.update({"torque_derating": 1.0, "include_skin": False})
    graph.node("sim").params.update({"duration_s": 13.5, "start_pose": "stand", "stop_on_fall": False})
    graph.node("fitness").params.update({"preset": "walk"})
    project = Project.create(path, name, DocumentState(graph=graph))
    _store_default_belts(project)
    return project


def _store_default_belts(project: Project) -> None:
    """Build once with the project's catalog and store the drives it chose, so the document says what it uses."""
    from calflab.design import build_design, genome_definition
    from calflab.graph import node_types

    state = project.state
    node = state.graph.node("morphology")
    design = build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", node.params, project.path)
    drives = design.spec.metadata["feral"]["belt_drives"]
    node.params = node_types()[node.type].clean_params(
        {**node.params, "belts": {d: r["choice"] for d, r in drives.items() if r["ok"]}})
    project.save(state)
