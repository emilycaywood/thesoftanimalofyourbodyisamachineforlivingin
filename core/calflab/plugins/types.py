"""The plugin types. Subclass one of these and decorate it with ``@register``.

Units: plugin ``Params`` are in design units (mm, g, deg) and say so via
``P(unit=...)``. Objects exchanged with the simulator at run time
(:class:`ControlInfo`, :class:`Observation`, controller outputs) are SI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from calflab.plugins.base import Plugin

if TYPE_CHECKING:
    from calflab.components.library import Component, Library
    from calflab.model.genome import GeneValue, GenomeDefinition
    from calflab.model.overrides import ElementParams, Override
    from calflab.model.spec import Joint, RobotSpec

PLUGIN_TYPES: list[str] = [
    "gene_definition",
    "part_generator",
    "joint_type",
    "component",
    "controller",
    "behavior",
    "fitness_term",
    "behavior_descriptor",
    "optimizer",
    "simulator",
    "compute_backend",
    "exporter",
    "analysis",
    "panel",
    "command",
]


# ============================================================ genome / morphology
class GeneDefinition(Plugin):
    """Provides a versioned genome definition (usually loaded from YAML)."""

    plugin_type = "gene_definition"

    def definition(self) -> GenomeDefinition:
        raise NotImplementedError

    @classmethod
    def extra(cls) -> dict[str, Any]:
        d = cls().definition()
        return {"definition": d.model_dump(mode="json"), "genome_schema": d.ui_schema()}


@dataclass
class BuildContext:
    """What a part generator may read besides the genome."""

    library: Library
    defaults: dict[str, Any]
    geometry_overrides: dict[str, Override] = field(default_factory=dict)


class PartGenerator(Plugin):
    """Genome -> element parameters -> RobotSpec (two stages, ADR-007)."""

    plugin_type = "part_generator"
    genome_definition: ClassVar[str] = ""

    def element_params(self, genes: dict[str, GeneValue]) -> ElementParams:
        """Per-element parametric values, each naming the gene that drives it."""
        raise NotImplementedError

    def build(
        self, genes: dict[str, GeneValue], params: ElementParams, ctx: BuildContext
    ) -> RobotSpec:
        """Build the explicit spec from (possibly overridden) element parameters."""
        raise NotImplementedError

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"genome_definition": cls.genome_definition}


class JointType(Plugin):
    """How a joint kind maps to simulator joints."""

    plugin_type = "joint_type"
    dof: ClassVar[int] = 1
    mjcf_type: ClassVar[str | None] = "hinge"  # None = welded (no MJCF joint)

    def mjcf_attrs(self, joint: Joint) -> dict[str, str]:
        """Extra MJCF attributes for this joint (SI units, strings)."""
        return {}

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"dof": cls.dof, "mjcf_type": cls.mjcf_type}


class ComponentProvider(Plugin):
    """Adds entries to the component library from code (prefer YAML)."""

    plugin_type = "component"

    def components(self) -> list[Component]:
        raise NotImplementedError


# ============================================================ control / behavior
@dataclass
class ControlInfo:
    """Static information a controller gets at reset (SI units)."""

    actuator_ids: list[str]
    joint_ids: list[str]  # joint driven by each actuator, same order
    rest: np.ndarray  # standing-pose joint angle per actuator, rad
    lo: np.ndarray  # lower joint limit per actuator, rad
    hi: np.ndarray  # upper joint limit per actuator, rad
    control_dt: float  # s

    def index(self, joint_id: str) -> int | None:
        try:
            return self.joint_ids.index(joint_id)
        except ValueError:
            return None


@dataclass
class Observation:
    """What a controller sees each control step (SI units)."""

    t: float
    q: np.ndarray  # joint angle per actuator, rad
    dq: np.ndarray  # joint velocity per actuator, rad/s
    trunk_quat: np.ndarray  # (w, x, y, z)
    trunk_gyro: np.ndarray  # rad/s, body frame
    foot_contact: np.ndarray  # 0/1 per foot, order = spec foot geoms


@dataclass
class VectorDim:
    """One optimisable controller parameter: field name and bounds (design units)."""

    name: str
    lo: float
    hi: float


class Controller(Plugin):
    """Maps observations to target joint angles (rad, one per actuator)."""

    plugin_type = "controller"

    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        self.info = info

    def act(self, obs: Observation) -> np.ndarray:
        raise NotImplementedError

    # ---- optional: expose parameters to optimizers as a bounded vector
    @classmethod
    def vector_dims(cls) -> list[VectorDim]:
        return []

    @classmethod
    def params_from_vector(cls, base: dict[str, Any], x: np.ndarray) -> dict[str, Any]:
        """Decode a vector in [0, 1]^n into a params dict (starting from ``base``)."""
        out = dict(base)
        for d, v in zip(cls.vector_dims(), np.clip(x, 0.0, 1.0), strict=True):
            out[d.name] = d.lo + float(v) * (d.hi - d.lo)
        return out

    @classmethod
    def vector_from_params(cls, params: dict[str, Any]) -> np.ndarray:
        defaults = cls.Params().model_dump()
        vals = []
        for d in cls.vector_dims():
            v = float(params.get(d.name, defaults[d.name]))
            vals.append((v - d.lo) / ((d.hi - d.lo) or 1.0))
        return np.clip(np.array(vals, dtype=float), 0.0, 1.0)

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"vector_dims": [d.__dict__ for d in cls.vector_dims()]}


class Behavior(Plugin):
    """High-level behavior node (state-machine leaf). Phase 4 fills these in."""

    plugin_type = "behavior"

    def tick(self, t: float, sensors: dict[str, Any]) -> dict[str, Any]:
        """Return requests for the controller layer (e.g. gait, gaze target)."""
        raise NotImplementedError


# ============================================================ evaluation
class FitnessTerm(Plugin):
    """One term of a fitness preset. Returns a score where higher is better."""

    plugin_type = "fitness_term"

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        raise NotImplementedError


class BehaviorDescriptor(Plugin):
    """A measure used as a MAP-Elites archive axis."""

    plugin_type = "behavior_descriptor"
    range: ClassVar[tuple[float, float]] = (0.0, 1.0)
    unit: ClassVar[str] = ""

    def describe_candidate(
        self, spec: RobotSpec, metrics: dict[str, Any], controller_params: dict[str, Any]
    ) -> float:
        raise NotImplementedError

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"range": list(cls.range), "unit": cls.unit}


class Optimizer(Plugin):
    """Search over genomes and/or controller parameters."""

    plugin_type = "optimizer"

    def run(self, problem: Any, backend: ComputeBackend, report: Callable[..., None]) -> Any:
        raise NotImplementedError


class Simulator(Plugin):
    """Runs a rollout of a compiled design under a controller."""

    plugin_type = "simulator"

    def rollout(self, spec: RobotSpec, controller: Controller, settings: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


# ============================================================ compute
@dataclass
class Task:
    """A unit of work: an importable function ``module:function`` + JSON payload (ADR-013)."""

    fn: str
    payload: dict[str, Any]
    id: str = ""


class ComputeBackend(Plugin):
    """Where tasks run. ``map`` blocks until all tasks finish or are cancelled."""

    plugin_type = "compute_backend"

    def available(self) -> tuple[bool, str]:
        """(usable right now, human-readable reason)."""
        return True, "ok"

    def map(
        self,
        tasks: list[Task],
        on_result: Callable[[int, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Any]:
        raise NotImplementedError

    def shutdown(self) -> None:  # noqa: B027 - optional hook
        """Release workers."""


# ============================================================ output
@dataclass
class ExportContext:
    """Everything an exporter may need."""

    spec: RobotSpec
    genes: dict[str, Any]
    element_params: ElementParams
    library: Library
    project_dir: Path | None = None
    selection: list[str] = field(default_factory=list)
    design_name: str = "design"
    run: dict[str, Any] | None = None  # a sim run record, when the export needs one


class Exporter(Plugin):
    """Writes files for a design. Returns the paths it created."""

    plugin_type = "exporter"
    formats: ClassVar[list[str]] = []
    category: ClassVar[str] = "geometry"  # geometry | fabrication | simulation | wiring | firmware

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        raise NotImplementedError

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"formats": cls.formats, "category": cls.category}


class Analysis(Plugin):
    """Computes a JSON-able result from the current lab state."""

    plugin_type = "analysis"

    def run(self, lab: Any) -> dict[str, Any]:
        raise NotImplementedError


class Panel(Plugin):
    """A custom UI view, declared as data (no code runs in the browser).

    ``widgets`` is a list of dicts understood by the web app's generic panel
    renderer, e.g. ``{"kind": "analysis", "analysis": "mass_budget"}`` or
    ``{"kind": "markdown", "text": "..."}``.
    """

    plugin_type = "panel"
    workspace: ClassVar[str | None] = None
    widgets: ClassVar[list[dict[str, Any]]] = []

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {"workspace": cls.workspace, "widgets": cls.widgets}


class Command(Plugin):
    """A named action. Every UI action maps to a command.

    Set ``mutates = True`` for commands that edit the document: ``run`` then
    receives a private copy of the document state, edits it in place, and the
    lab logs the change for undo/redo and broadcasts it.
    """

    plugin_type = "command"
    mutates: ClassVar[bool] = False
    category: ClassVar[str] = "General"
    shortcut: ClassVar[str | None] = None
    aliases: ClassVar[list[str]] = []

    def run(self, lab: Any, state: Any) -> Any:
        raise NotImplementedError

    def title(self) -> str:
        """Text shown in the undo history."""
        return self.label or self.key

    @classmethod
    def extra(cls) -> dict[str, Any]:
        return {
            "mutates": cls.mutates,
            "category": cls.category,
            "shortcut": cls.shortcut,
            "aliases": cls.aliases,
        }


BASES: dict[str, type[Plugin]] = {
    "gene_definition": GeneDefinition,
    "part_generator": PartGenerator,
    "joint_type": JointType,
    "component": ComponentProvider,
    "controller": Controller,
    "behavior": Behavior,
    "fitness_term": FitnessTerm,
    "behavior_descriptor": BehaviorDescriptor,
    "optimizer": Optimizer,
    "simulator": Simulator,
    "compute_backend": ComputeBackend,
    "exporter": Exporter,
    "analysis": Analysis,
    "panel": Panel,
    "command": Command,
}
