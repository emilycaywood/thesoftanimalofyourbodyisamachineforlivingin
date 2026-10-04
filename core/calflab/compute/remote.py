"""Remote compute backends (Phase 2). Interfaces and job packaging are real;
transport and polling are stubs.

RemoteSSH design (package -> copy -> run -> poll -> fetch):

1. ``write_bundle(tasks)`` creates ``job-<id>.zip`` (see :mod:`calflab.compute.bundle`).
2. ``scp job.zip user@host:remote_dir/``
3. ``ssh user@host "cd remote_dir && unzip -o job.zip -d job && cd job &&
   nohup python run_job.py > log.txt 2>&1 &"``
4. poll: ``ssh user@host "wc -l < remote_dir/job/results.jsonl"`` for progress
5. ``scp user@host:remote_dir/job/results.jsonl .`` then ``read_results``

Windows 11 ships OpenSSH (``ssh``/``scp``), so no bash tooling is required.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from calflab.compute.bundle import read_results, write_bundle
from calflab.plugins import ComputeBackend, Task, register
from calflab.schema import P


@register
class RemoteSSH(ComputeBackend):
    """Run jobs on a remote NVIDIA workstation over SSH."""

    key = "remote_ssh"
    label = "Remote workstation (SSH)"
    description = "Packages the job, copies it over SSH, runs it remotely and fetches results (Phase 2)."
    stub = True

    class Params(BaseModel):
        host: str = P("", desc="Remote host name or IP.")
        user: str = P("", desc="Remote user name.")
        remote_dir: str = P("~/calflab_jobs", desc="Working directory on the remote machine.")
        python: str = P("python3", desc="Python executable on the remote machine.")
        workers: int = P(0, ge=0, le=256, desc="Remote worker processes (0 = all cores).")

    def target(self) -> str:
        p = self.params
        return f"{p.user}@{p.host}" if p.user else str(p.host)  # type: ignore[attr-defined]

    def available(self) -> tuple[bool, str]:
        if not self.params.host:  # type: ignore[attr-defined]
            return False, "no host configured"
        if shutil.which("ssh") is None or shutil.which("scp") is None:
            return False, "OpenSSH client (ssh/scp) not found on PATH"
        return False, "RemoteSSH transport is not implemented yet (Phase 2)"

    def commands(self, job_id: str, bundle: Path) -> dict[str, list[str]]:
        """The exact commands the backend will run (pure; used by tests and docs)."""
        p = self.params
        rd = f"{p.remote_dir}/{job_id}"  # type: ignore[attr-defined]
        workers = f" --workers {p.workers}" if p.workers else ""  # type: ignore[attr-defined]
        return {
            "mkdir": ["ssh", self.target(), f"mkdir -p {rd}"],
            "upload": ["scp", str(bundle), f"{self.target()}:{rd}/job.zip"],
            "run": [
                "ssh",
                self.target(),
                f"cd {rd} && unzip -o -q job.zip && nohup {p.python} run_job.py{workers} > log.txt 2>&1 &",  # type: ignore[attr-defined]
            ],
            "poll": ["ssh", self.target(), f"wc -l < {rd}/results.jsonl 2>/dev/null || echo 0"],
            "fetch": ["scp", f"{self.target()}:{rd}/results.jsonl", str(bundle.with_suffix(".results.jsonl"))],
        }

    def map(
        self,
        tasks: list[Task],
        on_result: Callable[[int, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Any]:
        # TODO(phase2): run self.commands(...) with subprocess, poll until the
        # result count equals len(tasks), honour `cancelled`, then read_results().
        raise NotImplementedError(
            "RemoteSSH is scaffolded: bundle packaging and the command plan exist "
            "(see RemoteSSH.commands), the transport loop is Phase 2."
        )


NOTEBOOK_CELLS = [
    ("markdown", "# CALFLAB cloud job\nUpload `{bundle}` next to this notebook, then run all cells. "
                 "Download `results.jsonl` when it finishes and import it with "
                 "`calflab.compute.remote.CloudNotebook.import_results`."),
    ("code", "!pip -q install mujoco mujoco-mjx playground pydantic pyyaml cma ribs"),
    ("code", "import zipfile, os\nzipfile.ZipFile('{bundle}').extractall('job')\nos.chdir('job')"),
    ("code", "# CPU evaluation of the packaged tasks (same code path as the local pool)\n"
             "!python run_job.py"),
    ("markdown", "## GPU training (Phase 2)\nMJX / MuJoCo Playground PPO training on the exported MJCF "
                 "goes here. The bundle's `job.json` carries the compiled model in `meta.mjcf`."),
    ("code", "import json\nmeta = json.load(open('job.json'))['meta']\nprint(list(meta))"),
]


@register
class CloudNotebook(ComputeBackend):
    """Export a self-contained job bundle plus a Colab notebook; import the results."""

    key = "cloud_notebook"
    label = "Cloud notebook (Colab)"
    description = "Exports a job bundle and a notebook for MJX / MuJoCo Playground training (Phase 2)."
    stub = True

    class Params(BaseModel):
        out_dir: str = P("exports/cloud", desc="Project-relative folder for exported bundles.")

    def available(self) -> tuple[bool, str]:
        return False, "manual: export a bundle, run it in Colab, import the results"

    def export_bundle(
        self, tasks: list[Task], out_dir: Path, name: str = "job", meta: dict[str, Any] | None = None
    ) -> tuple[Path, Path]:
        """Write ``<name>.zip`` and ``<name>.ipynb`` into ``out_dir``."""
        bundle = write_bundle(tasks, out_dir / f"{name}.zip", meta)
        cells = []
        for kind, text in NOTEBOOK_CELLS:
            src = text.replace("{bundle}", bundle.name)
            cell: dict[str, Any] = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
            if kind == "code":
                cell.update({"outputs": [], "execution_count": None})
            cells.append(cell)
        nb = {
            "cells": cells,
            "metadata": {
                "accelerator": "GPU",
                "kernelspec": {"display_name": "Python 3", "name": "python3"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        nb_path = out_dir / f"{name}.ipynb"
        nb_path.write_text(json.dumps(nb, indent=1), encoding="utf-8")
        return bundle, nb_path

    @staticmethod
    def import_results(path: Path, n_tasks: int | None = None) -> list[Any]:
        return read_results(path, n_tasks)

    def map(
        self,
        tasks: list[Task],
        on_result: Callable[[int, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Any]:
        raise NotImplementedError(
            "CloudNotebook is a manual backend: call export_bundle(), run the notebook, "
            "then import_results()."
        )
