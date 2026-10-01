"""Built-in wiring/firmware exporters, analyses and panels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from calflab.components import library
from calflab.plugins import Analysis, ExportContext, Exporter, Panel, register
from calflab.schema import P
from calflab.wiring import (
    bill_of_materials,
    bom_csv,
    component_audit,
    power_budget,
    render_harness,
    torque_margins,
)


# ====================================================================== exporters
@register
class BomExporter(Exporter):
    key = "bom"
    label = "Bill of materials"
    description = "BOM with costs, links and verified flags (CSV + JSON)."
    formats = ["csv", "json"]
    category = "wiring"

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        bom = bill_of_materials(ctx.spec, ctx.library)
        csv = out_dir / f"{ctx.design_name}_bom.csv"
        js = out_dir / f"{ctx.design_name}_bom.json"
        csv.write_text(bom_csv(bom), encoding="utf-8")
        js.write_text(json.dumps(bom, indent=2), encoding="utf-8")
        return [csv, js]


@register
class WireVizExporter(Exporter):
    key = "wireviz"
    label = "Harness diagram (WireViz)"
    description = "WireViz YAML and an SVG diagram of the harness with real cable lengths."
    formats = ["yml", "svg"]
    category = "wiring"

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        res = render_harness(ctx.spec, out_dir, f"{ctx.design_name}_harness")
        return [res["yaml"], res["svg"]]


@register
class PowerBudgetExporter(Exporter):
    key = "power_budget"
    label = "Power budget"
    description = "Current, power and battery runtime estimated from a sim run's torque profile."
    formats = ["json"]
    category = "wiring"

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        metrics = (ctx.run or {}).get("metrics")
        data = power_budget(ctx.spec, ctx.library, metrics)
        data["run_id"] = (ctx.run or {}).get("id")
        path = out_dir / f"{ctx.design_name}_power.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return [path]


_PIO_INI = """; CALFLAB firmware skeleton (generated). Low-level control on a Teensy 4.1.
[env:teensy41]
platform = teensy
board = teensy41
framework = arduino
monitor_speed = 115200
"""

_MAIN_CPP = """// CALFLAB firmware skeleton (generated). Fill in the servo bus driver.
#include <Arduino.h>
#include "robot_config.h"

static float target_rad[CALFLAB_NUM_JOINTS];

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < CALFLAB_NUM_JOINTS; ++i) target_rad[i] = CALFLAB_JOINTS[i].rest_rad;
  // TODO(phase3): open the servo bus, enable torque, start the IMU.
}

void loop() {
  // TODO(phase3): read targets from the Raspberry Pi (USB serial), clamp to
  // CALFLAB_JOINTS[i].min_rad / max_rad, write to the servos, stream telemetry.
  delay(1000 / CALFLAB_CONTROL_HZ);
}
"""

_PI_PY = '''"""CALFLAB high-level skeleton for the Raspberry Pi 5 (generated).

