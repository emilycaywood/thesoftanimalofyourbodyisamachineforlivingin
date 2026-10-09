"""Component verification: what is unverified and which results depend on it.

Two outputs, both read-only with respect to the library (the code never sets
``verified``; only the researcher does, in ``config/components/*.yaml``):

* :func:`worksheet` - one row per recorded spec value, with its source and a
  blank column for the value the researcher reads off the real datasheet.
* :func:`audit` - which components the current design uses, which results
  (BOM cost, mass, torque margins, power, runtime, thermal estimate) each
  unverified component feeds, and which actuators run at their usable torque
  limit in a chosen sim run.

``FIELD_USES`` states, per component kind, what every spec field is used for
by the core. A field with no uses is recorded in the library but read by no
calculation yet.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from calflab.components.library import Component, Library
from calflab.model.spec import RobotSpec
from calflab.wiring.budget import bill_of_materials, power_budget, torque_margins

# What a result key means, in the words used by the UI and the CLI.
RESULTS: dict[str, str] = {
    "mass": "Mass budget and centre of mass",
    "geometry": "Viewport / Rhino / Blender geometry",
    "cad": "CAD actuator mount (leg segment export)",
    "sim_dynamics": "Simulated dynamics (gait, speed, stability)",
    "sim_torque": "Simulated torque limit and servo gain",
    "speed_cap": "Joint speed cap of gait tuning",
    "torque_margin": "Torque margins",
    "power": "Power budget",
    "runtime": "Battery runtime",
    "thermal": "Actuator temperature estimate",
    "bom_cost": "BOM cost",
}

# kind -> field -> (unit, results the field feeds). Mass also feeds the
# simulated dynamics because the MJCF takes geom masses from the spec.
FIELD_USES: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {
    "actuator": {
        "mass_g": ("g", ("mass", "sim_dynamics")),
        "dims_mm": ("mm", ("geometry", "cad")),
        "stall_torque_nm": ("N*m", ("sim_torque", "torque_margin", "power", "runtime", "thermal")),
        "stall_current_a": ("A", ("power", "runtime", "thermal")),
        "no_load_speed_rpm": ("rpm", ("speed_cap",)),
        "voltage_v": ("V", ()),
        "gear_ratio": ("", ()),
        "idle_current_a": ("A", ("power", "runtime", "thermal")),
        "armature_kgm2": ("kg*m^2", ("sim_dynamics",)),
        "winding_resistance_ohm": ("ohm", ("thermal",)),
        "r_thermal_k_per_w": ("K/W", ("thermal",)),
        "c_thermal_j_per_k": ("J/K", ("thermal",)),
        "max_temp_c": ("degC", ()),
        "cost_usd": ("USD", ("bom_cost",)),
    },
    "sensor": {
        "mass_g": ("g", ("mass", "sim_dynamics")),
        "dims_mm": ("mm", ("geometry",)),
        "current_ma": ("mA", ("power", "runtime")),
        "voltage_v": ("V", ("power", "runtime")),
        "cost_usd": ("USD", ("bom_cost",)),
    },
    "board": {
        "mass_g": ("g", ("mass", "sim_dynamics")),
        "dims_mm": ("mm", ("geometry",)),
        "voltage_v": ("V", ()),
        "power_w": ("W", ("power", "runtime")),
        "cost_usd": ("USD", ("bom_cost",)),
    },
    "battery": {
        "mass_g": ("g", ("mass", "sim_dynamics")),
        "dims_mm": ("mm", ("geometry",)),
        "voltage_v": ("V", ("runtime",)),
        "capacity_mah": ("mAh", ("runtime",)),
        "max_current_a": ("A", ("power",)),
        "cost_usd": ("USD", ("bom_cost",)),
    },
    "material": {
        "density_g_cm3": ("g/cm^3", ("mass", "sim_dynamics")),
        "areal_density_g_cm2": ("g/cm^2", ("mass", "sim_dynamics")),
        "joint_stiffness_nm_per_rad_per_mm": ("N*m/rad per mm", ("sim_dynamics",)),
        "joint_damping_nms_per_rad_per_mm": ("N*m*s/rad per mm", ("sim_dynamics",)),
        "cost_usd_per_kg": ("USD/kg", ("bom_cost",)),
    },
}

WORKSHEET_COLUMNS = (
    "component", "kind", "name", "field", "unit", "recorded_value", "flag", "used_for",
    "source", "url", "datasheet_value", "datasheet_reference", "ok", "notes",
)


def affects(component: Component) -> list[str]:
    """Result keys (see ``RESULTS``) that any field of this component feeds."""
    seen: list[str] = []
    for _unit, uses in FIELD_USES[component.kind].values():
        for use in uses:
            if use not in seen:
                seen.append(use)
    return [r for r in RESULTS if r in seen]


def _value(component: Component, field: str) -> str:
    v = getattr(component, field)
    if isinstance(v, tuple):
        return " x ".join(f"{x:g}" for x in v)
    return f"{v:g}" if isinstance(v, float) else str(v)


def worksheet(lib: Library) -> list[dict[str, str]]:
    """One row per recorded spec value; the last four columns are for the researcher."""
    rows: list[dict[str, str]] = []
    for c in lib.all():
        for field, (unit, uses) in FIELD_USES[c.kind].items():
            flag = "guess" if field in c.guessed else ("default assumed" if field in c.defaulted else "")
            rows.append(
                {
                    "component": c.key,
                    "kind": c.kind,
                    "name": c.name,
                    "field": field,
                    "unit": unit,
                    "recorded_value": _value(c, field),
                    "flag": flag,
                    "used_for": "; ".join(RESULTS[x] for x in uses) or "not used by any calculation yet",
                    "source": c.source,
                    "url": c.url,
                    "datasheet_value": "",
                    "datasheet_reference": "",
                    "ok": "",
                    "notes": "",
                }
            )
    return rows


def worksheet_csv(lib: Library) -> str:
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=WORKSHEET_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(worksheet(lib))
    return out.getvalue()


def audit(
    spec: RobotSpec, lib: Library, metrics: dict[str, Any] | None, limit_margin: float = 0.01
) -> dict[str, Any]:
    """Unverified components, the results that depend on them, and saturated actuators.

    ``metrics`` are a sim run's metrics (or None: torque rows then have no
    required torque). An actuator is "at its limit" when its torque margin
    (1 - peak / usable torque) is at or below ``limit_margin``.
    """
    bom = bill_of_materials(spec, lib)
    used: dict[str, dict[str, Any]] = {}
    for line in bom["lines"]:  # a material can have two lines (e.g. cast silicone: hooves and face skin)
        if line["key"] in used:
            for k in ("qty", "cost_usd", "mass_g"):
                used[line["key"]][k] = round(used[line["key"]][k] + line[k], 2)
        else:
            used[line["key"]] = dict(line)
    components: list[dict[str, Any]] = []
    for c in lib.all():
        line = used.get(c.key)
        components.append(
            {
                "key": c.key,
                "kind": c.kind,
                "name": c.name,
                "verified": c.verified,
                "source": c.source,
                "url": c.url,
                "in_design": line is not None,
                "qty": line["qty"] if line else 0,
                "qty_unit": (line.get("qty_unit", "") if line else ""),
                "cost_usd": line["cost_usd"] if line else 0.0,
                "mass_g": line["mass_g"] if line else 0.0,
                "affects": affects(c),
                "unused_fields": [f for f, (_u, uses) in FIELD_USES[c.kind].items() if not uses],
                # values that are not datasheet values: guessed by the researcher / left to the code's default
                "guessed": list(c.guessed),
                "defaulted": list(c.defaulted),
            }
        )

    def depends(result: str) -> list[str]:
        return [c["key"] for c in components if c["in_design"] and not c["verified"] and result in c["affects"]]

    pb = power_budget(spec, lib, metrics)
    rows = torque_margins(spec, lib, metrics)
    for r in rows:
        r["at_limit"] = r["margin"] is not None and r["margin"] <= limit_margin
    margins = [r["margin"] for r in rows if r["margin"] is not None]
    unverified_cost = sum(c["cost_usd"] for c in components if c["in_design"] and not c["verified"])
    results = [
        {"key": "bom_cost", "label": "BOM total", "value": bom["total_cost_usd"], "unit": "USD",
         "unverified_share": round(unverified_cost / bom["total_cost_usd"], 3) if bom["total_cost_usd"] else 0.0},
        {"key": "mass", "label": "Total mass", "value": bom["total_mass_g"], "unit": "g"},
        {"key": "torque_margin", "label": "Worst torque margin", "value": min(margins) if margins else None, "unit": ""},
        {"key": "power", "label": "Mean power", "value": pb["mean_power_w"], "unit": "W"},
        {"key": "runtime", "label": "Battery runtime",
         "value": pb["battery"]["runtime_min"] if pb["battery"] else None, "unit": "min"},
    ]
    for res in results:
        res["depends_on_unverified"] = depends(res["key"])
        res["from_run"] = bool(margins) if res["key"] in ("torque_margin", "power", "runtime") else None

    return {
        "total": len(components),
        "unverified": sum(1 for c in components if not c["verified"]),
        "in_design_unverified": sum(1 for c in components if c["in_design"] and not c["verified"]),
        "components": components,
        "incomplete": list(lib.incomplete.values()),
        "results": results,
        "torque": rows,
        "at_limit": [r["actuator"] for r in rows if r["at_limit"]],
        "limit_margin": limit_margin,
        "from_run": bool(margins),
        "note": "Read-only report. Set verified: true in config/components/*.yaml yourself after "
                "checking each value against its datasheet.",
    }
