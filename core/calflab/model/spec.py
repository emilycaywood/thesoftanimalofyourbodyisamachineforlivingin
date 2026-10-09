"""RobotSpec: the explicit description of one robot design.

Units: **mm, g, degrees**. Frame: X forward, Y left, Z up. Quaternions are
(w, x, y, z). Every element has a stable, human-readable ID that is shared by
Rhino user text, Blender bone names, the web scene graph and fabrication
labels (ADR-006).
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from calflab.model.xform import IDENTITY, Quat, Vec3, compose, quat_axis_angle

SPEC_SCHEMA_VERSION = 1

LAYERS: list[str] = [
    "Structure",
    "Actuators",
    "Transmission",
    "Electronics",
    "Sensors",
    "Skin",
    "Harness",
    "Annotations",
]

LAYER_COLORS: dict[str, str] = {
    "Structure": "#b9c0c9",
    "Actuators": "#e0823d",
    "Transmission": "#d4b13f",
    "Electronics": "#4fa36b",
    "Sensors": "#3f9fd4",
    "Skin": "#d9a48f",
    "Harness": "#c4504e",
    "Annotations": "#9b7fd1",
}

GeomShape = Literal["box", "capsule", "cylinder", "sphere", "ellipsoid", "mesh"]

#: Where a geom's mass comes from (ADR-050). ``parametric`` is the envelope
#: estimate of ADR-017; ``geometry`` is a pushed closed solid x material density.
MassSource = Literal["parametric", "component", "geometry", "measured"]
#: (ixx, iyy, izz, ixy, ixz, iyz)
Inertia6 = tuple[float, float, float, float, float, float]


class Geom(BaseModel):
    """A primitive attached to a body, in the body frame.

    ``size`` (mm): box = full extents (x, y, z); sphere = (radius, 0, 0);
    capsule/cylinder = (radius, length, 0) along the geom's local Z, centred on
    ``pos`` (capsule length excludes the end caps); ellipsoid = semi-axes.
    """

    id: str
    shape: GeomShape
    size: Vec3
    pos: Vec3 = (0.0, 0.0, 0.0)
    quat: Quat = IDENTITY
    layer: str = "Structure"
    role: Literal["visual", "collision", "both"] = "both"
    mass_g: float = 0.0
    color: str | None = None
    component: str | None = None  # component-library key (repeated parts become Rhino blocks)
    mesh: str | None = None  # project-relative asset path for shape == "mesh"
    label: str | None = None
    foot: bool = False  # ground-contact geom used for gait metrics
    # ---- mass bookkeeping (ADR-050)
    mass_source: MassSource = "parametric"
    material: str | None = None  # material-library key the mass was computed with
    #: centre of mass in the geom frame (mm); None = the geom origin
    com: Vec3 | None = None
    #: inertia tensor about the centre of mass, geom axes (g*mm^2); None = that of the primitive
    inertia: Inertia6 | None = None
    mass_computed_g: float | None = None  # value a measured mass replaced
    mass_replaced_g: float | None = None  # envelope estimate a pushed solid replaced (not counted)
    mass_note: str = ""  # e.g. why a pushed solid was not used for mass

    def mass_center(self) -> Vec3:
        """Centre of mass in the body frame (mm)."""
        if self.com is None:
            return self.pos
        from calflab.model.xform import quat_rotate

        r = quat_rotate(self.quat, self.com)
        return (self.pos[0] + r[0], self.pos[1] + r[1], self.pos[2] + r[2])

    def volume_mm3(self) -> float:
        a, b, c = self.size
        if self.shape == "box":
            return a * b * c
        if self.shape == "sphere":
            return 4.0 / 3.0 * math.pi * a**3
        if self.shape == "capsule":
            return math.pi * a * a * b + 4.0 / 3.0 * math.pi * a**3
        if self.shape == "cylinder":
            return math.pi * a * a * b
        if self.shape == "ellipsoid":
            return 4.0 / 3.0 * math.pi * a * b * c
        return 0.0

    def area_mm2(self) -> float:
        a, b, c = self.size
        if self.shape == "box":
            return 2.0 * (a * b + b * c + a * c)
        if self.shape == "sphere":
            return 4.0 * math.pi * a * a
        if self.shape == "capsule":
            return 2.0 * math.pi * a * b + 4.0 * math.pi * a * a
        if self.shape == "cylinder":
            return 2.0 * math.pi * a * b + 2.0 * math.pi * a * a
        if self.shape == "ellipsoid":
            p = 1.6075  # Knud Thomsen approximation
            return 4.0 * math.pi * (((a * b) ** p + (a * c) ** p + (b * c) ** p) / 3.0) ** (1 / p)
        return 0.0


class Body(BaseModel):
    """A rigid body. ``pos``/``quat`` are relative to the parent body frame."""

    id: str
    name: str = ""
    parent: str | None = None
    pos: Vec3 = (0.0, 0.0, 0.0)
    quat: Quat = IDENTITY
    geoms: list[Geom] = Field(default_factory=list)
    layer: str = "Structure"
    part: bool = True  # a fabricated part (appears in the parts list)

    def mass_g(self) -> float:
        return sum(g.mass_g for g in self.geoms)


JointKind = Literal["hinge", "slide", "ball", "free", "fixed"]


class Joint(BaseModel):
    """Joint between ``body`` and its parent, located at the body origin."""

    id: str
    name: str = ""
    body: str
    type: JointKind = "hinge"
    axis: Vec3 = (0.0, 1.0, 0.0)
    range_deg: tuple[float, float] = (-90.0, 90.0)
    rest_deg: float = 0.0  # standing pose
    group: str = "leg"
    cosmetic: bool = False
    damping: float = 0.0  # N*m*s/rad, structural (skin adds more)
    friction: float = 0.0  # N*m dry friction


class Transmission(BaseModel):
    id: str
    type: Literal["direct", "belt", "linkage"] = "direct"
    ratio: float = 1.0  # output torque = motor torque * ratio
    efficiency: float = 1.0
    motor_body: str | None = None  # where the motor mass sits


class Actuator(BaseModel):
    id: str
    joint: str
    component: str  # key in the actuator library
    transmission: str | None = None


class Sensor(BaseModel):
    id: str
    type: str  # imu | fsr | touch | microphone | depth_camera | motor_feedback
    component: str | None = None
    body: str
    pos: Vec3 = (0.0, 0.0, 0.0)
    params: dict[str, Any] = Field(default_factory=dict)


class Seam(BaseModel):
    """A seam line on a skin region (Phase 4: pattern flattening)."""

    id: str
    points: list[Vec3] = Field(default_factory=list)  # in the frame of ``body``
    body: str | None = None


class SkinRegion(BaseModel):
    id: str
    bodies: list[str]
    joints: list[str] = Field(default_factory=list)
    material: str
    thickness_mm: float
    area_mm2: float = 0.0
    seams: list[Seam] = Field(default_factory=list)


class Wire(BaseModel):
    signal: str
    gauge_awg: int = 22
    color: str = "BK"


class HarnessRoute(BaseModel):
    """A cable from one element to another, routed through the body."""

    id: str
    src: str  # element id (component geom / sensor / actuator)
    dst: str
    via_bodies: list[str] = Field(default_factory=list)
    wires: list[Wire] = Field(default_factory=list)
    length_mm: float = 0.0
    connector: str = "JST-EH-3"


class RobotSpec(BaseModel):
    name: str = "calf"
    schema_version: int = SPEC_SCHEMA_VERSION
    bodies: list[Body] = Field(default_factory=list)
    joints: list[Joint] = Field(default_factory=list)
    actuators: list[Actuator] = Field(default_factory=list)
    transmissions: list[Transmission] = Field(default_factory=list)
    sensors: list[Sensor] = Field(default_factory=list)
    skin_regions: list[SkinRegion] = Field(default_factory=list)
    harness_routes: list[HarnessRoute] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------ validation
    @model_validator(mode="after")
    def _check(self) -> RobotSpec:
        ids: set[str] = set()
        for group in (
            self.bodies,
            self.joints,
            self.actuators,
            self.transmissions,
            self.sensors,
            self.skin_regions,
            self.harness_routes,
        ):
            for el in group:
                if el.id in ids:
                    raise ValueError(f"Duplicate element id {el.id!r}")
                ids.add(el.id)
        for b in self.bodies:
            for g in b.geoms:
                if g.id in ids:
                    raise ValueError(f"Duplicate element id {g.id!r}")
                ids.add(g.id)
        body_ids = {b.id for b in self.bodies}
        roots = [b for b in self.bodies if b.parent is None]
        if self.bodies and len(roots) != 1:
            raise ValueError(f"RobotSpec needs exactly one root body, found {len(roots)}")
        seen: set[str] = set()
        for b in self.bodies:  # parents must precede children
            if b.parent is not None and b.parent not in seen:
                raise ValueError(f"Body {b.id!r}: parent {b.parent!r} must be defined before it")
            seen.add(b.id)
        for j in self.joints:
            if j.body not in body_ids:
                raise ValueError(f"Joint {j.id!r} references unknown body {j.body!r}")
        joint_ids = {j.id for j in self.joints}
        for a in self.actuators:
            if a.joint not in joint_ids:
                raise ValueError(f"Actuator {a.id!r} references unknown joint {a.joint!r}")
        return self

    # ------------------------------------------------------------------ lookup
    def body(self, body_id: str) -> Body:
        for b in self.bodies:
            if b.id == body_id:
                return b
        raise KeyError(body_id)

    def joint(self, joint_id: str) -> Joint:
        for j in self.joints:
            if j.id == joint_id:
                return j
        raise KeyError(joint_id)

    @property
    def root(self) -> Body:
        return next(b for b in self.bodies if b.parent is None)

    def joints_of(self, body_id: str) -> list[Joint]:
        return [j for j in self.joints if j.body == body_id]

    def actuator_for(self, joint_id: str) -> Actuator | None:
        for a in self.actuators:
            if a.joint == joint_id:
                return a
        return None

    def element_ids(self) -> list[str]:
        out = [b.id for b in self.bodies]
        out += [g.id for b in self.bodies for g in b.geoms]
        out += [j.id for j in self.joints]
        out += [a.id for a in self.actuators]
        out += [s.id for s in self.sensors]
        out += [s.id for s in self.skin_regions]
        out += [h.id for h in self.harness_routes]
        return out

    # ------------------------------------------------------------------ kinematics
    def rest_angles(self) -> dict[str, float]:
        """Standing-pose joint angles (deg) by joint id."""
        return {j.id: j.rest_deg for j in self.joints if j.type in ("hinge", "slide")}

    def world_poses(
        self, angles_deg: dict[str, float] | None = None, root_pos: Vec3 | None = None
    ) -> dict[str, tuple[Vec3, Quat]]:
        """Forward kinematics: world pose (mm, quat) of every body.

        ``angles_deg`` defaults to the standing pose. ``root_pos`` defaults to
        the root body's ``pos``.
        """
        angles = self.rest_angles() if angles_deg is None else angles_deg
        out: dict[str, tuple[Vec3, Quat]] = {}
        for b in self.bodies:
            p, q = b.pos, b.quat
            for j in self.joints_of(b.id):
                if j.type == "hinge":
                    q = _qmul(q, quat_axis_angle(j.axis, angles.get(j.id, 0.0)))
                elif j.type == "slide":
                    d = angles.get(j.id, 0.0)
                    p = (p[0] + j.axis[0] * d, p[1] + j.axis[1] * d, p[2] + j.axis[2] * d)
            if b.parent is None:
                out[b.id] = (root_pos if root_pos is not None else p, q)
            else:
                pp, pq = out[b.parent]
                out[b.id] = compose(pp, pq, p, q)
        return out

    # ------------------------------------------------------------------ mass
    def total_mass_g(self) -> float:
        return sum(b.mass_g() for b in self.bodies)

    def mass_by_layer(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for b in self.bodies:
            for g in b.geoms:
                out[g.layer] = out.get(g.layer, 0.0) + g.mass_g
        return out

    def center_of_mass(self, poses: dict[str, tuple[Vec3, Quat]] | None = None) -> Vec3:
        """Centre of mass (mm, world) in the given or standing pose."""
        from calflab.model.xform import quat_rotate

        poses = poses or self.world_poses()
        m = 0.0
        acc = [0.0, 0.0, 0.0]
        for b in self.bodies:
            bp, bq = poses[b.id]
            for g in b.geoms:
                if g.mass_g <= 0:
                    continue
                r = quat_rotate(bq, g.mass_center())
                for i in range(3):
                    acc[i] += g.mass_g * (bp[i] + r[i])
                m += g.mass_g
        if m == 0:
            return (0.0, 0.0, 0.0)
        return (acc[0] / m, acc[1] / m, acc[2] / m)


def _qmul(a: Quat, b: Quat) -> Quat:
    from calflab.model.xform import quat_mul

    return quat_mul(a, b)
