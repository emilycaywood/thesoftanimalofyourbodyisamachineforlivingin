"""Production sheets of a feral calf body (session R11c, ADR-103): a geometry table for Rhino / Grasshopper and a
parts list, both from the built spec and the catalog only (pure functions; no value is invented).

Geometry (mm, world frame X forward, Y left, Z up, standing pose, trunk origin midway between the axles at axle
height + standing height): every segment's length, every joint's centre, every servo case centre, every pulley
centre, every spring anchor. The right legs mirror the left ones; both are listed.

Parts list: per belt drive the belt (system, width, pitch length, teeth, source, listings) and both pulleys (teeth,
belt width, bores, listings), per spring site the spring to source (rate, free length, max extension and peak force
through the joint range), the servos per joint pair. Everything is ``verified: false`` until the researcher says so.
"""

from __future__ import annotations

from typing import Any

from calflab.mech.belts import BeltChoice
from calflab.model.xform import quat_rotate

SEGMENT_GENES = {"femur": "femur_length", "tibia": "tibia_length", "rear cannon": "rear_cannon_length",
                 "upper leg": "upper_leg_length", "front cannon": "front_cannon_length"}


def _world(poses: dict[str, Any], body: str, pos: Any) -> tuple[float, float, float]:
    bp, bq = poses[body]
    r = quat_rotate(bq, pos)
    return (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2])


