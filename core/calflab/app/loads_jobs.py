"""Lab jobs for the feral calf's mechanical analysis (ADR-069): load runs per
scenario, the belt comparison, and the data behind the Belts and springs panel.

Every load run is a run record of kind ``loads`` with its rollout (so it
replays in the viewport), a per-frame CSV and a per-joint summary CSV.
"""

from __future__ import annotations

import time
from typing import Any

from calflab.app.jobs import Job, JobContext
from calflab.app.scene import build_scene, geometry_record
from calflab.components import library
from calflab.mech.compare import belt_comparison, comparison_csv, run_scenario
from calflab.mech.loads import (
    SCENARIOS,
    analyse,
    frames_csv,
    spring_relief,
    static_spring_report,
    summary_csv,
)
from calflab.model.genome import Genome
from calflab.project import RunRecord
from calflab.project.store import write_json


class FeralError(Exception):
    """A request that does not apply to this document (shown to the user)."""


def _require_feral(lab: Any) -> tuple[Any, Any]:
    g = lab.state.graph
    node = g.role("design")
    if node.type != "part_generator:feral_calf":
        raise FeralError("This analysis is for the final feral calf (part generator 'feral_calf'); this document builds "
                         f"{node.type.split(':', 1)[-1]!r}.")
    return g, node


def refuse_invalid_belts(design: Any) -> None:
    """A design whose belt drives fail a check is not simulated (ADR-063)."""
    meta = design.spec.metadata.get("feral")
    if meta and not meta.get("belts_ok", True):
        bad = [d for d, r in meta["belt_drives"].items() if not r["ok"]]
        raise FeralError(f"Simulation refused: the belt drive at the {', '.join(bad)} fails a check. Choose a valid belt in the "
                         "Belts panel (or change the body) first; the reasons are in the design's warnings.")


def _springs_off(genome: Genome) -> Genome:
    values = dict(genome.values)
    for k in ("spring_stifle", "spring_hock", "spring_shoulder"):
        if k in values:
            values[k] = False
    return Genome(definition=genome.definition, version=genome.version, values=values)


