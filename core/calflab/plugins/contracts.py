"""Plugin contracts.

``check_plugin(cls)`` returns a list of problems (empty = the plugin honours
its contract). ``tests/test_plugins.py`` runs it over every registered plugin
and ``calflab new-plugin`` generates a test that runs it on the new plugin.

Contracts are deliberately behavioural: they exercise each plugin with its
default parameters on small sample inputs.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.plugins.base import Plugin
from calflab.plugins.types import BASES, ControlInfo, ExportContext, Observation, Task

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

SAMPLE_METRICS: dict[str, Any] = {
    "speed_mps": 0.3,
    "distance_m": 1.8,
    "lateral_drift_m": 0.05,
    "cost_of_transport": 0.8,
    "energy_j": 60.0,
    "mean_power_w": 10.0,
    "stability": 0.7,
    "roll_rms_deg": 3.0,
    "pitch_rms_deg": 2.0,
    "height_std_mm": 2.0,
    "fell": False,
    "survival": 1.0,
    "torque_rms_nm": 1.0,
    "torque_peak_nm": 4.0,
    "torque_margin_min": 0.2,
    "temp_peak_c": 30.0,
    "foot_impact_mps": 0.2,
    "foot_impact_peak_mps": 0.5,
    "time_to_stand_s": None,
    "joint_limit_violation": 0.0,
    "mass_kg": 5.0,
    "by_actuator": {},
}


def contract_echo(payload: dict[str, Any]) -> dict[str, Any]:
    """Task used to exercise compute backends."""
    return {"echo": payload.get("x")}


def _generic(cls: type[Plugin]) -> list[str]:
    problems: list[str] = []
    if cls.plugin_type not in BASES:
        return [f"unknown plugin_type {cls.plugin_type!r}"]
    if not issubclass(cls, BASES[cls.plugin_type]):
        problems.append(f"must subclass {BASES[cls.plugin_type].__name__}")
    if not _KEY_RE.match(cls.key or ""):
        problems.append(f"key {cls.key!r} is not snake_case")
    if not cls.label:
        problems.append("label is empty")
    if not (cls.description or cls.__doc__):
        problems.append("description (or docstring) is empty")
    if not (isinstance(cls.Params, type) and issubclass(cls.Params, BaseModel)):
        problems.append("Params must be a pydantic BaseModel")
        return problems
    try:
        cls.Params()
    except Exception as exc:
        problems.append(f"every parameter needs a default (Params() failed: {exc})")
        return problems
    try:
        desc = cls.describe()
        json.dumps(desc)
    except Exception as exc:
        problems.append(f"describe() must be JSON-serialisable: {exc}")
        return problems
    for f in desc["schema"]["fields"]:
        if not f.get("description"):
            problems.append(f"parameter {f['name']!r} has no description (use P(..., desc=...))")
    try:
        cls()
    except Exception as exc:
        problems.append(f"cannot instantiate with default parameters: {exc}")
    return problems


def _gene_definition(cls: type[Plugin]) -> list[str]:
    from calflab.model.genome import GenomeDefinition

    d = cls().definition()  # type: ignore[attr-defined]
    if not isinstance(d, GenomeDefinition):
        return ["definition() must return a GenomeDefinition"]
    out = []
    if d.name != cls.key:
        out.append(f"definition name {d.name!r} must equal the plugin key {cls.key!r}")
    if d.complete({}) != d.defaults():
        out.append("complete({}) must equal defaults()")
    return out


def _part_generator(cls: type[Plugin]) -> list[str]:
    from calflab.design import build_design, genome_definition
    from calflab.model.overrides import Override

    gname = cls.genome_definition  # type: ignore[attr-defined]
    if not gname:
        return ["genome_definition is not set"]
    gdef = genome_definition(gname)
    d = build_design(gdef.default_genome(), generator=cls.key)
    out = []
    ids = d.spec.element_ids()
    if len(ids) != len(set(ids)):
        out.append("element ids are not unique")
    if d.spec.total_mass_g() <= 0:
        out.append("spec has no mass")
    for el, table in d.element_params.items():
        for name, pv in table.items():
            if pv.gene and not gdef.has(pv.gene):
                out.append(f"{el}.{name} is bound to unknown gene {pv.gene!r}")
    again = build_design(gdef.default_genome(), generator=cls.key)
    if again.spec.model_dump() != d.spec.model_dump():
        out.append("build is not deterministic")
    # an override must change the built spec and be recorded
    el, name, pv = next(
        (e, n, p) for e, t in d.element_params.items() for n, p in t.items() if p.gene is not None
    )
    ov = Override(id="ov-contract", name="contract", target=el, param=name, value=pv.value * 1.1)
    d2 = build_design(gdef.default_genome(), [ov], generator=cls.key)
    if d2.element_params[el][name].override != "ov-contract":
        out.append("override was not recorded on the element parameter")
    if d2.spec.model_dump() == d.spec.model_dump():
        out.append(f"overriding {el}.{name} did not change the spec")
    return out


def _joint_type(cls: type[Plugin]) -> list[str]:
    out = []
    if not isinstance(cls.dof, int) or cls.dof < 0:  # type: ignore[attr-defined]
        out.append("dof must be a non-negative int")
    return out


def _component(cls: type[Plugin]) -> list[str]:
    out = []
    for c in cls().components():  # type: ignore[attr-defined]
        if not c.source:
            out.append(f"component {c.key!r} has no source")
        if c.verified:
            out.append(f"component {c.key!r}: plugins must not mark specs verified")
    return out


def _controller(cls: type[Plugin]) -> list[str]:
    n = 12
    ids = [f"act.{leg}.{j}" for leg in ("fl", "fr", "hl", "hr") for j in ("hip_abd", "hip_flex", "knee")]
    jids = [i.replace("act.", "joint.") for i in ids]
    info = ControlInfo(
        actuator_ids=ids,
        joint_ids=jids,
        rest=np.zeros(n),
        lo=-np.ones(n),
        hi=np.ones(n),
        control_dt=0.02,
    )
    c = cls()
    c.reset(info, seed=0)  # type: ignore[attr-defined]
    obs = Observation(
        t=0.5,
        q=np.zeros(n),
        dq=np.zeros(n),
        trunk_quat=np.array([1.0, 0, 0, 0]),
        trunk_gyro=np.zeros(3),
        foot_contact=np.ones(4),
    )
    a = np.asarray(c.act(obs))  # type: ignore[attr-defined]
    out = []
    if a.shape != (n,):
        out.append(f"act() must return one target per actuator, got shape {a.shape}")
    elif not np.all(np.isfinite(a)):
        out.append("act() returned non-finite targets")
    dims = cls.vector_dims()  # type: ignore[attr-defined]
    fields = cls.Params.model_fields
    for d in dims:
        if d.name not in fields:
            out.append(f"vector dim {d.name!r} is not a Params field")
    if dims and not out:
        x = cls.vector_from_params({})  # type: ignore[attr-defined]
        p = cls.params_from_vector({}, x)  # type: ignore[attr-defined]
        try:
            cls(p)
        except Exception as exc:
            out.append(f"params_from_vector produced invalid params: {exc}")
    return out


def _fitness_term(cls: type[Plugin]) -> list[str]:
    v = cls().evaluate(dict(SAMPLE_METRICS), {})  # type: ignore[attr-defined]
    if not isinstance(v, (int, float)) or not np.isfinite(v):
        return [f"evaluate() must return a finite number, got {v!r}"]
    return []


def _behavior_descriptor(cls: type[Plugin]) -> list[str]:
    from calflab.design import build_design, genome_definition

    out = []
    lo, hi = cls.range  # type: ignore[attr-defined]
    if not lo < hi:
        out.append("range must be (low, high) with low < high")
    spec = build_design(genome_definition("calf").default_genome()).spec
    v = cls().describe_candidate(spec, dict(SAMPLE_METRICS), {"frequency": 1.5})  # type: ignore[attr-defined]
    if not isinstance(v, (int, float)) or not np.isfinite(v):
        out.append(f"describe_candidate() must return a finite number, got {v!r}")
    return out


def _compute_backend(cls: type[Plugin]) -> list[str]:
    b = cls()
    ok, reason = b.available()  # type: ignore[attr-defined]
    out = []
    if not isinstance(ok, bool) or not isinstance(reason, str):
        out.append("available() must return (bool, str)")
    if cls.stub:
        return out
    if ok:
        try:
            tasks = [Task(fn="calflab.plugins.contracts:contract_echo", payload={"x": i}) for i in range(3)]
            res = b.map(tasks)  # type: ignore[attr-defined]
            if [r.get("echo") for r in res] != [0, 1, 2]:
                out.append(f"map() must return results in task order, got {res!r}")
        finally:
            b.shutdown()  # type: ignore[attr-defined]
    return out


def _exporter(cls: type[Plugin]) -> list[str]:
    out = []
    if not cls.formats:  # type: ignore[attr-defined]
        out.append("formats is empty")
    if cls.stub:
        return out
    from calflab.components import library
    from calflab.design import build_design, genome_definition

    d = build_design(genome_definition("calf").default_genome())
    ctx = ExportContext(spec=d.spec, genes=d.genome.values, element_params=d.element_params, library=library())
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            paths = cls().export(ctx, Path(tmp))  # type: ignore[attr-defined]
        except ImportError as exc:  # optional dependency missing is not a contract failure
            return out + ([] if "optional" in str(exc).lower() else [f"export() raised {exc!r}"])
        if not paths:
            out.append("export() returned no files")
        for p in paths:
            if not Path(p).is_file() or Path(p).stat().st_size == 0:
                out.append(f"export() reported {p} but it is missing or empty")
    return out


def _optimizer(cls: type[Plugin]) -> list[str]:
    return [] if callable(getattr(cls, "run", None)) else ["run() missing"]


def _simulator(cls: type[Plugin]) -> list[str]:
    return [] if callable(getattr(cls, "rollout", None)) else ["rollout() missing"]


def _behavior(cls: type[Plugin]) -> list[str]:
    if cls.stub:
        return []
    r = cls().tick(0.0, {})  # type: ignore[attr-defined]
    return [] if isinstance(r, dict) else ["tick() must return a dict"]


def _analysis(cls: type[Plugin]) -> list[str]:
    return [] if callable(getattr(cls, "run", None)) else ["run() missing"]


def _panel(cls: type[Plugin]) -> list[str]:
    out = []
    w = cls.widgets  # type: ignore[attr-defined]
    if not isinstance(w, list) or not w:
        out.append("widgets must be a non-empty list of dicts")
    else:
        for i, item in enumerate(w):
            if not isinstance(item, dict) or "kind" not in item:
                out.append(f"widget {i} needs a 'kind'")
    return out


def _command(cls: type[Plugin]) -> list[str]:
    out = []
    if not isinstance(cls.mutates, bool):  # type: ignore[attr-defined]
        out.append("mutates must be a bool")
    if not cls.category:  # type: ignore[attr-defined]
        out.append("category is empty")
    return out


_SPECIFIC: dict[str, Callable[[type[Plugin]], list[str]]] = {
    "gene_definition": _gene_definition,
    "part_generator": _part_generator,
    "joint_type": _joint_type,
    "component": _component,
    "controller": _controller,
    "behavior": _behavior,
    "fitness_term": _fitness_term,
    "behavior_descriptor": _behavior_descriptor,
    "optimizer": _optimizer,
    "simulator": _simulator,
    "compute_backend": _compute_backend,
    "exporter": _exporter,
    "analysis": _analysis,
    "panel": _panel,
    "command": _command,
}


def check_plugin(cls: type[Plugin]) -> list[str]:
    """Return contract violations for a plugin class (empty list = OK)."""
    problems = _generic(cls)
    if problems:
        return problems
    try:
        problems += _SPECIFIC[cls.plugin_type](cls)
    except NotImplementedError as exc:
        if not cls.stub:
            problems.append(f"not implemented and not marked stub = True: {exc}")
    except Exception as exc:
        problems.append(f"contract check raised {type(exc).__name__}: {exc}")
    return problems
