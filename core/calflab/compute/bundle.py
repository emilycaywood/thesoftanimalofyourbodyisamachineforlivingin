"""Self-contained job bundles for remote backends.

A bundle is a zip with:

    job.json            tasks ({fn, payload, id})
    run_job.py          runner: executes every task, writes results.jsonl
    src/calflab/        the core package source
    config/             component library, gene definitions, fitness presets
    requirements.txt    runtime dependencies

It runs anywhere Python and the requirements are available:
``python run_job.py`` -> ``results.jsonl``. The same bundle is used by the
RemoteSSH backend and by the CloudNotebook (Colab) export.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from calflab.paths import repo_root
from calflab.plugins import Task

RUNNER = '''"""CALFLAB job runner (generated). Usage: python run_job.py [--workers N]"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
os.environ["CALFLAB_REPO"] = HERE

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()
    from calflab.compute.worker import init_worker, run_task_safe
    with open(os.path.join(HERE, "job.json"), encoding="utf-8") as fh:
        job = json.load(fh)
    tasks = job["tasks"]
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
        futures = [pool.submit(run_task_safe, t["fn"], t["payload"]) for t in tasks]
        with open(os.path.join(HERE, "results.jsonl"), "w", encoding="utf-8") as out:
            for t, f in zip(tasks, futures):
                out.write(json.dumps({"id": t["id"], "result": f.result()}) + "\\n")
                out.flush()
                print("done", t["id"], flush=True)

if __name__ == "__main__":
    main()
'''

REQUIREMENTS = ["pydantic>=2.7", "pyyaml>=6.0", "numpy>=1.26", "mujoco>=3.1", "cma>=3.3", "ribs>=0.7"]


def write_bundle(tasks: list[Task], path: Path, meta: dict[str, Any] | None = None) -> Path:
    """Write a job bundle zip to ``path``."""
    root = repo_root()
    path.parent.mkdir(parents=True, exist_ok=True)
    job = {
        "meta": meta or {},
        "tasks": [{"id": t.id or str(i), "fn": t.fn, "payload": t.payload} for i, t in enumerate(tasks)],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("job.json", json.dumps(job))
        z.writestr("run_job.py", RUNNER)
        z.writestr("requirements.txt", "\n".join(REQUIREMENTS) + "\n")
        for src in sorted((root / "core" / "calflab").rglob("*.py")):
            z.write(src, Path("src") / src.relative_to(root / "core"))
        for cfg in sorted((root / "config").rglob("*.yaml")):
            z.write(cfg, cfg.relative_to(root))
    return path


def read_results(path: Path, n_tasks: int | None = None) -> list[Any]:
    """Read ``results.jsonl`` produced by the runner, ordered by task id."""
    by_id: dict[str, Any] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                by_id[str(rec["id"])] = rec["result"]
    n = n_tasks if n_tasks is not None else len(by_id)
    return [by_id.get(str(i), {"error": "missing result"}) for i in range(n)]
