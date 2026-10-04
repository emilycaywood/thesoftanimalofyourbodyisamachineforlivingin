"""RobotSpec -> MJCF compiler (SI units). All unit conversion goes through
:mod:`calflab.units`.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from calflab import units as u
from calflab.components.library import Library
from calflab.model.spec import Body, Geom, RobotSpec
from calflab.schema import P
from calflab.sim.skin import skin_joint_effects


class DomainRandomization(BaseModel):
    """Ranges sampled once per rollout (multiplicative scales unless noted)."""

    enabled: bool = P(False, desc="Randomize physical parameters for each rollout.")
    friction: tuple[float, float] = P((0.6, 1.2), ui="json", desc="Floor friction coefficient range.")
    mass_scale: tuple[float, float] = P((0.9, 1.1), ui="json", desc="Scale applied to every mass.")
    torque_scale: tuple[float, float] = P((0.85, 1.05), ui="json", desc="Scale on available torque.")
    kp_scale: tuple[float, float] = P((0.8, 1.2), ui="json", desc="Scale on servo stiffness.")
    damping_scale: tuple[float, float] = P((0.7, 1.5), ui="json", desc="Scale on joint damping.")
    skin_scale: tuple[float, float] = P((0.5, 2.0), ui="json", desc="Scale on skin stiffness/damping.")


class CompileOptions(BaseModel):
    """How a design is turned into a simulation model."""

    timestep_ms: float = P(2.0, unit="ms", ge=0.5, le=10, step=0.5, desc="Physics time step.")
    terrain: Literal["flat", "slope", "bumps"] = P("flat", desc="Ground preset.")
    slope_deg: float = P(5.0, unit="deg", ge=-20, le=20, desc="Incline for the 'slope' terrain (uphill positive).")
    floor_friction: float = P(0.9, ge=0.1, le=2.0, step=0.05, desc="Sliding friction coefficient of the ground.")
    torque_derating: float = P(0.6, ge=0.1, le=1.0, step=0.05, desc="Usable fraction of actuator stall torque.")
    servo_saturation_deg: float = P(10.0, unit="deg", ge=1, le=45, desc="Position error at which a servo reaches its usable torque.")
    servo_kd_ratio_s: float = P(0.03, unit="s", ge=0.0, le=0.2, step=0.005, desc="Servo damping as a fraction of its stiffness.")
    include_skin: bool = P(True, desc="Apply the skin model (joint stiffness/damping and added mass).")
    randomization: DomainRandomization = P(default_factory=DomainRandomization, ui="json", desc="Domain randomization ranges.", advanced=True)


@dataclass
class Scales:
    friction: float = 1.0
    mass: float = 1.0
    torque: float = 1.0
    kp: float = 1.0
    damping: float = 1.0
    skin: float = 1.0


def sample_scales(rand: DomainRandomization, seed: int, floor_friction: float) -> Scales:
    if not rand.enabled:
        return Scales(friction=floor_friction)
    rng = np.random.default_rng(seed)

    def s(r: tuple[float, float]) -> float:
        return float(rng.uniform(r[0], r[1]))

    return Scales(
        friction=s(rand.friction),
        mass=s(rand.mass_scale),
        torque=s(rand.torque_scale),
        kp=s(rand.kp_scale),
        damping=s(rand.damping_scale),
        skin=s(rand.skin_scale),
    )


@dataclass
class CompiledModel:
    """MJCF text plus the name tables the runner and metrics need."""

    xml: str
    body_ids: list[str]
    joint_ids: list[str]  # actuated + passive hinge/slide joints, qpos order after the root
    actuator_ids: list[str]
    actuator_joint: list[str]  # joint id per actuator
    actuator_component: list[str]
    actuator_torque_limit: list[float]  # usable torque at the joint, N*m
    actuator_stall: list[float]  # stall torque at the joint, N*m
    foot_geoms: list[str]
    rest: dict[str, float]  # rad
    limits: dict[str, tuple[float, float]]  # rad
    total_mass_kg: float
    timestep: float
    root_height: float  # m
    scales: dict[str, float] = field(default_factory=dict)


def _f(x: float) -> str:
    return f"{x:.6g}"


def _vec(v: Any) -> str:
    return " ".join(_f(float(x)) for x in v)


def _geom_size(g: Geom) -> str:
    a, b, c = g.size
    if g.shape == "box":
        return _vec((u.mm_to_m(a) / 2, u.mm_to_m(b) / 2, u.mm_to_m(c) / 2))
    if g.shape == "sphere":
        return _f(u.mm_to_m(a))
    if g.shape in ("capsule", "cylinder"):
        return _vec((u.mm_to_m(a), u.mm_to_m(b) / 2))
    if g.shape == "ellipsoid":
        return _vec(u.vec_mm_to_m((a, b, c)))
    return _f(0.005)


def compile_mjcf(
    spec: RobotSpec, lib: Library, options: CompileOptions | None = None, seed: int = 0
) -> CompiledModel:
    """Compile a RobotSpec to MJCF. Deterministic for a given ``seed``."""
    from calflab.plugins import load_plugins, registry

    load_plugins()
    opt = options or CompileOptions()
    sc = sample_scales(opt.randomization, seed, opt.floor_friction)
    skin = skin_joint_effects(spec, lib, sc.skin) if opt.include_skin else {}

    root = ET.Element("mujoco", model=spec.name)
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", boundmass="0.001", boundinertia="1e-8")
    g = 9.81
    if opt.terrain == "slope":
        a = u.deg_to_rad(opt.slope_deg)
        gravity = (-g * math.sin(a), 0.0, -g * math.cos(a))
    else:
        gravity = (0.0, 0.0, -g)
    ET.SubElement(
        root,
        "option",
        timestep=_f(u.to_si(opt.timestep_ms, "ms")),
        integrator="implicitfast",
        gravity=_vec(gravity),
    )
    default = ET.SubElement(root, "default")
    ET.SubElement(default, "geom", condim="3", friction=_vec((sc.friction, 0.02, 0.001)), solref="0.01 1")
    ET.SubElement(default, "joint", limited="true")

    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 0 3", dir="0 0 -1")
    ET.SubElement(
        world, "geom", name="floor", type="plane", size="20 20 0.1", contype="0", conaffinity="1", rgba="0.3 0.3 0.3 1"
    )
    if opt.terrain == "bumps":
        rng = np.random.default_rng(seed + 7919)
        for i in range(24):
            x, y = rng.uniform(0.2, 4.0), rng.uniform(-0.5, 0.5)
            h = rng.uniform(0.004, 0.012)
            ET.SubElement(
                world,
                "geom",
                name=f"bump{i}",
                type="box",
                pos=_vec((x, y, h)),
                size=_vec((rng.uniform(0.02, 0.06), rng.uniform(0.05, 0.2), h)),
                contype="0",
                conaffinity="1",
            )

    children: dict[str | None, list[Body]] = {}
    for b in spec.bodies:
        children.setdefault(b.parent, []).append(b)

    act_by_joint = {a.joint: a for a in spec.actuators}
    trans_by_id = {t.id: t for t in spec.transmissions}
    joint_order: list[str] = []
    body_order: list[str] = []
    foot_geoms: list[str] = []
    rest: dict[str, float] = {}
    limits: dict[str, tuple[float, float]] = {}
    total_mass = 0.0

    def emit(parent_el: ET.Element, body: Body) -> None:
        nonlocal total_mass
        pos = u.vec_mm_to_m(body.pos)
        if body.parent is None:
            pos = (pos[0], pos[1], pos[2] + 0.002)
        el = ET.SubElement(parent_el, "body", name=body.id, pos=_vec(pos), quat=_vec(body.quat))
        body_order.append(body.id)
        if body.parent is None:
            ET.SubElement(el, "freejoint", name="root")
            ET.SubElement(el, "site", name="imu", pos="0 0 0", size="0.005")
        for j in spec.joints_of(body.id):
            jt_cls = registry.get("joint_type", j.type)
            if jt_cls.mjcf_type is None:  # type: ignore[attr-defined]
                continue
            lo, hi = u.deg_to_rad(j.range_deg[0]), u.deg_to_rad(j.range_deg[1])
            r = u.deg_to_rad(j.rest_deg)
            sk = skin.get(j.id)
            damping = j.damping * sc.damping + (sk.damping if sk else 0.0)
            attrs = {
                "name": j.id,
                "type": jt_cls.mjcf_type,  # type: ignore[attr-defined]
                "axis": _vec(j.axis),
                "range": _vec((lo, hi)),
                "damping": _f(damping),
                "frictionloss": _f(j.friction),
            }
            if sk and sk.stiffness > 0:
                attrs["stiffness"] = _f(sk.stiffness)
                attrs["springref"] = _f(r)
            act = act_by_joint.get(j.id)
            if act is not None:
                comp = lib.actuator(act.component)
                ratio = trans_by_id[act.transmission].ratio if act.transmission else 1.0
                attrs["armature"] = _f(comp.armature_kgm2 * ratio * ratio)
            attrs.update(jt_cls().mjcf_attrs(j))  # type: ignore[attr-defined]
            ET.SubElement(el, "joint", **attrs)
            joint_order.append(j.id)
            rest[j.id] = r
            limits[j.id] = (lo, hi)
        for geom in body.geoms:
            if geom.layer == "Skin" and not opt.include_skin and not geom.foot:
                continue
            mass = u.g_to_kg(geom.mass_g) * sc.mass
            total_mass += mass
            shape = "sphere" if geom.shape == "mesh" else geom.shape
            collide = geom.role in ("collision", "both")
            attrs = {
                "name": geom.id,
                "type": shape,
                "size": _geom_size(geom),
                "pos": _vec(u.vec_mm_to_m(geom.pos)),
                "quat": _vec(geom.quat),
                "mass": _f(mass),
                "contype": "1" if collide else "0",
                "conaffinity": "0",
                "group": "0" if collide else "1",
            }
            ET.SubElement(el, "geom", **attrs)
            if geom.foot:
                foot_geoms.append(geom.id)
        for child in children.get(body.id, []):
            emit(el, child)

    for rb in children.get(None, []):
        emit(world, rb)

    actuator_el = ET.SubElement(root, "actuator")
    a_ids: list[str] = []
    a_joint: list[str] = []
    a_comp: list[str] = []
    a_limit: list[float] = []
    a_stall: list[float] = []
    sat = u.deg_to_rad(opt.servo_saturation_deg)
    for act in spec.actuators:
        if act.joint not in limits:
            continue
        comp = lib.actuator(act.component)
        tr = trans_by_id.get(act.transmission) if act.transmission else None
        gain = (tr.ratio * tr.efficiency) if tr else 1.0
        stall = comp.stall_torque_nm * gain
        usable = stall * opt.torque_derating * sc.torque
        kp = usable / sat * sc.kp
        lo, hi = limits[act.joint]
        ET.SubElement(
            actuator_el,
            "position",
            name=act.id,
            joint=act.joint,
            kp=_f(kp),
            kv=_f(kp * opt.servo_kd_ratio_s),
            forcerange=_vec((-usable, usable)),
            ctrlrange=_vec((lo, hi)),
        )
        a_ids.append(act.id)
        a_joint.append(act.joint)
        a_comp.append(act.component)
        a_limit.append(usable)
        a_stall.append(stall)

    sensor_el = ET.SubElement(root, "sensor")
    ET.SubElement(sensor_el, "gyro", name="imu_gyro", site="imu")
    ET.SubElement(sensor_el, "accelerometer", name="imu_acc", site="imu")

    root_h = u.mm_to_m(spec.root.pos[2]) + 0.002
    key = ET.SubElement(root, "keyframe")
    qpos = [0.0, 0.0, root_h, 1.0, 0.0, 0.0, 0.0] + [rest[j] for j in joint_order]
    ctrl = [rest[j] for j in a_joint]
    ET.SubElement(key, "key", name="stand", qpos=_vec(qpos), ctrl=_vec(ctrl))

    ET.indent(root)
    xml = ET.tostring(root, encoding="unicode")
    return CompiledModel(
        xml=xml,
        body_ids=body_order,
        joint_ids=joint_order,
        actuator_ids=a_ids,
        actuator_joint=a_joint,
        actuator_component=a_comp,
        actuator_torque_limit=a_limit,
        actuator_stall=a_stall,
        foot_geoms=foot_geoms,
        rest=rest,
        limits=limits,
        total_mass_kg=total_mass,
        timestep=u.to_si(opt.timestep_ms, "ms"),
        root_height=root_h,
        scales=sc.__dict__.copy(),
    )
