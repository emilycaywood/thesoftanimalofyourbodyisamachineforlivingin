"""Bill of materials and power budget.

The BOM is derived from the RobotSpec and the component library; every line
carries the component's ``verified`` flag and ``source`` so unverified numbers
stay visible. The power budget turns a sim run's per-actuator torque statistics
into current, power and battery-runtime estimates.
"""

from __future__ import annotations

from typing import Any

from calflab.components.library import ActuatorSpec, BatterySpec, BoardSpec, Library, SensorSpec
from calflab.config import default
from calflab.model.spec import RobotSpec


def bill_of_materials(spec: RobotSpec, lib: Library) -> dict[str, Any]:
    """BOM lines grouped by component, plus printed and skin material."""
    counts: dict[str, int] = {}
    refs: dict[str, list[str]] = {}

    def add(key: str | None, ref: str) -> None:
        if not key or not lib.has(key):
            return
        counts[key] = counts.get(key, 0) + 1
        refs.setdefault(key, []).append(ref)

    for a in spec.actuators:
        add(a.component, a.id)
    actuator_keys = {a.component for a in spec.actuators}
    for b in spec.bodies:
        for g in b.geoms:
            if g.component and g.component not in actuator_keys and g.layer == "Electronics":
                add(g.component, g.id)
    for s in spec.sensors:
        add(s.component, s.id)

    lines: list[dict[str, Any]] = []
    for key, qty in counts.items():
        c = lib.get(key)
        lines.append(
            {
                "key": key,
                "kind": c.kind,
                "name": c.name,
                "manufacturer": c.manufacturer,
                "qty": qty,
                "unit_cost_usd": c.cost_usd,
                "cost_usd": round(c.cost_usd * qty, 2),
                "unit_mass_g": c.mass_g,
                "mass_g": round(c.mass_g * qty, 1),
                "url": c.url,
                "source": c.source,
                "verified": c.verified,
                "refs": refs[key],
            }
        )

    # materials
    by_layer = spec.mass_by_layer()
    struct_key = default("structure.material", "petg")
    if lib.has(struct_key) and by_layer.get("Structure", 0) > 0:
        m = lib.material(struct_key)
        mass = by_layer["Structure"]
        lines.append(_material_line(m, mass, "printed structure"))
    skin_mass: dict[str, float] = {}
    for r in spec.skin_regions:
        geoms = [g for b in spec.bodies if b.id in r.bodies for g in b.geoms if g.layer == "Skin"]
        skin_mass[r.material] = skin_mass.get(r.material, 0.0) + sum(g.mass_g for g in geoms)
    for key, mass in skin_mass.items():
        if lib.has(key) and mass > 0:
            lines.append(_material_line(lib.material(key), mass, "skin"))

    order = {"actuator": 0, "board": 1, "battery": 2, "sensor": 3, "material": 4}
    lines.sort(key=lambda r: (order.get(r["kind"], 9), r["name"]))
    total_cost = round(sum(r["cost_usd"] for r in lines), 2)
    return {
        "lines": lines,
        "total_cost_usd": total_cost,
        "total_mass_g": round(spec.total_mass_g(), 1),
        "unverified": sum(1 for r in lines if not r["verified"]),
        "note": "Costs and masses come from the component library; unverified lines need checking.",
    }


def _material_line(m: Any, mass_g: float, use: str) -> dict[str, Any]:
    cost = m.cost_usd_per_kg * mass_g / 1000.0
    return {
        "key": m.key,
        "kind": "material",
        "name": f"{m.name} ({use})",
        "manufacturer": m.manufacturer,
        "qty": round(mass_g, 0),
        "qty_unit": "g",
        "unit_cost_usd": m.cost_usd_per_kg,
        "cost_usd": round(cost, 2),
        "unit_mass_g": 1.0,
        "mass_g": round(mass_g, 1),
        "url": m.url,
        "source": m.source,
        "verified": m.verified,
        "refs": [],
    }


def bom_csv(bom: dict[str, Any]) -> str:
    cols = ["kind", "name", "manufacturer", "qty", "unit_cost_usd", "cost_usd", "mass_g", "verified", "source", "url"]
    rows = [",".join(cols)]
    for r in bom["lines"]:
        rows.append(",".join('"' + str(r.get(c, "")).replace('"', "'") + '"' for c in cols))
    rows.append(f'"TOTAL","","","","","{bom["total_cost_usd"]}","{bom["total_mass_g"]}","","",""')
    return "\n".join(rows) + "\n"


