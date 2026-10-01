"""LocalProcessPool: parallel CPU work on this machine."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from typing import Any, ClassVar

from pydantic import BaseModel

from calflab.compute.worker import init_worker, run_task_safe
from calflab.plugins import ComputeBackend, Task, register
from calflab.schema import P


def default_workers() -> int:
    return max(1, (os.cpu_count() or 4) // 2 - 1) if (os.cpu_count() or 4) > 4 else 2


@register
class LocalProcessPool(ComputeBackend):
    """A pool of worker processes on this machine (MuJoCo on CPU)."""

    key = "local"
    label = "Local process pool"
    description = "Runs tasks in parallel worker processes on this computer."

    class Params(BaseModel):
        workers: int = P(0, ge=0, le=64, desc="Worker processes (0 = automatic: physical cores minus one).")

    _pools: ClassVar[dict[int, ProcessPoolExecutor]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def n_workers(self) -> int:
        return self.params.workers or default_workers()  # type: ignore[attr-defined]

    def available(self) -> tuple[bool, str]:
        return True, f"{self.n_workers()} worker processes"

    def _pool(self) -> ProcessPoolExecutor:
        n = self.n_workers()
        with self._lock:
            pool = self._pools.get(n)
            if pool is None:
                pool = ProcessPoolExecutor(max_workers=n, initializer=init_worker)
                self._pools[n] = pool
            return pool

    def map(
        self,
        tasks: list[Task],
        on_result: Callable[[int, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Any]:
        pool = self._pool()
        futures: dict[Future[Any], int] = {
            pool.submit(run_task_safe, t.fn, t.payload): i for i, t in enumerate(tasks)
        }
        results: list[Any] = [None] * len(tasks)
        pending = set(futures)
        while pending:
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for f in done:
                i = futures[f]
                try:
                    results[i] = f.result()
                except Exception as exc:  # worker crashed
                    results[i] = {"error": f"{type(exc).__name__}: {exc}"}
                if on_result:
                    on_result(i, results[i])
            if cancelled and cancelled():
                for f in pending:
                    f.cancel()
                for f in pending:
                    results[futures[f]] = {"error": "cancelled"}
                break
        return results

    def shutdown(self) -> None:
        """Pools are shared and reused; they are released by ``shutdown_all``."""

    @classmethod
    def shutdown_all(cls) -> None:
        with cls._lock:
            for pool in cls._pools.values():
                pool.shutdown(wait=False, cancel_futures=True)
            cls._pools.clear()


@register
class InProcess(ComputeBackend):
    """Runs tasks one after another in the calling process (debugging, tests)."""

    key = "inline"
    label = "In-process (serial)"
    description = "Runs tasks serially in the server process. Slow, but easy to debug."

    def available(self) -> tuple[bool, str]:
        return True, "serial"

    def map(
        self,
        tasks: list[Task],
        on_result: Callable[[int, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Any]:
        results: list[Any] = []
        for i, t in enumerate(tasks):
            if cancelled and cancelled():
                results.append({"error": "cancelled"})
                continue
            r = run_task_safe(t.fn, t.payload)
            results.append(r)
            if on_result:
                on_result(i, r)
        return results
