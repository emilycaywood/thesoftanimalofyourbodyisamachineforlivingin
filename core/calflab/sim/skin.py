"""Reduced-order skin model (ADR-018).

The skin is represented in simulation by, for every joint it spans, a passive
stiffness and damping proportional to the skin thickness, plus its mass
distributed over the covered bodies (carried by the Skin-layer geoms of the
RobotSpec). Coefficients come from the material library and are placeholders
until fitted from physical tests (Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from calflab.components.library import Library
from calflab.model.spec import RobotSpec


@dataclass
class JointSkin:
    stiffness: float = 0.0  # N*m/rad
    damping: float = 0.0  # N*m*s/rad


def skin_joint_effects(spec: RobotSpec, lib: Library, scale: float = 1.0) -> dict[str, JointSkin]:
    """Passive stiffness/damping added to each joint by the skin regions over it."""
    out: dict[str, JointSkin] = {}
    for region in spec.skin_regions:
        mat = lib.material(region.material)
        k = mat.joint_stiffness_nm_per_rad_per_mm * region.thickness_mm * scale
        b = mat.joint_damping_nms_per_rad_per_mm * region.thickness_mm * scale
        for jid in region.joints:
            js = out.setdefault(jid, JointSkin())
            js.stiffness += k
            js.damping += b
    return out


def skin_mass_g(spec: RobotSpec) -> float:
    return sum(g.mass_g for b in spec.bodies for g in b.geoms if g.layer == "Skin")
