"""Experiment registry (ADR-014).

The truth is text: ``runs/<id>/run.json`` (+ ``candidates.jsonl``) and
``designs/<id>/design.json``. ``index.sqlite`` is a query index that
:meth:`Registry.rebuild` can recreate from those files at any time.
"""

from __future__ import annotations

import json
import platform
import sqlite3
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from calflab import CODE_VERSION, __version__
from calflab.project.store import Project, now_iso, read_json, slugify, write_json

INDEX_FILE = "index.sqlite"
_PACKAGES = ("mujoco", "numpy", "pydantic", "ribs", "cma", "trimesh", "build123d", "rhino3dm")


def git_hash(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


_code_hash: list[str | None] = []


def code_git_hash() -> str:
    """Git hash of the CALFLAB code that produced a result ("unknown" outside git)."""
    if not _code_hash:
        from calflab.paths import repo_root

        _code_hash.append(git_hash(repo_root()))
    return _code_hash[0] or "unknown"


def package_versions() -> dict[str, str]:
    out = {"python": platform.python_version(), "calflab": __version__, "code_version": CODE_VERSION}
    for name in _PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    out["platform"] = sys.platform
    return out


class RunRecord(BaseModel):
    """Provenance of one sim, optimization, training job, bake or export."""

    id: str
    kind: str  # sim | evolve | train | bake | export
    title: str = ""
    status: str = "done"  # running | done | failed | cancelled
    created: str = Field(default_factory=now_iso)
    duration_s: float = 0.0
    seed: int | None = None
    git_hash: str | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    backend: str = "local"
    inputs: dict[str, Any] = Field(default_factory=dict)  # settings, optimizer params, exporter params
    genome: dict[str, Any] | None = None
    overrides: list[dict[str, Any]] = Field(default_factory=list)
    controller: dict[str, Any] | None = None
    fitness: dict[str, Any] | None = None  # full preset snapshot + result
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)  # name -> project-relative path
    thumbnail: str | None = None
    parent: str | None = None  # run or design this derives from
    cache_key: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class DesignRecord(BaseModel):
    """A baked, immutable, citable design."""

    id: str  # "<slug>-v003"
    name: str
    version: int
    created: str = Field(default_factory=now_iso)
    note: str = ""
    genome: dict[str, Any]
    overrides: list[dict[str, Any]] = Field(default_factory=list)
    graph: dict[str, Any]
    spec: dict[str, Any]
    mass_g: float = 0.0
    code_version: str = CODE_VERSION
    calflab_version: str = __version__
    git_hash: str | None = None
    thumbnail: str | None = None
    command_seq: int = 0  # position in the command log when baked


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, kind TEXT, title TEXT, status TEXT, created TEXT,
    duration_s REAL, seed INTEGER, backend TEXT, fitness REAL, cache_key TEXT,
    parent TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS runs_kind ON runs(kind, created);
CREATE INDEX IF NOT EXISTS runs_key ON runs(cache_key);
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY, run_id TEXT, generation INTEGER, fitness REAL,
    status TEXT, cell TEXT, parents TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS cand_run ON candidates(run_id, generation);
