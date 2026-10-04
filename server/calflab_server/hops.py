"""Grasshopper Hops endpoints (ADR-024).

Point a Hops component at ``http://127.0.0.1:8000/hops/<name>``. Hops first
GETs that URL for the component's inputs/outputs, then POSTs to
``/hops/solve``. Geometry is not sent through Hops; the BakeToRhino endpoint
returns the Rhino build list as JSON for the GH Python "bake" component in
``bridges/rhino/grasshopper``.

NOTE: implemented from the Hops HTTP protocol as documented by ghhops-server;
it is covered by HTTP-level tests but has not been exercised against a live
Grasshopper session yet.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from calflab.app import Lab
from calflab.bridge import rhino_build_list
from fastapi import APIRouter, Body

_TYPES = {"Number": "System.Double", "Text": "System.String", "Boolean": "System.Boolean", "Integer": "System.Int32"}


def _param(name: str, ptype: str, desc: str, default: Any = None, many: bool = False) -> dict[str, Any]:
    p: dict[str, Any] = {
        "Name": name,
        "Nickname": name,
        "Description": desc,
        "ParamType": ptype,
        "ResultType": _TYPES[ptype],
        "AtLeast": 0 if default is not None or many else 1,
        "AtMost": 2147483647 if many else 1,
    }
    if default is not None:
        p["Default"] = default
    return p


def _decode(values: list[dict[str, Any]]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for v in values:
        items: list[Any] = []
        for branch in (v.get("InnerTree") or {}).values():
            for item in branch:
                data = item.get("data")
                try:
                    items.append(json.loads(data) if isinstance(data, str) else data)
                except json.JSONDecodeError:
                    items.append(data)
        out[v.get("ParamName", "")] = items
    return out


def _encode(name: str, ptype: str, items: list[Any]) -> dict[str, Any]:
    return {
        "ParamName": name,
        "InnerTree": {"{0}": [{"type": _TYPES[ptype], "data": json.dumps(i)} for i in items]},
    }


def hops_router(lab: Lab) -> APIRouter:
    router = APIRouter(prefix="/hops")

    def get_design(_: dict[str, list[Any]]) -> dict[str, list[Any]]:
        s = lab.scene()
        return {
            "genome": [json.dumps(s["genome"]["values"])],
            "mass_g": [s["mass"]["total_g"]],
            "revision": [lab.revision],
        }

    def set_genome_params(i: dict[str, list[Any]]) -> dict[str, list[Any]]:
        names, values = i.get("names", []), i.get("values", [])
        if names and len(names) == len(values):
            lab.execute("set_genes", {"values": dict(zip(names, values, strict=True))}, client="grasshopper")
        return {"revision": [lab.revision]}

    def run_sim(i: dict[str, list[Any]]) -> dict[str, list[Any]]:
        if not (i.get("run") or [False])[0]:
            return {"job": [""]}
        return {"job": [lab.run_sim(client="grasshopper").id]}

    def get_metrics(i: dict[str, list[Any]]) -> dict[str, list[Any]]:
        job_id = (i.get("job") or [""])[0]
        if not job_id:
            return {"status": ["no job"], "metrics": ["{}"]}
        job = lab.jobs.get(job_id)
        metrics = {k: v for k, v in job.result.get("metrics", {}).items() if k != "by_actuator"}
        return {"status": [job.status], "metrics": [json.dumps(metrics)]}

    def bake_to_rhino(_: dict[str, list[Any]]) -> dict[str, list[Any]]:
        return {"build_list": [json.dumps(rhino_build_list(lab.design(), lab.revision))]}

    endpoints: dict[str, tuple[str, list[dict[str, Any]], list[tuple[str, str, str]], Callable[..., Any]]] = {
        "getdesign": (
            "Current CALFLAB design: genome values (JSON), total mass, revision.",
            [_param("refresh", "Boolean", "Toggle to re-read.", default=True)],
            [("genome", "Text", "Gene values as JSON"), ("mass_g", "Number", "Total mass in g"),
             ("revision", "Integer", "Document revision")],
            get_design,
        ),
        "setgenomeparams": (
            "Set genome values by gene id.",
            [_param("names", "Text", "Gene ids", many=True), _param("values", "Number", "Gene values", many=True)],
            [("revision", "Integer", "Document revision after the edit")],
            set_genome_params,
        ),
        "runsim": (
            "Start a simulation job (asynchronous). Returns the job id.",
            [_param("run", "Boolean", "Set true to start.", default=False)],
            [("job", "Text", "Job id for GetMetrics")],
            run_sim,
        ),
        "getmetrics": (
            "Status and metrics of a simulation job.",
            [_param("job", "Text", "Job id from RunSim")],
            [("status", "Text", "queued | running | done | failed"), ("metrics", "Text", "Metrics as JSON")],
            get_metrics,
        ),
        "baketorhino": (
            "Rhino build list (layers, blocks, objects with IDs) as JSON.",
            [_param("refresh", "Boolean", "Toggle to re-read.", default=True)],
            [("build_list", "Text", "Build list JSON for the CalflabBake GH Python component")],
            bake_to_rhino,
        ),
    }

    def describe(name: str) -> dict[str, Any]:
        desc, inputs, outputs, _ = endpoints[name]
        return {
            "Description": desc,
            "Inputs": inputs,
            "Outputs": [
                {"Name": n, "Nickname": n, "Description": d, "ParamType": t, "ResultType": _TYPES[t],
                 "AtLeast": 1, "AtMost": 1}
                for n, t, d in outputs
            ],
        }

    @router.get("")
    def index() -> list[dict[str, Any]]:
        return [{"name": k, "uri": f"/hops/{k}", "description": v[0]} for k, v in endpoints.items()]

    @router.get("/{name}")
    def io(name: str) -> dict[str, Any]:
        key = name.lower()
        if key not in endpoints:
            raise KeyError(f"No Hops endpoint {name!r}")
        return describe(key)

    @router.post("/solve")
    def solve(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        key = str(body.get("pointer", "")).rstrip("/").split("/")[-1].lower()
        if key not in endpoints:
            raise KeyError(f"No Hops endpoint {key!r}")
        _, _, outputs, fn = endpoints[key]
        result = fn(_decode(body.get("values", [])))
        types = {n: t for n, t, _ in outputs}
        return {"values": [_encode(n, types[n], items) for n, items in result.items()], "errors": [], "warnings": []}

    return router
