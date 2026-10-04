"""Where the web app is built and run (ADR-003).

On a normal NTFS checkout the web app runs in ``web/``. When the repo lives on
a filesystem that cannot host ``node_modules`` (Google Drive's virtual FAT32
volume: no junctions, no symlinks, everything synced), a work directory under
``%LOCALAPPDATA%\\calflab\\web`` holds ``node_modules`` and the build output;
top-level files are copied into it and sub-directories are junctioned back to
the repo, so edits in ``web/src`` are live.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from calflab.paths import home_dir, web_dir

SKIP = {"node_modules", "dist", "test-results", "playwright-report", ".vite"}
COPY_DIRS = {"e2e"}


def can_host_node_modules(directory: Path) -> bool:
    """True if ``directory`` supports directory junctions/symlinks (pnpm needs them)."""
    probe_target = directory / "_calflab_probe_target"
    probe_link = directory / "_calflab_probe_link"
    try:
        probe_target.mkdir(exist_ok=True)
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(probe_target), str(probe_link))
        else:
            os.symlink(probe_target, probe_link, target_is_directory=True)
        return True
    except OSError:
        return False
    finally:
        for p in (probe_link, probe_target):
            try:
                if p.is_symlink() or p.exists():
                    os.rmdir(p)
            except OSError:
                pass


def _junction(link: Path, target: Path) -> None:
    if link.exists() or link.is_symlink():
        try:
            if os.path.samefile(link, target):
                return
        except OSError:
            pass
        os.rmdir(link) if _is_link(link) else shutil.rmtree(link)
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _is_link(p: Path) -> bool:
    try:
        return p.is_symlink() or bool(os.readlink(p))
    except OSError:
        return False


def cloud_synced(directory: Path) -> str | None:
    """Name of the sync service if ``directory`` is inside a cloud-synced folder."""
    p = str(directory.resolve()).lower()
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.environ.get(var)
        if root and p.startswith(str(Path(root).resolve()).lower() + os.sep):
            return "OneDrive"
    parts = {part.lower() for part in directory.resolve().parts}
    for marker, name in (("onedrive", "OneDrive"), ("my drive", "Google Drive"), ("google drive", "Google Drive"),
                         ("dropbox", "Dropbox"), ("icloud drive", "iCloud Drive"), ("iclouddrive", "iCloud Drive")):
        if any(part == marker or part.startswith(marker + " - ") for part in parts):
            return name
    return None


def in_tree() -> bool:
    """True if node_modules may live in ``web/``: the filesystem supports links
    and the repo is not inside a cloud-synced folder (tens of thousands of
    small files would be uploaded)."""
    override = os.environ.get("CALFLAB_WEB_IN_TREE")
    if override is not None:
        return override == "1"
    if cloud_synced(web_dir()) is not None:
        return False
    return can_host_node_modules(web_dir())


def workdir() -> Path:
    """Directory to run pnpm/vite/playwright in (synced with ``web/`` if out of tree)."""
    src = web_dir()
    if in_tree():
        return src
    work = home_dir() / "web"
    work.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in SKIP:
            continue
        dest = work / item.name
        if item.is_dir() and item.name in COPY_DIRS:
            # Playwright resolves test files to their real path, so junctioned
            # tests cannot find node_modules; these small folders are copied.
            if dest.exists() and _is_link(dest):
                os.rmdir(dest)
            elif dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        elif item.is_dir():
            _junction(dest, item)
        elif not dest.exists() or item.stat().st_mtime > dest.stat().st_mtime or item.stat().st_size != dest.stat().st_size:
            shutil.copy2(item, dest)
    return work


def save_lockfile(work: Path) -> None:
    """Copy the lockfile produced in the work directory back into the repo."""
    lock = work / "pnpm-lock.yaml"
    if lock.is_file() and work != web_dir():
        shutil.copy2(lock, web_dir() / "pnpm-lock.yaml")


def dist_dir() -> Path:
    return (web_dir() if in_tree() else home_dir() / "web") / "dist"


def pnpm() -> str | None:
    return shutil.which("pnpm") or shutil.which("pnpm.cmd")


def run_pnpm(args: list[str], cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None) -> int:
    exe = pnpm()
    if exe is None:
        raise RuntimeError("pnpm not found. Install it with: npm install -g pnpm")
    proc = subprocess.run([exe, *args], cwd=str(cwd or workdir()), env={**os.environ, **(env or {})}, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"pnpm {' '.join(args)} failed with exit code {proc.returncode}")
    return proc.returncode
