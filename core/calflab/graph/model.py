"""Serializable graph model: nodes, edges, groups."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    pos: tuple[float, float] = (0.0, 0.0)
    enabled: bool = True
    preview: bool = True
    label: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    source_socket: str
    target: str
    target_socket: str


class GraphGroup(BaseModel):
    id: str
    label: str = "Group"
    color: str = "#5b6b8a"
    nodes: list[str] = Field(default_factory=list)


class Graph(BaseModel):
    """A directed acyclic graph of typed nodes.

    ``roles`` names the nodes the lab treats as the design pipeline
    (``genome``, ``design``, ``model``, ``controller``, ``simulation``,
    ``metrics``, ``fitness``), so the viewport and commands know which node
    produces "the" robot.
    """

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    groups: list[GraphGroup] = Field(default_factory=list)
    roles: dict[str, str] = Field(default_factory=dict)

    def node(self, node_id: str) -> GraphNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"No node {node_id!r} in the graph")

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    def role(self, role: str) -> GraphNode:
        nid = self.roles.get(role)
        if nid is None or not self.has_node(nid):
            raise KeyError(
                f"The graph has no node with the {role!r} role. "
                "Re-create it or run the ResetGraph command."
            )
        return self.node(nid)

    def incoming(self, node_id: str) -> dict[str, GraphEdge]:
        """Edges into ``node_id`` keyed by target socket (one edge per input)."""
        return {e.target_socket: e for e in self.edges if e.target == node_id}

    def topo_order(self) -> list[str]:
        """Node ids in dependency order. Raises ``ValueError`` on a cycle."""
        ids = [n.id for n in self.nodes]
        indeg = {i: 0 for i in ids}
        out: dict[str, list[str]] = {i: [] for i in ids}
        for e in self.edges:
            if e.source in indeg and e.target in indeg:
                indeg[e.target] += 1
                out[e.source].append(e.target)
        queue = [i for i in ids if indeg[i] == 0]
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for m in out[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        if len(order) != len(ids):
            raise ValueError("The graph has a cycle")
        return order

    def ancestors(self, node_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            n = stack.pop()
            for e in self.edges:
                if e.target == n and e.source not in seen:
                    seen.add(e.source)
                    stack.append(e.source)
        return seen

    def new_id(self, prefix: str) -> str:
        base = prefix.split(":")[-1].replace(".", "_")
        existing = {n.id for n in self.nodes} | {e.id for e in self.edges} | {g.id for g in self.groups}
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"
