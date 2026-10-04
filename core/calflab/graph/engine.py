"""Cached graph evaluation.

Each node's outputs are cached under
``sha256(node type, code version, params, input hashes, context salt)``, which
gives Grasshopper-like incremental recompute: editing a parameter re-runs only
that node and what is downstream of it. Nodes marked ``expensive`` (simulation,
exports) never run implicitly; until someone runs them they report ``stale``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from calflab.graph.model import Graph
from calflab.graph.nodes import EvalContext, NodeType, node_code_version, node_types

log = logging.getLogger(__name__)

OK_STATES = ("ok", "warning")


@dataclass
class NodeResult:
    status: str  # ok | warning | error | stale | blocked | disabled
    outputs: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    key: str | None = None
    messages: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.status in OK_STATES


def _hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:24]


class Cache:
    """In-memory LRU of node outputs, with optional on-disk persistence for
    expensive nodes (so a rollout survives a server restart)."""

    def __init__(self, capacity: int = 256, disk_dir: Path | None = None):
        self.capacity = capacity
        self.disk_dir = disk_dir
        self._mem: OrderedDict[str, tuple[dict[str, Any], list[str]]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> tuple[dict[str, Any], list[str]] | None:
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                self.hits += 1
                return self._mem[key]
        if self.disk_dir is not None:
            p = self.disk_dir / f"{key}.pkl"
            if p.is_file():
                try:
                    with p.open("rb") as fh:
                        value = pickle.load(fh)
                    self._remember(key, value)
                    self.hits += 1
                    return value
                except Exception:
                    log.warning("Discarding unreadable cache entry %s", p)
        self.misses += 1
        return None

    def _remember(self, key: str, value: tuple[dict[str, Any], list[str]]) -> None:
        with self._lock:
            self._mem[key] = value
            self._mem.move_to_end(key)
            while len(self._mem) > self.capacity:
                self._mem.popitem(last=False)

    def put(self, key: str, outputs: dict[str, Any], messages: list[str], persist: bool = False) -> None:
        self._remember(key, (outputs, messages))
        if persist and self.disk_dir is not None:
            try:
                self.disk_dir.mkdir(parents=True, exist_ok=True)
                with (self.disk_dir / f"{key}.pkl").open("wb") as fh:
                    pickle.dump((outputs, messages), fh)
            except Exception:
                log.exception("Could not persist cache entry %s", key)

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()


class Evaluator:
    def __init__(self, cache: Cache | None = None):
        self.cache = cache or Cache()

    def evaluate(
        self,
        graph: Graph,
        ctx: EvalContext | None = None,
        targets: list[str] | None = None,
        run_expensive: bool | set[str] = False,
        types: dict[str, NodeType] | None = None,
    ) -> dict[str, NodeResult]:
        """Evaluate ``graph`` (or just ``targets`` and their ancestors).

        ``run_expensive``: ``True`` runs every expensive node that is not
        cached; a set of node ids runs only those.
        """
        ctx = ctx or EvalContext()
        types = types or node_types()
        try:
            order = graph.topo_order()
        except ValueError as exc:
            return {n.id: NodeResult("error", messages=[str(exc)]) for n in graph.nodes}
        if targets is not None:
            wanted: set[str] = set()
            for t in targets:
                wanted |= {t} | graph.ancestors(t)
            order = [n for n in order if n in wanted]

        results: dict[str, NodeResult] = {}
        for nid in order:
            results[nid] = self._eval_node(graph, nid, results, ctx, run_expensive, types)
        return results

    def _eval_node(
        self,
        graph: Graph,
        nid: str,
        results: dict[str, NodeResult],
        ctx: EvalContext,
        run_expensive: bool | set[str],
        types: dict[str, NodeType],
    ) -> NodeResult:
        node = graph.node(nid)
        if not node.enabled:
            return NodeResult("disabled", messages=["Node is disabled"])
        nt = types.get(node.type)
        if nt is None:
            return NodeResult("error", messages=[f"Unknown node type {node.type!r} (is its plugin loaded?)"])
        try:
            params = nt.clean_params(dict(node.params))
        except Exception as exc:
            return NodeResult("error", messages=[f"Invalid parameters: {exc}"])

        incoming = graph.incoming(nid)
        inputs: dict[str, Any] = {}
        input_hashes: list[tuple[str, str]] = []
        for sock in nt.inputs_for(params):
            edge = incoming.get(sock.name)
            if edge is None:
                if sock.required:
                    return NodeResult("error", messages=[f"Input '{sock.label or sock.name}' is not connected"])
                continue
            src = results.get(edge.source)
            if src is None or not src.ok:
                state = "stale" if src is not None and src.status == "stale" else "blocked"
                why = "needs to be run" if state == "stale" else "has no result"
                return NodeResult(state, messages=[f"Upstream node '{edge.source}' {why}"])
            if edge.source_socket not in src.outputs:
                return NodeResult("error", messages=[f"'{edge.source}' has no output '{edge.source_socket}'"])
            inputs[sock.name] = src.outputs[edge.source_socket]
            input_hashes.append((sock.name, src.hashes[edge.source_socket]))

        key = _hash(node.type, node_code_version(nt), params, sorted(input_hashes), nt.salt(params, ctx))
        out_names = [s.name for s in nt.outputs_for(params)]
        hashes = {name: _hash(key, name) for name in out_names}

        hit = self.cache.get(key)
        if hit is not None:
            outputs, messages = hit
            return NodeResult(
                "warning" if messages else "ok", outputs, hashes, key, list(messages), cached=True
            )

        allowed = run_expensive is True or (isinstance(run_expensive, set) and nid in run_expensive)
        if nt.expensive and not allowed:
            return NodeResult("stale", key=key, messages=["Not computed yet. Run this node."])

        t0 = time.perf_counter()
        before = len(ctx.warnings)
        try:
            if node.type == "cluster":
                outputs = self._eval_cluster(params, inputs, dict(input_hashes), ctx, run_expensive, types)
            else:
                outputs = nt.evaluate(params, inputs, ctx)
        except Exception as exc:
            log.debug("Node %s failed", nid, exc_info=True)
            del ctx.warnings[before:]
            return NodeResult("error", key=key, messages=[f"{type(exc).__name__}: {exc}"])
        messages = ctx.warnings[before:]
        del ctx.warnings[before:]
        if ctx.cancelled and ctx.cancelled() and nt.expensive:
            return NodeResult("stale", key=key, messages=["Cancelled"])
        self.cache.put(key, outputs, messages, persist=nt.expensive)
        return NodeResult(
            "warning" if messages else "ok",
            outputs,
            hashes,
            key,
            list(messages),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def _eval_cluster(
        self,
        params: dict[str, Any],
        inputs: dict[str, Any],
        input_hashes: dict[str, str],
        ctx: EvalContext,
        run_expensive: bool | set[str],
        types: dict[str, NodeType],
    ) -> dict[str, Any]:
        inner = Graph.model_validate(params.get("graph") or {})
        sub = EvalContext(
            overrides=ctx.overrides,
            project_dir=ctx.project_dir,
            on_frames=ctx.on_frames,
            cancelled=ctx.cancelled,
            cluster_inputs=inputs,
            cluster_input_hashes=input_hashes,
        )
        res = self.evaluate(inner, sub, run_expensive=run_expensive is True, types=types)
        outputs: dict[str, Any] = {}
        for n in inner.nodes:
            r = res[n.id]
            if r.status == "error":
                raise RuntimeError(f"cluster node '{n.id}': {'; '.join(r.messages)}")
            if n.type == "cluster_output":
                if not r.ok:
                    raise RuntimeError(f"cluster output '{n.id}' is {r.status}")
                outputs[str(n.params.get("name", n.id))] = r.outputs["value"]
        ctx.warnings.extend(sub.warnings)
        return outputs


def summarize(value: Any, limit: int = 4000) -> Any:
    """Small JSON-able preview of a node output for the inspector panel."""
    from calflab.design import EvaluatedDesign
    from calflab.model.genome import Genome
    from calflab.sim.mjcf import CompiledModel
    from calflab.sim.rollout import Rollout

    if isinstance(value, Genome):
        return {"kind": "genome", "definition": value.definition, "version": value.version, "values": value.values}
    if isinstance(value, EvaluatedDesign):
        s = value.spec
        return {
            "kind": "design",
            "bodies": len(s.bodies),
            "joints": len(s.joints),
            "actuators": len(s.actuators),
            "mass_g": round(s.total_mass_g(), 1),
            "mass_by_layer_g": {k: round(v, 1) for k, v in s.mass_by_layer().items()},
            "warnings": value.warnings,
        }
    if isinstance(value, CompiledModel):
        return {
            "kind": "model",
            "actuators": len(value.actuator_ids),
            "joints": len(value.joint_ids),
            "mass_kg": round(value.total_mass_kg, 3),
            "timestep_s": value.timestep,
            "xml_chars": len(value.xml),
        }
    if isinstance(value, Rollout):
        return {
            "kind": "rollout",
            "frames": value.n_frames,
            "duration_s": float(value.t[-1] - value.t[0]) if value.n_frames else 0.0,
            "fell": value.meta.get("fell"),
        }
    if isinstance(value, dict):  # keep scalars, collapse bulky nested tables
        compact: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, (dict, list)) and len(json.dumps(v, default=str)) > 600:
                compact[str(k)] = f"<{len(v)} items>"
            else:
                compact[str(k)] = v
        value = compact
    try:
        text = json.dumps(value, default=str)
    except Exception:
        text = repr(value)
    if len(text) > limit:
        return {"kind": "text", "text": text[:limit] + "..."}
    return json.loads(text) if text and text[0] in "[{\"-0123456789tfn" else text
