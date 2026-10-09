"""Rhino bridge logic (pure; testable without Rhino).

``rhino_build_list`` turns a design into explicit instructions the Rhino
script follows literally: a layer tree mirroring the CALFLAB layers, block
definitions for repeated components, and objects with world transforms and
user text carrying the stable IDs. The script in ``bridges/rhino`` contains no
geometry decisions of its own.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from calflab.components import library
from calflab.design import EvaluatedDesign
from calflab.model.spec import LAYER_COLORS, LAYERS
from calflab.model.xform import matrix4

ROOT_LAYER = "CALFLAB"
ID_KEY = "calflab.id"


def block_name(component_key: str) -> str:
    return f"calflab.{component_key}"


def rhino_build_list(design: EvaluatedDesign, revision: int = 0) -> dict[str, Any]:
    spec = design.spec
    lib = library()
    poses = spec.world_poses()
    layers = [{"path": ROOT_LAYER, "color": "#000000"}] + [
        {"path": f"{ROOT_LAYER}::{name}", "color": LAYER_COLORS[name]} for name in LAYERS
    ]
    blocks: dict[str, dict[str, Any]] = {}
    objects: list[dict[str, Any]] = []
    for body in spec.bodies:
        bp, bq = poses[body.id]
        tb = np.array(matrix4(bp, bq))
        for g in body.geoms:
            if g.role == "collision":
                continue  # the envelope a pushed solid replaced: simulator collision shape only
            xform = (tb @ np.array(matrix4(g.pos, g.quat))).round(6).tolist()
            user_text = {
                ID_KEY: g.id,
                "calflab.body": body.id,
                "calflab.layer": g.layer,
                "calflab.revision": str(revision),
                "calflab.mass_g": f"{g.mass_g:.2f}",
                "calflab.mass_source": g.mass_source,
            }
            if g.material:
                # CalflabPush offers this as the material of whatever is pushed back
                user_text["calflab.material"] = g.material
            obj: dict[str, Any] = {
                "id": g.id,
                "name": g.id,
                "layer": f"{ROOT_LAYER}::{g.layer}",
                "body": body.id,
                "xform": xform,
                "color": g.color,
                "user_text": user_text,
            }
            if g.component and lib.has(g.component):
                comp = lib.get(g.component)
                name = block_name(g.component)
                blocks.setdefault(
                    name,
                    {
                        "name": name,
                        "description": f"{comp.name} ({'verified' if comp.verified else 'UNVERIFIED dims'})",
                        "geoms": [{"shape": "box", "size": list(g.size)}],
                    },
                )
                user_text["calflab.component"] = g.component
                user_text["calflab.verified"] = str(comp.verified).lower()
                obj.update({"kind": "block", "block": name})
            elif g.shape == "mesh":
                obj.update({"kind": "mesh", "asset": g.mesh})
            else:
                obj.update({"kind": "primitive", "shape": g.shape, "size": list(g.size)})
            objects.append(obj)
    annotations = []
    for j in spec.joints:
        p, q = poses[j.body]
        from calflab.model.xform import quat_rotate

        axis = quat_rotate(q, j.axis)
        annotations.append(
            {
                "id": j.id,
                "layer": f"{ROOT_LAYER}::Annotations",
                "kind": "axis",
                "from": [round(p[i] - axis[i] * 30.0, 3) for i in range(3)],
                "to": [round(p[i] + axis[i] * 30.0, 3) for i in range(3)],
                "user_text": {ID_KEY: j.id, "calflab.range_deg": f"{j.range_deg[0]},{j.range_deg[1]}"},
            }
        )
    from calflab.wiring.harness import harness_paths

    curves = []
    paths = harness_paths(spec)
    for h in spec.harness_routes:
        pts = paths[h.id]
        if len(pts) < 2:
            continue
        curves.append(
            {
                "id": h.id,
                "layer": f"{ROOT_LAYER}::Harness",
                "kind": "polyline",
                "points": [[round(c, 3) for c in p] for p in pts],
                "user_text": {
                    ID_KEY: h.id,
                    "calflab.layer": "Harness",
                    "calflab.src": h.src,
                    "calflab.dst": h.dst,
                    "calflab.length_mm": f"{h.length_mm:g}",
                    "calflab.connector": h.connector,
                    "calflab.wires": ",".join(w.signal for w in h.wires),
                    "calflab.revision": str(revision),
                },
            }
        )
    return {
        "units": "mm",
        "name": spec.name,
        "revision": revision,
        "root_layer": ROOT_LAYER,
        "id_key": ID_KEY,
        "layers": layers,
        "blocks": list(blocks.values()),
        "objects": objects,
        "annotations": annotations,
        "curves": curves,
    }


def fabrication_layout(kind: str) -> dict[str, Any]:
    """Fabrication-oriented exports to Rhino (flattened skin, mold halves, nesting).

    TODO(phase4): return build lists for flattened skin pieces laid out on a
    sheet, mold halves and nesting layouts, produced by the skin_pattern, mold
    and nesting exporters.
    """
    raise NotImplementedError(f"Rhino fabrication layout {kind!r} arrives with the Phase 4 exporters.")
