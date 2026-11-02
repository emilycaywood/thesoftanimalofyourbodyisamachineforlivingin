"""Running the load scenarios and the belt comparison (ADR-069).

``run_scenario`` simulates one motion of the feral calf with the servos
allowed up to their stall torque (torque derating 1), so "at stall" in the
load report is the moment a servo saturates. ``belt_comparison`` runs the same
walk on every catalog combination of belt system and pulley pair, holding
everything else fixed; each drive takes the length the default rule picks for
that combination (closest to its target C, passing every check).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from calflab.mech.loads import analyse, scenario_duration
from calflab.model.genome import Genome
from calflab.model.overrides import Override
from calflab.model.spec import RobotSpec
from calflab.sim.rollout import Rollout


def run_scenario(
    spec: RobotSpec,
    lib: Any,
    mode: str,
    controller_params: dict[str, Any] | None = None,
    compile_params: dict[str, Any] | None = None,
    seed: int = 0,
) -> tuple[Rollout, dict[str, Any], float]:
    """Simulate one scenario. Returns the rollout, the controller params used and the gait-cycle window (s)."""
    from calflab.plugins import load_plugins, registry
    from calflab.sim.mjcf import CompileOptions, compile_mjcf
    from calflab.sim.rollout import SimSettings, run_rollout

    load_plugins()
    cls = registry.get("controller", "feral_motion")
    ctrl = cls({**(controller_params or {}), "mode": mode})
    params = ctrl.params.model_dump(mode="json")  # type: ignore[attr-defined]
    opts = CompileOptions.model_validate({**(compile_params or {}), "torque_derating": 1.0})
    cm = compile_mjcf(spec, lib, opts, seed=seed)
    settings = SimSettings(duration_s=scenario_duration(mode, params), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=False, seed=seed)
    rollout = run_rollout(cm, ctrl, settings, lib)  # type: ignore[arg-type]
    rollout.meta["scenario"] = mode
    rollout.meta["torque_derating"] = 1.0
    return rollout, params, float(params.get("cycle_s", 4.0))


def belt_comparison(
    genome: Genome,
    overrides: list[Override],
    generator_params: dict[str, Any],
    project_dir: Path | None,
    controller_params: dict[str, Any] | None = None,
    compile_params: dict[str, Any] | None = None,
    progress: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """The walk on every belt system x pulley pair of the catalog. One row per combination."""
    from calflab.components import library
    from calflab.design import build_design
    from calflab.mech.belts import load_catalog

    lib = library()
    catalog, note = load_catalog(project_dir)
    rows: list[dict[str, Any]] = []
    for system in catalog.systems:
        for pair in catalog.pairs:
            if cancelled is not None and cancelled():
                break
            row: dict[str, Any] = {"system": system.id, "pulleys": pair.id, "pitch_mm": system.pitch_mm,
                                   "width_mm": system.width_mm, "allowable_n": system.allowable_working_tension_n,
                                   "breaking_n": system.breaking_strength_n, "status": "ran", "reason": "", "drives": {}}
            if pair.pitch_mm != system.pitch_mm:
                row.update(status="not buildable", reason=f"{pair.id} is a {pair.pitch_mm:g} mm pitch pair; the belt is {system.pitch_mm:g} mm")
                rows.append(row)
                continue
            params = {**generator_params, "belts": {}, "default_system": system.id, "default_pulleys": pair.id}
            try:
                design = build_design(genome, overrides, "feral_calf", params, project_dir)
            except Exception as exc:  # e.g. no length of this system is offered in its width
                row.update(status="not buildable", reason=str(exc))
                rows.append(row)
                continue
            meta = design.spec.metadata["feral"]
            for d, rep in meta["belt_drives"].items():
                row["drives"][d] = {"length": rep["choice"]["length"], "length_mm": rep["length_mm"], "c_mm": rep["c_mm"],
                                    "ok": rep["ok"], "unknown": rep["unknown"], "purchase_confirmed": rep["purchase_confirmed"],
                                    "failed": [f"{c['label']}: {c['detail']}" for c in rep["checks"] if c["status"] == "fail"]}
            if not meta["belts_ok"]:
                row.update(status="rejected", reason="; ".join(f"{d}: {', '.join(v['failed'])}" for d, v in row["drives"].items()
                                                                if v["failed"]))
                rows.append(row)
                continue
            if progress:
                progress(f"{system.id} with {pair.id}: walking")
            rollout, ctrl_used, cycle = run_scenario(design.spec, lib, "walk", controller_params, compile_params)
            res = analyse(rollout, design.spec, lib, cycle, meta["checks"], meta["belt_drives"])
            row["outcome"] = res["outcome"]
            row["flags"] = res["flags"]
            for s in res["summary"]:
                if "belt_tension_peak_n" not in s:
                    continue
                d = s["joint"].split(".")[-1]
                side = s["joint"].split(".")[1]
                key = f"{d}.{side}"
                row["drives"].setdefault(key, {})
                row["drives"][key] = {
                    "c_mm": s["c_mm"], "length": s["belt_length"], "peak_n": s["belt_tension_peak_n"],
                    "mean_n": s["belt_tension_mean_n"], "above_allowable_fraction_of_cycle": s["above_allowable_fraction_of_cycle"],
                    "sustained_above_allowable": s["sustained_above_allowable"], "peak_over_breaking": s["peak_over_breaking"],
                    "breaking_flag": s["breaking_flag"], "servo_peak_nm": s["servo_torque_peak_nm"],
                }
            rows.append(row)
    return {"rows": rows, "catalog": {"origin": catalog.origin, "digest": catalog.digest(), "note": note},
            "scenario": "walk", "held_fixed": "genome, overrides, springs, controller and simulation settings; only the belt "
            "system and pulley pair change, and with them each drive's belt length (default rule), C and servo position"}


def comparison_csv(result: dict[str, Any]) -> str:
    import csv
    import io

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["system", "pulleys", "status", "drive", "length", "c_mm", "peak_n", "mean_n", "allowable_n",
                "above_allowable_fraction_of_cycle", "sustained_above_allowable", "breaking_n", "peak_over_breaking",
                "breaking_flag", "reason"])
    for r in result["rows"]:
        drives = {k: v for k, v in r["drives"].items() if "peak_n" in v}
        if not drives:
            w.writerow([r["system"], r["pulleys"], r["status"], "", "", "", "", "", r["allowable_n"], "", "", r["breaking_n"],
                        "", "", r["reason"]])
            continue
        for d, v in sorted(drives.items()):
            w.writerow([r["system"], r["pulleys"], r["status"], d, v["length"], _f(v["c_mm"]), _f(v["peak_n"]), _f(v["mean_n"]),
                        r["allowable_n"] if r["allowable_n"] is not None else "unknown",
                        _f(v["above_allowable_fraction_of_cycle"]), v["sustained_above_allowable"], r["breaking_n"],
                        _f(v["peak_over_breaking"]), v["breaking_flag"], r["reason"]])
    return out.getvalue()


def _f(v: Any) -> str:
    return "" if v is None else f"{float(v):.4g}"