def run_loads(lab: Any, scenarios: list[str] | None = None, compare_springs: bool = True) -> Job:
    """Simulate the scenarios (quiet standing, slow walk, lying down and rising) and log every joint's loads."""
    from calflab.design import build_design

    g, node = _require_feral(lab)
    names = scenarios or list(SCENARIOS)
    unknown = [s for s in names if s not in SCENARIOS]
    if unknown:
        raise FeralError(f"Unknown scenario(s) {unknown}; choose from {list(SCENARIOS)}")
    state = lab.state.model_copy(deep=True)
    design = lab.design()
    refuse_invalid_belts(design)
    overrides = [o for o in state.overrides if o.enabled]
    ctrl_node = g.role("controller")
    ctrl_params = dict(ctrl_node.params) if ctrl_node.type == "controller:feral_motion" else {}
    compile_params = dict(g.role("model").params)
    gen_params = dict(node.params)

    def work(job: JobContext) -> dict[str, Any]:
        lib = library()
        meta = design.spec.metadata["feral"]
        no_springs = None
        if compare_springs:
            no_springs = build_design(_springs_off(design.genome), overrides, "feral_calf", gen_params, lab.project.path)
        out: dict[str, Any] = {"runs": {}}
        for n, name in enumerate(names):
            if job.cancelled():
                break
            label = SCENARIOS[name]["label"]
            job.report(progress=n / len(names), message=f"{label}: simulating")
            t0 = time.perf_counter()
            rollout, used, cycle = run_scenario(design.spec, lib, SCENARIOS[name]["mode"], ctrl_params, compile_params)
            res = analyse(rollout, design.spec, lib, cycle, meta["checks"], meta["belt_drives"])
            relief: list[dict[str, Any]] = []
            if no_springs is not None and not job.cancelled():
                job.report(message=f"{label}: the same without springs")
                r0, _, _ = run_scenario(no_springs.spec, lib, SCENARIOS[name]["mode"], ctrl_params, compile_params)
                res0 = analyse(r0, no_springs.spec, lib, cycle, meta["checks"], meta["belt_drives"])
                relief = spring_relief(res, res0)
            run_id = lab.registry.new_run_id("loads")
            run_dir = lab.registry.run_dir(run_id)
            rollout.save(run_dir / "rollout.npz")
            write_json(run_dir / "scene.json", build_scene(design, state.layers, state.settings))
            (run_dir / "loads.csv").write_bytes(frames_csv(res).encode("utf-8"))
            (run_dir / "loads_summary.csv").write_bytes(summary_csv(res).encode("utf-8"))
            report = {"scenario": name, "label": label, "summary": res["summary"], "flags": res["flags"],
                      "outcome": res["outcome"], "window_s": res["window_s"], "checks": res["checks"],
                      "spring_relief": relief, "springs_standing": static_spring_report(design.spec),
                      "belt_drives": {d: {k: r[k] for k in ("choice", "c_mm", "d1_mm", "d2_mm", "ratio", "ok", "unknown",
                                                               "allowable_working_tension_n", "breaking_strength_n")}
                                      for d, r in meta["belt_drives"].items()},
                      "missing_masses": design.spec.metadata.get("missing_masses", []),
                      "provisional": meta["provisional"], "total_mass_g": design.spec.total_mass_g()}
            write_json(run_dir / "loads.json", report)
            worst = max(res["summary"], key=lambda r: r["pct_stall_peak"]) if res["summary"] else None
            record = RunRecord(
                id=run_id, kind="loads", title=f"Loads: {label}", duration_s=time.perf_counter() - t0,
                seed=0, backend="local",
                inputs={"scenario": name, "controller_mode": used.get("mode"), "compile": {**compile_params, "torque_derating": 1.0},
                        "generator": node.type, "generator_params": gen_params, "mass": lab._mass_record(design),
                        "geometry": geometry_record(design), "belt_catalog": meta["belt_catalog"],
                        "springs_compared": no_springs is not None},
                genome=design.genome.model_dump(mode="json"),
                overrides=[o.model_dump(mode="json") for o in overrides],
                controller={"key": "feral_motion", "params": used},
                metrics={"flags": len(res["flags"]), "fell": res["outcome"]["fell"],
                         "worst_pct_stall": worst["pct_stall_peak"] if worst else None,
                         "worst_joint": worst["joint"] if worst else None,
                         "distance_mm": res["outcome"]["distance_mm"]},
                artifacts={"rollout": f"runs/{run_id}/rollout.npz", "scene": f"runs/{run_id}/scene.json",
                           "loads_csv": f"runs/{run_id}/loads.csv", "summary_csv": f"runs/{run_id}/loads_summary.csv",
                           "report": f"runs/{run_id}/loads.json"},
            )
            lab.registry.save_run(record)
            lab.bus.emit("runs.changed", run_id=run_id)
            job.log(f"{label}: run {run_id}, {len(res['flags'])} flag(s)"
                    + (", FELL" if res["outcome"]["fell"] else ""))
            for f in res["flags"]:
                job.log(f"  {f}")
            out["runs"][name] = run_id
        return out

    return lab.jobs.submit("loads", "Load analysis", work)


