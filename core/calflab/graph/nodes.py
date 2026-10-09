"""Node types.

Most node types are generated from plugins: every gene definition, part
generator, controller, simulator, fitness term and exporter is automatically a
node whose parameter panel comes from the plugin's schema. A handful of core
nodes (MJCF compile, metrics, fitness preset, numbers, clusters) are defined
here. ``node_types()`` rebuilds the table on demand so hot-reloaded plugins
appear without a restart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from calflab import CODE_VERSION
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.plugins import ExportContext, load_plugins, registry
from calflab.schema import P, dynamic_schema, ui_schema

#: socket data types and their wire colours (Grasshopper-style type colouring)
SOCKET_TYPES: dict[str, str] = {
    "genome": "#8bc34a",
    "design": "#4fc3f7",
    "model": "#ffb74d",
    "controller": "#ba68c8",
    "rollout": "#f06292",
    "metrics": "#4db6ac",
    "fitness": "#ffd54f",
    "number": "#b0bec5",
    "files": "#a1887f",
    "any": "#90a4ae",
}


@dataclass
class Socket:
    name: str
    type: str
    label: str = ""
    required: bool = True


@dataclass
class EvalContext:
    """What node evaluation may read besides its inputs."""

    overrides: list[Override] = field(default_factory=list)
    project_dir: Path | None = None
    on_frames: Callable[[dict[str, Any]], None] | None = None
    cancelled: Callable[[], bool] | None = None
    cluster_inputs: dict[str, Any] = field(default_factory=dict)
    cluster_input_hashes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


class NodeType:
    """Behaviour of one kind of node."""

    type: str = ""
    label: str = ""
    category: str = "Core"
    description: str = ""
    inputs: list[Socket] = []
    outputs: list[Socket] = []
    expensive: bool = False  # runs as a job, never implicitly
    version: str = "1"

    def schema(self) -> dict[str, Any]:
        return dynamic_schema(self.label, [])

    def default_params(self) -> dict[str, Any]:
        return {f["name"]: f["default"] for f in self.schema()["fields"]}

    def clean_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate/normalise params (raise ``ValueError`` if invalid)."""
        return params

    def inputs_for(self, params: dict[str, Any]) -> list[Socket]:
        return self.inputs

    def outputs_for(self, params: dict[str, Any]) -> list[Socket]:
        return self.outputs

    def salt(self, params: dict[str, Any], ctx: EvalContext) -> str:
        """Extra cache-key material read from the context (e.g. overrides)."""
        return ""

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "inputs": [s.__dict__ for s in self.inputs],
            "outputs": [s.__dict__ for s in self.outputs],
            "expensive": self.expensive,
            "schema": self.schema(),
            "defaults": self.default_params(),
        }


class _ModelParamsNode(NodeType):
    """Node whose params are a Pydantic model."""

    params_model: type[BaseModel]

    def schema(self) -> dict[str, Any]:
        return ui_schema(self.params_model)

    def default_params(self) -> dict[str, Any]:
        return self.params_model().model_dump(mode="json")

    def clean_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.params_model.model_validate(params).model_dump(mode="json")


# ====================================================================== plugin-backed
class GenomeNode(NodeType):
    category = "Genome"
    outputs = [Socket("genome", "genome", "Genome")]

    def __init__(self, key: str):
        self.key = key
        self.type = f"genome:{key}"
        cls = registry.get("gene_definition", key)
        self._definition = cls().definition()  # type: ignore[attr-defined]
        self.label = f"Genome: {key}"
        self.description = self._definition.description.strip()
        self.version = str(self._definition.version)

    @property
    def definition(self) -> Any:
        """The gene definition behind this node."""
        return self._definition

    def schema(self) -> dict[str, Any]:
        return self._definition.ui_schema()

    def default_params(self) -> dict[str, Any]:
        return self._definition.defaults()

    def clean_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._definition.complete(params)

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        d = self._definition
        return {"genome": Genome(definition=d.name, version=d.version, values=d.complete(params))}


class _PluginNode(NodeType):
    plugin_type = ""

    def __init__(self, key: str):
        self.key = key
        self.cls = registry.get(self.plugin_type, key)
        self.type = f"{self.plugin_type}:{key}"
        self.label = self.cls.label or key
        self.description = self.cls.description
        self.version = self.cls.version

    def schema(self) -> dict[str, Any]:
        return self.cls.params_schema()

    def default_params(self) -> dict[str, Any]:
        return self.cls.Params().model_dump(mode="json")

    def clean_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.cls.Params.model_validate(params).model_dump(mode="json")


