"""Task execution shared by every compute backend (ADR-013)."""

from __future__ import annotations

import importlib
import traceback
from typing import Any


def resolve(fn: str) -> Any:
    """Import ``module:function``."""
    module, _, name = fn.partition(":")
    if not module or not name:
        raise ValueError(f"Task function must be 'module:function', got {fn!r}")
    return getattr(importlib.import_module(module), name)


def run_task(fn: str, payload: dict[str, Any]) -> Any:
    """Run one task in the current process."""
    return resolve(fn)(payload)


def run_task_safe(fn: str, payload: dict[str, Any]) -> Any:
    """Run one task; a failure becomes ``{"error": ...}`` instead of raising."""
    try:
        return run_task(fn, payload)
    except Exception as exc:  # the batch must survive one bad candidate
        return {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}


def init_worker() -> None:
    """Process-pool initializer: pay the import cost once per worker."""
    import mujoco  # noqa: F401

    from calflab.plugins import load_plugins

    load_plugins()
