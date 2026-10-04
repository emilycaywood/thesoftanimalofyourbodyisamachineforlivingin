"""Built-in commands. Every UI action that changes the document or starts
work is one of these, so the command line, menus, shortcuts, Rhino, Blender,
the CLI and notebooks all do the same thing.

Mutating commands receive a private copy of the document state and edit it in
place; the lab logs the difference for undo/redo.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from calflab.graph import Graph, GraphEdge, GraphGroup, GraphNode, default_graph, node_types
from calflab.model.overrides import Override
from calflab.plugins import Command, register
from calflab.project.store import DocumentState, ReferenceImage, now_iso
from calflab.schema import P


def _err(msg: str) -> Exception:
    from calflab.app.lab import LabError

    return LabError(msg)


# ====================================================================== genome
@register
class SetGenes(Command):
    key = "set_genes"
    label = "Set genes"
    description = "Change one or more genome values."
    category = "Form"
    mutates = True

    class Params(BaseModel):
        values: dict[str, Any] = P(default_factory=dict, ui="json", desc="Gene id -> new value.")

    def coalesce_key(self) -> str:
        return "genes:" + ",".join(sorted(self.params.values))  # type: ignore[attr-defined]

    def title(self) -> str:
        v = self.params.values  # type: ignore[attr-defined]
        return "Set " + ", ".join(v) if len(v) <= 3 else f"Set {len(v)} genes"

    def run(self, lab: Any, state: DocumentState) -> Any:
        node = state.graph.role("genome")
        nt = node_types()[node.type]
        merged = {**node.params, **self.params.values}  # type: ignore[attr-defined]
        try:
            node.params = nt.clean_params(merged)
        except Exception as exc:
            raise _err(f"Invalid gene value: {exc}") from exc
        return {"genes": {k: node.params[k] for k in self.params.values if k in node.params}}  # type: ignore[attr-defined]


@register
class ResetGenes(Command):
    key = "reset_genes"
    label = "Reset genome to defaults"
    description = "Restore every gene to its default value."
    category = "Form"
    mutates = True

    def run(self, lab: Any, state: DocumentState) -> Any:
        node = state.graph.role("genome")
        node.params = node_types()[node.type].default_params()
        return {}


# ====================================================================== overrides
@register
class AddOverride(Command):
    key = "add_override"
    label = "Override parameter"
    description = "Explicitly set one parameter of one element (e.g. from a gumball drag)."
    category = "Form"
    mutates = True

    class Params(BaseModel):
        target: str = P("", desc="Element id, e.g. leg.fl.shank.")
        param: str = P("", desc="Element parameter, e.g. length.")
        value: float = P(0.0, ui="number", desc="New value in the parameter's unit.")
        name: str = P("", desc="Name of the override record (auto-generated if empty).")
        bound: bool = P(False, desc="Drive the gene behind the parameter instead of creating an override.")
        source: str = P("web", desc="Client that made the edit.")

    def coalesce_key(self) -> str:
        p = self.params
        return f"override:{p.target}.{p.param}:{p.bound}"  # type: ignore[attr-defined]

    def title(self) -> str:
        p = self.params
        return f"{'Drive' if p.bound else 'Override'} {p.target}.{p.param} = {p.value:g}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        design = lab.design(state.graph)
        table = design.element_params.get(p.target)  # type: ignore[attr-defined]
        if table is None or p.param not in table:  # type: ignore[attr-defined]
            raise _err(f"{p.target} has no parameter {p.param!r}")  # type: ignore[attr-defined]
        pv = table[p.param]  # type: ignore[attr-defined]
        if p.bound:  # type: ignore[attr-defined]
            if not pv.gene:
                raise _err(f"{p.target}.{p.param} is not driven by a gene")  # type: ignore[attr-defined]
            node = state.graph.role("genome")
            nt = node_types()[node.type]
            node.params = nt.clean_params({**node.params, pv.gene: pv.gene_value_for(p.value)})  # type: ignore[attr-defined]
            return {"gene": pv.gene, "value": node.params[pv.gene]}
        for ov in state.overrides:
            if ov.kind == "param" and ov.target == p.target and ov.param == p.param:  # type: ignore[attr-defined]
                ov.value = p.value  # type: ignore[attr-defined]
                ov.enabled = True
                return {"override": ov.id, "updated": True}
        ov = Override(
            id=f"ov-{uuid.uuid4().hex[:8]}",
            name=p.name or f"{p.target} {p.param}",  # type: ignore[attr-defined]
            target=p.target,  # type: ignore[attr-defined]
            param=p.param,  # type: ignore[attr-defined]
            value=p.value,  # type: ignore[attr-defined]
            source=p.source,  # type: ignore[attr-defined]
            created=now_iso(),
        )
        state.overrides.append(ov)
        return {"override": ov.id, "updated": False}


@register
class AddGeometryOverride(Command):
    key = "add_geometry_override"
    label = "Override geometry"
    description = "Replace an element's surface with sculpted geometry (e.g. pushed from Rhino)."
    category = "Form"
    mutates = True

    class Params(BaseModel):
        target: str = P("", desc="Body id whose surface is replaced.")
        asset: str = P("", desc="Project-relative mesh file under assets/.")
        name: str = P("", desc="Name of the override record.")
        layer: str = P("Skin", desc="Layer whose geometry is replaced.")
        source: str = P("rhino", desc="Client that made the edit.")

    def title(self) -> str:
        return f"Geometry override on {self.params.target}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        if not p.target or not p.asset:  # type: ignore[attr-defined]
            raise _err("target and asset are required")
        state.overrides = [
            o for o in state.overrides
            if not (o.kind == "geometry" and o.target == p.target and o.meta.get("layer", "Skin") == p.layer)  # type: ignore[attr-defined]
        ]
        ov = Override(
            id=f"ov-{uuid.uuid4().hex[:8]}",
            name=p.name or f"{p.target} sculpt",  # type: ignore[attr-defined]
            target=p.target,  # type: ignore[attr-defined]
            kind="geometry",
            asset=p.asset,  # type: ignore[attr-defined]
            source=p.source,  # type: ignore[attr-defined]
            created=now_iso(),
            meta={"layer": p.layer},  # type: ignore[attr-defined]
        )
        state.overrides.append(ov)
        return {"override": ov.id}


def _find_override(state: DocumentState, oid: str) -> Override:
    for o in state.overrides:
        if o.id == oid:
            return o
    raise _err(f"No override {oid!r}")


class _OverrideId(BaseModel):
    id: str = P("", desc="Override id.")


@register
class RemoveOverride(Command):
    key = "remove_override"
    label = "Remove override"
    description = "Delete an override; the element returns to its parametric value."
    category = "Form"
    mutates = True
    Params = _OverrideId

    def run(self, lab: Any, state: DocumentState) -> Any:
        ov = _find_override(state, self.params.id)  # type: ignore[attr-defined]
        state.overrides.remove(ov)
        return {"removed": ov.id}


@register
class ToggleOverride(Command):
    key = "toggle_override"
    label = "Toggle override"
    description = "Enable or disable an override without deleting it."
    category = "Form"
    mutates = True

    class Params(BaseModel):
        id: str = P("", desc="Override id.")
        enabled: bool | None = P(None, desc="New state (omit to flip).")

    def run(self, lab: Any, state: DocumentState) -> Any:
        ov = _find_override(state, self.params.id)  # type: ignore[attr-defined]
        e = self.params.enabled  # type: ignore[attr-defined]
        ov.enabled = (not ov.enabled) if e is None else e
        return {"id": ov.id, "enabled": ov.enabled}


@register
class InternalizeOverride(Command):
    key = "internalize_override"
    label = "Internalize override"
    description = "Write the override's value into the gene that drives the parameter, then remove it."
    category = "Form"
    mutates = True
    Params = _OverrideId

    def run(self, lab: Any, state: DocumentState) -> Any:
        ov = _find_override(state, self.params.id)  # type: ignore[attr-defined]
        if ov.kind != "param" or ov.param is None or ov.value is None:
            raise _err("Only parameter overrides can be internalized")
        design = lab.design(state.graph)
        pv = design.element_params.get(ov.target, {}).get(ov.param)
        if pv is None or not pv.gene:
            raise _err(f"{ov.target}.{ov.param} is not driven by a gene, so it cannot be internalized")
        node = state.graph.role("genome")
        nt = node_types()[node.type]
        node.params = nt.clean_params({**node.params, pv.gene: pv.gene_value_for(ov.value)})
        state.overrides.remove(ov)
        return {"gene": pv.gene, "value": node.params[pv.gene]}


@register
class ClearOverrides(Command):
    key = "clear_overrides"
    label = "Remove all overrides"
    description = "Delete every override."
    category = "Form"
    mutates = True

    def run(self, lab: Any, state: DocumentState) -> Any:
        n = len(state.overrides)
        state.overrides = []
        return {"removed": n}


# ====================================================================== graph
@register
class SetNodeParams(Command):
    key = "set_node_params"
    label = "Set node parameters"
    description = "Change parameters of a graph node."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        node: str = P("", desc="Node id.")
        params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Parameter name -> value (partial).")

    def coalesce_key(self) -> str:
        p = self.params
        return f"node:{p.node}:" + ",".join(sorted(p.params))  # type: ignore[attr-defined]

    def title(self) -> str:
        p = self.params
        return f"Set {p.node}: " + ", ".join(p.params)  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        try:
            node = state.graph.node(p.node)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise _err(str(exc)) from exc
        nt = node_types().get(node.type)
        merged = {**node.params, **p.params}  # type: ignore[attr-defined]
        try:
            node.params = nt.clean_params(merged) if nt else merged
        except Exception as exc:
            raise _err(f"Invalid parameters for {node.id}: {exc}") from exc
        return {"node": node.id, "params": node.params}


@register
class ResetNodeParams(Command):
    key = "reset_node_params"
    label = "Reset node to defaults"
    description = "Restore every parameter of a graph node (e.g. the gait controller) to its default value."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        node: str = P("", desc="Node id, or a pipeline role such as controller.")

    def title(self) -> str:
        return f"Reset {self.params.node} to defaults"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        ref = self.params.node  # type: ignore[attr-defined]
        try:
            node = state.graph.node(state.graph.roles.get(ref, ref))
        except KeyError as exc:
            raise _err(f"No node or pipeline role {ref!r}") from exc
        nt = node_types().get(node.type)
        if nt is None:
            raise _err(f"Node {node.id} has an unknown type {node.type!r}")
        node.params = nt.default_params()
        return {"node": node.id, "params": node.params}


@register
class AddNode(Command):
    key = "add_node"
    label = "Add node"
    description = "Add a node to the graph."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        type: str = P("", desc="Node type, e.g. slider or controller:cpg.")
        x: float = P(0.0, ui="number", desc="Canvas X.")
        y: float = P(0.0, ui="number", desc="Canvas Y.")
        params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Initial parameters.")
        id: str = P("", desc="Node id (auto-generated if empty).")

    def title(self) -> str:
        return f"Add node {self.params.type}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        nt = node_types().get(p.type)  # type: ignore[attr-defined]
        if nt is None:
            raise _err(f"Unknown node type {p.type!r}")  # type: ignore[attr-defined]
        nid = p.id or state.graph.new_id(p.type)  # type: ignore[attr-defined]
        if state.graph.has_node(nid):
            raise _err(f"Node id {nid!r} already exists")
        params = nt.clean_params({**nt.default_params(), **p.params})  # type: ignore[attr-defined]
        state.graph.nodes.append(GraphNode(id=nid, type=p.type, params=params, pos=(p.x, p.y)))  # type: ignore[attr-defined]
        return {"node": nid}


@register
class RemoveNodes(Command):
    key = "remove_nodes"
    label = "Delete nodes"
    description = "Delete nodes and their wires."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        ids: list[str] = P(default_factory=list, ui="json", desc="Node ids.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        ids = set(self.params.ids)  # type: ignore[attr-defined]
        g = state.graph
        g.nodes = [n for n in g.nodes if n.id not in ids]
        g.edges = [e for e in g.edges if e.source not in ids and e.target not in ids]
        for grp in g.groups:
            grp.nodes = [n for n in grp.nodes if n not in ids]
        g.groups = [grp for grp in g.groups if grp.nodes]
        g.roles = {r: n for r, n in g.roles.items() if n not in ids}
        return {"removed": sorted(ids)}


@register
class MoveNodes(Command):
    key = "move_nodes"
    label = "Move nodes"
    description = "Reposition nodes on the canvas."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        positions: dict[str, tuple[float, float]] = P(default_factory=dict, ui="json", desc="Node id -> (x, y).")

    def coalesce_key(self) -> str:
        return "move:" + ",".join(sorted(self.params.positions))  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        for nid, pos in self.params.positions.items():  # type: ignore[attr-defined]
            if state.graph.has_node(nid):
                state.graph.node(nid).pos = (float(pos[0]), float(pos[1]))
        return {}


@register
class Connect(Command):
    key = "connect"
    label = "Connect"
    description = "Wire an output socket to an input socket (replaces any wire already on that input)."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        source: str = P("", desc="Source node id.")
        source_socket: str = P("", desc="Output socket name.")
        target: str = P("", desc="Target node id.")
        target_socket: str = P("", desc="Input socket name.")

    def title(self) -> str:
        p = self.params
        return f"Connect {p.source}.{p.source_socket} -> {p.target}.{p.target_socket}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        g = state.graph
        types = node_types()
        try:
            src, dst = g.node(p.source), g.node(p.target)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise _err(str(exc)) from exc
        s_out = {s.name: s for s in types[src.type].outputs_for(src.params)}.get(p.source_socket)  # type: ignore[attr-defined]
        s_in = {s.name: s for s in types[dst.type].inputs_for(dst.params)}.get(p.target_socket)  # type: ignore[attr-defined]
        if s_out is None or s_in is None:
            raise _err("No such socket")
        if "any" not in (s_out.type, s_in.type) and s_out.type != s_in.type:
            raise _err(f"Cannot connect {s_out.type} to {s_in.type}")
        g.edges = [e for e in g.edges if not (e.target == dst.id and e.target_socket == s_in.name)]
        edge = GraphEdge(
            id=f"{src.id}.{s_out.name}->{dst.id}.{s_in.name}",
            source=src.id,
            source_socket=s_out.name,
            target=dst.id,
            target_socket=s_in.name,
        )
        g.edges.append(edge)
        try:
            g.topo_order()
        except ValueError as exc:
            raise _err("That wire would create a cycle") from exc
        return {"edge": edge.id}


@register
class Disconnect(Command):
    key = "disconnect"
    label = "Disconnect"
    description = "Remove wires."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        ids: list[str] = P(default_factory=list, ui="json", desc="Edge ids.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        ids = set(self.params.ids)  # type: ignore[attr-defined]
        state.graph.edges = [e for e in state.graph.edges if e.id not in ids]
        return {"removed": sorted(ids)}


@register
class SetNodeFlags(Command):
    key = "set_node_flags"
    label = "Set node flags"
    description = "Enable/disable a node, toggle its preview, or rename it."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        node: str = P("", desc="Node id.")
        enabled: bool | None = P(None, desc="Enabled state.")
        preview: bool | None = P(None, desc="Preview state.")
        label: str | None = P(None, desc="Display label.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        try:
            n = state.graph.node(p.node)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise _err(str(exc)) from exc
        if p.enabled is not None:  # type: ignore[attr-defined]
            n.enabled = p.enabled  # type: ignore[attr-defined]
        if p.preview is not None:  # type: ignore[attr-defined]
            n.preview = p.preview  # type: ignore[attr-defined]
        if p.label is not None:  # type: ignore[attr-defined]
            n.label = p.label or None  # type: ignore[attr-defined]
        return {"node": n.id}


@register
class GroupNodes(Command):
    key = "group_nodes"
    label = "Group nodes"
    description = "Put nodes in a labelled, coloured group."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        ids: list[str] = P(default_factory=list, ui="json", desc="Node ids.")
        label: str = P("Group", desc="Group label.")
        color: str = P("#5b6b8a", ui="color", desc="Group colour.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        ids = [i for i in p.ids if state.graph.has_node(i)]  # type: ignore[attr-defined]
        if not ids:
            raise _err("Select nodes to group")
        gid = state.graph.new_id("group")
        state.graph.groups.append(GraphGroup(id=gid, label=p.label, color=p.color, nodes=ids))  # type: ignore[attr-defined]
        return {"group": gid}


@register
class Ungroup(Command):
    key = "ungroup"
    label = "Ungroup"
    description = "Remove a group (its nodes stay)."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        id: str = P("", desc="Group id.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        state.graph.groups = [g for g in state.graph.groups if g.id != self.params.id]  # type: ignore[attr-defined]
        return {}


@register
class ClusterNodes(Command):
    key = "cluster_nodes"
    label = "Make cluster"
    description = "Collapse nodes into a reusable cluster with exposed inputs and outputs."
    category = "Graph"
    mutates = True

    class Params(BaseModel):
        ids: list[str] = P(default_factory=list, ui="json", desc="Node ids to cluster.")
        label: str = P("Cluster", desc="Cluster label.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        g = state.graph
        ids = [i for i in self.params.ids if g.has_node(i)]  # type: ignore[attr-defined]
        if not ids:
            raise _err("Select nodes to cluster")
        idset = set(ids)
        if idset & set(g.roles.values()):
            raise _err("Pipeline nodes (genome, morphology, simulation, ...) cannot be clustered")
        types = node_types()
        inner = Graph(nodes=[n.model_copy(deep=True) for n in g.nodes if n.id in idset])
        outer_edges: list[GraphEdge] = []
        cid = g.new_id("cluster")
        xs = [n.pos[0] for n in inner.nodes]
        ys = [n.pos[1] for n in inner.nodes]
        made_in: dict[tuple[str, str], str] = {}
        made_out: dict[tuple[str, str], str] = {}
        for e in g.edges:
            s_in, t_in = e.source in idset, e.target in idset
            if s_in and t_in:
                inner.edges.append(e.model_copy())
            elif t_in:  # crossing in -> exposed input
                key = (e.source, e.source_socket)
                name = made_in.get(key)
                if name is None:
                    name = f"in{len(made_in) + 1}"
                    made_in[key] = name
                    src = g.node(e.source)
                    stype = {s.name: s.type for s in types[src.type].outputs_for(src.params)}.get(e.source_socket, "any")
                    inner.nodes.append(GraphNode(id=f"__{name}", type="cluster_input", params={"name": name, "type": stype}))
                    outer_edges.append(GraphEdge(id=f"{e.source}.{e.source_socket}->{cid}.{name}", source=e.source,
                                                 source_socket=e.source_socket, target=cid, target_socket=name))
                inner.edges.append(GraphEdge(id=f"__{name}->{e.target}.{e.target_socket}", source=f"__{name}",
                                             source_socket="value", target=e.target, target_socket=e.target_socket))
            elif s_in:  # crossing out -> exposed output
                key = (e.source, e.source_socket)
                name = made_out.get(key)
                if name is None:
                    name = f"out{len(made_out) + 1}"
                    made_out[key] = name
                    src = g.node(e.source)
                    stype = {s.name: s.type for s in types[src.type].outputs_for(src.params)}.get(e.source_socket, "any")
                    inner.nodes.append(GraphNode(id=f"__{name}", type="cluster_output", params={"name": name, "type": stype}))
                    inner.edges.append(GraphEdge(id=f"{e.source}.{e.source_socket}->__{name}", source=e.source,
                                                 source_socket=e.source_socket, target=f"__{name}", target_socket="value"))
                outer_edges.append(GraphEdge(id=f"{cid}.{name}->{e.target}.{e.target_socket}", source=cid,
                                             source_socket=name, target=e.target, target_socket=e.target_socket))
            else:
                outer_edges.append(e)
        g.nodes = [n for n in g.nodes if n.id not in idset]
        g.nodes.append(
            GraphNode(
                id=cid,
                type="cluster",
                label=self.params.label,  # type: ignore[attr-defined]
                params={"graph": inner.model_dump(mode="json")},
                pos=(sum(xs) / len(xs), sum(ys) / len(ys)),
            )
        )
        g.edges = outer_edges
        for grp in g.groups:
            grp.nodes = [n for n in grp.nodes if n not in idset]
        g.groups = [grp for grp in g.groups if grp.nodes]
        return {"cluster": cid, "inputs": list(made_in.values()), "outputs": list(made_out.values())}


@register
class ResetGraph(Command):
    key = "reset_graph"
    label = "Reset graph to default pipeline"
    description = "Replace the graph with the default pipeline, keeping genome and controller values."
    category = "Graph"
    mutates = True

    def run(self, lab: Any, state: DocumentState) -> Any:
        from calflab.config import default

        new = default_graph(default("simulation", {}))
        for role in ("genome", "controller"):
            try:
                old = state.graph.role(role)
                if new.role(role).type == old.type:
                    new.role(role).params = old.params
            except KeyError:
                pass
        state.graph = new
        return {}


# ====================================================================== layers / references
@register
class SetLayer(Command):
    key = "set_layer"
    label = "Set layer state"
    description = "Change a layer's visibility, lock or colour."
    category = "View"
    mutates = True

    class Params(BaseModel):
        layer: str = P("", desc="Layer name.")
        visible: bool | None = P(None, desc="Visible.")
        locked: bool | None = P(None, desc="Locked (not selectable).")
        color: str | None = P(None, ui="color", desc="Layer colour.")

    def title(self) -> str:
        return f"Layer {self.params.layer}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        layer = state.layers.get(p.layer)  # type: ignore[attr-defined]
        if layer is None:
            raise _err(f"No layer {p.layer!r}")  # type: ignore[attr-defined]
        if p.visible is not None:  # type: ignore[attr-defined]
            layer.visible = p.visible  # type: ignore[attr-defined]
        if p.locked is not None:  # type: ignore[attr-defined]
            layer.locked = p.locked  # type: ignore[attr-defined]
        if p.color:  # type: ignore[attr-defined]
            layer.color = p.color  # type: ignore[attr-defined]
        return layer.model_dump()


@register
class SetReference(Command):
    key = "set_reference"
    label = "Place reference image"
    description = "Add or update a reference image on a view plane."
    category = "Form"
    mutates = True

    class Params(BaseModel):
        id: str = P("", desc="Reference id (empty = new).")
        asset: str = P("", desc="Project-relative image path under assets/.")
        plane: str = P("right", choices=["front", "right", "top"], desc="View plane.")
        center: tuple[float, float, float] = P((0.0, 0.0, 300.0), unit="mm", desc="Centre of the image.")
        width_mm: float = P(700.0, unit="mm", ge=10, le=5000, desc="Image width in the scene.")
        opacity: float = P(0.5, ge=0.05, le=1, step=0.05, desc="Opacity.")
        visible: bool = P(True, desc="Visible.")
        remove: bool = P(False, desc="Delete this reference.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        if p.remove:  # type: ignore[attr-defined]
            state.references = [r for r in state.references if r.id != p.id]  # type: ignore[attr-defined]
            return {"removed": p.id}  # type: ignore[attr-defined]
        data = p.model_dump(exclude={"remove"})
        for i, r in enumerate(state.references):
            if r.id == p.id:  # type: ignore[attr-defined]
                state.references[i] = ReferenceImage(**{**r.model_dump(), **data})
                return {"reference": r.id}
        rid = p.id or f"ref-{uuid.uuid4().hex[:6]}"  # type: ignore[attr-defined]
        if not p.asset:  # type: ignore[attr-defined]
            raise _err("asset is required for a new reference image")
        state.references.append(ReferenceImage(**{**data, "id": rid}))
        return {"reference": rid}


@register
class AdoptCandidate(Command):
    key = "adopt_candidate"
    label = "Adopt candidate"
    description = "Load an evolved candidate's genome and gait into the document."
    category = "Evolve"
    mutates = True

    class Params(BaseModel):
        id: str = P("", desc="Candidate id.")

    def title(self) -> str:
        return f"Adopt {self.params.id}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        try:
            c = lab.registry.get_candidate(self.params.id)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise _err(str(exc)) from exc
        types = node_types()
        gnode = state.graph.role("genome")
        gnode.params = types[gnode.type].clean_params(c["genome"]["values"])
        cnode = state.graph.role("controller")
        ctype = f"controller:{c['controller']['key']}"
        if ctype in types:
            cnode.type = ctype
            cnode.params = types[ctype].clean_params(c["controller"].get("params", {}))
        # The candidate was built with the overrides of its run. If the document
        # carries different ones, adopting only the genes would give another body.
        replaced = False
        try:
            run_overrides = lab.registry.get_run(str(c.get("run_id"))).overrides
        except KeyError:
            run_overrides = None
        if run_overrides is not None:

            def sig(o: dict[str, Any]) -> tuple[Any, ...]:
                return (o.get("kind", "param"), o.get("target"), o.get("param"), o.get("value"), o.get("asset"))

            mine = sorted(map(repr, (sig(o.model_dump(mode="json")) for o in state.overrides if o.enabled)))
            if mine != sorted(map(repr, map(sig, run_overrides))):
                state.overrides = [Override.model_validate(o) for o in run_overrides]
                replaced = True
                lab.bus.emit(
                    "log",
                    level="warn",
                    source="adopt",
                    message=f"Adopt {c['id']}: the document's overrides were replaced by the {len(run_overrides)} "
                    "this candidate was evaluated with (Ctrl+Z restores them).",
                )
        return {"candidate": c["id"], "fitness": c.get("fitness"), "overrides_replaced": replaced}


@register
class LoadDesign(Command):
    key = "load_design"
    label = "Load baked design"
    description = "Replace the working document's graph and overrides with those of a baked design (undoable)."
    category = "Edit"
    mutates = True

    class Params(BaseModel):
        id: str = P("", desc="Design id, e.g. calf-v003.")

    def title(self) -> str:
        return f"Load design {self.params.id}"  # type: ignore[attr-defined]

    def run(self, lab: Any, state: DocumentState) -> Any:
        design_id = self.params.id  # type: ignore[attr-defined]
        if not design_id:
            raise _err("Which design? Give its id, e.g. load_design id=calf-v001")
        graph, overrides = lab.design_document(design_id)
        state.graph = graph
        state.overrides = overrides
        return {"design": design_id, "overrides": len(overrides)}


# ====================================================================== actions (not undoable)
@register
class Undo(Command):
    key = "undo"
    label = "Undo"
    description = "Undo the last document edit (shared by all clients)."
    category = "Edit"
    shortcut = "Ctrl+Z"

    def run(self, lab: Any, state: DocumentState) -> Any:
        return lab.undo()


@register
class Redo(Command):
    key = "redo"
    label = "Redo"
    description = "Redo the last undone edit."
    category = "Edit"
    shortcut = "Ctrl+Y"

    def run(self, lab: Any, state: DocumentState) -> Any:
        return lab.redo()


@register
class Bake(Command):
    key = "bake"
    label = "Bake design"
    description = "Freeze the current state into an immutable, named, versioned Design."
    category = "Edit"
    shortcut = "B"

    class Params(BaseModel):
        name: str = P("calf", desc="Design name (a version number is appended).")
        note: str = P("", desc="What is this design? (stored with it)")

    def run(self, lab: Any, state: DocumentState) -> Any:
        rec = lab.bake(self.params.name, self.params.note)  # type: ignore[attr-defined]
        return {"design": rec.id, "version": rec.version, "mass_g": rec.mass_g}


@register
class RunSim(Command):
    key = "run_sim"
    label = "Simulate"
    description = "Run the simulation node; poses stream into the viewport."
    category = "Simulate"
    shortcut = "F5"
    aliases = ["sim", "simulate"]

    def run(self, lab: Any, state: DocumentState) -> Any:
        return {"job": lab.run_sim().id}


@register
class RunEvolve(Command):
    key = "run_evolve"
    label = "Evolve"
    description = "Start an optimization run on the selected compute backend."
    category = "Evolve"
    aliases = ["evolve"]

    class Params(BaseModel):
        optimizer: str = P("map_elites_cma", desc="Optimizer plugin key.")
        params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Optimizer parameters.")
        backend: str = P("", desc="Compute backend key (empty = current).")
        sim: dict[str, Any] = P(default_factory=dict, ui="json", desc="Simulation overrides for evaluation rollouts.")
        design: str = P("", desc="Baked design to start from (empty = the working document).")

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        job = lab.run_evolve(p.optimizer, p.params, p.backend or None, p.sim, p.design or None)  # type: ignore[attr-defined]
        return {"job": job.id, "run_id": job.result.get("run_id")}


@register
class Export(Command):
    key = "export"
    label = "Export"
    description = "Run an exporter plugin on the current design."
    category = "Fabricate"

    class Params(BaseModel):
        exporter: str = P("", desc="Exporter plugin key.")
        params: dict[str, Any] = P(default_factory=dict, ui="json", desc="Exporter parameters.")
        selection: list[str] = P(default_factory=list, ui="json", desc="Element ids to export (empty = all).")
        run_id: str = P("", desc="Sim run to use (for exporters that need one).")

    def run(self, lab: Any, state: DocumentState) -> Any:
        p = self.params
        return {"job": lab.export(p.exporter, p.params, p.selection, p.run_id or None).id}  # type: ignore[attr-defined]


@register
class SetBackend(Command):
    key = "set_backend"
    label = "Set compute backend"
    description = "Choose where optimization jobs run."
    category = "Evolve"

    class Params(BaseModel):
        backend: str = P("local", desc="Compute backend plugin key.")

    def run(self, lab: Any, state: DocumentState) -> Any:
        from calflab.plugins import registry

        key = self.params.backend  # type: ignore[attr-defined]
        if not registry.has("compute_backend", key):
            raise _err(f"No compute backend {key!r}")
        lab.backend_key = key
        lab.bus.emit("backend.changed", backend=key)
        return {"backend": key}