class PartGeneratorNode(_PluginNode):
    plugin_type = "part_generator"
    category = "Morphology"
    inputs = [Socket("genome", "genome", "Genome")]
    outputs = [Socket("design", "design", "Design")]

    def salt(self, params: dict[str, Any], ctx: EvalContext) -> str:
        from calflab.components.library import _stamp
        from calflab.paths import config_dir

        ov = [o.model_dump(mode="json") for o in ctx.overrides if o.enabled]
        stamp = _stamp(config_dir() / "components")
        defaults = (config_dir() / "robot_defaults.yaml").stat().st_mtime
        return repr((ov, stamp, defaults))

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.design import build_design

        design = build_design(inputs["genome"], ctx.overrides, self.key, params)
        for w in design.warnings:
            ctx.warn(w)
        return {"design": design}


class ControllerNode(_PluginNode):
    plugin_type = "controller"
    category = "Control"
    outputs = [Socket("controller", "controller", "Controller")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        return {"controller": {"key": self.key, "params": params}}


class SimulatorNode(_PluginNode):
    plugin_type = "simulator"
    category = "Simulation"
    inputs = [Socket("model", "model", "Model"), Socket("controller", "controller", "Controller")]
    outputs = [Socket("rollout", "rollout", "Rollout")]
    expensive = True

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.sim.rollout import SimSettings

        sim = self.cls(params)
        c = inputs["controller"]
        controller = registry.get("controller", c["key"])(c["params"])
        rollout = sim.rollout(  # type: ignore[attr-defined]
            inputs["model"],
            controller,
            SimSettings.model_validate(params),
            on_frames=ctx.on_frames,
            cancelled=ctx.cancelled,
        )
        return {"rollout": rollout}


class FitnessTermNode(_PluginNode):
    plugin_type = "fitness_term"
    category = "Fitness"
    inputs = [Socket("metrics", "metrics", "Metrics")]
    outputs = [Socket("score", "number", "Score")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        return {"score": float(self.cls(params).evaluate(inputs["metrics"], {}))}  # type: ignore[attr-defined]


class ExporterNode(_PluginNode):
    plugin_type = "exporter"
    category = "Export"
    inputs = [Socket("design", "design", "Design")]
    outputs = [Socket("files", "files", "Files")]
    expensive = True

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.components import library

        d = inputs["design"]
        ectx = ExportContext(
            spec=d.spec,
            genes=d.genome.values,
            element_params=d.element_params,
            library=library(),
            project_dir=ctx.project_dir,
        )
        out_dir = (ctx.project_dir or Path.cwd()) / "exports" / "graph"
        paths = self.cls(params).export(ectx, out_dir)  # type: ignore[attr-defined]
        return {"files": [str(p) for p in paths]}


# ====================================================================== core nodes
class MjcfNode(_ModelParamsNode):
    type = "mjcf"
    label = "MJCF compile"
    category = "Simulation"
    description = "Compile the design into a MuJoCo model (SI units), with skin model and randomization."
    inputs = [Socket("design", "design", "Design")]
    outputs = [Socket("model", "model", "Model")]

    def __init__(self) -> None:
        from calflab.sim.mjcf import CompileOptions

        self.params_model = CompileOptions

    def salt(self, params: dict[str, Any], ctx: EvalContext) -> str:
        from calflab.components.library import _stamp
        from calflab.paths import config_dir

        return repr(_stamp(config_dir() / "components"))

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.components import library
        from calflab.sim.mjcf import CompileOptions, compile_mjcf

        return {"model": compile_mjcf(inputs["design"].spec, library(), CompileOptions.model_validate(params))}


class MetricsNode(NodeType):
    type = "metrics"
    label = "Metrics"
    category = "Simulation"
    description = "Speed, cost of transport, stability, torque, thermal, impact, joint-limit metrics."
    inputs = [Socket("rollout", "rollout", "Rollout")]
    outputs = [Socket("metrics", "metrics", "Metrics")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.sim.metrics import compute_metrics

        return {"metrics": compute_metrics(inputs["rollout"])}


class FitnessNode(NodeType):
    type = "fitness"
    label = "Fitness preset"
    category = "Fitness"
    description = "Weighted sum of fitness terms from a named, versioned preset."
    inputs = [Socket("metrics", "metrics", "Metrics")]
    outputs = [Socket("fitness", "fitness", "Fitness"), Socket("total", "number", "Total")]

    def schema(self) -> dict[str, Any]:
        from calflab.fitness import presets

        names = sorted(presets())
        return dynamic_schema(
            self.label,
            [
                {
                    "name": "preset",
                    "type": "enum",
                    "choices": names,
                    "default": "walk" if "walk" in names else (names[0] if names else ""),
                    "description": "Fitness preset (config/fitness/*.yaml).",
                }
            ],
        )

    def salt(self, params: dict[str, Any], ctx: EvalContext) -> str:
        from calflab.fitness import presets

        p = presets().get(str(params.get("preset")))
        return p.model_dump_json() if p else ""

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.fitness import preset

        result = preset(str(params.get("preset"))).evaluate(inputs["metrics"])
        return {"fitness": result, "total": result["total"]}


class MassReportNode(NodeType):
    type = "mass_report"
    label = "Mass report"
    category = "Analysis"
    description = "Total mass, mass by layer and centre of mass of the design."
    inputs = [Socket("design", "design", "Design")]
    outputs = [Socket("mass", "number", "Mass (g)"), Socket("report", "any", "Report")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        spec = inputs["design"].spec
        report = {
            "total_g": spec.total_mass_g(),
            "by_layer_g": spec.mass_by_layer(),
            "com_mm": list(spec.center_of_mass()),
        }
        return {"mass": report["total_g"], "report": report}


class _NumberParams(BaseModel):
    value: float = P(0.0, ui="number", desc="The number.")


class NumberNode(_ModelParamsNode):
    type = "number"
    label = "Number"
    category = "Input"
    description = "A constant number."
    outputs = [Socket("value", "number", "Value")]
    params_model = _NumberParams

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        return {"value": float(params.get("value", 0.0))}


class _SliderParams(BaseModel):
    value: float = P(0.5, ui="number", desc="Current value.")
    min: float = P(0.0, ui="number", desc="Lower bound.")
    max: float = P(1.0, ui="number", desc="Upper bound.")


class SliderNode(_ModelParamsNode):
    type = "slider"
    label = "Number slider"
    category = "Input"
    description = "A number with bounds, like a Grasshopper slider."
    outputs = [Socket("value", "number", "Value")]
    params_model = _SliderParams

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        lo, hi = float(params.get("min", 0.0)), float(params.get("max", 1.0))
        return {"value": min(max(float(params.get("value", lo)), lo), hi)}


class _GeneSetParams(BaseModel):
    gene: str = P("trunk_length", desc="Gene id to drive.")


class GeneSetNode(_ModelParamsNode):
    type = "gene_set"
    label = "Set gene"
    category = "Genome"
    description = "Drive one gene of a genome from a number (wire a slider or an expression into a gene)."
    inputs = [Socket("genome", "genome", "Genome"), Socket("value", "number", "Value")]
    outputs = [Socket("genome", "genome", "Genome")]
    params_model = _GeneSetParams

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        from calflab.design import genome_definition

        g: Genome = inputs["genome"]
        d = genome_definition(g.definition)
        gene = str(params.get("gene"))
        if not d.has(gene):
            raise ValueError(f"Genome {g.definition!r} has no gene {gene!r}")
        values = dict(g.values)
        values[gene] = d.gene(gene).coerce(inputs["value"])
        return {"genome": Genome(definition=g.definition, version=g.version, values=values)}


class PanelNode(NodeType):
    type = "panel"
    label = "Panel"
    category = "Input"
    description = "Shows whatever is wired into it and passes it through."
    inputs = [Socket("in", "any", "In")]
    outputs = [Socket("out", "any", "Out")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        return {"out": inputs["in"]}


class ClusterInputNode(NodeType):
    type = "cluster_input"
    label = "Cluster input"
    category = "Cluster"
    description = "An exposed input of a cluster."
    outputs = [Socket("value", "any", "Value")]

    def schema(self) -> dict[str, Any]:
        return dynamic_schema(
            self.label,
            [
                {"name": "name", "type": "string", "default": "in", "description": "Socket name on the cluster."},
                {"name": "type", "type": "enum", "choices": sorted(SOCKET_TYPES), "default": "any",
                 "description": "Data type of the socket."},
            ],
        )

    def outputs_for(self, params: dict[str, Any]) -> list[Socket]:
        return [Socket("value", str(params.get("type", "any")), "Value")]

    def salt(self, params: dict[str, Any], ctx: EvalContext) -> str:
        return ctx.cluster_input_hashes.get(str(params.get("name")), "")

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        name = str(params.get("name"))
        if name not in ctx.cluster_inputs:
            raise ValueError(f"Cluster input {name!r} is not connected")
        return {"value": ctx.cluster_inputs[name]}


class ClusterOutputNode(NodeType):
    type = "cluster_output"
    label = "Cluster output"
    category = "Cluster"
    description = "An exposed output of a cluster."
    outputs = [Socket("value", "any", "Value")]

    def schema(self) -> dict[str, Any]:
        return dynamic_schema(
            self.label,
            [
                {"name": "name", "type": "string", "default": "out", "description": "Socket name on the cluster."},
                {"name": "type", "type": "enum", "choices": sorted(SOCKET_TYPES), "default": "any",
                 "description": "Data type of the socket."},
            ],
        )

    def inputs_for(self, params: dict[str, Any]) -> list[Socket]:
        return [Socket("value", str(params.get("type", "any")), "Value")]

    def outputs_for(self, params: dict[str, Any]) -> list[Socket]:
        return [Socket("value", str(params.get("type", "any")), "Value")]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        return {"value": inputs["value"]}


class ClusterNode(NodeType):
    """A reusable subgraph. ``params['graph']`` is a Graph dump whose
    ``cluster_input`` / ``cluster_output`` nodes define the sockets."""

    type = "cluster"
    label = "Cluster"
    category = "Cluster"
    description = "A subgraph with exposed inputs and outputs."

    def schema(self) -> dict[str, Any]:
        return dynamic_schema(
            self.label,
            [{"name": "graph", "type": "object", "ui": "json", "default": {"nodes": [], "edges": []},
              "description": "The cluster's inner graph."}],
        )

    def _inner(self, params: dict[str, Any]) -> Any:
        from calflab.graph.model import Graph

        return Graph.model_validate(params.get("graph") or {})

    def inputs_for(self, params: dict[str, Any]) -> list[Socket]:
        g = self._inner(params)
        return [
            Socket(str(n.params.get("name", n.id)), str(n.params.get("type", "any")), n.label or "")
            for n in g.nodes
            if n.type == "cluster_input"
        ]

    def outputs_for(self, params: dict[str, Any]) -> list[Socket]:
        g = self._inner(params)
        return [
            Socket(str(n.params.get("name", n.id)), str(n.params.get("type", "any")), n.label or "")
            for n in g.nodes
            if n.type == "cluster_output"
        ]

    def evaluate(self, params: dict[str, Any], inputs: dict[str, Any], ctx: EvalContext) -> dict[str, Any]:
        raise RuntimeError("clusters are evaluated by the engine")  # pragma: no cover


CORE_NODES: list[type[NodeType]] = [
    MjcfNode,
    MetricsNode,
    FitnessNode,
    MassReportNode,
    NumberNode,
    SliderNode,
    GeneSetNode,
    PanelNode,
    ClusterInputNode,
    ClusterOutputNode,
    ClusterNode,
]

_PLUGIN_NODES: list[tuple[str, Callable[[str], NodeType]]] = [
    ("gene_definition", GenomeNode),
    ("part_generator", PartGeneratorNode),
    ("controller", ControllerNode),
    ("simulator", SimulatorNode),
    ("fitness_term", FitnessTermNode),
    ("exporter", ExporterNode),
]


def node_types() -> dict[str, NodeType]:
    """All node types currently available (core + one per relevant plugin)."""
    load_plugins()
    out: dict[str, NodeType] = {}
    for cls in CORE_NODES:
        nt = cls()
        out[nt.type] = nt
    for ptype, factory in _PLUGIN_NODES:
        for key, pcls in registry.all(ptype).items():
            if pcls.stub:
                continue
            try:
                nt = factory(key)
                out[nt.type] = nt
            except Exception:  # a broken plugin must not hide the others
                continue
    return out


def node_code_version(nt: NodeType) -> str:
    return f"{CODE_VERSION}.{nt.version}"