CREATE TABLE IF NOT EXISTS designs (
    id TEXT PRIMARY KEY, name TEXT, version INTEGER, created TEXT, mass_g REAL, data TEXT
);
"""


class Registry:
    def __init__(self, project: Project):
        self.project = project
        self._lock = threading.RLock()
        self._db = sqlite3.connect(project.path / INDEX_FILE, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ ids
    def new_run_id(self, kind: str) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{kind}-{uuid.uuid4().hex[:4]}"

    def run_dir(self, run_id: str) -> Path:
        return self.project.dir("runs") / run_id

    # ------------------------------------------------------------------ runs
    def stamp(self, record: RunRecord) -> RunRecord:
        """Fill in git hash and package versions."""
        record.git_hash = record.git_hash or code_git_hash()
        record.versions = record.versions or package_versions()
        return record

    def save_run(self, record: RunRecord) -> RunRecord:
        self.stamp(record)
        d = self.run_dir(record.id)
        d.mkdir(parents=True, exist_ok=True)
        write_json(d / "run.json", record.model_dump(mode="json"))
        self._index_run(record)
        return record

    def _index_run(self, r: RunRecord) -> None:
        fitness = None
        if r.fitness and isinstance(r.fitness.get("result"), dict):
            fitness = r.fitness["result"].get("total")
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r.id, r.kind, r.title, r.status, r.created, r.duration_s, r.seed, r.backend,
                    fitness, r.cache_key, r.parent, r.model_dump_json(),
                ),
            )
            self._db.commit()

    def get_run(self, run_id: str) -> RunRecord:
        with self._lock:
            row = self._db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"No run {run_id!r}")
        return RunRecord.model_validate_json(row[0])

    def find_run_by_key(self, cache_key: str, kind: str = "sim") -> RunRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM runs WHERE cache_key=? AND kind=? AND status='done' ORDER BY created DESC",
                (cache_key, kind),
            ).fetchone()
        return RunRecord.model_validate_json(row[0]) if row else None

    def list_runs(self, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = "SELECT id, kind, title, status, created, duration_s, seed, backend, fitness, parent FROM runs"
        args: tuple[Any, ...] = ()
        if kind:
            q += " WHERE kind=?"
            args = (kind,)
        q += " ORDER BY created DESC, id DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, (*args, limit)).fetchall()
        keys = ("id", "kind", "title", "status", "created", "duration_s", "seed", "backend", "fitness", "parent")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    # ------------------------------------------------------------------ candidates / lineage
    def save_candidates(self, run_id: str, candidates: list[dict[str, Any]]) -> None:
        d = self.run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        with (d / "candidates.jsonl").open("a", encoding="utf-8") as fh:
            for c in candidates:
                fh.write(json.dumps(c, default=str) + "\n")
        self._index_candidates(candidates)

    def _index_candidates(self, candidates: list[dict[str, Any]]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        c["id"], c.get("run_id"), c.get("generation"), c.get("fitness"), c.get("status"),
                        json.dumps(c.get("cell")), json.dumps(c.get("parents", [])), json.dumps(c, default=str),
                    )
                    for c in candidates
                ],
            )
            self._db.commit()

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute("SELECT data FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(f"No candidate {candidate_id!r}")
        return json.loads(row[0])

    def list_candidates(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM candidates WHERE run_id=? ORDER BY generation, id", (run_id,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def lineage(self, candidate_id: str) -> list[dict[str, Any]]:
        """The candidate and all its ancestors (id, generation, fitness, parents)."""
        seen: dict[str, dict[str, Any]] = {}
        stack = [candidate_id]
        while stack:
            cid = stack.pop()
            if cid in seen:
                continue
            try:
                c = self.get_candidate(cid)
            except KeyError:
                continue
            seen[cid] = {k: c.get(k) for k in ("id", "generation", "fitness", "parents", "status", "cell")}
            stack.extend(c.get("parents", []))
        return sorted(seen.values(), key=lambda c: (c["generation"], c["id"]))

    # ------------------------------------------------------------------ designs
    def next_design_version(self, name: str) -> int:
        slug = slugify(name, "design")
        with self._lock:
            row = self._db.execute(
                "SELECT MAX(version) FROM designs WHERE id LIKE ?", (f"{slug}-v%",)
            ).fetchone()
        return int(row[0] or 0) + 1

    def save_design(self, record: DesignRecord) -> DesignRecord:
        d = self.project.dir("designs") / record.id
        if (d / "design.json").exists():
            raise FileExistsError(f"Design {record.id!r} already exists; baked designs are immutable")
        d.mkdir(parents=True, exist_ok=True)
        record.git_hash = record.git_hash or code_git_hash()
        write_json(d / "design.json", record.model_dump(mode="json"))
        self._index_design(record)
        return record

    def _index_design(self, r: DesignRecord) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO designs VALUES (?,?,?,?,?,?)",
                (r.id, r.name, r.version, r.created, r.mass_g, r.model_dump_json()),
            )
            self._db.commit()

    def set_design_thumbnail(self, design_id: str, rel_path: str) -> None:
        """Attach a thumbnail (the only field that may be added after baking)."""
        rec = self.get_design(design_id)
        rec.thumbnail = rel_path
        write_json(self.project.dir("designs") / design_id / "design.json", rec.model_dump(mode="json"))
        self._index_design(rec)

    def get_design(self, design_id: str) -> DesignRecord:
        with self._lock:
            row = self._db.execute("SELECT data FROM designs WHERE id=?", (design_id,)).fetchone()
        if row is None:
            raise KeyError(f"No design {design_id!r}")
        return DesignRecord.model_validate_json(row[0])

    def list_designs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM designs ORDER BY created DESC, id DESC"
            ).fetchall()
        out = []
        for (data,) in rows:
            d = json.loads(data)
            out.append({k: d.get(k) for k in ("id", "name", "version", "created", "note", "mass_g", "thumbnail", "git_hash")})
        return out

    # ------------------------------------------------------------------ integrity
    def rebuild(self) -> dict[str, int]:
        """Recreate the index from the text files."""
        with self._lock:
            self._db.executescript("DELETE FROM runs; DELETE FROM candidates; DELETE FROM designs;")
            self._db.commit()
        n_runs = n_cands = n_designs = 0
        for f in sorted(self.project.dir("runs").glob("*/run.json")):
            self._index_run(RunRecord.model_validate(read_json(f)))
            n_runs += 1
            cfile = f.parent / "candidates.jsonl"
            if cfile.is_file():
                with cfile.open("r", encoding="utf-8") as fh:
                    cands = [json.loads(line) for line in fh if line.strip()]
                self._index_candidates(cands)
                n_cands += len(cands)
        for f in sorted(self.project.dir("designs").glob("*/design.json")):
            self._index_design(DesignRecord.model_validate(read_json(f)))
            n_designs += 1
        return {"runs": n_runs, "candidates": n_cands, "designs": n_designs}

    def check(self) -> list[str]:
        """Integrity problems: index rows without files, files without rows, missing artifacts."""
        problems: list[str] = []
        with self._lock:
            indexed = {r[0] for r in self._db.execute("SELECT id FROM runs").fetchall()}
            designs = {r[0] for r in self._db.execute("SELECT id FROM designs").fetchall()}
        on_disk = {f.parent.name for f in self.project.dir("runs").glob("*/run.json")}
        for rid in sorted(indexed - on_disk):
            problems.append(f"run {rid} is indexed but runs/{rid}/run.json is missing")
        for rid in sorted(on_disk - indexed):
            problems.append(f"run {rid} exists on disk but is not indexed (run: calflab registry rebuild)")
        for rid in sorted(indexed & on_disk):
            rec = self.get_run(rid)
            for name, rel in rec.artifacts.items():
                if not (self.project.path / rel).exists():
                    problems.append(f"run {rid}: artifact {name} ({rel}) is missing")
            for field in ("git_hash", "versions"):
                if rec.kind in ("sim", "evolve") and not getattr(rec, field):
                    problems.append(f"run {rid}: no {field} recorded")
        disk_designs = {f.parent.name for f in self.project.dir("designs").glob("*/design.json")}
        for did in sorted(designs ^ disk_designs):
            problems.append(f"design {did}: index and disk disagree")
        return problems
