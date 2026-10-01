"""The Lab: one open project plus everything clients do to it.

All clients (web, Rhino, Blender, CLI, notebooks) drive the same ``Lab``
through the server. Document edits go through :meth:`Lab.execute` so they are
logged, undoable and broadcast; long operations are jobs.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from calflab import CODE_VERSION
from calflab import units as u
from calflab.app.events import EventBus
from calflab.app.jobs import Job, JobContext, JobManager
from calflab.app.scene import build_scene, foot_tracks
from calflab.components import library
from calflab.design import EvaluatedDesign
from calflab.graph import Cache, EvalContext, Evaluator, Graph, NodeResult, node_types, summarize
from calflab.plugins import ExportContext, load_plugins, registry
from calflab.project import (
    CommandLog,
    CommandRecord,
    DesignRecord,
    DocumentState,
    Journal,
    Project,
    Registry,
    RunRecord,
)
from calflab.project.commands import LOG_FILE
from calflab.project.motions import MotionLibrary
from calflab.project.store import slugify, write_json
from calflab.sim.rollout import Rollout

log = logging.getLogger(__name__)

COALESCE_WINDOW_S = 1.5


class LabError(Exception):
    """A user-facing error (shown in the command line / log console)."""


class Lab:
    def __init__(self, project: Project):
        load_plugins()
        self.project = project
        self.bus = EventBus()
        self.jobs = JobManager(self.bus)
        self.registry = Registry(project)
        self.journal = Journal(project)
        self.motions = MotionLibrary(project)
        self.log = CommandLog(project.path / LOG_FILE)
        self.evaluator = Evaluator(Cache(disk_dir=project.path / ".cache"))
        self.revision = self.log.total
        self.backend_key = "local"
        self._lock = threading.RLock()
        self._last_push = 0.0

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def open(cls, path: Path, create: bool = True, name: str | None = None) -> Lab:
        path = Path(path)
        if (path / "project.calflab.json").is_file():
            return cls(Project.open(path))
        if not create:
            raise FileNotFoundError(f"No CALFLAB project at {path}")
        load_plugins()
        return cls(Project.create(path, name))

    def close(self) -> None:
        self.jobs.shutdown()
        self.registry.close()

    @property
    def state(self) -> DocumentState:
        return self.project.state

    # ------------------------------------------------------------------ commands
    def execute(self, name: str, params: dict[str, Any] | None = None, client: str = "api") -> dict[str, Any]:
        """Run a named command. Mutating commands are logged and broadcast."""
        try:
            cls = registry.get("command", name)
        except KeyError as exc:
            raise LabError(str(exc)) from exc
        try:
            cmd = cls(params or {})
        except Exception as exc:
            raise LabError(f"{name}: invalid parameters: {exc}") from exc
        if not cls.mutates:  # type: ignore[attr-defined]
            result = cmd.run(self, self.state)  # type: ignore[attr-defined]
            return {"result": result, "revision": self.revision, "changed": []}
        with self._lock:
            work = self.state.model_copy(deep=True)
            result = cmd.run(self, work)  # type: ignore[attr-defined]
            before_dump = self.state.model_dump(mode="json")
            after_dump = work.model_dump(mode="json")
            changed = [k for k in after_dump if after_dump[k] != before_dump[k]]
            if changed:
                now = time.monotonic()
                if now - self._last_push > COALESCE_WINDOW_S:
                    self.log.break_coalescing()
                self._last_push = now
                self.log.push(
                    CommandRecord(
                        command=name,
                        params=cmd.params.model_dump(mode="json"),
                        title=cmd.title(),  # type: ignore[attr-defined]
                        client=client,
                        before={k: before_dump[k] for k in changed},
                        after={k: after_dump[k] for k in changed},
                        coalesce=getattr(cmd, "coalesce_key", lambda: None)(),
                    )
                )
                self._commit(work, changed, client, name)
        return {"result": result, "revision": self.revision, "changed": changed}

    def _commit(self, state: DocumentState, changed: list[str], client: str, cause: str) -> None:
        self.project.save(state)
        self.revision += 1
        self.bus.emit(
            "state.changed",
            revision=self.revision,
            changed=changed,
            client=client,
            cause=cause,
            can_undo=self.log.can_undo,
            can_redo=self.log.can_redo,
        )

    def _apply_patch(self, patch: dict[str, Any], client: str, cause: str) -> None:
        dump = self.state.model_dump(mode="json")
        dump.update(patch)
        self._commit(DocumentState.model_validate(dump), list(patch), client, cause)

    def undo(self, client: str = "api") -> dict[str, Any]:
        with self._lock:
            rec = self.log.undo()
            if rec is None:
                raise LabError("Nothing to undo")
            self._apply_patch(rec.before, client, f"undo:{rec.command}")
            return {"undone": rec.title or rec.command, "revision": self.revision}

    def redo(self, client: str = "api") -> dict[str, Any]:
        with self._lock:
            rec = self.log.redo()
            if rec is None:
                raise LabError("Nothing to redo")
            self._apply_patch(rec.after, client, f"redo:{rec.command}")
            return {"redone": rec.title or rec.command, "revision": self.revision}

    def end_gesture(self) -> None:
        """A drag/slider gesture ended: the next edit starts a new undo step."""
        self.log.break_coalescing()

    # ------------------------------------------------------------------ evaluation
    def _ctx(self, state: DocumentState | None = None, **kw: Any) -> EvalContext:
        s = state or self.state
        return EvalContext(overrides=list(s.overrides), project_dir=self.project.path, **kw)

    def evaluate(
        self, graph: Graph | None = None, targets: list[str] | None = None, **kw: Any
    ) -> dict[str, NodeResult]:
        return self.evaluator.evaluate(graph or self.state.graph, self._ctx(), targets=targets, **kw)

    def _role_output(self, role: str, socket: str, graph: Graph | None = None) -> Any:
        g = graph or self.state.graph
        try:
            node = g.role(role)
        except KeyError as exc:
            raise LabError(str(exc)) from exc
        res = self.evaluate(g, targets=[node.id])[node.id]
        if not res.ok:
            raise LabError(f"Node '{node.id}' ({role}): {'; '.join(res.messages) or res.status}")
        return res.outputs[socket]

    def design(self, graph: Graph | None = None) -> EvaluatedDesign:
        """The evaluated design of the current document (cached)."""
        return self._role_output("design", "design", graph)

    def variant_graph(
        self, genes: dict[str, Any] | None = None, controller: dict[str, Any] | None = None
    ) -> Graph:
        """A copy of the document graph with genome/controller params replaced
        (used to preview evolved candidates without editing the document)."""
        g = self.state.graph.model_copy(deep=True)
        if genes is not None:
            g.role("genome").params = dict(genes)
        if controller is not None:
            node = g.role("controller")
            if controller.get("key") and node.type != f"controller:{controller['key']}":
                node.type = f"controller:{controller['key']}"
            node.params = dict(controller.get("params", {}))
        return g

    def scene(self, graph: Graph | None = None) -> dict[str, Any]:
        s = build_scene(self.design(graph), self.state.layers)
        s["revision"] = self.revision
        return s

    def graph_view(self) -> dict[str, Any]:
        """The graph with per-node evaluation status and socket lists for the node editor."""
        graph = self.state.graph
        types = node_types()
        results = self.evaluator.evaluate(graph, self._ctx(), types=types)
        status: dict[str, Any] = {}
        for n in graph.nodes:
            r = results.get(n.id)
            nt = types.get(n.type)
            status[n.id] = {
                "status": r.status if r else "error",
                "messages": r.messages if r else ["not evaluated"],
                "cached": r.cached if r else False,
                "duration_ms": round(r.duration_ms, 2) if r else 0,
                "inputs": [s.__dict__ for s in nt.inputs_for(n.params)] if nt else [],
                "outputs": [s.__dict__ for s in nt.outputs_for(n.params)] if nt else [],
                "expensive": nt.expensive if nt else False,
            }
        return {"graph": graph.model_dump(mode="json"), "status": status, "revision": self.revision}

    def node_output(self, node_id: str) -> dict[str, Any]:
        res = self.evaluate(targets=[node_id]).get(node_id)
        if res is None:
            raise LabError(f"No node {node_id!r}")
        return {
            "node": node_id,
            "status": res.status,
            "messages": res.messages,
            "outputs": {k: summarize(v) for k, v in res.outputs.items()},
        }

    def state_view(self) -> dict[str, Any]:
        s = self.state
        return {
            "project": {"name": self.project.name, "path": str(self.project.path)},
            "revision": self.revision,
            "can_undo": self.log.can_undo,
            "can_redo": self.log.can_redo,
            "overrides": [o.model_dump(mode="json") for o in s.overrides],
            "layers": {k: v.model_dump() for k, v in s.layers.items()},
            "references": [r.model_dump(mode="json") for r in s.references],
            "settings": s.settings,
            "roles": s.graph.roles,
            "backend": self.backend_key,
            "code_version": CODE_VERSION,
        }

    # ------------------------------------------------------------------ simulation
    def _frames_payload(self, chunk: dict[str, Any]) -> dict[str, Any]:
        pos = u.from_si(np.asarray(chunk["pos"], dtype=float), "mm")
        return {
            "start": int(chunk["start"]),
            "t": [round(float(x), 4) for x in chunk["t"]],
            "pos": np.round(pos, 2).reshape(len(chunk["t"]), -1).tolist(),
            "quat": np.round(np.asarray(chunk["quat"], dtype=float), 5).reshape(len(chunk["t"]), -1).tolist(),
        }

    def run_sim(
        self,
        graph: Graph | None = None,
        title: str = "Simulate",
        parent: str | None = None,
        client: str = "api",
    ) -> Job:
        """Run the simulation node as a job; poses stream out as ``sim.frames`` events."""
        g = (graph or self.state.graph).model_copy(deep=True)
        state = self.state.model_copy(deep=True)
        try:
            sim_id = g.role("simulation").id
        except KeyError as exc:
            raise LabError(str(exc)) from exc
        # fail fast (in the caller) if the pipeline feeding the simulation is broken
        for role, socket in (("design", "design"), ("model", "model"), ("controller", "controller")):
            self._role_output(role, socket, g)

        def work(job: JobContext) -> dict[str, Any]:
            t0 = time.perf_counter()
            design = self._role_output("design", "design", g)
            model = self._role_output("model", "model", g)
            self.bus.emit("sim.started", job=job.job.id, body_ids=model.body_ids, scene=build_scene(design, state.layers))
            streamed = [0]

            def on_frames(chunk: dict[str, Any]) -> None:
                streamed[0] += len(chunk["t"])
                self.bus.emit("sim.frames", job=job.job.id, **self._frames_payload(chunk))
                job.report(message=f"{streamed[0]} frames")

            ctx = self._ctx(state, on_frames=on_frames, cancelled=job.cancelled)
            results = self.evaluator.evaluate(g, ctx, run_expensive={sim_id})
            res = results[sim_id]
            if job.cancelled():
                return {}
            if not res.ok:
                raise LabError(f"Simulation failed: {'; '.join(res.messages) or res.status}")
            rollout: Rollout = res.outputs["rollout"]
            existing = self.registry.find_run_by_key(res.key or "") if res.key else None
            if existing is not None:
                job.log(f"Identical inputs: reusing run {existing.id}")
                self.bus.emit("sim.done", job=job.job.id, run_id=existing.id, cached=True)
                return {"run_id": existing.id, "cached": True, "metrics": existing.metrics}

            metrics = self._ok_output(results, g, "metrics", "metrics")
            fitness = self._ok_output(results, g, "fitness", "fitness")
            run_id = self.registry.new_run_id("sim")
            run_dir = self.registry.run_dir(run_id)
            rollout.save(run_dir / "rollout.npz")
            write_json(run_dir / "scene.json", build_scene(design, state.layers))
            (run_dir / "model.xml").write_text(model.xml, encoding="utf-8")
            sim_node = g.node(sim_id)
            preset = None
            if fitness is not None:
                from calflab.fitness import presets

                p = presets().get(str(g.role("fitness").params.get("preset")))
                preset = {"preset": p.model_dump(mode="json") if p else None, "result": fitness}
            record = RunRecord(
                id=run_id,
                kind="sim",
                title=title,
                duration_s=time.perf_counter() - t0,
                seed=int(sim_node.params.get("seed", 0)),
                backend="local",
                inputs={
                    "sim": sim_node.params,
                    "compile": g.role("model").params,
                    "generator": g.role("design").type,
                    "generator_params": g.role("design").params,
                },
                genome=design.genome.model_dump(mode="json"),
                overrides=[o.model_dump(mode="json") for o in state.overrides if o.enabled],
                controller=self._role_output("controller", "controller", g),
                fitness=preset,
                metrics=metrics or {},
                artifacts={
                    "rollout": f"runs/{run_id}/rollout.npz",
                    "scene": f"runs/{run_id}/scene.json",
                    "mjcf": f"runs/{run_id}/model.xml",
                },
                parent=parent,
                cache_key=res.key,
            )
            self.registry.save_run(record)
            job.log(f"Run {run_id}: speed {record.metrics.get('speed_mps', 0):.3f} m/s")
            self.bus.emit("sim.done", job=job.job.id, run_id=run_id, cached=False)
            self.bus.emit("runs.changed", run_id=run_id)
            return {"run_id": run_id, "cached": False, "metrics": record.metrics}

        return self.jobs.submit("sim", title, work)

    @staticmethod
    def _ok_output(results: dict[str, NodeResult], g: Graph, role: str, socket: str) -> Any:
        nid = g.roles.get(role)
        r = results.get(nid) if nid else None
        return r.outputs.get(socket) if r is not None and r.ok else None

    def load_rollout(self, run_id: str) -> Rollout:
        rec = self.registry.get_run(run_id)
        rel = rec.artifacts.get("rollout")
        if not rel:
            raise LabError(f"Run {run_id} has no rollout")
        return Rollout.load(self.project.resolve(rel))

    def rollout_payload(self, run_id: str) -> dict[str, Any]:
        """Recorded poses for playback/scrubbing (mm, quaternions w-first)."""
        from calflab.project.store import read_json
        from calflab.sim.metrics import timeseries

        r = self.load_rollout(run_id)
        rec = self.registry.get_run(run_id)
        scene_rel = rec.artifacts.get("scene")
        frames = self._frames_payload({"start": 0, "t": r.t, "pos": r.body_pos, "quat": r.body_quat})
        scene = read_json(self.project.resolve(scene_rel)) if scene_rel else None
        tracks = foot_tracks(r, scene) if scene else {"foot_pos": [], "support": []}
        return {
            **tracks,
            "run_id": run_id,
            "body_ids": r.body_ids,
            "dt": r.meta.get("record_dt"),
            "t": frames["t"],
            "pos": frames["pos"],
            "quat": frames["quat"],
            "com": np.round(u.from_si(r.com.astype(float), "mm"), 2).tolist(),
            "foot_force": np.round(r.foot_force.astype(float), 2).tolist(),
            "foot_geoms": r.foot_geoms,
            "series": timeseries(r),
            "scene": scene,
            "metrics": rec.metrics,
        }

    # ------------------------------------------------------------------ evolution
    def run_evolve(
        self,
        optimizer: str = "map_elites_cma",
        params: dict[str, Any] | None = None,
        backend: str | None = None,
        sim: dict[str, Any] | None = None,
    ) -> Job:
        from calflab.evolve import EvolveProblem
        from calflab.fitness import presets

        g = self.state.graph.model_copy(deep=True)
        state = self.state.model_copy(deep=True)
        try:
            opt = registry.get("optimizer", optimizer)(params or {})
        except Exception as exc:
            raise LabError(f"Optimizer {optimizer!r}: {exc}") from exc
        if opt.stub:
            raise LabError(f"Optimizer {optimizer!r} is scaffolded but not implemented yet")
        bkey = backend or self.backend_key
        backend_obj = registry.get("compute_backend", bkey)()
        ok, reason = backend_obj.available()  # type: ignore[attr-defined]
        if not ok:
            raise LabError(f"Compute backend {bkey!r} is not available: {reason}")
        design = self.design(g)
        preset = presets().get(str(g.role("fitness").params.get("preset")))
        if preset is None:
            raise LabError("The fitness node has no valid preset")
        ctrl = self._role_output("controller", "controller", g)
        sim_params = {**g.role("simulation").params, **(sim or {})}
        run_id = self.registry.new_run_id("evolve")

        def work(job: JobContext) -> dict[str, Any]:
            t0 = time.perf_counter()
            run_dir = self.registry.run_dir(run_id)
            record = RunRecord(
                id=run_id,
                kind="evolve",
                title=f"{opt.label}",
                status="running",
                seed=int(opt.params.seed) if hasattr(opt.params, "seed") else None,
                backend=bkey,
                inputs={"optimizer": optimizer, "params": opt.params.model_dump(mode="json"), "sim": sim_params,
                        "compile": g.role("model").params},
                genome=design.genome.model_dump(mode="json"),
                overrides=[o.model_dump(mode="json") for o in state.overrides if o.enabled],
                controller=ctrl,
                fitness={"preset": preset.model_dump(mode="json")},
            )
            self.registry.save_run(record)
            self.bus.emit("runs.changed", run_id=run_id)
            problem = EvolveProblem(
                genome=design.genome.model_dump(mode="json"),
                overrides=record.overrides,
                generator=g.role("design").type.split(":", 1)[1],
                generator_params=g.role("design").params,
                compile=g.role("model").params,
                sim=sim_params,
                controller=ctrl,
                fitness=preset.model_dump(mode="json"),
                run_id=run_id,
                cancelled=job.cancelled,
            )

            def report(kind: str, **kw: Any) -> None:
                if kind == "progress":
                    job.report(kw["fraction"], f"generation {kw['generation'] + 1}")
                    return
                result = kw["result"]
                entry = kw["entry"]
                self.registry.save_candidates(run_id, [c.model_dump(mode="json") for c in kw["candidates"]])
                write_json(run_dir / "archive.json", {"archive": result.archive, "history": result.history})
                best = entry["best"]
                job.log(
                    f"gen {entry['generation']}: best {best:.3f}, {entry['elites']} elites, "
                    f"{entry['evals']} rollouts"
                    if best is not None
                    else f"gen {entry['generation']}: no valid candidates"
                )
                self.bus.emit("evolve.update", run_id=run_id, job=job.job.id, entry=entry,
                              archive=result.archive, history=result.history)

            self.bus.emit("evolve.started", run_id=run_id, job=job.job.id)
            result = opt.run(problem, backend_obj, report)  # type: ignore[attr-defined]
            ok_c = [c for c in result.candidates if c.status != "failed"]
            best_c = max(ok_c, key=lambda c: c.fitness, default=None)
            record.status = "cancelled" if job.cancelled() else "done"
            record.duration_s = time.perf_counter() - t0
            record.metrics = {
                "evals": result.evals,
                "candidates": len(result.candidates),
                "elites": len(result.cells),
                "best_fitness": best_c.fitness if best_c else None,
                "best_candidate": best_c.id if best_c else None,
                "history": result.history,
            }
            if best_c is not None:
                record.fitness = {"preset": preset.model_dump(mode="json"),
                                  "result": {"total": best_c.fitness, "terms": best_c.fitness_terms}}
            record.artifacts = {
                "archive": f"runs/{run_id}/archive.json",
                "candidates": f"runs/{run_id}/candidates.jsonl",
            }
            write_json(run_dir / "archive.json", {"archive": result.archive, "history": result.history})
            if not (run_dir / "candidates.jsonl").exists():
                (run_dir / "candidates.jsonl").write_text("", encoding="utf-8")
            self.registry.save_run(record)
            self.bus.emit("evolve.done", run_id=run_id, job=job.job.id)
            self.bus.emit("runs.changed", run_id=run_id)
            return {"run_id": run_id, "best_candidate": record.metrics["best_candidate"],
                    "best_fitness": record.metrics["best_fitness"]}

        job = self.jobs.submit("evolve", f"Evolve ({opt.label})", work, backend=bkey)
        job.result = {"run_id": run_id}
        return job

    def evolve_view(self, run_id: str) -> dict[str, Any]:
        from calflab.project.store import read_json

        rec = self.registry.get_run(run_id)
        f = self.registry.run_dir(run_id) / "archive.json"
        data = read_json(f) if f.is_file() else {"archive": {}, "history": []}
        return {"run": rec.model_dump(mode="json"), **data}

    def simulate_candidate(self, candidate_id: str) -> Job:
        """Replay an evolved candidate (its own body and gait) without editing the document."""
        try:
            c = self.registry.get_candidate(candidate_id)
        except KeyError as exc:
            raise LabError(str(exc)) from exc
        g = self.variant_graph(c["genome"]["values"], c["controller"])
        return self.run_sim(g, title=f"Candidate {candidate_id}", parent=candidate_id)

    # ------------------------------------------------------------------ bake / export
    def bake(self, name: str, note: str = "") -> DesignRecord:
        """Freeze the current state into an immutable, versioned Design."""
        design = self.design()
        version = self.registry.next_design_version(name)
        record = DesignRecord(
            id=f"{slugify(name, 'design')}-v{version:03d}",
            name=name,
            version=version,
            note=note,
            genome=design.genome.model_dump(mode="json"),
            overrides=[o.model_dump(mode="json") for o in self.state.overrides],
            graph=self.state.graph.model_dump(mode="json"),
            spec=design.spec.model_dump(mode="json"),
            mass_g=design.spec.total_mass_g(),
            command_seq=self.log.total,
        )
        self.registry.save_design(record)
        self.registry.save_run(
            RunRecord(
                id=self.registry.new_run_id("bake"),
                kind="bake",
                title=f"Bake {record.id}",
                genome=record.genome,
                overrides=record.overrides,
                artifacts={"design": f"designs/{record.id}/design.json"},
                parent=record.id,
            )
        )
        self.bus.emit("designs.changed", design_id=record.id)
        self.bus.emit("log", level="info", source="bake", message=f"Baked design {record.id}")
        return record

    def export_context(self, design_name: str = "current", run_id: str | None = None) -> ExportContext:
        d = self.design()
        run = self.registry.get_run(run_id).model_dump(mode="json") if run_id else None
        return ExportContext(
            spec=d.spec,
            genes=d.genome.values,
            element_params=d.element_params,
            library=library(),
            project_dir=self.project.path,
            design_name=design_name,
            run=run,
        )

    def export(
        self,
        exporter: str,
        params: dict[str, Any] | None = None,
        selection: list[str] | None = None,
        run_id: str | None = None,
    ) -> Job:
        try:
            cls = registry.get("exporter", exporter)
            exp = cls(params or {})
        except Exception as exc:
            raise LabError(f"Exporter {exporter!r}: {exc}") from exc
        ctx = self.export_context(run_id=run_id)
        ctx.selection = selection or []

        def work(job: JobContext) -> dict[str, Any]:
            t0 = time.perf_counter()
            rid = self.registry.new_run_id("export")
            out_dir = self.project.dir("exports") / exporter
            job.report(0.1, f"Exporting with {exp.label}")
            paths = exp.export(ctx, out_dir)  # type: ignore[attr-defined]
            rels = {Path(p).name: self.project.rel(Path(p)) for p in paths}
            self.registry.save_run(
                RunRecord(
                    id=rid,
                    kind="export",
                    title=f"Export {exp.label}",
                    duration_s=time.perf_counter() - t0,
                    inputs={"exporter": exporter, "params": exp.params.model_dump(mode="json"),
                            "selection": ctx.selection},
                    genome={"definition": ctx.spec.metadata.get("genome_definition"), "values": ctx.genes},
                    overrides=[o.model_dump(mode="json") for o in self.state.overrides if o.enabled],
                    artifacts=rels,
                    parent=run_id,
                )
            )
            for name in rels:
                job.log(f"Wrote {name}")
            self.bus.emit("runs.changed", run_id=rid)
            return {"run_id": rid, "files": rels}

        return self.jobs.submit("export", f"Export: {exp.label}", work)

    def analysis(self, key: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            cls = registry.get("analysis", key)
            return cls(params or {}).run(self)  # type: ignore[attr-defined]
        except KeyError as exc:
            raise LabError(str(exc)) from exc
