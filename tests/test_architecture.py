"""Architecture boundaries (PLAN.md, CLAUDE.md golden rules)."""

import ast
from pathlib import Path

from calflab.paths import repo_root

CORE = repo_root() / "core" / "calflab"
FORBIDDEN = ("calflab_server", "fastapi", "uvicorn", "starlette")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_core_never_imports_server_or_web_frameworks():
    offenders = []
    for path in CORE.rglob("*.py"):
        if "cli" in path.relative_to(CORE).parts:
            continue  # the CLI may launch the server
        for mod in _imports(path):
            if mod.split(".")[0] in FORBIDDEN:
                offenders.append(f"{path.relative_to(CORE)} imports {mod}")
    assert offenders == []


def test_unit_conversion_happens_only_in_units_module():
    """No hand-rolled mm/deg conversion factors outside calflab.units."""
    suspicious = ("math.radians(", "math.degrees(", "np.radians(", "np.deg2rad(", "np.rad2deg(")
    allowed = {"units.py", "xform.py", "calf.py", "metrics.py"}  # geometry helpers working in degrees by contract
    offenders = []
    for path in CORE.rglob("*.py"):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for token in suspicious:
            if token in text:
                offenders.append(f"{path.relative_to(CORE)} uses {token}")
    assert offenders == []
