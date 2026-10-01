"""Bridge scripts that only run inside Rhino, checked as far as possible without it.

The real checks are `calflab bridge rhino --check`, `--grasshopper` and
`calflab bridge blender --check-ui`; these tests guard the two mistakes those
checks found that can be caught headlessly.
"""

from __future__ import annotations

import ast
import inspect
import runpy
import sys
import types
from pathlib import Path

import pytest

RHINO = Path(__file__).resolve().parents[1] / "bridges" / "rhino"


def test_install_script_can_run_twice(monkeypatch, capsys):
    """CalflabInstall crashed in Rhino when the aliases already existed: it
    called a rhinoscriptsyntax function that does not exist. This fake offers
    only the real alias functions, so any other name fails the test."""
    aliases: dict[str, str] = {}
    rs = types.ModuleType("rhinoscriptsyntax")
    rs.IsAlias = lambda name: name in aliases  # type: ignore[attr-defined]
    rs.AddAlias = lambda name, macro: aliases.__setitem__(name, macro) or True  # type: ignore[attr-defined]

    def alias_macro(name: str, macro: str | None = None) -> str:
        old = aliases[name]
        if macro is not None:
            aliases[name] = macro
        return old

    rs.AliasMacro = alias_macro  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rhinoscriptsyntax", rs)
    script = str(RHINO / "scripts" / "CalflabInstall.py")
    runpy.run_path(script, run_name="__main__")
    aliases["CalflabPull"] = "stale macro"
    runpy.run_path(script, run_name="__main__")
    assert set(aliases) == {"CalflabConnect", "CalflabPull", "CalflabPush", "CalflabLiveSync"}
    for name, macro in aliases.items():
        assert macro.startswith("_-ScriptEditor _Run ") and (RHINO / "scripts" / f"{name}.py").is_file()
    capsys.readouterr()


def _example_components() -> dict[str, tuple[list[tuple[str, bool]], list[str], str]]:
    tree = ast.parse((RHINO / "grasshopper" / "build_example.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "COMPONENTS":
            return ast.literal_eval(node.value)
    raise AssertionError("COMPONENTS not found in build_example.py")


def test_grasshopper_example_calls_match_calflab_gh(monkeypatch):
    """Each generated GH component calls a calflab_gh function that exists,
    with that function's arguments, and unpacks as many outputs as it declares."""
    monkeypatch.syspath_prepend(str(RHINO / "grasshopper"))
    monkeypatch.syspath_prepend(str(RHINO / "scripts"))
    gh = pytest.importorskip("calflab_gh")
    components = _example_components()
    assert set(components) == {"GetDesign", "SetGenomeParams", "RunSim", "GetMetrics", "BakeToRhino"}
    for name, (inputs, outputs, body) in components.items():
        stmt = ast.parse(body).body[0]
        assert isinstance(stmt, ast.Assign), name
        targets = stmt.targets[0]
        assigned = [t.id for t in targets.elts] if isinstance(targets, ast.Tuple) else [targets.id]  # type: ignore[attr-defined]
        assert assigned == outputs, name
        call = next(n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
        fn = getattr(gh, call.func.attr)  # type: ignore[attr-defined]
        args = [a.id for a in call.args]  # type: ignore[attr-defined]
        assert args == list(inspect.signature(fn).parameters), name
        used = {n.id for n in ast.walk(stmt.value) if isinstance(n, ast.Name)} - {"gh"}
        assert used == {n for n, _is_list in inputs}, name