Loads an ONNX policy (Phase 2) and exchanges joint targets / telemetry with the
Teensy over USB serial.
"""
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).parent / "robot_config.json").read_text())


def main() -> None:
    # TODO(phase3): import onnxruntime, load policy.onnx, open serial port,
    # run the control loop at CONFIG["control_hz"].
    print(f"{len(CONFIG['joints'])} joints configured")


if __name__ == "__main__":
    main()
'''


@register
class FirmwareExporter(Exporter):
    key = "firmware"
    label = "Firmware project skeleton"
    description = "PlatformIO project (Teensy 4.1) and Raspberry Pi skeleton with the joint map of this design."
    formats = ["ini", "cpp", "h", "py", "json"]
    category = "firmware"

    class Params(BaseModel):
        control_hz: int = P(100, unit="Hz", ge=10, le=1000, desc="Low-level control loop rate.")

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        from calflab import units as u

        root = out_dir / f"{ctx.design_name}_firmware"
        (root / "teensy" / "src").mkdir(parents=True, exist_ok=True)
        (root / "pi").mkdir(parents=True, exist_ok=True)
        joints = []
        for i, a in enumerate(ctx.spec.actuators):
            j = ctx.spec.joint(a.joint)
            joints.append(
                {
                    "index": i,
                    "servo_id": i + 1,
                    "actuator": a.id,
                    "joint": j.id,
                    "component": a.component,
                    "min_rad": round(u.deg_to_rad(j.range_deg[0]), 5),
                    "max_rad": round(u.deg_to_rad(j.range_deg[1]), 5),
                    "rest_rad": round(u.deg_to_rad(j.rest_deg), 5),
                }
            )
        rows = ",\n".join(
            f'  {{{j["servo_id"]}, "{j["joint"]}", {j["min_rad"]}f, {j["max_rad"]}f, {j["rest_rad"]}f}}' for j in joints
        )
        header = (
            "// Generated by CALFLAB from the current design. Do not edit by hand.\n"
            "#pragma once\n"
            f"#define CALFLAB_NUM_JOINTS {len(joints)}\n"
            f"#define CALFLAB_CONTROL_HZ {self.params.control_hz}\n"  # type: ignore[attr-defined]
            "struct CalflabJoint { int servo_id; const char* id; float min_rad; float max_rad; float rest_rad; };\n"
            f"static const CalflabJoint CALFLAB_JOINTS[CALFLAB_NUM_JOINTS] = {{\n{rows}\n}};\n"
        )
        files = {
            root / "teensy" / "platformio.ini": _PIO_INI,
            root / "teensy" / "src" / "main.cpp": _MAIN_CPP,
            root / "teensy" / "src" / "robot_config.h": header,
            root / "pi" / "main.py": _PI_PY,
            root / "pi" / "robot_config.json": json.dumps(
                {"control_hz": self.params.control_hz, "joints": joints}, indent=2  # type: ignore[attr-defined]
            ),
        }
        for path, text in files.items():
            path.write_text(text, encoding="utf-8")
        return list(files)


# ====================================================================== analyses
@register
class MassBudget(Analysis):
    key = "mass_budget"
    label = "Mass budget"
    description = "Total mass against the target, by layer and by body, with the centre of mass."

    def run(self, lab: Any) -> dict[str, Any]:
        s = lab.scene()
        return {"mass": s["mass"], "com_mm": s["com"], "com_margin_mm": s["com_margin_mm"], "extents": s["extents"]}


class _RunParams(BaseModel):
    run_id: str = P("", desc="Sim run to read torques from (empty = latest sim run).")


def _metrics_for(lab: Any, run_id: str) -> tuple[str | None, dict[str, Any] | None]:
    rid = run_id
    if not rid:
        runs = [r for r in lab.registry.list_runs("sim", 1)]
        rid = runs[0]["id"] if runs else ""
    if not rid:
        return None, None
    return rid, lab.registry.get_run(rid).metrics


@register
class TorqueMargins(Analysis):
    key = "torque_margin"
    label = "Torque margins"
    description = "Required vs. available torque per joint, from a chosen sim run."
    Params = _RunParams

    def run(self, lab: Any) -> dict[str, Any]:
        rid, metrics = _metrics_for(lab, self.params.run_id)  # type: ignore[attr-defined]
        return {"run_id": rid, "rows": torque_margins(lab.design().spec, library(), metrics)}


@register
class PowerBudget(Analysis):
    key = "power_budget"
    label = "Power budget"
    description = "Current and power per actuator and battery runtime, from a chosen sim run."
    Params = _RunParams

    def run(self, lab: Any) -> dict[str, Any]:
        rid, metrics = _metrics_for(lab, self.params.run_id)  # type: ignore[attr-defined]
        return {"run_id": rid, **power_budget(lab.design().spec, library(), metrics)}


@register
class Bom(Analysis):
    key = "bom"
    label = "Bill of materials"
    description = "Components and materials with cost, mass, links and verified flags."

    def run(self, lab: Any) -> dict[str, Any]:
        return bill_of_materials(lab.design().spec, library())


@register
class ComponentAudit(Analysis):
    key = "component_audit"
    label = "Component audit"
    description = "Unverified components, the results that depend on them, and actuators at their torque limit."
    Params = _RunParams

    def run(self, lab: Any) -> dict[str, Any]:
        rid, metrics = _metrics_for(lab, self.params.run_id)  # type: ignore[attr-defined]
        return {"run_id": rid, **component_audit(lab.design().spec, library(), metrics)}


@register
class HarnessAnalysis(Analysis):
    key = "harness"
    label = "Harness"
    description = "Cable list with routed lengths and the WireViz diagram."

    def run(self, lab: Any) -> dict[str, Any]:
        spec = lab.design().spec
        res = render_harness(spec, lab.project.dir("exports") / "wireviz", "current_harness")
        return {
            "routes": [r.model_dump(mode="json") for r in spec.harness_routes],
            "total_length_mm": round(sum(r.length_mm for r in spec.harness_routes), 1),
            "svg": lab.project.rel(res["svg"]),
            "yaml": lab.project.rel(res["yaml"]),
            "renderer": res["renderer"],
            "renderer_note": res["reason"],
        }


# ====================================================================== panels
@register
class MassPanel(Panel):
    key = "mass_panel"
    label = "Mass budget"
    description = "Live mass budget and centre of mass."
    workspace = "form"
    widgets = [{"kind": "analysis", "analysis": "mass_budget"}]
