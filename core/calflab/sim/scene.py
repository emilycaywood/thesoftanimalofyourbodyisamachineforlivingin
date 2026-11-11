"""Things in the world besides the floor, and contact probes (ADR-110).

A compiled model has a floor and nothing else. Outcome behaviours need a little more: suckling pushes the head into a
fixed block, and lying down is judged by how hard the body (not the hooves) meets the floor. This module edits a
``CompiledModel`` after ``compile_mjcf``:

* ``with_scene(cm, blocks=..., collide=..., probes=...)`` adds fixed boxes to the world, makes named robot geoms
  collide (the head is a visual-only lump in the feral calf), and asks the runner to record contact forces;
* ``collision_geoms(cm)`` lists the robot's colliding geoms (to build "everything but the hooves" probes).

Nothing here changes a model that does not use it: ``compile_mjcf`` is unchanged and a model without probes records
exactly what it did before. Units: blocks in mm in a world frame (X forward, Z up), converted with ``calflab.units``.
"""
from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from typing import Any

from pydantic import BaseModel

from calflab import units as u
from calflab.schema import P
from calflab.sim.mjcf import CompiledModel


class Block(BaseModel):
    """A fixed box in the world."""

    id: str = P("block", desc="Geom name (unique in the model).")
    center_mm: tuple[float, float, float] = P((0.0, 0.0, 0.0), unit="mm", desc="Centre in the world frame.")
    half_mm: tuple[float, float, float] = P((20.0, 60.0, 40.0), unit="mm", desc="Half extents (x, y, z).")
    friction: float | None = P(None, ge=0.0, le=3.0, desc="Sliding friction; None = the model's default.")


def collision_geoms(cm: CompiledModel) -> list[str]:
    """Names of the robot's geoms that collide (contype 1), in model order."""
    root = ET.fromstring(cm.xml)
    out = []
    for body in root.iter("body"):
        for g in body.findall("geom"):
            if g.get("contype") == "1" and g.get("name"):
                out.append(str(g.get("name")))
    return out


def with_scene(cm: CompiledModel, blocks: list[Block] | None = None, collide: list[str] | None = None,
               probes: list[dict[str, Any]] | None = None) -> CompiledModel:
    """A copy of ``cm`` with ``blocks`` in the world, the robot geoms named in ``collide`` colliding, and ``probes``
    (``{"id", "geoms", "other"}``, geom names) recorded by the runner. Unknown geom names raise ``KeyError``."""
    root = ET.fromstring(cm.xml)
    world = root.find("worldbody")
    assert world is not None
    for b in blocks or []:
        attrs = {"name": b.id, "type": "box", "pos": " ".join(f"{u.mm_to_m(v):.6g}" for v in b.center_mm),
                 "size": " ".join(f"{u.mm_to_m(v):.6g}" for v in b.half_mm), "contype": "0", "conaffinity": "1",
                 "rgba": "0.55 0.45 0.35 1"}
        if b.friction is not None:
            attrs["friction"] = f"{b.friction:.6g} 0.02 0.001"
        ET.SubElement(world, "geom", attrib=attrs)
    names = set(collide or [])
    found: set[str] = set()
    for body in root.iter("body"):
        for g in body.findall("geom"):
            if g.get("name") in names:
                g.set("contype", "1")
                g.set("group", "0")
                found.add(str(g.get("name")))
    missing = names - found
    if missing:
        raise KeyError(f"no such robot geom: {sorted(missing)}")
    ET.indent(root)
    return dataclasses.replace(cm, xml=ET.tostring(root, encoding="unicode"), probes=list(probes or []))