def power_budget(spec: RobotSpec, lib: Library, metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Current/power per actuator from a run's torque statistics, plus boards and battery.

    Current = |torque| / (stall torque / stall current) + idle current, at the
    bus voltage. With no run, only idle and board loads are reported.
    """
    bus_v = float(default("electronics.bus_voltage_v", 11.1))
    by_act = (metrics or {}).get("by_actuator", {})
    trans = {t.id: t for t in spec.transmissions}
    rows: list[dict[str, Any]] = []
    mean_a = peak_a = 0.0
    for a in spec.actuators:
        c: ActuatorSpec = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        kt = c.torque_constant_nm_per_a * ((tr.ratio * tr.efficiency) if tr else 1.0)
        stats = by_act.get(a.id, {})
        i_rms = float(stats.get("torque_rms_nm", 0.0)) / kt + c.idle_current_a
        i_peak = min(float(stats.get("torque_peak_nm", 0.0)) / kt + c.idle_current_a, c.stall_current_a)
        mean_a += i_rms
        peak_a += i_peak
        rows.append(
            {
                "id": a.id,
                "component": c.key,
                "name": c.name,
                "current_rms_a": round(i_rms, 3),
                "current_peak_a": round(i_peak, 3),
                "power_rms_w": round(i_rms * bus_v, 2),
                "torque_margin": stats.get("torque_margin"),
                "temp_peak_c": stats.get("temp_peak_c"),
                "verified": c.verified,
            }
        )
    loads: list[dict[str, Any]] = []
    other_w = 0.0
    seen: set[str] = set()
    for b in spec.bodies:
        for g in b.geoms:
            if g.component and lib.has(g.component) and g.id not in seen:
                comp = lib.get(g.component)
                if isinstance(comp, BoardSpec):
                    seen.add(g.id)
                    other_w += comp.power_w
                    loads.append({"id": g.id, "name": comp.name, "power_w": comp.power_w, "verified": comp.verified})
    for s in spec.sensors:
        sc = lib.get(s.component) if s.component and lib.has(s.component) else None
        if isinstance(sc, SensorSpec) and sc.current_ma > 0:
            w = sc.current_ma / 1000.0 * sc.voltage_v
            other_w += w
            loads.append({"id": s.id, "name": sc.name, "power_w": round(w, 3), "verified": sc.verified})

    mean_w = mean_a * bus_v + other_w
    peak_w = peak_a * bus_v + other_w
    battery = None
    bat_geom = next((g for b in spec.bodies for g in b.geoms if g.id == "elec.battery"), None)
    if bat_geom and bat_geom.component and lib.has(bat_geom.component):
        bc = lib.get(bat_geom.component)
        if isinstance(bc, BatterySpec):
            usable_wh = bc.energy_wh * 0.8
            battery = {
                "name": bc.name,
                "energy_wh": round(bc.energy_wh, 1),
                "usable_wh": round(usable_wh, 1),
                "runtime_min": round(usable_wh / mean_w * 60.0, 1) if mean_w > 0 else None,
                "peak_current_a": round(peak_w / bc.voltage_v, 2),
                "max_current_a": bc.max_current_a,
                "peak_ok": (peak_w / bc.voltage_v) <= bc.max_current_a if bc.max_current_a else None,
                "verified": bc.verified,
            }
    return {
        "bus_voltage_v": bus_v,
        "from_run": bool(by_act),
        "actuators": rows,
        "other_loads": loads,
        "mean_power_w": round(mean_w, 2),
        "peak_power_w": round(peak_w, 2),
        "mean_current_a": round(mean_w / bus_v, 2),
        "peak_current_a": round(peak_w / bus_v, 2),
        "battery": battery,
        "note": "Estimate from torque statistics and unverified component data; not a measurement.",
    }


def torque_margins(spec: RobotSpec, lib: Library, metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Required vs. available torque per joint from a chosen sim run."""
    derating = float(default("simulation.torque_derating", 0.6))
    by_act = (metrics or {}).get("by_actuator", {})
    trans = {t.id: t for t in spec.transmissions}
    rows = []
    for a in spec.actuators:
        c = lib.actuator(a.component)
        tr = trans.get(a.transmission) if a.transmission else None
        stall = c.stall_torque_nm * ((tr.ratio * tr.efficiency) if tr else 1.0)
        stats = by_act.get(a.id)
        required = float(stats["torque_peak_nm"]) if stats else None
        available = float(stats["torque_limit_nm"]) if stats else stall * derating
        rows.append(
            {
                "joint": a.joint,
                "actuator": a.id,
                "component": c.key,
                "name": c.name,
                "transmission": tr.type if tr else "direct",
                "stall_nm": round(stall, 3),
                "available_nm": round(available, 3),
                "required_peak_nm": round(required, 3) if required is not None else None,
                "required_rms_nm": round(float(stats["torque_rms_nm"]), 3) if stats else None,
                "margin": round(1.0 - required / available, 3) if required is not None and available else None,
                "verified": c.verified,
            }
        )
    return rows
