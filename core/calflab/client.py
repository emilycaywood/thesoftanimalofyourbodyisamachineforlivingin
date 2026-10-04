"""Python client for a running CALFLAB server.

Use it from Jupyter, Grasshopper (GH Python 3) or scripts. It talks to the
same server and project as the web app, so edits made here appear live there.

    from calflab.client import Client
    lab = Client()
    lab.set_genes(shank_length=190)
    run = lab.simulate()
    print(run["metrics"]["speed_mps"])
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx


class CalflabError(RuntimeError):
    """The server rejected a request (message is user-facing)."""


class Client:
    def __init__(self, url: str = "http://127.0.0.1:8000", client: str = "python", timeout: float = 60.0):
        self.url = url.rstrip("/")
        self._http = httpx.Client(base_url=self.url, timeout=timeout, headers={"x-calflab-client": client})

    # ------------------------------------------------------------------ plumbing
    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.ConnectError as exc:
            raise CalflabError(f"No CALFLAB server at {self.url}. Start it with: calflab lab") from exc
        if r.status_code >= 400:
            try:
                msg = r.json().get("error") or r.json().get("detail") or r.text
            except Exception:
                msg = r.text
            raise CalflabError(str(msg))
        return r.json()

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, json=body if body is not None else {})

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ document
    def health(self) -> dict[str, Any]:
        return self.get("/api/health")

    def state(self) -> dict[str, Any]:
        return self.get("/api/state")

    def scene(self) -> dict[str, Any]:
        """The evaluated design: bodies, joints, mass, CoM, element parameters (mm, g, deg)."""
        return self.get("/api/scene")

    def genome(self) -> dict[str, Any]:
        return self.scene()["genome"]["values"]

    def execute(self, command: str, **params: Any) -> Any:
        """Run any named command (see ``commands()``)."""
        return self.post(f"/api/commands/{command}", params)["result"]

    def commands(self) -> list[dict[str, Any]]:
        return self.get("/api/commands")

    def set_genes(self, **values: Any) -> dict[str, Any]:
        return self.execute("set_genes", values=values)

    def override(self, target: str, param: str, value: float, name: str = "") -> dict[str, Any]:
        return self.execute("add_override", target=target, param=param, value=value, name=name, source="python")

    def undo(self) -> dict[str, Any]:
        return self.post("/api/undo")

    def redo(self) -> dict[str, Any]:
        return self.post("/api/redo")

    def bake(self, name: str, note: str = "") -> dict[str, Any]:
        return self.execute("bake", name=name, note=note)

    # ------------------------------------------------------------------ jobs
    def job(self, job_id: str) -> dict[str, Any]:
        return self.get(f"/api/jobs/{job_id}")

    def wait(self, job_id: str, timeout: float = 3600.0, poll: float = 0.25) -> dict[str, Any]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = self.job(job_id)
            if job["status"] in ("done", "failed", "cancelled"):
                if job["status"] == "failed":
                    raise CalflabError(f"Job {job_id} failed: {job['error']}")
                return job
            time.sleep(poll)
        raise TimeoutError(f"Job {job_id} did not finish in {timeout}s")

    def simulate(self, wait: bool = True) -> dict[str, Any]:
        """Run the simulation node. Returns the run record (or the job if ``wait=False``)."""
        job_id = self.execute("run_sim")["job"]
        if not wait:
            return self.job(job_id)
        return self.run(self.wait(job_id)["result"]["run_id"])

    def evolve(self, wait: bool = False, **params: Any) -> dict[str, Any]:
        r = self.execute("run_evolve", params=params)
        return self.wait(r["job"]) if wait else r

    def export(self, exporter: str, wait: bool = True, **params: Any) -> dict[str, Any]:
        job_id = self.execute("export", exporter=exporter, params=params)["job"]
        return self.wait(job_id) if wait else self.job(job_id)

    # ------------------------------------------------------------------ registry
    def runs(self, kind: str | None = None) -> list[dict[str, Any]]:
        return self.get("/api/runs", kind=kind)

    def run(self, run_id: str) -> dict[str, Any]:
        return self.get(f"/api/runs/{run_id}")

    def rollout(self, run_id: str) -> dict[str, Any]:
        return self.get(f"/api/runs/{run_id}/rollout")

    def designs(self) -> list[dict[str, Any]]:
        return self.get("/api/designs")

    def analysis(self, key: str, **params: Any) -> dict[str, Any]:
        return self.post(f"/api/analysis/{key}", params)

    # ------------------------------------------------------------------ bridges
    def rhino_scene(self) -> dict[str, Any]:
        return self.get("/api/bridge/rhino/scene")

    def armature(self) -> dict[str, Any]:
        return self.get("/api/bridge/blender/armature")

    # ------------------------------------------------------------------ events
    def events(self) -> Iterator[dict[str, Any]]:
        """Yield live events (state changes, job progress, sim frames) until closed."""
        from websockets.sync.client import connect

        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        with connect(ws_url) as ws:
            for message in ws:
                event = json.loads(message)
                if event.get("type") != "ping":
                    yield event
