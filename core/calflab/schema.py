"""Schema-driven parameters.

Every plugin declares a ``Params`` Pydantic model whose fields are created with
:func:`P`. :func:`ui_schema` turns such a model into a flat, JSON-able
description (type, unit, range, default, UI hint, description) from which the
web UI generates property panels, node sockets, tooltips and validation.
Adding a parameter never requires UI code.
"""

from __future__ import annotations

import enum
import types
import typing
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

UiHint = Literal[
    "slider", "number", "toggle", "enum", "text", "color", "curve", "vector3", "json", "file"
]


def P(
    default: Any = PydanticUndefined,
    *,
    unit: str | None = None,
    ge: float | None = None,
    le: float | None = None,
    step: float | None = None,
    ui: UiHint | None = None,
    desc: str = "",
    label: str | None = None,
    choices: list[Any] | None = None,
    group: str | None = None,
    advanced: bool = False,
    default_factory: Any = None,
) -> Any:
    """Declare a plugin parameter.

    Args:
        default: default value (design units: mm, g, deg unless ``unit`` says otherwise).
        unit: unit string understood by :mod:`calflab.units` (shown in the UI).
        ge, le: inclusive range; enables a slider.
        step: slider/number increment.
        ui: explicit widget hint; inferred from the type when omitted.
        desc: tooltip text.
        label: display label (defaults to the field name, humanised).
        choices: allowed values for an enum widget.
        group: collapsible group heading in the property panel.
        advanced: hide behind an "advanced" disclosure.
    """
    extra: dict[str, Any] = {}
    if unit is not None:
        extra["unit"] = unit
    if step is not None:
        extra["step"] = step
    if ui is not None:
        extra["ui"] = ui
    if label is not None:
        extra["label"] = label
    if choices is not None:
        extra["choices"] = choices
    if group is not None:
        extra["group"] = group
    if advanced:
        extra["advanced"] = True
    kwargs: dict[str, Any] = {"description": desc, "json_schema_extra": extra}
    if ge is not None:
        kwargs["ge"] = ge
    if le is not None:
        kwargs["le"] = le
    if default_factory is not None:
        return Field(default_factory=default_factory, **kwargs)
    return Field(default, **kwargs)


class EmptyParams(BaseModel):
    """Params model for plugins that take no parameters."""


def _humanise(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _bounds(info: FieldInfo) -> tuple[float | None, float | None]:
    lo = hi = None
    for m in info.metadata:
        if getattr(m, "ge", None) is not None:
            lo = m.ge
        if getattr(m, "gt", None) is not None:
            lo = m.gt
        if getattr(m, "le", None) is not None:
            hi = m.le
        if getattr(m, "lt", None) is not None:
            hi = m.lt
    return lo, hi


def _strip_optional(tp: Any) -> Any:
    origin = get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _field_type(tp: Any) -> tuple[str, list[Any] | None]:
    """Map a Python annotation to (ui type name, enum choices)."""
    tp = _strip_optional(tp)
    origin = get_origin(tp)
    if origin is Literal:
        return "enum", list(get_args(tp))
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return "enum", [e.value for e in tp]
    if tp is bool:
        return "boolean", None
    if tp is int:
        return "integer", None
    if tp is float:
        return "number", None
    if tp is str:
        return "string", None
    if origin in (tuple, list):
        args = get_args(tp)
        if origin is tuple and len(args) == 3 and all(a in (float, int) for a in args):
            return "vector3", None
        return "array", None
    if origin is dict or tp is dict:
        return "object", None
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return "group", None
    return "json", None


_DEFAULT_UI = {
    "boolean": "toggle",
    "enum": "enum",
    "string": "text",
    "vector3": "vector3",
    "array": "json",
    "object": "json",
    "json": "json",
}


def field_schema(name: str, info: FieldInfo) -> dict[str, Any]:
    extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
    ftype, choices = _field_type(info.annotation)
    lo, hi = _bounds(info)
    if "choices" in extra:
        choices = list(extra["choices"])  # type: ignore[arg-type]
        ftype = "enum"
    ui = extra.get("ui")
    if ui is None:
        if ftype in ("number", "integer"):
            ui = "slider" if lo is not None and hi is not None else "number"
        else:
            ui = _DEFAULT_UI.get(ftype, "json")
    default: Any = None
    if info.default is not PydanticUndefined:
        default = info.default
    elif info.default_factory is not None:
        default = info.default_factory()  # type: ignore[call-arg]
    if isinstance(default, BaseModel):
        default = default.model_dump(mode="json")
    elif isinstance(default, enum.Enum):
        default = default.value
    out: dict[str, Any] = {
        "name": name,
        "label": extra.get("label") or _humanise(name),
        "type": ftype,
        "ui": ui,
        "default": default,
        "unit": extra.get("unit"),
        "min": lo,
        "max": hi,
        "step": extra.get("step"),
        "description": info.description or "",
        "group": extra.get("group"),
        "advanced": bool(extra.get("advanced", False)),
        "required": info.is_required(),
    }
    if choices is not None:
        out["choices"] = choices
    if ftype == "group":
        sub = _strip_optional(info.annotation)
        out["fields"] = ui_schema(sub)["fields"]
    return out


def ui_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Flat UI description of a Pydantic model (see module docstring)."""
    return {
        "title": model.__name__,
        "description": (model.__doc__ or "").strip(),
        "fields": [field_schema(n, f) for n, f in model.model_fields.items()],
    }


def dynamic_schema(title: str, fields: list[dict[str, Any]], description: str = "") -> dict[str, Any]:
    """Build a UI schema for parameters that are data-defined (e.g. genes)."""
    norm = []
    for f in fields:
        base = {
            "label": _humanise(f["name"]),
            "type": "number",
            "ui": None,
            "default": None,
            "unit": None,
            "min": None,
            "max": None,
            "step": None,
            "description": "",
            "group": None,
            "advanced": False,
            "required": False,
        }
        base.update(f)
        if base["ui"] is None:
            if base["type"] in ("number", "integer"):
                ranged = base["min"] is not None and base["max"] is not None
                base["ui"] = "slider" if ranged else "number"
            else:
                base["ui"] = _DEFAULT_UI.get(str(base["type"]), "json")
        norm.append(base)
    return {"title": title, "description": description, "fields": norm}
