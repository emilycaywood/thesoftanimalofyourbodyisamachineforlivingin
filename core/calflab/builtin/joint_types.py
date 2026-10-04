"""Built-in joint types."""

from __future__ import annotations

from calflab.plugins import JointType, register


@register
class Hinge(JointType):
    key = "hinge"
    label = "Hinge"
    description = "1-DOF revolute joint about an axis."
    dof = 1
    mjcf_type = "hinge"


@register
class Slide(JointType):
    key = "slide"
    label = "Slide"
    description = "1-DOF prismatic joint along an axis (range in mm)."
    dof = 1
    mjcf_type = "slide"


@register
class Fixed(JointType):
    key = "fixed"
    label = "Fixed"
    description = "Rigid connection (welded in simulation)."
    dof = 0
    mjcf_type = None


@register
class Free(JointType):
    key = "free"
    label = "Free"
    description = "6-DOF floating joint (used for the root body)."
    dof = 6
    mjcf_type = None  # the compiler adds the root free joint itself


@register
class Ball(JointType):
    key = "ball"
    label = "Ball"
    description = "3-DOF spherical joint."
    dof = 3
    mjcf_type = None
    stub = True  # TODO(phase2): cone limits and actuation for ball joints
