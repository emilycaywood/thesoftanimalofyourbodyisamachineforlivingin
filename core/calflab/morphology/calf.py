"""Reference calf part generator.

Genome (``config/genes/calf.yaml``) -> element parameters -> RobotSpec.

Frame: X forward, Y left, Z up; mm, g, degrees. Leg keys: ``fl``, ``fr``,
``hl``, ``hr``. A positive hinge angle about +Y swings a downward-pointing
segment backward, so the standing pose of a backward-pointing knee is
``hip_flex > 0`` and ``knee < 0``.

A front leg may have two motors instead of three (gene ``front_hip_flex`` off):
the thigh is then fixed to the hip at its standing angle, there is no
``joint.<k>.hip_flex`` / ``act.<k>.hip_flex``, and the knee works as an elbow.

Proportions and the mass model are assumptions (ADR-015, ADR-017).

Gene ``scale`` multiplies every length (mm) gene and the fixed millimetre
offsets of this generator, so a small test calf keeps the proportions the
ranges describe. Wall and skin thickness are fabrication choices and do not
scale (ADR-052).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from calflab.model.genome import GeneValue
from calflab.model.overrides import ElementParams, ParamValue
from calflab.model.spec import (
    Actuator,
    Body,
    Geom,
    HarnessRoute,
    Joint,
    RobotSpec,
    Sensor,
    SkinRegion,
    Transmission,
    Wire,
)
from calflab.model.xform import IDENTITY, Vec3, quat_axis_angle, quat_from_z_to, quat_rotate
from calflab.plugins import BuildContext, PartGenerator, register
from calflab.schema import P

LEGS: dict[str, tuple[int, int]] = {"fl": (1, 1), "fr": (1, -1), "hl": (-1, 1), "hr": (-1, -1)}
LEG_NAMES = {"fl": "front left", "fr": "front right", "hl": "hind left", "hr": "hind right"}


def standing_leg_angles(l1: float, l2: float, bend_deg: float, forward: bool) -> tuple[float, float]:
    """(hip_flex, knee) in degrees that put the hoof directly under the hip."""
    b = math.radians(bend_deg)
    th = math.atan2(l2 * math.sin(b), l1 + l2 * math.cos(b))
    if forward:
        return -math.degrees(th), bend_deg
    return math.degrees(th), -bend_deg


def standing_leg_height(l1: float, l2: float, bend_deg: float) -> float:
    """Vertical distance hip axis -> hoof centre in the standing pose (mm)."""
    b = math.radians(bend_deg)
    th = math.atan2(l2 * math.sin(b), l1 + l2 * math.cos(b))
    return l1 * math.cos(th) + l2 * math.cos(b - th)


@register
class CalfGenerator(PartGenerator):
    """Trunk + four 3-DOF legs + neck/head + optional tail and ears."""

    key = "calf"
    label = "Reference calf"
    description = "Quadruped calf: trunk, 4 legs (hip abduction, hip flexion, knee; front hip flexion optional), neck, head, tail, ears."
    version = "1"
    genome_definition = "calf"

    class Params(BaseModel):
        skin_clearance: float = P(
            4.0, unit="mm", ge=0, le=20, desc="Gap between structure and skin surface."
        )
        show_skin: bool = P(True, desc="Generate skin preview surfaces.")

    # ------------------------------------------------------------------ stage 1
    def element_params(self, genes: dict[str, GeneValue]) -> ElementParams:
        from calflab.config import gene_definition_files

        gdef = gene_definition_files()["calf"]
        s = float(genes.get("scale", 1.0))  # type: ignore[arg-type]

        def pv(
            gene: str,
            label: str | None = None,
            handle: tuple[float, float, float] | None = None,
            frac: float = 1.0,
        ) -> ParamValue:
            g = gdef.gene(gene)
            k = s if g.unit == "mm" else 1.0  # lengths follow the overall scale
            return ParamValue(
                value=float(genes[gene]) * k,  # type: ignore[arg-type]
                unit=g.unit,
                gene=gene,
                scale=k,
                min=None if g.min is None else g.min * k,
                max=None if g.max is None else g.max * k,
                label=label,
                handle_axis=handle,
                handle_frac=frac,
            )

        def offsets() -> dict[str, ParamValue]:
            return {
                f"offset_{a}": ParamValue(value=0.0, unit="mm", min=-200, max=200, label=f"Offset {a.upper()}")
                for a in "xyz"
            }

        out: ElementParams = {
            "trunk": {
                "length": pv("trunk_length", handle=(1.0, 0.0, 0.0), frac=0.5),
                "width": pv("trunk_width", handle=(0.0, 1.0, 0.0), frac=0.4),
                "height": pv("trunk_height", handle=(0.0, 0.0, 1.0), frac=0.4),
            }
        }
        down = (0.0, 0.0, -1.0)
        for k in LEGS:
            out[f"leg.{k}.hip"] = {"offset": pv("leg_offset", "Leg offset"), **offsets()}
            out[f"leg.{k}.thigh"] = {
                "length": pv("thigh_length", handle=down),
                "radius": pv("leg_radius"),
                **offsets(),
            }
            out[f"leg.{k}.shank"] = {
                "length": pv("shank_length", handle=down),
                "radius": pv("leg_radius"),
                "hoof_radius": pv("hoof_radius"),
                **offsets(),
            }
        out["neck"] = {
            "length": pv("neck_length"),
            "radius": pv("neck_radius"),
            "angle": pv("neck_angle"),
            **offsets(),
        }
        out["head"] = {
            "length": pv("head_length"),
            "width": pv("head_width"),
            "height": pv("head_height"),
            "tilt": pv("head_tilt"),
            **offsets(),
        }
        if genes.get("has_tail"):
            out["tail"] = {"length": pv("tail_length"), **offsets()}
        if genes.get("has_ears"):
            for side in ("l", "r"):
                out[f"ear.{side}"] = {"length": pv("ear_length"), **offsets()}
        return out

    # ------------------------------------------------------------------ stage 2
    def build(
        self, genes: dict[str, GeneValue], params: ElementParams, ctx: BuildContext
    ) -> RobotSpec:
        lib = ctx.library
        d = ctx.defaults
        gp = self.params
        limits: dict[str, list[float]] = d.get("joint_limits_deg", {})
        s = float(genes.get("scale", 1.0))  # type: ignore[arg-type]
        default_struct = lib.material(d.get("structure", {}).get("material", "petg"))
        struct_cache: dict[str, Any] = {}

        def struct_of(body_id: str) -> Any:
            """Structure material of one body: its material override, else the default."""
            if body_id not in struct_cache:
                key = ctx.materials.get(body_id)
                mat = default_struct
                if key:
                    try:
                        mat = lib.material(key)
                    except (KeyError, TypeError):
                        mat = default_struct  # build_design reports the unknown key
                struct_cache[body_id] = mat
            return struct_cache[body_id]

        wall = float(genes["wall_thickness"])  # type: ignore[arg-type]
        jd = float(d.get("structure", {}).get("joint_damping_nms_per_rad", 0.05))
        jf = float(d.get("structure", {}).get("joint_friction_nm", 0.02))
        skin_mat = lib.material(str(genes["skin_material"]))
        skin_t = float(genes["skin_thickness"])  # type: ignore[arg-type]
        face_mat = lib.material(d.get("skin", {}).get("face_material", "cast_silicone"))
        face_t = float(d.get("skin", {}).get("face_thickness_mm", 3.0))
        hoof_mat = lib.material(d.get("skin", {}).get("hoof_material", "cast_silicone"))
        clear = gp.skin_clearance  # type: ignore[attr-defined]

        def val(el: str, name: str) -> float:
            return params[el][name].value

        def off(el: str) -> Vec3:
            t = params[el]
            return (t["offset_x"].value, t["offset_y"].value, t["offset_z"].value)

        def add(a: Vec3, b: Vec3) -> Vec3:
            return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

        def shell(g: Geom, body_id: str) -> Geom:
            """Printed shell: mass = surface area x wall thickness x density."""
            mat = struct_of(body_id)
            g.mass_g = g.area_mm2() * wall * mat.density_g_cm3 / 1000.0
            g.material = mat.key
            return g

        def motor(act_id: str, comp_key: str, pos: Vec3) -> Geom:
            c = lib.actuator(comp_key)
            return Geom(
                id=f"{act_id}.motor",
                shape="box",
                size=c.dims_mm,
                pos=pos,
                layer="Actuators",
                role="visual",
                mass_g=c.mass_g,
                mass_source="component",
                component=comp_key,
                label=c.name,
            )

        def part(key: str, comp_key: str, pos: Vec3, layer: str) -> Geom:
            c = lib.get(comp_key)
            dims = c.dims_mm if max(c.dims_mm) > 0 else (10.0, 10.0, 3.0)
            return Geom(
                id=key,
                shape="box",
                size=dims,
                pos=pos,
                layer=layer,
                role="visual",
                mass_g=c.mass_g,
                mass_source="component",
                component=comp_key,
                label=c.name,
            )

        def skin_mass(mat: Any, area_mm2: float, thickness: float) -> float:
            area_cm2 = area_mm2 / 100.0
            return area_cm2 * (mat.areal_density_g_cm2 + mat.density_g_cm3 * thickness / 10.0)

        bodies: list[Body] = []
        joints: list[Joint] = []
        actuators: list[Actuator] = []
        transmissions: list[Transmission] = []
        sensors: list[Sensor] = []
        skins: list[SkinRegion] = []

        def lim(name: str, default: tuple[float, float]) -> tuple[float, float]:
            v = limits.get(name)
            return (float(v[0]), float(v[1])) if v else default

        act_small = str(genes["act_small"])

        # ------------------------------------------------------------ trunk
        L, W, H = val("trunk", "length"), val("trunk", "width"), val("trunk", "height")
        bend = float(genes["knee_bend"])  # type: ignore[arg-type]
        hip_drop = float(genes["hip_drop"]) * s  # type: ignore[arg-type]
        stance = float(genes["stance_width"]) * s  # type: ignore[arg-type]
        inset = float(genes["hip_inset"]) * s  # type: ignore[arg-type]
        # Trunk height is set by the longest leg so all hooves reach the ground.
        leg_h = max(
            standing_leg_height(val(f"leg.{k}.thigh", "length"), val(f"leg.{k}.shank", "length"), bend)
            + val(f"leg.{k}.shank", "hoof_radius")
            - params[f"leg.{k}.hip"]["offset_z"].value
            for k in LEGS
        )
        trunk_z = leg_h + hip_drop

        trunk = Body(id="trunk", name="Trunk", pos=(0.0, 0.0, trunk_z))
        trunk.geoms.append(
            shell(Geom(id="trunk.shell", shape="box", size=(L, W * 0.8, H * 0.8), label="Trunk shell"), "trunk")
        )
        bat_key = str(genes.get("battery") or d.get("electronics", {}).get("battery", "lipo_3s_5000"))
        trunk.geoms.append(part("elec.battery", bat_key, (0.0, 0.0, -H * 0.18), "Electronics"))
        boards = d.get("electronics", {}).get("boards", [])
        for i, bkey in enumerate(boards):
            x = L * 0.22 * (1 if i % 2 == 0 else -1)
            trunk.geoms.append(part(f"elec.{bkey}", bkey, (x, 0.0, H * 0.12), "Electronics"))
        imu_key = d.get("sensors", {}).get("imu", "bno085")
        trunk.geoms.append(part("sensor.imu.board", imu_key, (0.0, 0.0, H * 0.02), "Sensors"))
        sensors.append(Sensor(id="sensor.imu", type="imu", component=imu_key, body="trunk"))
        bodies.append(trunk)

        trunk_skin_area = 0.0
        if gp.show_skin:  # type: ignore[attr-defined]
            sk = Geom(
                id="trunk.skin",
                shape="ellipsoid",
                size=(L * 0.56, W * 0.5 + clear, H * 0.5 + clear),
                layer="Skin",
                role="visual",
                color=skin_mat.color,
                material=skin_mat.key,
                label="Trunk skin",
            )
            trunk_skin_area = sk.area_mm2()
            sk.mass_g = skin_mass(skin_mat, trunk_skin_area, skin_t)
            trunk.geoms.append(sk)
        skins.append(
            SkinRegion(
                id="skin.trunk",
                bodies=["trunk"],
                material=skin_mat.key,
                thickness_mm=skin_t,
                area_mm2=trunk_skin_area,
            )
        )
        touch_key = d.get("sensors", {}).get("touch", "cap_touch_zone")
        for zone in d.get("sensors", {}).get("touch_zones", []):
            if zone.startswith("flank"):
                sy = 1 if zone.endswith("left") else -1
                sensors.append(
                    Sensor(
                        id=f"sensor.touch.{zone}",
                        type="touch",
                        component=touch_key,
                        body="trunk",
                        pos=(0.0, sy * W * 0.5, 0.0),
                    )
                )

        # ------------------------------------------------------------ legs
        for k, (sx, sy) in LEGS.items():
            hind = sx < 0
            forward = bool(genes.get("hind_knee_forward" if hind else "front_knee_forward"))
            hip_flexes = hind or bool(genes.get("front_hip_flex", True))
            hip_id, thigh_id, shank_id = f"leg.{k}.hip", f"leg.{k}.thigh", f"leg.{k}.shank"
            tl, tr = val(thigh_id, "length"), val(thigh_id, "radius")
            sl, sr = val(shank_id, "length"), val(shank_id, "radius")
            hr_ = val(shank_id, "hoof_radius")
            leg_off = val(hip_id, "offset")
            rest_hip, rest_knee = standing_leg_angles(tl, sl, bend, forward)

            hx = sx * (L / 2.0 - inset)
            hy = sy * stance / 2.0
            a_abd, a_flex, a_knee = f"act.{k}.hip_abd", f"act.{k}.hip_flex", f"act.{k}.knee"

            # hip abduction motor lives in the trunk
            trunk.geoms.append(
                motor(a_abd, str(genes["act_hip_abd"]), (hx - sx * 30.0 * s, hy * 0.6, -hip_drop))
            )

            hip = Body(
                id=hip_id,
                name=f"Hip ({LEG_NAMES[k]})",
                parent="trunk",
                pos=add((hx, hy, -hip_drop), off(hip_id)),
            )
            hip.geoms.append(
                shell(Geom(id=f"{hip_id}.block", shape="sphere", size=(tr * 1.3, 0, 0), label="Hip block"), hip_id)
            )
            if hip_flexes:
                hip.geoms.append(motor(a_flex, str(genes["act_hip_flex"]), (0.0, sy * leg_off * 0.4, 0.0)))
            bodies.append(hip)
            joints.append(
                Joint(
                    id=f"joint.{k}.hip_abd",
                    name=f"Hip abduction ({LEG_NAMES[k]})",
                    body=hip_id,
                    axis=(1.0, 0.0, 0.0),
                    range_deg=lim("hip_abd", (-30, 30)),
                    damping=jd,
                    friction=jf,
                )
            )

            thigh = Body(
                id=thigh_id,
                name=f"Thigh ({LEG_NAMES[k]})",
                parent=hip_id,
                pos=add((0.0, sy * leg_off, 0.0), off(thigh_id)),
                # without a hip-flexion motor the thigh is a fixed strut at its standing angle
                quat=IDENTITY if hip_flexes else quat_axis_angle((0.0, 1.0, 0.0), rest_hip),
            )
            thigh.geoms.append(
                shell(
                    Geom(
                        id=f"{thigh_id}.tube",
                        shape="capsule",
                        size=(tr, tl, 0),
                        pos=(0.0, 0.0, -tl / 2.0),
                        label="Thigh",
                    ),
                    thigh_id,
                )
            )
            belt = str(genes["knee_drive"]) == "belt"
            knee_motor_z = -tl * 0.18 if belt else -tl + 12.0 * s
            thigh.geoms.append(motor(a_knee, str(genes["act_knee"]), (0.0, sy * tr * 0.6, knee_motor_z)))
            if belt:
                thigh.geoms.append(
                    Geom(
                        id=f"trans.{k}.knee.belt",
                        shape="box",
                        size=(10.0 * s, 6.0 * s, tl * 0.82),
                        pos=(0.0, -sy * tr * 0.9, -tl * 0.59),
                        layer="Transmission",
                        role="visual",
                        mass_g=12.0 * s,
                        label="Knee belt",
                    )
                )
            bodies.append(thigh)
            if hip_flexes:
                joints.append(
                    Joint(
                        id=f"joint.{k}.hip_flex",
                        name=f"Hip flexion ({LEG_NAMES[k]})",
                        body=thigh_id,
                        axis=(0.0, 1.0, 0.0),
                        range_deg=lim("hip_flex", (-75, 75)),
                        rest_deg=rest_hip,
                        damping=jd,
                        friction=jf,
                    )
                )

            shank = Body(
                id=shank_id,
                name=f"Shank ({LEG_NAMES[k]})",
                parent=thigh_id,
                pos=add((0.0, 0.0, -tl), off(shank_id)),
            )
            shank.geoms.append(
                shell(
                    Geom(
                        id=f"{shank_id}.tube",
                        shape="capsule",
                        size=(sr, sl, 0),
                        pos=(0.0, 0.0, -sl / 2.0),
                        label="Shank",
                    ),
                    shank_id,
                )
            )
            hoof = Geom(
                id=f"leg.{k}.hoof",
                shape="sphere",
                size=(hr_, 0, 0),
                pos=(0.0, 0.0, -sl),
                color="#3b3531",
                foot=True,
                material=hoof_mat.key,
                label="Hoof",
            )
            hoof.mass_g = hoof.volume_mm3() / 1000.0 * hoof_mat.density_g_cm3
            shank.geoms.append(hoof)
            bodies.append(shank)
            klim = lim("knee", (-150, -3))
            if forward:
                klim = (-klim[1], -klim[0])
            joints.append(
                Joint(
                    id=f"joint.{k}.knee",
                    name=f"Knee ({LEG_NAMES[k]})",
                    body=shank_id,
                    axis=(0.0, 1.0, 0.0),
                    range_deg=klim,
                    rest_deg=rest_knee,
                    damping=jd,
                    friction=jf,
                )
            )

            # skin sleeve
            area = 0.0
            for b, length, radius in ((thigh, tl, tr), (shank, sl, sr)):
                sg = Geom(
                    id=f"{b.id}.skin",
                    shape="capsule",
                    size=(radius + clear, length, 0),
                    pos=(0.0, 0.0, -length / 2.0),
                    layer="Skin",
                    role="visual",
                    color=skin_mat.color,
                    material=skin_mat.key,
                    label="Leg skin",
                )
                a = sg.area_mm2()
                area += a
                sg.mass_g = skin_mass(skin_mat, a, skin_t)
                if gp.show_skin:  # type: ignore[attr-defined]
                    b.geoms.append(sg)
            skins.append(
                SkinRegion(
                    id=f"skin.leg.{k}",
                    bodies=[thigh_id, shank_id],
                    joints=([f"joint.{k}.hip_flex"] if hip_flexes else []) + [f"joint.{k}.knee"],
                    material=skin_mat.key,
                    thickness_mm=skin_t,
                    area_mm2=area,
                )
            )

            tr_id = None
            if belt:
                tr_id = f"trans.{k}.knee"
                transmissions.append(
                    Transmission(id=tr_id, type="belt", ratio=1.0, efficiency=0.95, motor_body=thigh_id)
                )
            actuators.append(Actuator(id=a_abd, joint=f"joint.{k}.hip_abd", component=str(genes["act_hip_abd"])))
            if hip_flexes:
                actuators.append(
                    Actuator(id=a_flex, joint=f"joint.{k}.hip_flex", component=str(genes["act_hip_flex"]))
                )
            actuators += [
                Actuator(
                    id=a_knee,
                    joint=f"joint.{k}.knee",
                    component=str(genes["act_knee"]),
                    transmission=tr_id,
                ),
            ]
            sensors.append(
                Sensor(
                    id=f"sensor.fsr.{k}",
                    type="fsr",
                    component=d.get("sensors", {}).get("foot", "fsr_foot"),
                    body=shank_id,
                    pos=(0.0, 0.0, -sl - hr_),
                )
            )

        # ------------------------------------------------------------ neck and head
        nl, nr, na = val("neck", "length"), val("neck", "radius"), val("neck", "angle")
        nd = (math.cos(math.radians(na)), 0.0, math.sin(math.radians(na)))
        neck_root: Vec3 = (L / 2.0 - nr * 0.5, 0.0, H * 0.4 - nr * 0.5)
        trunk.geoms.append(motor("act.neck_yaw", act_small, (neck_root[0] - 30.0 * s, 0.0, neck_root[2] - 10.0 * s)))

        base = Body(id="neck.base", name="Neck base", parent="trunk", pos=add(neck_root, off("neck")), part=False)
        base.geoms.append(
            shell(Geom(id="neck.base.block", shape="sphere", size=(nr * 0.7, 0, 0), label="Neck base"), "neck.base")
        )
        base.geoms.append(motor("act.neck_pitch", act_small, (0.0, 0.0, 0.0)))
        bodies.append(base)
        joints.append(
            Joint(
                id="joint.neck_yaw",
                name="Neck yaw",
                body="neck.base",
                axis=(0.0, 0.0, 1.0),
                range_deg=lim("neck_yaw", (-50, 50)),
                group="neck",
                damping=jd,
                friction=jf,
            )
        )

        neck = Body(id="neck", name="Neck", parent="neck.base")
        nq = quat_from_z_to(nd)
        neck.geoms.append(
            shell(
                Geom(
                    id="neck.tube",
                    shape="capsule",
                    size=(nr * 0.6, nl, 0),
                    pos=(nd[0] * nl / 2, 0.0, nd[2] * nl / 2),
                    quat=nq,
                    label="Neck",
                ),
                "neck",
            )
        )
        neck_end: Vec3 = (nd[0] * nl, 0.0, nd[2] * nl)
        neck.geoms.append(motor("act.head_pitch", act_small, (neck_end[0] * 0.9, 0.0, neck_end[2] * 0.9)))
        nsk = Geom(
            id="neck.skin",
            shape="capsule",
            size=(nr + clear, nl, 0),
            pos=(nd[0] * nl / 2, 0.0, nd[2] * nl / 2),
            quat=nq,
            layer="Skin",
            role="visual",
            color=skin_mat.color,
            material=skin_mat.key,
            label="Neck skin",
        )
        nsk.mass_g = skin_mass(skin_mat, nsk.area_mm2(), skin_t)
        if gp.show_skin:  # type: ignore[attr-defined]
            neck.geoms.append(nsk)
        bodies.append(neck)
        joints.append(
            Joint(
                id="joint.neck_pitch",
                name="Neck pitch",
                body="neck",
                axis=(0.0, 1.0, 0.0),
                range_deg=lim("neck_pitch", (-40, 40)),
                group="neck",
                damping=jd,
                friction=jf,
            )
        )
        skins.append(
            SkinRegion(
                id="skin.neck",
                bodies=["neck"],
                joints=["joint.neck_yaw", "joint.neck_pitch", "joint.head_pitch"],
                material=skin_mat.key,
                thickness_mm=skin_t,
                area_mm2=nsk.area_mm2(),
            )
        )

        hl_, hw, hh, tilt = (
            val("head", "length"),
            val("head", "width"),
            val("head", "height"),
            val("head", "tilt"),
        )
        hq = quat_axis_angle((0.0, 1.0, 0.0), tilt)  # +Y rotation tips local +X nose-down

        def hp(x: float, y: float, z: float) -> Vec3:
            """Head-box coordinates (origin at the box centre) -> head body frame."""
            c = quat_rotate(hq, (hl_ / 2.0 - hh * 0.3, 0.0, 0.0))
            r = quat_rotate(hq, (x, y, z))
            return (c[0] + r[0], c[1] + r[1], c[2] + r[2])

        head = Body(id="head", name="Head", parent="neck", pos=add(neck_end, off("head")))
        head.geoms.append(
            shell(
                Geom(
                    id="head.shell",
                    shape="box",
                    size=(hl_, hw * 0.8, hh * 0.8),
                    pos=hp(0, 0, 0),
                    quat=hq,
                    label="Head shell",
                ),
                "head",
            )
        )
        hsk = Geom(
            id="head.skin",
            shape="ellipsoid",
            size=(hl_ * 0.56, hw * 0.5 + clear, hh * 0.5 + clear),
            pos=hp(0, 0, 0),
            quat=hq,
            layer="Skin",
            role="visual",
            color=face_mat.color,
            material=face_mat.key,
            label="Face skin",
        )
        hsk.mass_g = skin_mass(face_mat, hsk.area_mm2(), face_t)
        if gp.show_skin:  # type: ignore[attr-defined]
            head.geoms.append(hsk)
        bodies.append(head)
        joints.append(
            Joint(
                id="joint.head_pitch",
                name="Head pitch",
                body="head",
                axis=(0.0, 1.0, 0.0),
                range_deg=lim("head_pitch", (-35, 35)),
                group="neck",
                damping=jd,
                friction=jf,
            )
        )
        skins.append(
            SkinRegion(
                id="skin.head",
                bodies=["head"],
                material=face_mat.key,
                thickness_mm=face_t,
                area_mm2=hsk.area_mm2(),
            )
        )
        actuators += [
            Actuator(id="act.neck_yaw", joint="joint.neck_yaw", component=act_small),
            Actuator(id="act.neck_pitch", joint="joint.neck_pitch", component=act_small),
            Actuator(id="act.head_pitch", joint="joint.head_pitch", component=act_small),
        ]
        sd = d.get("sensors", {})
        for zone in sd.get("touch_zones", []):
            if zone == "head":
                sensors.append(
                    Sensor(id="sensor.touch.head", type="touch", component=touch_key, body="head", pos=hp(-hl_ * 0.2, 0, hh * 0.5))
                )
            elif zone == "muzzle":
                sensors.append(
                    Sensor(id="sensor.touch.muzzle", type="touch", component=touch_key, body="head", pos=hp(hl_ * 0.5, 0, 0))
                )
        mic_key = sd.get("microphone", "i2s_microphone")
        head.geoms.append(part("sensor.microphone.board", mic_key, hp(-hl_ * 0.1, 0, hh * 0.2), "Sensors"))
        sensors.append(Sensor(id="sensor.microphone", type="microphone", component=mic_key, body="head"))
        if genes.get("has_depth_camera"):
            cam_key = sd.get("depth_camera", "depth_camera")
            cam = part("sensor.depth_camera.board", cam_key, hp(hl_ * 0.25, 0, hh * 0.3), "Sensors")
            cam.quat = hq
            cam.size = (cam.size[2], cam.size[0], cam.size[1])  # lens faces +X
            head.geoms.append(cam)
            sensors.append(Sensor(id="sensor.depth_camera", type="depth_camera", component=cam_key, body="head"))
        sensors.append(
            Sensor(
                id="sensor.motor_feedback",
                type="motor_feedback",
                component=sd.get("motor_feedback", "motor_feedback"),
                body="trunk",
            )
        )

        # ------------------------------------------------------------ ears
        if genes.get("has_ears"):
            for side, sy in (("l", 1), ("r", -1)):
                eid = f"ear.{side}"
                el = val(eid, "length")
                ed = (0.0, sy * 0.8, 0.6)
                ear = Body(
                    id=eid,
                    name=f"Ear ({'left' if sy > 0 else 'right'})",
                    parent="head",
                    pos=add(hp(-hl_ * 0.3, sy * hw * 0.4, hh * 0.35), off(eid)),
                )
                ear.geoms.append(
                    Geom(
                        id=f"{eid}.blade",
                        shape="capsule",
                        size=(7.0 * s, el, 0),
                        pos=(0.0, ed[1] * el / 2, ed[2] * el / 2),
                        quat=quat_from_z_to(ed),
                        color=face_mat.color,
                        material=face_mat.key,
                        mass_g=math.pi * (7.0 * s) ** 2 * el / 1000.0 * face_mat.density_g_cm3 * 0.5,
                        role="visual",
                        layer="Skin",
                        label="Ear",
                    )
                )
                head.geoms.append(motor(f"act.ear.{side}", act_small, hp(-hl_ * 0.3, sy * hw * 0.15, hh * 0.1)))
                bodies.append(ear)
                joints.append(
                    Joint(
                        id=f"joint.ear.{side}",
                        name=f"Ear ({side})",
                        body=eid,
                        axis=(1.0, 0.0, 0.0),
                        range_deg=lim("ear", (-40, 40)),
                        group="ear",
                        cosmetic=True,
                        damping=jd,
                    )
                )
                actuators.append(Actuator(id=f"act.ear.{side}", joint=f"joint.ear.{side}", component=act_small))

        # ------------------------------------------------------------ tail
        if genes.get("has_tail"):
            tl_ = val("tail", "length")
            td = (-0.35, 0.0, -0.94)
            tail = Body(
                id="tail",
                name="Tail",
                parent="trunk",
                pos=add((-L / 2.0, 0.0, H * 0.3), off("tail")),
            )
            tail.geoms.append(
                Geom(
                    id="tail.cord",
                    shape="capsule",
                    size=(7.0 * s, tl_, 0),
                    pos=(td[0] * tl_ / 2, 0.0, td[2] * tl_ / 2),
                    quat=quat_from_z_to(td),
                    color=skin_mat.color,
                    material=skin_mat.key,
                    mass_g=math.pi * (7.0 * s) ** 2 * tl_ / 1000.0 * skin_mat.density_g_cm3 * 0.6,
                    role="visual",
                    layer="Skin",
                    label="Tail",
                )
            )
            trunk.geoms.append(motor("act.tail", act_small, (-L / 2.0 + 30.0 * s, 0.0, H * 0.25)))
            bodies.append(tail)
            joints.append(
                Joint(
                    id="joint.tail",
                    name="Tail",
                    body="tail",
                    axis=(0.0, 0.0, 1.0),
                    range_deg=lim("tail", (-45, 45)),
                    group="tail",
                    cosmetic=True,
                    damping=jd,
                )
            )
            actuators.append(Actuator(id="act.tail", joint="joint.tail", component=act_small))

        spec = RobotSpec(
            name="calf",
            bodies=bodies,
            joints=joints,
            actuators=actuators,
            transmissions=transmissions,
            sensors=sensors,
            skin_regions=skins,
            metadata={"generator": self.key, "generator_version": self.version, "scale": s},
        )
        spec.harness_routes = _harness(spec, d)
        return spec


# ---------------------------------------------------------------------- harness
def _geom_world(spec: RobotSpec, geom_id: str, poses: dict[str, Any]) -> Vec3:
    for b in spec.bodies:
        for g in b.geoms:
            if g.id == geom_id:
                bp, bq = poses[b.id]
                r = quat_rotate(bq, g.pos)
                return (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2])
    raise KeyError(geom_id)


def _dist(a: Vec3, b: Vec3) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _harness(spec: RobotSpec, defaults: dict[str, Any]) -> list[HarnessRoute]:
    """Minimal harness: power, one servo bus per leg, neck bus, IMU, Pi link.

    Cable length = straight segments through the origins of the bodies the
    cable passes (standing pose) times a slack factor.
    """
    h = defaults.get("harness", {})
    slack = float(h.get("slack_factor", 1.25))
    bus_awg = int(h.get("bus_gauge_awg", 20))
    sig_awg = int(h.get("signal_gauge_awg", 26))
    poses = spec.world_poses()
    geom_ids = {g.id for b in spec.bodies for g in b.geoms}
    boards = [g for g in geom_ids if g.startswith("elec.") and g != "elec.battery"]
    mcu = "elec.teensy_41" if "elec.teensy_41" in geom_ids else (sorted(boards)[0] if boards else None)
    routes: list[HarnessRoute] = []
    if mcu is None:
        return routes

    def route(rid: str, src: str, dst: str, via: list[str], wires: list[Wire], connector: str) -> None:
        pts = [_geom_world(spec, src, poses)] + [poses[b][0] for b in via] + [_geom_world(spec, dst, poses)]
        length = sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * slack
        routes.append(
            HarnessRoute(id=rid, src=src, dst=dst, via_bodies=via, wires=wires, length_mm=round(length, 1), connector=connector)
        )

    bus = [
        Wire(signal="VBUS", gauge_awg=bus_awg, color="RD"),
        Wire(signal="GND", gauge_awg=bus_awg, color="BK"),
        Wire(signal="DATA", gauge_awg=sig_awg, color="YE"),
    ]
    if "elec.battery" in geom_ids:
        route(
            "harness.power",
            "elec.battery",
            mcu,
            [],
            [Wire(signal="VBAT", gauge_awg=bus_awg - 4, color="RD"), Wire(signal="GND", gauge_awg=bus_awg - 4, color="BK")],
            "XT60",
        )
    for k in LEGS:
        dst = f"act.{k}.knee.motor"
        if dst in geom_ids:
            route(f"harness.bus.{k}", mcu, dst, [f"leg.{k}.hip", f"leg.{k}.thigh"], list(bus), "JST-EH-3")
    if "act.head_pitch.motor" in geom_ids:
        route("harness.bus.neck", mcu, "act.head_pitch.motor", ["neck.base"], list(bus), "JST-EH-3")
    if "sensor.imu.board" in geom_ids:
        route(
            "harness.imu",
            "sensor.imu.board",
            mcu,
            [],
            [
                Wire(signal="3V3", gauge_awg=sig_awg, color="RD"),
                Wire(signal="GND", gauge_awg=sig_awg, color="BK"),
                Wire(signal="SDA", gauge_awg=sig_awg, color="BU"),
                Wire(signal="SCL", gauge_awg=sig_awg, color="GN"),
            ],
            "JST-SH-4",
        )
    if "elec.raspberry_pi_5" in geom_ids and mcu != "elec.raspberry_pi_5":
        route(
            "harness.link",
            "elec.raspberry_pi_5",
            mcu,
            [],
            [Wire(signal="USB_D+", gauge_awg=28, color="GN"), Wire(signal="USB_D-", gauge_awg=28, color="WH"), Wire(signal="GND", gauge_awg=28, color="BK")],
            "USB",
        )
    return routes
