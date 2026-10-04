"""FastAPI application: a thin facade over :class:`calflab.app.Lab`.

No domain logic lives here. REST carries commands and queries; ``/ws`` carries
the event stream (state changes, job progress, simulation frames, logs).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from calflab import CODE_VERSION, __version__
from calflab.app import Lab, LabError
from calflab.bridge import armature_plan, rhino_build_list, rollout_action
from calflab.bridge.sculpt import save_pushed_mesh
from calflab.components import library
from calflab.fitness import presets
from calflab.graph import SOCKET_TYPES, node_types
from calflab.model.spec import LAYER_COLORS, LAYERS
from calflab.plugins import PluginWatcher, registry
from calflab.project.motions import MotionClip
from calflab.sim.metrics import METRIC_DEFS
from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from calflab_server.hops import hops_router

log = logging.getLogger(__name__)


class Hub:
    """Fans core events out to websocket clients (events arrive from any thread)."""

    def __init__(self) -> None:
        self.clients: set[asyncio.Queue[str]] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, event: dict[str, Any]) -> None:
        if self.loop is None or not self.clients:
            return
        try:
            text = json.dumps(event, default=str)
        except Exception:
            log.exception("Unserialisable event %s", event.get("type"))
            return
        with contextlib.suppress(RuntimeError):  # loop closed during shutdown
            self.loop.call_soon_threadsafe(self._fanout, text)

    def _fanout(self, text: str) -> None:
        for q in list(self.clients):
            if q.qsize() > 2000:  # a stalled client must not grow memory without bound
                continue
            q.put_nowait(text)


def create_app(lab: Lab, web_dist: Path | None = None, watch_plugins: bool = True) -> FastAPI:
    hub = Hub()
    watcher: PluginWatcher | None = None

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal watcher
        hub.loop = asyncio.get_running_loop()
        unsubscribe = lab.bus.subscribe(hub.publish)
        if watch_plugins:
            from calflab.paths import plugins_dir

            def changed(files: list[str]) -> None:
                lab.evaluator.cache.clear()
                lab.bus.emit("plugins.changed", files=files, errors=dict(registry.errors))

            watcher = PluginWatcher(plugins_dir(), on_change=changed)
            watcher.start()
        yield
        unsubscribe()
        if watcher:
            watcher.stop()

    app = FastAPI(title="CALFLAB", version=__version__, lifespan=lifespan)
    app.state.lab = lab
    app.state.hub = hub
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LabError)
    async def lab_error(_: Request, exc: LabError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def key_error(_: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"error": str(exc.args[0]) if exc.args else "not found"}, status_code=404)

    @app.exception_handler(NotImplementedError)
    async def not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse({"error": str(exc), "stub": True}, status_code=501)

    def client_of(request: Request) -> str:
        return request.headers.get("x-calflab-client", "api")

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "project": lab.project.name, "revision": lab.revision}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {
            "version": __version__,
            "code_version": CODE_VERSION,
            "units": {"length": "mm", "mass": "g", "angle": "deg"},
            "layers": [{"name": n, "color": LAYER_COLORS[n]} for n in LAYERS],
            "socket_types": SOCKET_TYPES,
            "metrics": {k: {"label": v[0], "unit": v[1], "better": v[2]} for k, v in METRIC_DEFS.items()},
            "fitness_presets": {k: p.model_dump(mode="json") for k, p in presets().items()},
            "plugin_errors": dict(registry.errors),
        }

    @app.get("/api/plugins")
    def plugins() -> dict[str, Any]:
        return {"plugins": registry.describe_all(), "errors": dict(registry.errors)}

    @app.get("/api/components")
    def components() -> list[dict[str, Any]]:
        return library().to_json()

    # ------------------------------------------------------------------ document
    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return lab.state_view()

    @app.get("/api/scene")
    def scene(candidate: str | None = None) -> dict[str, Any]:
        if candidate:
            return lab.candidate_scene(candidate)
        return lab.scene()

    @app.get("/api/commands")
    def commands() -> list[dict[str, Any]]:
        return registry.describe_all().get("command", [])

    @app.post("/api/commands/{name}")
    def execute(name: str, request: Request, params: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        return lab.execute(name, params, client_of(request))

    @app.post("/api/undo")
    def undo(request: Request) -> dict[str, Any]:
        return lab.undo(client_of(request))

    @app.post("/api/redo")
    def redo(request: Request) -> dict[str, Any]:
        return lab.redo(client_of(request))

    @app.post("/api/gesture/end")
    def gesture_end() -> dict[str, Any]:
        lab.end_gesture()
        return {"ok": True}

    @app.get("/api/history")
    def history(limit: int = 100) -> dict[str, Any]:
        return {"records": lab.log.history(limit), "cursor": lab.log.cursor}

    # ------------------------------------------------------------------ graph
    @app.get("/api/graph")
    def graph() -> dict[str, Any]:
        return lab.graph_view()

    @app.get("/api/graph/node-types")
    def graph_node_types() -> list[dict[str, Any]]:
        return [nt.describe() for nt in node_types().values()]

    @app.get("/api/graph/nodes/{node_id}/output")
    def node_output(node_id: str) -> dict[str, Any]:
        return lab.node_output(node_id)

    # ------------------------------------------------------------------ jobs
    @app.get("/api/jobs")
    def jobs() -> list[dict[str, Any]]:
        return lab.jobs.list()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        return lab.jobs.get(job_id).view(logs=True)

    @app.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str) -> dict[str, Any]:
        return lab.jobs.cancel(job_id).view()

    @app.post("/api/jobs/{job_id}/retry")
    def job_retry(job_id: str) -> dict[str, Any]:
        return lab.jobs.retry(job_id).view()

    # ------------------------------------------------------------------ runs / registry
    @app.get("/api/runs")
    def runs(kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return lab.registry.list_runs(kind, limit)

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        return lab.registry.get_run(run_id).model_dump(mode="json")

    @app.get("/api/runs/{run_id}/rollout")
    def rollout(run_id: str) -> dict[str, Any]:
        return lab.rollout_payload(run_id)

    @app.get("/api/evolve/{run_id}")
    def evolve(run_id: str) -> dict[str, Any]:
        return lab.evolve_view(run_id)

    @app.get("/api/evolve/{run_id}/candidates")
    def evolve_candidates(run_id: str) -> list[dict[str, Any]]:
        return lab.registry.list_candidates(run_id)

    @app.get("/api/candidates/{candidate_id}")
    def candidate(candidate_id: str) -> dict[str, Any]:
        return lab.registry.get_candidate(candidate_id)

    @app.get("/api/candidates/{candidate_id}/genes")
    def candidate_genes(candidate_id: str, compare: str | None = None) -> dict[str, Any]:
        return lab.candidate_genes(candidate_id, compare)

    @app.get("/api/candidates/{candidate_id}/lineage")
    def lineage(candidate_id: str) -> list[dict[str, Any]]:
        return lab.registry.lineage(candidate_id)

    @app.post("/api/candidates/{candidate_id}/simulate")
    def candidate_simulate(candidate_id: str) -> dict[str, Any]:
        return lab.simulate_candidate(candidate_id).view()

    @app.get("/api/designs")
    def designs() -> list[dict[str, Any]]:
        return lab.registry.list_designs()

    @app.get("/api/designs/{design_id}")
    def design(design_id: str) -> dict[str, Any]:
        return lab.registry.get_design(design_id).model_dump(mode="json")

    @app.post("/api/designs/{design_id}/thumbnail")
    def design_thumbnail(design_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        cap = lab.journal.add_capture(body["data_url"], {"design": design_id, "revision": lab.revision})
        lab.registry.set_design_thumbnail(design_id, cap["path"])
        lab.bus.emit("designs.changed", design_id=design_id)
        return cap

    @app.get("/api/registry/check")
    def registry_check() -> dict[str, Any]:
        return {"problems": lab.registry.check()}

    # ------------------------------------------------------------------ analyses
    @app.post("/api/analysis/{key}")
    def analysis(key: str, params: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        return lab.analysis(key, params)

    # ------------------------------------------------------------------ journal / motions
    @app.get("/api/journal")
    def journal_list() -> dict[str, Any]:
        return {"entries": lab.journal.list(), "captures": lab.journal.captures()}

    @app.get("/api/journal/{entry_id}")
    def journal_get(entry_id: str) -> dict[str, Any]:
        e = lab.journal.get(entry_id)
        return {**e.model_dump(), "links": e.links()}

    @app.post("/api/journal")
    def journal_save(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        e = lab.journal.save(body.get("title", "Untitled"), body.get("body", ""), body.get("id"), body.get("tags"))
        lab.bus.emit("journal.changed", entry_id=e.id)
        return e.model_dump()

    @app.delete("/api/journal/{entry_id}")
    def journal_delete(entry_id: str) -> dict[str, Any]:
        lab.journal.delete(entry_id)
        lab.bus.emit("journal.changed", entry_id=entry_id)
        return {"ok": True}

    @app.post("/api/captures")
    def capture(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        prov = {**body.get("provenance", {}), "revision": lab.revision, "code_version": CODE_VERSION}
        cap = lab.journal.add_capture(body["data_url"], prov, body.get("kind", "image"))
        lab.bus.emit("journal.changed", capture_id=cap["id"])
        return cap

    @app.get("/api/motions")
    def motions() -> list[dict[str, Any]]:
        return lab.motions.list()

    @app.get("/api/motions/{clip_id}")
    def motion(clip_id: str) -> dict[str, Any]:
        return lab.motions.get(clip_id).model_dump(mode="json")

    @app.post("/api/motions")
    def motion_save(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            clip = lab.motions.save(MotionClip.model_validate(body))
        except ValueError as exc:
            raise LabError(f"Invalid motion clip: {exc}") from exc
        lab.bus.emit("motions.changed", clip_id=clip.id)
        return {"id": clip.id, "frames": clip.frames, "duration_s": clip.duration_s}

    # ------------------------------------------------------------------ files
    @app.get("/api/files/{rel:path}")
    def files(rel: str) -> FileResponse:
        try:
            p = lab.project.resolve(rel)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        if not p.is_file():
            raise HTTPException(404, f"No file {rel}")
        return FileResponse(p)

    @app.post("/api/assets")
    def upload_asset(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Store a small asset (reference image) sent as a data URL."""
        import base64
        import re

        name = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(body.get("name", "asset")))
        data = str(body["data_url"]).partition(",")[2]
        rel = f"assets/references/{name}"
        p = lab.project.resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(data))
        return {"path": rel}

    # ------------------------------------------------------------------ bridges
    @app.get("/api/bridge/rhino/scene")
    def bridge_rhino_scene() -> dict[str, Any]:
        return rhino_build_list(lab.design(), lab.revision)

    @app.post("/api/bridge/rhino/push")
    def bridge_rhino_push(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return save_pushed_mesh(
            lab,
            str(body.get("target", "")),
            body.get("vertices", []),
            body.get("faces", []),
            str(body.get("name", "")),
            str(body.get("layer", "Skin")),
            str(body.get("source", "rhino")),
        )

    @app.get("/api/bridge/mesh")
    def bridge_mesh(asset: str) -> dict[str, Any]:
        """A mesh asset (e.g. a pushed sculpt) as plain vertices/faces in its body frame (mm)."""
        import trimesh

        p = lab.project.resolve(asset)
        if not p.is_file():
            raise KeyError(f"No asset {asset!r}")
        mesh = trimesh.load(p, force="mesh")
        return {"asset": asset, "vertices": mesh.vertices.round(4).tolist(), "faces": mesh.faces.tolist()}

    @app.get("/api/bridge/blender/armature")
    def bridge_blender_armature() -> dict[str, Any]:
        plan = armature_plan(lab.design().spec)
        plan["revision"] = lab.revision
        return plan

    @app.get("/api/bridge/blender/rollout/{run_id}")
    def bridge_blender_rollout(run_id: str) -> dict[str, Any]:
        rec = lab.registry.get_run(run_id)
        rest = {}
        if rec.artifacts.get("scene"):
            from calflab.project.store import read_json

            sc = read_json(lab.project.resolve(rec.artifacts["scene"]))
            rest = {j["id"]: j["rest_deg"] for j in sc["joints"]}
        return {"run_id": run_id, **rollout_action(lab.load_rollout(run_id), rest)}

    app.include_router(hops_router(lab))

    # ------------------------------------------------------------------ websocket
    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        queue: asyncio.Queue[str] = asyncio.Queue()
        hub.clients.add(queue)
        await socket.send_text(json.dumps({"type": "hello", "revision": lab.revision, "project": lab.project.name}))

        async def reader() -> None:
            while True:
                await socket.receive_text()  # clients only listen; keep the socket alive

        task = asyncio.create_task(reader())
        try:
            while not task.done():
                try:
                    text = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    text = '{"type":"ping"}'
                await socket.send_text(text)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            task.cancel()
            hub.clients.discard(queue)

    # ------------------------------------------------------------------ web app (built)
    if web_dist is not None and (web_dist / "index.html").is_file():
        dist = web_dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith(("api/", "hops/")):
                raise HTTPException(404, f"No route /{path}")
            f = (dist / path).resolve()
            if path and f.is_file() and f.is_relative_to(dist):
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app
