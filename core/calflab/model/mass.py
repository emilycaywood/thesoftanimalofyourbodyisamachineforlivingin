"""Mass breakdown: every gram of a design, with where the number comes from.

Each geom carries its mass and a ``mass_source`` (ADR-050): a pushed closed
solid x material density (``geometry``), such a solid weighed as printed with
infill (``infill``, an estimate: ADR-054), a component-library entry
(``component``), the parametric envelope estimate of ADR-017 (``parametric``)
or a weighed value (``measured``). This module only groups and sums them, so
the breakdown always adds up to :meth:`RobotSpec.total_mass_g` and nothing is
counted twice: a body with a pushed solid lists its envelope estimate as
*replaced*, not as mass.

Units: g.
"""

from __future__ import annotations

from typing import Any

from calflab.model.spec import RobotSpec

SOURCES: dict[str, str] = {
    "infill": "Pushed solid, infill estimate (shell + infilled core)",
    "geometry": "Pushed solid x material density",
    "measured": "Measured (weighed)",
    "component": "Component library entry",
    "parametric": "Parametric estimate (envelope)",
}

#: shown wherever a structure mass rests on an infill estimate
INFILL_NOTE = (
    "Infill estimate, not a weighed mass: a shell of the wall thickness at full material density plus the core "
    "inside it at the infill percentage. It ignores the infill pattern and the slicer's real path. Weigh the print "
    "and enter it in Measured for the real value."
)


def mass_breakdown(spec: RobotSpec, lib: Any) -> dict[str, Any]:
    """Per-body mass items with their source, and totals by source.

    ``lib`` is the component library (for names and ``verified`` flags).
    """

    def entry(key: str | None) -> Any:
        return lib.get(key) if key and lib.has(key) else None

    by_source = dict.fromkeys(SOURCES, 0.0)
    unverified = 0.0
    bodies: list[dict[str, Any]] = []
    for b in spec.bodies:
        items: list[dict[str, Any]] = []
        body_sources = dict.fromkeys(SOURCES, 0.0)
        s_mass = 0.0
        s_sources: set[str] = set()
        s_materials: set[str] = set()
        s_notes: set[str] = set()
        s_computed: float | None = None
        s_replaced: float | None = None
        s_moment = [0.0, 0.0, 0.0]  # sum of mass x centre of mass (g*mm, body frame)
        s_solids: list[dict[str, Any]] = []
        for g in b.geoms:
            in_structure = g.layer == "Structure" and g.component is None and not g.foot
            if in_structure and g.mass_note:
                s_notes.add(g.mass_note)
            if g.mass_g <= 0 and g.mass_replaced_g is None:
                continue
            ref = entry(g.component) or entry(g.material)
            verified = bool(ref.verified) if ref is not None else None
            by_source[g.mass_source] += g.mass_g
            body_sources[g.mass_source] += g.mass_g
            if verified is False:
                unverified += g.mass_g
            items.append(
                {
                    "id": g.id,
                    "label": g.label or g.id,
                    "layer": g.layer,
                    "mass_g": round(g.mass_g, 2),
                    "source": g.mass_source,
                    "material": g.material,
                    "component": g.component,
                    "verified": verified,
                    "computed_g": None if g.mass_computed_g is None else round(g.mass_computed_g, 2),
                    "replaced_g": None if g.mass_replaced_g is None else round(g.mass_replaced_g, 2),
                    "note": g.mass_note,
                    #: settings and volumes behind an infill estimate (None = not one)
                    "infill": g.infill,
                }
            )
            if in_structure:
                s_mass += g.mass_g
                s_sources.add(g.mass_source)
                if g.material:
                    s_materials.add(g.material)
                if g.mass_computed_g is not None:
                    s_computed = (s_computed or 0.0) + g.mass_computed_g
                if g.mass_replaced_g is not None:
                    s_replaced = (s_replaced or 0.0) + g.mass_replaced_g
                c = g.mass_center()
                for k in range(3):
                    s_moment[k] += g.mass_g * c[k]
                if g.shape == "mesh":  # a pushed solid, weighed with its own material
                    s_solids.append(
                        {"id": g.id, "label": g.label or g.id, "material": g.material, "mass_g": round(g.mass_g, 2), "verified": verified,
                         "infill": g.infill}
                    )
        source = next((k for k in SOURCES if k in s_sources), None)  # the most specific one present
        materials = sorted(s_materials)
        bodies.append(
            {
                "body": b.id,
                "name": b.name or b.id,
                "total_g": round(b.mass_g(), 2),
                "by_source_g": {k: round(v, 2) for k, v in body_sources.items() if v > 0},
                "structure": {
                    "mass_g": round(s_mass, 2),
                    "source": source,
                    "source_label": SOURCES.get(source or "", ""),
                    "material": materials[0] if len(materials) == 1 else None,
                    #: every material the structure mass was computed with (several for a part of mixed solids)
                    "materials": materials,
                    "material_label": " + ".join(materials),
                    #: the pushed solids behind the mass, each with its own material
                    "solids": s_solids,
                    #: centre of mass of the structure in the body frame (mm), mass-weighted over its solids
                    "com_mm": [round(v / s_mass, 2) for v in s_moment] if s_mass > 0 else None,
                    "computed_g": None if s_computed is None else round(s_computed, 2),
                    "replaced_g": None if s_replaced is None else round(s_replaced, 2),
                    "note": " ".join(sorted(s_notes)),
                    #: said beside a structure mass that is an infill estimate
                    "estimate_note": INFILL_NOTE if source == "infill" else "",
                },
                "items": items,
            }
        )
    # components the model gives no body, hence no mass (e.g. foot sensors)
    placed = {g.component for b in spec.bodies for g in b.geoms if g.component}
    not_counted: dict[str, dict[str, Any]] = {}
    for s in spec.sensors:
        c = entry(s.component)
        if c is None or s.component in placed or c.mass_g <= 0:
            continue
        row = not_counted.setdefault(c.key, {"component": c.key, "name": c.name, "qty": 0, "mass_g": 0.0})
        row["qty"] += 1
        row["mass_g"] = round(row["mass_g"] + c.mass_g, 2)
    total = spec.total_mass_g()
    return {
        "total_g": round(total, 2),
        "by_source_g": {k: round(v, 2) for k, v in by_source.items()},
        "source_labels": SOURCES,
        "geometry_parts": [r["body"] for r in bodies if r["structure"]["source"] in ("geometry", "infill")],
        #: the parts among them whose mass is an infill estimate
        "infill_parts": [r["body"] for r in bodies if r["structure"]["source"] == "infill"],
        "measured_parts": [r["body"] for r in bodies if r["structure"]["source"] == "measured"],
        "unverified_g": round(unverified, 2),
        "bodies": bodies,
        "not_counted": list(not_counted.values()),
    }
