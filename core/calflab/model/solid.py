"""Mass properties of a pushed solid (ADR-050).

A mesh pushed from Rhino is analysed once, when it arrives: is it closed, and
if so what are its volume, centre of mass and inertia. The result is stored on
the geometry override (``meta["solid"]``) for unit density, so that building a
design needs no file access (evolution workers build from a JSON payload) and a
run record carries exactly what its masses were computed from.

Units: mm, mm^3, and mm^5 for the unit-density inertia (multiply by a density
in g/mm^3 to get g*mm^2).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.model.spec import Inertia6
from calflab.model.xform import IDENTITY, Quat, Vec3

WELD_DIGITS = 4  # vertices closer than 0.0001 mm are one vertex
MIN_BOX_MM = 0.1  # thinnest equivalent box the simulator is given


class SolidInfo(BaseModel):
    """What a pushed mesh is worth as a solid, in the frame of its body."""

    closed: bool = False
    problem: str = ""  # why it cannot be used for mass (empty when closed)
    faces: int = 0
    open_edges: int = 0
    area_mm2: float = 0.0
    volume_mm3: float = 0.0
    com_mm: Vec3 = (0.0, 0.0, 0.0)
    #: inertia about the centre of mass for density 1 (mm^5), body axes
    inertia_mm5: Inertia6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def analyze_mesh(vertices: Any, faces: Any) -> SolidInfo:
    """Closedness, volume, centre of mass and unit-density inertia of a triangle mesh.

    A mesh counts as a solid when every edge is shared by exactly two faces
    after welding coincident vertices, its faces can be oriented consistently
    and it encloses a volume. Several separate closed shells are accepted and
    add up; overlapping shells are counted twice (join them in Rhino first).
    """
    import trimesh

    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, dtype=float), faces=np.asarray(faces, dtype=int), process=False)
    mesh.merge_vertices(digits_vertex=WELD_DIGITS)
    mesh.update_faces(mesh.nondegenerate_faces())
    info = SolidInfo(faces=len(mesh.faces), area_mm2=float(mesh.area))
    if len(mesh.faces) < 4:
        info.problem = "it has fewer than four faces"
        return info
    info.open_edges = int(len(trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1)))
    if not mesh.is_watertight:
        info.problem = (
            f"it is open ({info.open_edges} naked edge{'s' if info.open_edges != 1 else ''})"
            if info.open_edges
            else "some edges are shared by more than two faces (non-manifold)"
        )
        return info
    if not mesh.is_winding_consistent:
        trimesh.repair.fix_normals(mesh)
        if not mesh.is_winding_consistent:
            info.problem = "its faces cannot be oriented consistently"
            return info
    if mesh.volume < 0:
        mesh.invert()
    volume = float(mesh.volume)
    if not math.isfinite(volume) or volume <= 1e-9:
        info.problem = "it encloses no volume"
        return info
    props = mesh.mass_properties  # density 1, inertia about the centre of mass
    i = np.asarray(props["inertia"], dtype=float)
    info.closed = True
    info.volume_mm3 = volume
    info.com_mm = (float(props["center_mass"][0]), float(props["center_mass"][1]), float(props["center_mass"][2]))
    info.inertia_mm5 = (float(i[0, 0]), float(i[1, 1]), float(i[2, 2]), float(i[0, 1]), float(i[0, 2]), float(i[1, 2]))
    return info


def inertia_matrix(i: Inertia6) -> np.ndarray:
    ixx, iyy, izz, ixy, ixz, iyz = i
    return np.array([[ixx, ixy, ixz], [ixy, iyy, iyz], [ixz, iyz, izz]], dtype=float)


def scaled_inertia(i: Inertia6, factor: float) -> Inertia6:
    return (i[0] * factor, i[1] * factor, i[2] * factor, i[3] * factor, i[4] * factor, i[5] * factor)


def _quat_from_matrix(m: np.ndarray) -> Quat:
    """Unit quaternion (w, x, y, z) of a proper rotation matrix."""
    t = float(np.trace(m))
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = (0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = ((m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s)
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s)
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return (float(q[0] / n), float(q[1] / n), float(q[2] / n), float(q[3] / n))


def equivalent_box(mass_g: float, inertia: Inertia6) -> tuple[Vec3, Quat]:
    """Full extents (mm) and orientation of the uniform box that has this mass
    and this inertia tensor (g*mm^2, about its centre).

    The simulator composes body inertia from primitives; a box with the same
    mass, centre and inertia tensor is dynamically identical to the solid. A
    box with principal moments (I1, I2, I3) has extents
    ``a^2 = 6 (I2 + I3 - I1) / m`` and cyclic.
    """
    if mass_g <= 0:
        return (MIN_BOX_MM, MIN_BOX_MM, MIN_BOX_MM), IDENTITY
    moments, axes = np.linalg.eigh(inertia_matrix(inertia))
    if np.linalg.det(axes) < 0:
        axes[:, 2] = -axes[:, 2]
    i1, i2, i3 = (float(v) for v in moments)

    def extent(a: float, b: float, c: float) -> float:
        return max(math.sqrt(max(6.0 * (b + c - a) / mass_g, 0.0)), MIN_BOX_MM)

    return (extent(i1, i2, i3), extent(i2, i3, i1), extent(i3, i1, i2)), _quat_from_matrix(axes)