def geometry_rows(spec: Any, values: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per item: kind, id, label, x, y, z (mm, world, standing), and a value (a length) where it has one."""
    poses = spec.world_poses()
    rows: list[dict[str, Any]] = []

    def add(kind: str, id_: str, label: str, p: Any, value: float | None = None, unit: str = "") -> None:
        rows.append({"kind": kind, "id": id_, "label": label, "x_mm": round(p[0], 2), "y_mm": round(p[1], 2),
                     "z_mm": round(p[2], 2), "value": None if value is None else round(float(value), 2), "unit": unit})

    for name, gene in SEGMENT_GENES.items():
        rows.append({"kind": "segment_length", "id": gene, "label": name, "x_mm": None, "y_mm": None, "z_mm": None,
                     "value": float(values[gene]), "unit": "mm"})
    from calflab.mech.statics import joint_frames

    for jid, (p, _ax) in joint_frames(spec, poses).items():
        j = spec.joint(jid) if hasattr(spec, "joint") else next(x for x in spec.joints if x.id == jid)
        add("joint", jid, j.name, p)
    for b in spec.bodies:
        for g in b.geoms:
            if g.id.endswith(".motor"):
                add("servo", g.id, g.label or "", _world(poses, b.id, g.pos))
            elif g.id.endswith(".driver") or g.id.endswith(".driven"):
                add("pulley", g.id, g.label or "", _world(poses, b.id, g.pos), 2.0 * g.size[0], "mm pitch diameter")
    for sp in spec.springs:
        add("spring_anchor", f"{sp.id}.upper", f"{sp.label} (upper)", _world(poses, sp.upper_body, sp.upper_pos))
        add("spring_anchor", f"{sp.id}.lower", f"{sp.label} (lower)", _world(poses, sp.lower_body, sp.lower_pos),
            sp.free_length_mm, "mm free length")
    fer = spec.metadata.get("feral") or {}
    for d, r in (fer.get("belt_drives") or {}).items():
        rows.append({"kind": "belt_centre_distance", "id": f"belt.{d}", "label": f"{d} C (derived)", "x_mm": None,
                     "y_mm": None, "z_mm": None, "value": round(float(r["c_mm"]), 2) if r.get("c_mm") else None,
                     "unit": "mm"})
    rows.append({"kind": "standing_height", "id": "standing_height", "label": "standing height", "x_mm": None,
                 "y_mm": None, "z_mm": None, "value": fer.get("standing_height_mm"), "unit": "mm"})
    return rows


def geometry_csv(rows: list[dict[str, Any]]) -> str:
    cols = ["kind", "id", "label", "x_mm", "y_mm", "z_mm", "value", "unit"]
    out = [",".join(cols)]
    for r in rows:
        out.append(",".join("" if r[c] is None else ('"' + str(r[c]).replace('"', "'") + '"' if c == "label"
                                                   else str(r[c])) for c in cols))
    return "\n".join(out) + "\n"


def _single_for(catalog: Any, teeth: int, width: float) -> Any:
    return next((p for p in catalog.pulleys if p.teeth == teeth and any(abs(w - width) < 1e-9
                                                                         for w in p.belt_widths_mm)), None)


def parts_list(spec: Any, values: dict[str, Any], catalog: Any, springs: dict[str, Any], lib: Any) -> dict[str, Any]:
    """Belts, pulleys, springs and servos to order or make, with their sources; ``to_verify`` lists what the
    researcher must check before ordering."""
    fer = spec.metadata.get("feral") or {}
    belts, pulleys, verify = [], [], []
    for d, r in (fer.get("belt_drives") or {}).items():
        ch = r["choice"]
        system = catalog.system(ch["system"])
        entry = catalog.length(ch["length"])
        src = catalog.source(entry.source)
        belts.append({"drive": d, "qty": 2, "system": system.id, "profile": system.profile, "pitch_mm": system.pitch_mm,
                      "vendor": system.vendor, "part_number": entry.part_number, "price_usd": entry.price_usd,
                      "guessed": list(system.guessed), "not_sourceable": catalog.sourcing_problems(
                          BeltChoice.model_validate(ch)),
                      "width_mm": system.width_mm, "pitch_length_mm": entry.pitch_length_mm, "teeth": entry.teeth,
                      "source": src.label, "url": src.url, "listings": list(src.listings) + list(entry.listings),
                      "purchase_confirmed": entry.purchase_confirmed, "c_mm": round(float(r["c_mm"]), 2),
                      "allowable_working_tension_n": system.allowable_working_tension_n,
                      "breaking_strength_n": system.breaking_strength_n, "verified": False})
        verify.append(f"{d} belt: {system.width_mm:g} mm {system.profile}, {entry.pitch_length_mm:g} mm ({entry.teeth} teeth) is "
                      f"really listed and orderable (source {entry.source}); purchase_confirmed is false")
        for role, teeth in (("driver (servo)", r["driver_teeth"]), ("driven (joint)", r["driven_teeth"])):
            s = _single_for(catalog, int(teeth), system.width_mm)
            pulleys.append({"drive": d, "role": role, "qty": 2, "teeth": int(teeth), "pitch_mm": system.pitch_mm,
                            "belt_width_mm": system.width_mm, "pitch_diameter_mm": round(
                                float(r["d1_mm"] if role.startswith("driver") else r["d2_mm"]), 3),
                            "bores_mm": s.bores_mm if s else None, "listed_mass_g": s.listed_mass_g if s else None,
                            "listings": [x.model_dump() for x in s.listings] if s else [],
                            "catalog_id": s.id if s else None, "verified": False,
                            "vendor": s.vendor if s else None, "part_number": s.part_number if s else None,
                            "price_usd": s.price_usd if s else None,
                            "listed": dict(s.listed) if s else {},
                            "note": "" if s else "no single listed pulley of this size for this width in the catalog"})
            verify.append(f"{d} {role} pulley {teeth}T for {system.width_mm:g} mm: listing, bore to fit "
                          + ("the servo horn / spline (not checked in simulation)" if role.startswith("driver")
                             else "the joint shaft") + ("" if s else " (NOT in the catalog as a single pulley)"))
    spring_rows = []
    for site, r in sorted(springs.items()):
        if site.startswith("_"):
            continue
        spring_rows.append({"site": site, "qty": 2, "rate_n_per_mm": r["k_n_per_mm"], "free_length_mm": r["free_mm"],
                            "standing_length_mm": r["standing_mm"], "max_extension_mm": r["max_extension_mm"],
                            "peak_force_n_range": r["peak_force_n"], "line_clear_of_joint": r.get("line_clear"),
                            "verified": False})
        verify.append(f"{site} spring: a tension spring of {r['k_n_per_mm']:g} N/mm, free length {r['free_mm']:g} mm, "
                      f"that survives {r['max_extension_mm']:g} mm of extension ({r['peak_force_n']:g} N) - no spring "
                      "has been sourced yet")
    servos = []
    for p, row in (fer.get("servos") or {}).items():
        servos.append({"pair": p, "qty": 2, "component": row["component"], "name": row["name"],
                       "verified": bool(row.get("verified"))})
    for c in sorted({s["component"] for s in servos}):
        if not lib.actuator(c).verified:
            verify.append(f"servo {c}: every library value (unverified)")
    verify.append("driving pulley to servo spline connection: not checked in simulation")
    verify.append("lateral stack (tube, pulley, belt, spring offsets) and pulley clearance at each joint for its own "
                  "diameter: not modelled (one-plane assumption)")
    return {"belts": belts, "pulleys": pulleys, "springs": spring_rows, "servos": servos, "to_verify": verify}


#: open items every belt drive of a McMaster (1/4 in bore) body needs, not modelled and not in any catalog (R18,
#: ADR-118): their part, mass and size are the researcher's to choose
OPEN_ITEMS_QUARTER_INCH = (
    ("servo_shaft_adapter", "Servo output (spline horn) to 1/4 in round shaft adapter, one per belted servo",
     "driver"),
    ("joint_axle", "1/4 in joint axle carrying the driven pulley, one per belted joint", "driven"),
)


def bom(parts: dict[str, Any]) -> dict[str, Any]:
    """Bill of materials of the belt drives from a ``parts_list``: one row per part number (quantity summed over the
    drives and both sides), unit price and line total as the catalog lists them (None = not listed; the total then
    counts only the priced rows and names the rest). Every part must come from a named vendor: a part without a part
    number is listed under ``unpriced`` with the reason. Open items (adapters, axles) are listed, never priced
    (R18, ADR-118)."""
    rows: dict[str, dict[str, Any]] = {}
    unpriced: list[str] = []
    for b in parts.get("belts", []):
        key = b.get("part_number") or f"(no part number) {b['system']} {b['pitch_length_mm']:g} mm"
        r = rows.setdefault(key, {"part_number": b.get("part_number"), "vendor": b.get("vendor"), "kind": "belt",
                                  "description": f"{b['profile']} closed belt, {b['pitch_length_mm']:g} mm pitch "
                                                 f"length ({b['teeth']} teeth), {b['width_mm']:g} mm wide",
                                  "qty": 0, "unit_usd": b.get("price_usd"), "used_by": []})
        r["qty"] += int(b["qty"])
        r["used_by"].append(f"{b['drive']} belt")
    driver_count = 0
    for p in parts.get("pulleys", []):
        key = p.get("part_number") or f"(no part number) {p['teeth']}T {p['pitch_mm']:g} mm for {p['belt_width_mm']:g} mm"
        r = rows.setdefault(key, {"part_number": p.get("part_number"), "vendor": p.get("vendor"), "kind": "pulley",
                                  "description": f"{p['teeth']}T {p['pitch_mm']:g} mm pitch pulley for "
                                                 f"{p['belt_width_mm']:g} mm belts, bore "
                                                 f"{'/'.join(f'{x:g}' for x in (p.get('bores_mm') or [])) or '?'} mm",
                                  "qty": 0, "unit_usd": p.get("price_usd"), "used_by": []})
        r["qty"] += int(p["qty"])
        r["used_by"].append(f"{p['drive']} {p['role']}")
        if p["role"].startswith("driver"):
            driver_count += int(p["qty"])
    total = 0.0
    out = []
    for r in sorted(rows.values(), key=lambda r: (r["kind"], str(r["part_number"]))):
        r["line_usd"] = None if r["unit_usd"] is None else round(r["unit_usd"] * r["qty"], 2)
        if r["line_usd"] is None:
            unpriced.append(f"{r['part_number'] or r['description']}: no price listed"
                            + ("" if r["part_number"] else " (and no part number)"))
        else:
            total += r["line_usd"]
        out.append(r)
    open_items = [{"item": k, "description": d, "qty": driver_count, "priced": False,
                   "note": "open: not chosen, not modelled (mass and size not added)"}
                  for k, d, _role in OPEN_ITEMS_QUARTER_INCH]
    return {"rows": out, "total_usd": round(total, 2), "complete": not unpriced, "unpriced": unpriced,
            "open_items": open_items, "currency": "USD", "note": "prices as read from the vendor's pages; shipping "
                                                                  "and tax not included"}
