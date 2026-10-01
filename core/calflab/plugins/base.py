"""Plugin base class and registry."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from calflab.schema import EmptyParams, ui_schema

log = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class Plugin:
    """Base of every plugin.

    Subclasses set ``key`` / ``label`` / ``description`` and declare a nested
    ``Params`` model built with :func:`calflab.schema.P`. The UI is generated
    from that schema; a plugin never ships UI code.
    """

    plugin_type: ClassVar[str] = ""
    key: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    version: ClassVar[str] = "1"
    #: later-phase scaffold: interface is real, behaviour is not implemented yet
    stub: ClassVar[bool] = False
    Params: ClassVar[type[BaseModel]] = EmptyParams

    def __init__(self, params: BaseModel | dict[str, Any] | None = None):
        if params is None:
            self.params = self.Params()
        elif isinstance(params, BaseModel):
            self.params = self.Params.model_validate(params.model_dump())
        else:
            self.params = self.Params.model_validate(params)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """UI schema of the parameters (override for data-defined parameters)."""
        return ui_schema(cls.Params)

    @classmethod
    def extra(cls) -> dict[str, Any]:
        """Type-specific metadata added to :meth:`describe`."""
        return {}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "type": cls.plugin_type,
            "key": cls.key,
            "label": cls.label or cls.key,
            "description": cls.description or (cls.__doc__ or "").strip().split("\n")[0],
            "version": cls.version,
            "stub": cls.stub,
            "module": cls.__module__,
            "schema": cls.params_schema(),
            **cls.extra(),
        }


T = TypeVar("T", bound=type[Plugin])


class Registry:
    """All known plugins, by type then key."""

    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, type[Plugin]]] = {}
        self._lock = threading.RLock()
        self.errors: dict[str, str] = {}  # source -> error message (shown in the UI)

    def register(self, cls: T) -> T:
        if not cls.plugin_type:
            raise TypeError(f"{cls.__name__} has no plugin_type (subclass a plugin type class)")
        if not _KEY_RE.match(cls.key or ""):
            raise ValueError(f"{cls.__name__}.key must be snake_case, got {cls.key!r}")
        with self._lock:
            table = self._plugins.setdefault(cls.plugin_type, {})
            prev = table.get(cls.key)
            if prev is not None and prev.__module__ != cls.__module__:
                raise ValueError(
                    f"{cls.plugin_type} plugin {cls.key!r} is already registered by "
                    f"{prev.__module__}; {cls.__module__} must use a different key"
                )
            table[cls.key] = cls
        return cls

    def unregister_module(self, module: str) -> int:
        """Remove every plugin defined in ``module`` (used by hot reload)."""
        n = 0
        with self._lock:
            for table in self._plugins.values():
                for key in [k for k, c in table.items() if c.__module__ == module]:
                    del table[key]
                    n += 1
        return n

    def get(self, plugin_type: str, key: str) -> type[Plugin]:
        with self._lock:
            try:
                return self._plugins[plugin_type][key]
            except KeyError as exc:
                known = ", ".join(sorted(self._plugins.get(plugin_type, {}))) or "none"
                raise KeyError(
                    f"No {plugin_type} plugin {key!r}. Known: {known}. "
                    f"Create one with: calflab new-plugin {plugin_type} {key}"
                ) from exc

    def has(self, plugin_type: str, key: str) -> bool:
        with self._lock:
            return key in self._plugins.get(plugin_type, {})

    def all(self, plugin_type: str) -> dict[str, type[Plugin]]:
        with self._lock:
            return dict(self._plugins.get(plugin_type, {}))

    def types(self) -> list[str]:
        with self._lock:
            return sorted(self._plugins)

    def everything(self) -> list[type[Plugin]]:
        with self._lock:
            return [c for t in sorted(self._plugins) for _, c in sorted(self._plugins[t].items())]

    def describe_all(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for cls in self.everything():
            try:
                out.setdefault(cls.plugin_type, []).append(cls.describe())
            except Exception as exc:  # a broken plugin must not take the UI down
                log.exception("describe() failed for %s", cls)
                self.errors[f"{cls.plugin_type}:{cls.key}"] = f"describe() failed: {exc}"
        return out


registry = Registry()


def register(cls: T) -> T:
    """Class decorator: register a plugin with the global registry."""
    return registry.register(cls)
