"""Environment checks for ``calflab doctor``."""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    fix: str = ""


def _version(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except Exception:
        return None


def find_rhino() -> Path | None:
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")):
        if base:
            p = Path(base) / "Rhino 8" / "System" / "Rhino.exe"
            if p.is_file():
                return p
    return None


def find_blender() -> Path | None:
    hit = shutil.which("blender")
    if hit:
        return Path(hit)
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steamapps" / "common" / "Blender",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        direct = root / "blender.exe"
        if direct.is_file():
            return direct
        for sub in sorted(root.glob("Blender*"), reverse=True):
            exe = sub / "blender.exe"
            if exe.is_file():
                return exe
    return None


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _module(name: str) -> str | None:
    try:
        m = importlib.import_module(name)
        return str(getattr(m, "__version__", "installed"))
    except Exception:
        return None


def run_checks(project: Path | None = None) -> list[Check]:
    from calflab.cli import webenv
    from calflab.paths import default_project, home_dir, repo_root, web_dir

    checks: list[Check] = []

    def add(name: str, ok: bool | None, detail: str, fix: str = "", warn_only: bool = False) -> None:
        status = "ok" if ok else ("warn" if warn_only or ok is None else "fail")
        checks.append(Check(name, status, detail, "" if ok else fix))

    add("Operating system", True, f"{platform.system()} {platform.release()} ({platform.machine()})")
    py = platform.python_version()
    add("Python", py.startswith(("3.11", "3.12")), py, "Run through .\\calflab.ps1 so uv picks Python 3.12")
    uv = _version(["uv", "--version"]) or _version(["python", "-m", "uv", "--version"])
    add("uv", uv is not None, uv or "not found", "python -m pip install --user uv", warn_only=True)

    for mod, label, fix, optional in (
        ("mujoco", "MuJoCo (CPU simulation)", "calflab setup", False),
        ("ribs", "pyribs (MAP-Elites)", "calflab setup", False),
        ("cma", "cma (CMA-ES)", "calflab setup", False),
        ("fastapi", "FastAPI (server)", "calflab setup", False),
        ("rhino3dm", "rhino3dm (.3dm export)", "calflab setup", False),
        ("build123d", "build123d (CAD export)", "uv sync --extra cad", True),
        ("wireviz", "WireViz (harness diagrams)", "uv sync --extra wire", True),
    ):
        v = _module(mod)
        add(label, v is not None, v or "not installed", fix, warn_only=optional)
    dot = shutil.which("dot")
    add("Graphviz dot", dot is not None, dot or "not found (built-in harness renderer will be used)",
        "winget install Graphviz.Graphviz", warn_only=True)

    node = _version(["node", "--version"])
    add("Node.js", node is not None, node or "not found", "Install Node LTS from https://nodejs.org")
    pn = webenv.pnpm()
    add("pnpm", pn is not None, pn or "not found", "npm install -g pnpm")

    root = repo_root()
    in_tree = webenv.in_tree()
    synced = webenv.cloud_synced(root)
    where = f"inside {synced}" if synced else ("supports links" if in_tree else "no junction support")
    add(
        "Repo location",
        in_tree,
        f"{root} ({where})",
        f"OK to keep working: environments live in {home_dir()}, outside the synced folder. Pause syncing "
        "during long runs if you see file-lock errors, and treat GitHub (not the sync service) as the backup "
        "of the repository.",
        warn_only=True,
    )
    work = web_dir() if in_tree else home_dir() / "web"
    add("Web dependencies", (work / "node_modules").is_dir(), str(work / "node_modules"), "calflab setup")
    dist = webenv.dist_dir()
    add("Web build", (dist / "index.html").is_file(), str(dist), "calflab setup (or calflab lab --dev)", warn_only=True)

    rhino = find_rhino()
    add("Rhino 8", rhino is not None, str(rhino) if rhino else "not found", "Install Rhino 8 (optional bridge)", warn_only=True)
    blender = find_blender()
    add("Blender", blender is not None, str(blender) if blender else "not found",
        "Install Blender 4.x or add blender.exe to PATH (optional bridge)", warn_only=True)

    for port, what in ((8000, "server"), (5173, "web dev server")):
        free = port_free(port)
        add(f"Port {port} ({what})", free, "free" if free else "in use",
            "Another CALFLAB (or app) is using it; close it or pass --port", warn_only=True)

    proj = project or default_project()
    add("Project", (proj / "project.calflab.json").is_file(), str(proj), "calflab setup creates the sample project")
    add("GPU compute", None, "No CUDA expected locally: MuJoCo runs on CPU; training uses a remote backend.", warn_only=True)

    try:
        from calflab.plugins import load_plugins, registry

        load_plugins()
        n = len(registry.everything())
        errs = registry.errors
        add("Plugins", not errs, f"{n} loaded" + (f", {len(errs)} failed: {'; '.join(errs.values())}" if errs else ""),
            "Fix the plugin file named in the message")
        from calflab.components import library

        unverified = sum(1 for c in library().all() if not c.verified)
        add("Component specs", None, f"{unverified} of {len(library().all())} unverified (see config/components/*.yaml)",
            warn_only=True)
    except Exception as exc:
        add("Plugins", False, f"{type(exc).__name__}: {exc}", "calflab setup")
    return checks
