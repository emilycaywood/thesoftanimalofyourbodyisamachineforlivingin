"""Job queue: every long operation is non-blocking, reports progress, and can
be cancelled or retried, independent of the compute backend."""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from calflab.app.events import EventBus
from calflab.project.store import now_iso

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str
    title: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    message: str = ""
    logs: list[str] = field(default_factory=list)
    created: str = field(default_factory=now_iso)
    started: float | None = None
    duration_s: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    backend: str = "local"
    retry_of: str | None = None

    def view(self, logs: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "created": self.created,
            "duration_s": round(self.duration_s, 2),
            "result": self.result,
            "error": self.error,
            "backend": self.backend,
            "retry_of": self.retry_of,
        }
        if logs:
            out["logs"] = list(self.logs)
        return out


class JobCancelled(Exception):
    pass


class JobContext:
    """Handed to the job function."""

    def __init__(self, job: Job, manager: JobManager, cancel: threading.Event):
        self.job = job
        self._manager = manager
        self._cancel = cancel
        self._last_emit = 0.0

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    def report(self, progress: float | None = None, message: str | None = None) -> None:
        if progress is not None:
            self.job.progress = max(0.0, min(1.0, progress))
        if message is not None:
            self.job.message = message
        now = time.monotonic()
        if now - self._last_emit > 0.1 or (progress is not None and progress >= 1.0):
            self._last_emit = now
            self._manager._emit(self.job)

    def log(self, message: str) -> None:
        self.job.logs.append(f"{now_iso()[11:19]} {message}")
        del self.job.logs[:-500]
        self._manager.bus.emit("log", level="info", source=f"job:{self.job.id}", message=message)


JobFn = Callable[[JobContext], dict[str, Any] | None]


class JobManager:
    def __init__(self, bus: EventBus, workers: int = 3):
        self.bus = bus
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="calflab-job")
        self._jobs: dict[str, Job] = {}
        self._fns: dict[str, JobFn] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def _emit(self, job: Job) -> None:
        self.bus.emit("job.updated", job=job.view())

    def submit(self, kind: str, title: str, fn: JobFn, backend: str = "local", retry_of: str | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:10], kind=kind, title=title, backend=backend, retry_of=retry_of)
        cancel = threading.Event()
        with self._lock:
            self._jobs[job.id] = job
            self._fns[job.id] = fn
            self._cancel[job.id] = cancel
        self._emit(job)
        self._pool.submit(self._run, job, fn, cancel)
        return job

    def _run(self, job: Job, fn: JobFn, cancel: threading.Event) -> None:
        if cancel.is_set():
            job.status = "cancelled"
            self._emit(job)
            return
        job.status = "running"
        job.started = time.perf_counter()
        self._emit(job)
        ctx = JobContext(job, self, cancel)
        try:
            result = fn(ctx)
            job.result = result or {}
            if cancel.is_set():
                job.status = "cancelled"
            else:
                job.status = "done"
                job.progress = 1.0
        except JobCancelled:
            job.status = "cancelled"
        except Exception as exc:
            log.exception("Job %s (%s) failed", job.id, job.title)
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.logs.append(traceback.format_exc())
        job.duration_s = time.perf_counter() - (job.started or time.perf_counter())
        self._emit(job)
        self.bus.emit("job.finished", job=job.view())

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        self._cancel[job_id].set()
        if job.status == "queued":
            job.status = "cancelled"
        job.message = "Cancelling..." if job.status == "running" else job.message
        self._emit(job)
        return job

    def retry(self, job_id: str) -> Job:
        old = self.get(job_id)
        return self.submit(old.kind, old.title, self._fns[job_id], old.backend, retry_of=old.id)

    def get(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"No job {job_id!r}")
            return self._jobs[job_id]

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [j.view() for j in reversed(jobs)]

    def wait(self, job_id: str, timeout: float = 600.0) -> Job:
        """Block until the job finishes (used by the CLI, notebooks and tests)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = self.get(job_id)
            if job.status in ("done", "failed", "cancelled"):
                return job
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not finish in {timeout}s")

    def shutdown(self) -> None:
        for ev in self._cancel.values():
            ev.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