def run_belt_comparison(lab: Any) -> Job:
    """The walk on every belt system x pulley pair of the catalog, everything else fixed."""
    g, node = _require_feral(lab)
    state = lab.state.model_copy(deep=True)
    design = lab.design()
    overrides = [o for o in state.overrides if o.enabled]
    ctrl_node = g.role("controller")
    ctrl_params = dict(ctrl_node.params) if ctrl_node.type == "controller:feral_motion" else {}
    compile_params = dict(g.role("model").params)
    gen_params = dict(node.params)

    def work(job: JobContext) -> dict[str, Any]:
        t0 = time.perf_counter()
        result = belt_comparison(design.genome, overrides, gen_params, lab.project.path, ctrl_params, compile_params,
                                 progress=lambda m: job.report(message=m), cancelled=job.cancelled)
        run_id = lab.registry.new_run_id("belts")
        run_dir = lab.registry.run_dir(run_id)
        write_json(run_dir / "belt_comparison.json", result)
        (run_dir / "belt_comparison.csv").write_bytes(comparison_csv(result).encode("utf-8"))
        lab.registry.save_run(RunRecord(
            id=run_id, kind="belts", title="Belt comparison (slow walk)", duration_s=time.perf_counter() - t0,
            backend="local", inputs={"generator_params": gen_params, "compile": compile_params, "catalog": result["catalog"]},
            genome=design.genome.model_dump(mode="json"), overrides=[o.model_dump(mode="json") for o in overrides],
            controller={"key": "feral_motion", "params": {**ctrl_params, "mode": "walk"}},
            metrics={"combinations": len(result["rows"]), "ran": sum(1 for r in result["rows"] if r["status"] == "ran")},
            artifacts={"report": f"runs/{run_id}/belt_comparison.json", "csv": f"runs/{run_id}/belt_comparison.csv"},
        ))
        lab.bus.emit("runs.changed", run_id=run_id)
        for r in result["rows"]:
            job.log(f"{r['system']} / {r['pulleys']}: {r['status']}" + (f" ({r['reason']})" if r["reason"] else ""))
        return {"run_id": run_id}

    return lab.jobs.submit("belts", "Belt comparison", work)


def belt_panel(lab: Any) -> dict[str, Any]:
    """Everything the Belts and springs panel shows, computed here (no logic in the UI)."""
    from calflab.mech.belts import BeltChoice, drive_options
    from calflab.morphology.feral import belt_context

    _require_feral(lab)
    design = lab.design()
    spec = design.spec
    meta = spec.metadata["feral"]
    catalog, layouts, extra = belt_context(spec, lab.project.path)
    drives = {}
    for d, rep in meta["belt_drives"].items():
        choice = BeltChoice.model_validate(rep["choice"])
        drives[d] = {
            "report": rep,
            "stored": d in (lab.state.graph.role("design").params.get("belts") or {}),
            "options": drive_options(catalog, layouts[d], choice, extra.get(d)),
            "joints": [j.id for j in spec.joints if j.id.endswith(f".{d}")],
        }
    runs = lab.registry.list_runs(kind="loads", limit=1)
    latest = runs[0]["id"] if runs else None
    return {
        "drives": drives,
        "belted": meta["belted"],
        "catalog": meta["belt_catalog"],
        "springs": static_spring_report(spec),
        "spring_genes": meta["springs"],
        "provisional": meta["provisional"],
        "missing_masses": spec.metadata.get("missing_masses", []),
        "servo": meta["servo"],
        "checks": meta["checks"],
        "standing_height_mm": meta["standing_height_mm"],
        "front_angle_deg": meta["front_angle_deg"],
        "total_mass_g": spec.total_mass_g(),
        "com_mm": list(spec.center_of_mass()),
        "joint_ranges_deg": meta["joint_ranges_deg"],
        "warnings": list(design.warnings),
        "latest_loads_run": latest,
    }


def loads_view(lab: Any, run_id: str | None = None) -> dict[str, Any]:
    """The stored report of a load run (default: the latest of each scenario)."""
    from calflab.project.store import read_json

    rows = [r for r in lab.registry.list_runs(limit=500) if r["kind"] in ("loads", "belts")]
    if run_id:
        rows = [r for r in rows if r["id"] == run_id]
    runs = [lab.registry.get_run(r["id"]) for r in rows]
    out: dict[str, Any] = {"scenarios": {}, "comparison": None}
    for r in runs:  # newest first
        if r.kind == "belts":
            if out["comparison"] is None and r.artifacts.get("report"):
                out["comparison"] = {"run_id": r.id, **read_json(lab.project.resolve(r.artifacts["report"]))}
            continue
        name = r.inputs.get("scenario")
        if name in out["scenarios"] or not r.artifacts.get("report"):
            continue
        out["scenarios"][name] = {"run_id": r.id, "created": r.created, **read_json(lab.project.resolve(r.artifacts["report"]))}
    return out
