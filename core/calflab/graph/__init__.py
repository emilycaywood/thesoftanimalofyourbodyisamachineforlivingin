"""Dataflow graph engine."""

from typing import Any

from calflab.graph.engine import Cache, Evaluator, NodeResult, summarize
from calflab.graph.model import Graph, GraphEdge, GraphGroup, GraphNode
from calflab.graph.nodes import SOCKET_TYPES, EvalContext, NodeType, Socket, node_types

__all__ = [
    "SOCKET_TYPES",
    "Cache",
    "EvalContext",
    "Evaluator",
    "Graph",
    "GraphEdge",
    "GraphGroup",
    "GraphNode",
    "NodeResult",
    "NodeType",
    "Socket",
    "default_graph",
    "node_types",
    "summarize",
]


def default_graph(sim_defaults: dict[str, Any] | None = None) -> Graph:
    """The standard pipeline: genome -> morphology -> MJCF -> sim -> metrics -> fitness."""
    types = node_types()

    def node(nid: str, ntype: str, x: float, y: float, **params: Any) -> GraphNode:
        p = types[ntype].default_params()
        p.update(params)
        return GraphNode(id=nid, type=ntype, params=p, pos=(x, y))

    mjcf_params = {
        k: v for k, v in (sim_defaults or {}).items() if k in types["mjcf"].default_params()
    }
    nodes = [
        node("genome", "genome:calf", 0, 0),
        node("morphology", "part_generator:calf", 320, 0),
        node("mjcf", "mjcf", 640, 0, **mjcf_params),
        node("controller", "controller:cpg", 640, 260),
        node("sim", "simulator:mujoco", 960, 80),
        node("metrics", "metrics", 1280, 80),
        node("fitness", "fitness", 1560, 80),
        node("mass", "mass_report", 640, -200),
    ]

    def edge(src: str, s_out: str, dst: str, s_in: str) -> GraphEdge:
        return GraphEdge(id=f"{src}.{s_out}->{dst}.{s_in}", source=src, source_socket=s_out, target=dst, target_socket=s_in)

    edges = [
        edge("genome", "genome", "morphology", "genome"),
        edge("morphology", "design", "mjcf", "design"),
        edge("morphology", "design", "mass", "design"),
        edge("mjcf", "model", "sim", "model"),
        edge("controller", "controller", "sim", "controller"),
        edge("sim", "rollout", "metrics", "rollout"),
        edge("metrics", "metrics", "fitness", "metrics"),
    ]
    groups = [
        GraphGroup(id="g_form", label="Form", color="#3d6b4f", nodes=["genome", "morphology", "mass"]),
        GraphGroup(id="g_sim", label="Simulation", color="#6b4f3d", nodes=["mjcf", "controller", "sim"]),
        GraphGroup(id="g_eval", label="Evaluation", color="#4f3d6b", nodes=["metrics", "fitness"]),
    ]
    roles = {
        "genome": "genome",
        "design": "morphology",
        "model": "mjcf",
        "controller": "controller",
        "simulation": "sim",
        "metrics": "metrics",
        "fitness": "fitness",
    }
    return Graph(nodes=nodes, edges=edges, groups=groups, roles=roles)
