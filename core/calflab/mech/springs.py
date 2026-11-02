"""Tension springs across a joint (ADR-065).

A spring pulls only: zero force while slack, never pushes. It is stretched
between an anchor on the segment above a joint and one on the segment below,
each stored relative to the joint axis. Its torque about the joint is the
force times the perpendicular distance from the joint axis to the spring
line, computed from the geometry at every pose (in the simulator, every
physics step).

Unlike a belt drive (ADR-063), every spring value is continuous and tunable:
rate, free length and the four anchor coordinates are genes.

Units: mm, N, N*m (torques), degrees.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.model.xform import Vec3


class SpringDef(BaseModel):
    """Genes of one spring type, shared by left and right (mm, N/mm).

    Anchors are measured from the joint axis in the plane of the leg:
    ``along`` up the segment above (``upper_along``) or down the segment
    below (``lower_along``), ``normal`` perpendicular to that segment,
    positive toward the front of the animal.
    """

    enabled: bool = True
    k_n_per_mm: float
    free_length_mm: float
    upper_along_mm: float
    upper_normal_mm: float
    lower_along_mm: float
    lower_normal_mm: float


def spring_force_n(length_mm: float, k_n_per_mm: float, free_length_mm: float) -> float:
    """Tension-only spring force (N): k (L - L0) when stretched, 0 when slack."""
    return k_n_per_mm * max(0.0, length_mm - free_length_mm)


class SpringState(BaseModel):
    length_mm: float
    stretch_mm: float  # negative = slack
    force_n: float
    arm_mm: float  # perpendicular distance from the joint axis to the spring line
    torque_nm: float  # on the lower segment about the joint axis (sign: positive turns the joint positive)
    slack: bool


def spring_state(
    upper_world: Vec3, lower_world: Vec3, joint_world: Vec3, axis_world: Vec3, k_n_per_mm: float, free_length_mm: float
) -> SpringState:
    """Force and torque of a spring between two world points (mm) about a joint axis."""
    pu, pl, pj = np.asarray(upper_world, float), np.asarray(lower_world, float), np.asarray(joint_world, float)
    a = np.asarray(axis_world, float)
    a = a / (np.linalg.norm(a) or 1.0)
    d = pu - pl
    length = float(np.linalg.norm(d))
    unit = d / length if length > 0 else np.zeros(3)
    moment = float(np.dot(np.cross(pl - pj, unit), a))  # mm per newton, signed
    f = spring_force_n(length, k_n_per_mm, free_length_mm)
    return SpringState(
        length_mm=length,
        stretch_mm=length - free_length_mm,
        force_n=f,
        arm_mm=abs(moment),
        torque_nm=u.nmm_to_nm(f * moment),
        slack=length <= free_length_mm,
    )


SideVerdict = Literal["resists", "helps_collapse", "slack", "no_load"]


def side_check(gravity_torque_nm: float, spring_torque_nm: float, tolerance_nm: float = 1e-4) -> tuple[SideVerdict, str]:
    """Is the spring on the side that resists the way gravity folds the joint?

    ``gravity_torque_nm`` is the torque the body's weight and the ground
    reaction put on the segment below the joint (the servo must supply the
    opposite); ``spring_torque_nm`` the spring's torque on the same segment.
    """
    if abs(spring_torque_nm) <= tolerance_nm:
        return "slack", "the spring is slack (or its line passes through the axis) in this pose"
    if abs(gravity_torque_nm) <= tolerance_nm:
        return "no_load", "gravity puts no torque on this joint in this pose"
    if math.copysign(1.0, spring_torque_nm) == math.copysign(1.0, gravity_torque_nm):
        return ("helps_collapse",
                f"WARNING: gravity folds the joint with {gravity_torque_nm:+.3f} N*m and the spring adds "
                f"{spring_torque_nm:+.3f} N*m the same way: it is on the side that helps it collapse")
    return "resists", f"gravity {gravity_torque_nm:+.3f} N*m, spring {spring_torque_nm:+.3f} N*m: the spring resists the fold"
