"""Plugin discovery: entry points, gene-definition YAML, and the ``plugins/`` folder.

``load_plugins()`` is idempotent. ``PluginWatcher`` polls the plugins folder
and re-imports changed files (hot reload in dev mode).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from calflab.plugins.base import registry

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "calflab.plugins"
USER_MODULE_PREFIX = "calflab_user_plugins."

_loaded = False
_lock = threading.RLock()


def _load_entry_points() -> None:
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # pragma: no cover
        eps = []  # type: ignore[assignment]
    names = set()
    for ep in eps:
        names.add(ep.value)
        try:
            ep.load()
            registry.errors.pop(f"entry_point:{ep.name}", None)
        except Exception as exc:
            log.exception("Plugin entry point %s failed", ep.name)
            registry.errors[f"entry_point:{ep.name}"] = repr(exc)
    if "calflab.builtin" not in names:  # running from a source tree without metadata
        importlib.import_module("calflab.builtin")


def _register_yaml_gene_definitions() -> None:
    from calflab.config import gene_definition_files
    from calflab.plugins.types import GeneDefinition

    for name, definition in gene_definition_files().items():
        if registry.has("gene_definition", name):
            existing = registry.get("gene_definition", name)
            if existing.__module__ != "calflab.plugins.yaml_genes":
                continue  # a code plugin takes precedence

        def _definition(self, _d=definition, _name=name):  # type: ignore[no-untyped-def]
            # read again: the file, or the component library its choices come from, may have changed
            return gene_definition_files().get(_name, _d)

        cls = type(
            f"YamlGenes_{name}",
            (GeneDefinition,),
            {
                "key": name,
                "label": f"{name} genome (YAML)",
                "description": definition.description.strip(),
                "version": str(definition.version),
                "definition": _definition,
                "__module__": "calflab.plugins.yaml_genes",
            },
        )
        registry.register(cls)


def _module_name(path: Path) -> str:
    return USER_MODULE_PREFIX + path.stem


def load_file(path: Path) -> str | None:
    """Import (or re-import) one plugin file. Returns an error message or None."""
    name = _module_name(path)
    registry.unregister_module(name)
    sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        registry.errors.pop(str(path), None)
        return None
    except Exception as exc:
        log.exception("Plugin file %s failed to load", path)
        sys.modules.pop(name, None)
        registry.unregister_module(name)
        msg = f"{type(exc).__name__}: {exc}"
        registry.errors[str(path)] = msg
        return msg


def plugin_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.py") if not p.name.startswith("_"))


def load_folder(directory: Path) -> dict[str, str]:
    """Import every plugin file in ``directory``. Returns ``{path: error}``."""
    errors: dict[str, str] = {}
    for p in plugin_files(directory):
        err = load_file(p)
        if err:
            errors[str(p)] = err
    return errors


def load_plugins(folder: Path | None = None, force: bool = False) -> None:
    """Load built-in, entry-point, YAML-defined and folder plugins."""
    global _loaded
    from calflab.paths import plugins_dir

    with _lock:
        if _loaded and not force:
            return
        _load_entry_points()
        _register_yaml_gene_definitions()
        load_folder(folder or plugins_dir())
        _loaded = True


class PluginWatcher:
    """Polls the plugins folder; reloads changed files and calls ``on_change``."""

    def __init__(
        self,
        directory: Path,
        on_change: Callable[[list[str]], None] | None = None,
        interval: float = 1.0,
    ):
        self.directory = directory
        self.on_change = on_change
        self.interval = interval
        self._mtimes: dict[Path, float] = {p: p.stat().st_mtime for p in plugin_files(directory)}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def poll(self) -> list[str]:
        """Check once. Returns the list of files that were (re)loaded or removed."""
        changed: list[str] = []
        current = {p: p.stat().st_mtime for p in plugin_files(self.directory)}
        for p, mtime in current.items():
            if self._mtimes.get(p) != mtime:
                load_file(p)
                changed.append(str(p))
        for p in set(self._mtimes) - set(current):
            registry.unregister_module(_module_name(p))
            registry.errors.pop(str(p), None)
            changed.append(str(p))
        self._mtimes = current
        if changed:
            _register_yaml_gene_definitions()
            if self.on_change:
                self.on_change(changed)
        return changed

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.interval):
                try:
                    self.poll()
                except Exception:  # pragma: no cover
                    log.exception("Plugin watcher poll failed")

        self._thread = threading.Thread(target=loop, name="calflab-plugin-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
