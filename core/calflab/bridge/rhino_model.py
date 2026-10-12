"""Take a whole modelled robot from Rhino and store it as one ``model`` override (ADR-062).

The Rhino script sends what is on the ``CALFLAB::Model`` layers and decides
nothing: joint axis lines with their joint id, and solids with the body they
belong to, their material, print tags and whether they are a foot. Everything
is checked and measured here. If anything is wrong nothing is stored and the
reply lists every problem at once.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from calflab.model.overrides import Override
from calflab.model.pushed_model import AXIS_WARN_DEG, HULL_VERTICES, lowest_point, support_hull
from calflab.model.xform import quat_to_matrix
from calflab.project.store import now_iso, slugify

#: feet whose lowest points differ by more than this (mm) are reported
FOOT_LEVEL_WARN_MM = 1.0


MODEL_LAYER = "CALFLAB::Model"
JOINTS_LAYER = "CALFLAB::Model::Joints"
#: user text keys. Not ``calflab.id``: CalflabPull deletes every object that carries that one.
JOINT_KEY = "calflab.joint"
FOOT_KEY = "calflab.foot"
AXIS_HALF_LENGTH_MM = 20.0


def model_layout(design: Any) -> dict[str, Any]:
    """What ``CalflabModelSetup`` creates in Rhino: a sublayer per body for the
    researcher's solids and, as starting points to move, one axis line per
    hinge where the parametric skeleton has it (world, mm, standing pose)."""
    from calflab.model.pushed_model import joint_world_axes
    from calflab.model.spec import LAYER_COLORS

    spec = design.spec
    axes = []
    names = {j.id: j.name or j.id for j in spec.joints}
    for jid, (p, a) in joint_world_axes(spec, spec.world_poses()).items():
        axes.append({
            "id": jid,
            "name": names[jid],
            "from": [round(p[k] - a[k] * AXIS_HALF_LENGTH_MM, 3) for k in range(3)],
            "to": [round(p[k] + a[k] * AXIS_HALF_LENGTH_MM, 3) for k in range(3)],
        })
    return {
        "root_layer": MODEL_LAYER,
        "joints_layer": JOINTS_LAYER,
        "joint_key": JOINT_KEY,
        "foot_key": FOOT_KEY,
        "layers": [{"path": MODEL_LAYER, "color": "#000000"}, {"path": JOINTS_LAYER, "color": LAYER_COLORS["Annotations"]}]
                  + [{"path": f"{MODEL_LAYER}::{b.id}", "color": LAYER_COLORS["Structure"]} for b in spec.bodies],
        "bodies": [{"id": b.id, "name": b.name or b.id} for b in spec.bodies],
        "axes": axes,
    }


def save_pushed_model(lab: Any, payload: dict[str, Any], check_only: bool = False) -> dict[str, Any]:
    """Check, measure and store a model pushed from Rhino.

    ``payload``::

        {"file": "prototype.3dm", "name": "Rhino model",
         "joints": [{"id": "joint.fl.knee", "from": [x, y, z], "to": [x, y, z]}],
         "solids": [{"body": "leg.fl.shank", "name": "...", "material": "pla", "foot": false,
                     "vertices": [[x, y, z]], "faces": [[a, b, c]],
                     "host": {"closed": true, "volume_mm3": 1234.5},
                     "print": {"infill": "20", "perimeters": "5", "line_width": "0.4"}}]}

    All coordinates are world, mm, in the standing pose the pulled calf was
    drawn in. A joint's line gives its axis (direction) and its place
    (midpoint). ``check_only`` measures and reports without storing anything.

    Returns the report: ``ok``, ``stored``, ``errors``, ``warnings``, the joint
    table against the parametric skeleton, a row per body, the feet, what the
    simulator will treat as one rigid body, and ``lines``: the same as text.
    """
    import trimesh

    from calflab.components import library
    from calflab.design import structure_material
    from calflab.model.infill import PrintSettings, measure_core, parse_print_tags, scale_core
    from calflab.model.mass import mass_breakdown
    from calflab.model.solid import HOST_VOLUME_TOLERANCE, analyze_mesh, use_host_volume

    lib = library()
    errors: list[str] = []
    warnings: list[str] = []
    base = [o for o in lab.state.overrides if o.kind != "model"]
    parametric = lab.design(overrides=base).spec
    body_ids = {b.id for b in parametric.bodies}
    hinge_ids = {j.id for j in parametric.joints if j.type == "hinge"}

    # ---- joints
    joints: dict[str, dict[str, Any]] = {}
    for row in payload.get("joints") or []:
        jid = str(row.get("id") or "")
        a, b = np.asarray(row.get("from", []), dtype=float), np.asarray(row.get("to", []), dtype=float)
        if jid not in hinge_ids:
            errors.append(f"Axis line tagged {jid!r}: this design has no such joint (it has: {', '.join(sorted(hinge_ids))})")
        elif jid in joints:
            errors.append(f"{jid} has more than one axis line; keep one")
        elif a.shape != (3,) or b.shape != (3,) or float(np.linalg.norm(b - a)) < 1e-6:
            errors.append(f"The axis line of {jid} has no length")
        else:
            joints[jid] = {"point": [round(float(c), 4) for c in (a + b) / 2.0], "axis": [round(float(c), 6) for c in (b - a) / np.linalg.norm(b - a)]}

    # ---- the skeleton the solids are measured against
    def trial(bodies: dict[str, Any]) -> Any:
        ov = Override(id="ov-model-check", name=str(payload.get("name") or "Rhino model"), target="model", kind="model",
                      source=str(payload.get("source") or "rhino"), created=now_iso(),
                      meta={"file": str(payload.get("file") or ""), "pushed": now_iso(), "joints": joints, "bodies": bodies})
        return lab.design(overrides=[*base, ov])

    poses = trial({}).spec.world_poses()
    stamp = now_iso().replace(":", "").replace("-", "")
    folder = f"assets/model/{stamp}"
    files: dict[str, bytes] = {}

    def glb(vertices: Any, faces: Any | None, rel: str) -> str:
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False) if faces is not None else trimesh.convex.convex_hull(vertices)
        files[rel] = trimesh.Scene(mesh).export(file_type="glb")
        return hashlib.sha256(files[rel]).hexdigest()

    # ---- solids, body by body
    bodies: dict[str, dict[str, Any]] = {}
    foot_points: dict[str, list[np.ndarray]] = {}
    loose = 0
    for n, part in enumerate(payload.get("solids") or [], start=1):
        label = f"Solid {str(part.get('name') or n)!r}"
        body_id = str(part.get("body") or "")
        if body_id not in body_ids:
            loose += 1
            errors.append(f"{label} is on {body_id or 'no body layer'!r}, which is not a body of this design")
            continue
        label += f" on {body_id}"
        v, f = np.asarray(part.get("vertices", []), dtype=float), np.asarray(part.get("faces", []), dtype=int)
        if v.ndim != 2 or v.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,) or len(v) == 0:
            errors.append(f"{label} has no mesh (is it a curve or a block?)")
            continue
        key = str(part.get("material") or "")
        if structure_material(lib, key) is None:
            errors.append(f"{label}: material {key or '(none)'!r} is not a structure material in the library")
        how: PrintSettings | None = None
        try:
            how = parse_print_tags(part["print"]) if isinstance(part.get("print"), dict) else None
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
        p, q = poses[body_id]
        r = quat_to_matrix(q)
        local = (v - np.asarray(p)) @ r
        solid = analyze_mesh(local, f)
        host = part.get("host") if isinstance(part.get("host"), dict) else {}
        if not solid.closed:
            hint = " (Rhino reports it closed, so its render mesh has gaps: try _ExtractRenderMesh)" if host.get("closed") else ""
            errors.append(f"{label} is not a closed solid: {solid.problem}{hint}")
            continue
        error = use_host_volume(solid, float(host.get("volume_mm3") or 0.0))
        if error is not None and abs(error) > HOST_VOLUME_TOLERANCE:
            warnings.append(f"{label}: its mesh volume differs {error * 100:+.1f} % from what Rhino reports; the mesh volume is used. "
                            "Check it for overlapping or inside-out pieces.")
        entry = bodies.setdefault(body_id, {"solids": []})
        k = len(entry["solids"]) + 1
        rel = f"{folder}/{slugify(body_id)}-{k}.glb"
        item: dict[str, Any] = {"name": str(part.get("name") or f"solid {k}"), "asset": rel, "material": key,
                                "solid": solid.model_dump(mode="json"), "foot": bool(part.get("foot")), "sha256": glb(local, f, rel)}
        if how is not None:
            core = measure_core(local, f, how.wall_mm)
            if solid.volume_source == "host":
                scale_core(core, solid.volume_mm3 / solid.mesh_volume_mm3)
            item.update({"print": how.model_dump(mode="json"), "print_core": core.model_dump(mode="json")})
        down = tuple(float(c) for c in r.T @ np.array([0.0, 0.0, -1.0]))
        if item["foot"]:
            foot_points.setdefault(body_id, []).append(local)
        else:
            hull = support_hull(local, HULL_VERTICES, keep=(down,))  # type: ignore[arg-type]
            if hull:
                item["hull"] = [[round(c, 4) for c in pt] for pt in hull]
                item["hull_asset"] = f"{folder}/{slugify(body_id)}-{k}-hull.glb"
                glb(np.asarray(hull), None, item["hull_asset"])
            else:
                warnings.append(f"{label} is too thin to make a collision shape from; it has mass but does not collide")
        entry["solids"].append(item)
    for body_id, clouds in foot_points.items():
        r = quat_to_matrix(poses[body_id][1])
        down = tuple(float(c) for c in r.T @ np.array([0.0, 0.0, -1.0]))
        hull = support_hull(np.vstack(clouds), HULL_VERTICES, keep=(down,))  # type: ignore[arg-type]
        rel = f"{folder}/{slugify(body_id)}-foot-hull.glb"
        glb(np.asarray(hull), None, rel)
        bodies[body_id]["foot"] = {"hull": [[round(c, 4) for c in pt] for pt in hull], "hull_asset": rel, "solids": len(clouds)}
    if not bodies and not joints and not errors:
        errors.append("Nothing to push: no axis lines on CALFLAB::Model::Joints and no solids on the body layers")

    # ---- the report, from the design this model gives
    design = trial(bodies)
    spec = design.spec
    record = spec.metadata.get("geometry") or {}
    rows = record.get("joints") or []
    for row in rows:
        if row["source"] == "model" and row["axis_angle_deg"] > AXIS_WARN_DEG:
            warnings.append(f"{row['joint']}: your axis is {row['axis_angle_deg']:.0f} deg from the pulled calf's. Check the line.")
    missing = sorted(hinge_ids - set(joints))
    if missing:
        warnings.append(f"No axis line for {', '.join(missing)}: {'they keep' if len(missing) > 1 else 'it keeps'} the pulled calf's "
                        "place relative to the part above.")
    if record.get("parametric_bodies"):
        warnings.append(f"No solids for {', '.join(record['parametric_bodies'])}: these stay the lab's parametric shapes and mass estimate.")
    hoofed = [b.id for b in spec.bodies if any(g.foot and not g.hull for g in b.geoms)]
    if hoofed and record.get("feet"):
        warnings.append(f"No solid tagged calflab.foot on {', '.join(hoofed)}: the lab's hoof sphere is still the foot there.")
    elif hoofed and bodies:
        warnings.append("No solid is tagged calflab.foot: the lab's hoof spheres are still the feet, so the ground does not touch "
                        "your foot geometry. Tag the solids that touch the ground and push again.")
    warnings.extend(w for w in design.warnings if w not in warnings)
    breakdown = mass_breakdown(spec, lib)
    by_body = {row["body"]: row for row in breakdown["bodies"]}
    world = spec.world_poses()
    body_rows = []
    for body_id, info in (record.get("bodies") or {}).items():
        st = by_body[body_id]["structure"]
        com = None
        if st["com_mm"] is not None:
            c = quat_to_matrix(world[body_id][1]) @ np.asarray(st["com_mm"]) + np.asarray(world[body_id][0])
            com = [round(float(x), 2) for x in c]
        body_rows.append({"body": body_id, "solids": info["solids"], "mass_g": st["mass_g"], "source": st["source"],
                          "materials": st["materials"], "com_world_mm": com, "collision": info["collision"],
                          "hulls": info["hulls"], "foot": info["foot"], "names": [m["name"] for m in info["meshes"]]})
    feet = []
    for gid in record.get("feet") or []:
        feet.append({"geom": gid, "lowest_z_mm": round(lowest_point(spec, gid)[0], 2)})
    if feet:
        zs = [f["lowest_z_mm"] for f in feet]
        if max(zs) - min(zs) > FOOT_LEVEL_WARN_MM:
            warnings.append(f"Your feet are not level as modelled: their lowest points are {max(zs) - min(zs):.1f} mm apart in height. "
                            "The calf starts on the lowest and settles onto the others.")
    hinges = [j.id for j in spec.joints if j.type == "hinge"]
    n_solids = sum(len(e["solids"]) for e in bodies.values())
    out: dict[str, Any] = {
        "ok": not errors,
        "stored": False,
        "errors": errors,
        "warnings": warnings,
        "joints": rows,
        "bodies": body_rows,
        "feet": feet,
        "hooves_removed": record.get("hooves_removed") or [],
        "structure": {"free_bodies": 1, "hinges": len(hinges), "dof": 6 + len(hinges), "rigid_bodies": len(spec.bodies),
                      "modelled_bodies": len(bodies), "solids": n_solids, "loose_solids": loose},
        "mass": {"total_g": breakdown["total_g"], "by_source_g": breakdown["by_source_g"]},
    }
    if not errors and not check_only:
        for rel, data in files.items():
            path = lab.project.path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        res = lab.execute(
            "set_rhino_model",
            {"name": str(payload.get("name") or "Rhino model"), "source": str(payload.get("source") or "rhino"),
             "file": str(payload.get("file") or ""), "joints": joints, "bodies": bodies},
            client=str(payload.get("source") or "rhino"),
        )
        out.update({"stored": True, "override": res["result"]["override"]})
    out["lines"] = report_lines(out, check_only)
    for w in warnings if out["stored"] else []:
        lab.bus.emit("log", level="warn", source="push", message=w)
    return out


def report_lines(r: dict[str, Any], check_only: bool = False) -> list[str]:
    """The report of :func:`save_pushed_model` as text (what CalflabPushModel prints)."""
    s = r["structure"]
    lines: list[str] = []
    if r["errors"]:
        lines.append(f"NOT PUSHED: {len(r['errors'])} problem{'s' if len(r['errors']) != 1 else ''} to fix first. Nothing was changed.")
        lines += [f"  problem: {e}" for e in r["errors"]]
    elif check_only:
        lines.append("Check only: nothing was stored. This is what a push would give.")
    else:
        lines.append(f"Pushed as override {r.get('override')}. The simulated calf is now built from this model.")
    lines.append(
        f"Simulated as: 1 free body (the trunk) + {s['hinges']} hinges = {s['dof']} degrees of freedom. {s['solids']} solids on "
        f"{s['modelled_bodies']} bodies, each body one rigid piece; {s['loose_solids']} loose solids."
    )
    if r["joints"]:
        lines.append("Joints, yours against the pulled calf's (mm, world; dx forward, dy left, dz up):")
        for j in r["joints"]:
            if j["source"] != "model":
                lines.append(f"  {j['joint']:<22} no axis line: follows the part above ({j['distance_mm']:.1f} mm from the pulled calf's)")
                continue
            p, d = j["pos_mm"], j["delta_mm"]
            lines.append(
                f"  {j['joint']:<22} at ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})  moved {j['distance_mm']:.1f} mm "
                f"(dx {d[0]:+.1f}, dy {d[1]:+.1f}, dz {d[2]:+.1f}), axis {j['axis_angle_deg']:.1f} deg off"
            )
    if r["bodies"]:
        lines.append("Bodies:")
        for b in r["bodies"]:
            est = " (infill estimate)" if b["source"] == "infill" else ""
            lines.append(
                f"  {b['body']:<16} {b['solids']:>3} solid{'s' if b['solids'] != 1 else ' '}  {b['mass_g']:>8.1f} g{est}  "
                f"{' + '.join(b['materials'])}  collision: {b['hulls']} hull{'s' if b['hulls'] != 1 else ''}"
                f"{' incl. the foot' if b['foot'] else ''}" if b["collision"] == "hulls" else
                f"  {b['body']:<16} {b['solids']:>3} solids: not used, the envelope stays (see warnings)"
            )
    for f in r["feet"]:
        lines.append(f"  foot {f['geom']}: lowest point at z = {f['lowest_z_mm']:.2f} mm as modelled")
    for h in r["hooves_removed"]:
        lines.append(f"  the lab's hoof {h['id']} ({h['mass_g']:.1f} g) is removed: your foot replaces it")
    by = {k: v for k, v in r["mass"]["by_source_g"].items() if v > 0}
    lines.append(f"Total mass {r['mass']['total_g']:.1f} g (" + ", ".join(f"{k} {v:.1f}" for k, v in by.items()) + ")")
    lines += [f"  warning: {w}" for w in r["warnings"]]
    return lines
