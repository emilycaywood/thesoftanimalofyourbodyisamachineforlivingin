"""Final feral calf part generator (ADR-066, ADR-067).

Genome (``config/genes/feral_calf.yaml``) + belt choices (this generator's
params) + ``config/feral_calf.yaml`` -> RobotSpec.

Body: one root ``trunk`` holding the hip block, the chest block, two rails
between them, the hip ab/ad and shoulder servos, the two battery packs and a
lumped head + neck mass. Hip axle and shoulder axle are level, ``axle_spacing``
apart; the trunk origin is midway between them at axle height.

Rear leg ``k`` in (hl, hr)::

    trunk --joint.k.hip_abd (fore-aft)--> leg.k.femur (fixed 40 deg forward, no hip pitch)
          --joint.k.stifle--> leg.k.tibia --joint.k.hock--> leg.k.cannon (hoof pad)

Front leg ``k`` in (fl, fr)::

    trunk --joint.k.shoulder--> leg.k.upper --joint.k.carpus--> leg.k.cannon (hoof pad)

Every segment body has its origin at its upper joint and runs down its own
-Z; its +X is perpendicular to the segment, toward the front. Joint angles
are 0 in the standing pose. Positive = flexion at stifle, hock and carpus; at
the shoulder positive swings the leg back; at the hip positive = abduction.

Belt drives (ADR-063, ADR-070): stifle and hock are always belted 2:1, the
carpus when gene ``carpus_belt`` is on. Each drive is three genes holding
catalog ids (``belt_<drive>_system``, ``_pulleys``, ``_length``); evolution
never varies them. Each driver servo rides on the segment above its
joint at the derived centre distance C from the joint axis; each driven pulley
is fixed to the segment below. No belt crosses a joint it does not drive: the
stifle servo is on the femur (which turns with the hip ab/ad joint), the hock
servo on the tibia, the carpus servo on the upper leg.

Springs (ADR-065): tension only, between the segment above and below a joint.

Masses (ADR-068): servos from the component library, tubes and rods from OD,
ID, length and density, batteries and the head + neck lump as supplied; every
other part is a required value in ``config/feral_calf.yaml`` that counts as
0 g until entered and is listed in ``spec.metadata["missing_masses"]``.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from calflab import units as u
from calflab.config import config_yaml
from calflab.mech.belts import (
    BeltCatalog,
    BeltChoice,
    CatalogError,
    Check,
    DriveLayout,
    DriveReport,
    DriveTarget,
    choose_default,
    clearance_sweep,
    evaluate_drive,
    load_catalog,
    rejection,
)
from calflab.model.genome import GeneValue
from calflab.model.overrides import ElementParams, ParamValue
from calflab.model.spec import Actuator, Body, Geom, Joint, RobotSpec, Spring, Transmission
from calflab.model.xform import Quat, Vec3, quat_axis_angle, quat_from_z_to, quat_mul, quat_rotate
from calflab.plugins import BuildContext, PartGenerator, register
from calflab.schema import P

REAR = ("hl", "hr")
FRONT = ("fl", "fr")
SIDE = {"fl": 1, "fr": -1, "hl": 1, "hr": -1}
LEG_NAMES = {"fl": "front left", "fr": "front right", "hl": "hind left", "hr": "hind right"}
DRIVES = ("stifle", "hock", "carpus")
SPRINGS = {"stifle": ("femur", "tibia"), "hock": ("tibia", "cannon"), "shoulder": (None, "upper")}
#: rail cross-sections (mm): (outer diameter, inner diameter, density gene or None if not entered)
RAILS = {"cf_rod_8mm": (8.0, 0.0, "tube_density"), "al_tube_half_inch": (12.7, 12.7 - 2 * 1.2446, None)}
RAIL_LABELS = {"cf_rod_8mm": "8 mm solid carbon fibre rod", "al_tube_half_inch": "1/2 in aluminium tube, 0.049 in wall"}


def ry(deg: float) -> Quat:
    return quat_axis_angle((0.0, 1.0, 0.0), deg)


def conj(q: Quat) -> Quat:
    return (q[0], -q[1], -q[2], -q[3])


def belt_choice(genes: dict[str, GeneValue], drive: str) -> BeltChoice:
    """The three catalog ids a drive's genes hold."""
    return BeltChoice(system=str(genes[f"belt_{drive}_system"]), pulleys=str(genes[f"belt_{drive}_pulleys"]),
                      length=str(genes[f"belt_{drive}_length"]))


def belt_genes(choice: BeltChoice, drive: str) -> dict[str, str]:
    return {f"belt_{drive}_system": choice.system, f"belt_{drive}_pulleys": choice.pulleys,
            f"belt_{drive}_length": choice.length}


def feral_config() -> dict[str, Any]:
    return config_yaml("feral_calf.yaml")


def _num(genes: dict[str, GeneValue], key: str) -> float:
    return float(genes[key])  # type: ignore[arg-type]


@register
class FeralCalfGenerator(PartGenerator):
    """The final feral calf: ten servos, belted stifles and hocks, tension springs."""

    key = "feral_calf"
    label = "Final feral calf"
    description = (
        "Hip and chest blocks on two rails; rear legs hip ab/ad, stifle, hock (stifle and hock belted 2:1); "
        "front legs shoulder, carpus; tension springs; head + neck as one mass."
    )
    version = "1"
    genome_definition = "feral_calf"

    class Params(BaseModel):
        belt_efficiency: float = P(
            1.0, ge=0.5, le=1.0, step=0.01, provisional=True,
            desc="Belt drive efficiency: joint torque = servo torque x ratio x efficiency (PROVISIONAL).",
        )
        tension_travel_mm: float = P(
            3.0, unit="mm", ge=0.0, le=10.0, step=0.5, provisional=True,
            desc="Travel of the belt tensioning slot, plus or minus (PROVISIONAL). A build tolerance only: reported, "
                 "never used to reach a centre distance.",
        )
        sustained_fraction: float = P(
            0.25, ge=0.01, le=1.0, step=0.01, provisional=True,
            desc="Belt tension or servo torque above its limit counts as sustained when it lasts more than this "
                 "fraction of a gait cycle (PROVISIONAL).",
        )
        breaking_fraction: float = P(
            0.25, ge=0.05, le=1.0, step=0.01, provisional=True,
            desc="Flag any belt tension peak above this fraction of the belt's breaking strength (PROVISIONAL: the "
                 "researcher's own safety factor, not a supplier value).",
        )
        rated_fraction: float = P(
            0.6, ge=0.1, le=1.0, step=0.05,
            desc="Flag a servo spending sustained time above this fraction of its rated torque.",
        )
        auto_belts: bool = P(
            False, advanced=True,
            desc="Choose every belt by the default rule (closest to its target C, passing every check) instead of "
                 "the belt genes. Used to make a new project's defaults and by the belt comparison.",
        )
        default_system: str = P(
            "", advanced=True, desc="With auto belts: the belt system to choose from (empty = the catalog's default).",
        )
        default_pulleys: str = P(
            "", advanced=True, desc="With auto belts: the pulley pair to choose from (empty = the catalog's default).",
        )
        belt_catalog: dict[str, Any] | None = P(
            None, ui="json", advanced=True,
            desc="The project's belt catalog, inlined by the lab into jobs that build bodies away from the project "
                 "folder (evolution, studies), so they use the same catalog. Never stored in the document.",
        )

    # ------------------------------------------------------------------ stage 1
    def element_params(self, genes: dict[str, GeneValue]) -> ElementParams:
        from calflab.config import gene_definition_files

        gdef = gene_definition_files()["feral_calf"]

        def pv(gene: str, label: str | None = None, handle: Vec3 | None = None, frac: float = 1.0) -> ParamValue:
            g = gdef.gene(gene)
            return ParamValue(value=_num(genes, gene), unit=g.unit, gene=gene, min=g.min, max=g.max, label=label,
                              handle_axis=handle, handle_frac=frac)

        down = (0.0, 0.0, -1.0)
        out: ElementParams = {
            "trunk": {
                "axle_spacing": pv("axle_spacing", "Hip axle to shoulder axle", handle=(1.0, 0.0, 0.0), frac=0.5),
                "rail_spacing": pv("rail_spacing", "Rail spacing"),
            }
        }
        for k in REAR:
            out[f"leg.{k}.femur"] = {"length": pv("femur_length", "Femur length", handle=down)}
            out[f"leg.{k}.tibia"] = {"length": pv("tibia_length", "Tibia length", handle=down)}
            out[f"leg.{k}.cannon"] = {"length": pv("rear_cannon_length", "Cannon length", handle=down)}
        for k in FRONT:
            out[f"leg.{k}.upper"] = {"length": pv("upper_leg_length", "Upper leg length", handle=down)}
            out[f"leg.{k}.cannon"] = {"length": pv("front_cannon_length", "Cannon length", handle=down)}
        return out

    # ------------------------------------------------------------------ stage 2
    def build(self, genes: dict[str, GeneValue], params: ElementParams, ctx: BuildContext) -> RobotSpec:
        cfg = feral_config()
        lib = ctx.library
        gp = self.params
        lay: dict[str, Any] = cfg.get("layout", {})
        ph: dict[str, Any] = cfg.get("placeholders", {})
        sc: dict[str, Any] = cfg.get("servo", {})
        ranges: dict[str, list[float]] = cfg.get("joint_ranges_deg", {})
        warnings: list[str] = []
        missing: dict[str, dict[str, Any]] = {}
        servo_key = str(genes["actuator"])
        servo = lib.actuator(servo_key)
        s_len = float(sc.get("length_along_segment_mm", servo.dims_mm[0]))
        s_wid = float(sc.get("width_across_segment_mm", servo.dims_mm[1]))
        s_dep = float(sc.get("depth_sideways_mm", servo.dims_mm[2]))
        offset = sc.get("output_axis_offset_mm")
        jd = float(ctx.defaults.get("structure", {}).get("joint_damping_nms_per_rad", 0.05))
        jf = float(ctx.defaults.get("structure", {}).get("joint_friction_nm", 0.02))
        density = u.g_cm3_to_g_mm3(_num(genes, "tube_density"))

        def val(el: str, name: str) -> float:
            return params[el][name].value

        # ------------------------------------------------------------ placeholders (ADR-068)
        def placeholder(key: str, label: str, where: str) -> float | None:
            """The entered mass of one placeholder part, or None (then it is listed as missing)."""
            v = ph.get(key)
            if v is None:
                row = missing.setdefault(key, {"item": key, "label": label, "qty": 0, "where": [],
                                               "enter_in": f"config/feral_calf.yaml placeholders.{key}"})
                row["qty"] += 1
                if where not in row["where"]:
                    row["where"].append(where)
                return None
            return float(v)

        def ph_geom(gid: str, key: str, label: str, pos: Vec3, where: str, layer: str = "Structure") -> list[Geom]:
            m = placeholder(key, label, where)
            if m is None:
                return []
            return [Geom(id=gid, shape="sphere", size=(5.0, 0.0, 0.0), pos=pos, layer=layer, role="visual",
                         mass_g=m, mass_source="specified", label=f"{label} (entered)")]

        def tube(gid: str, label: str, length: float, od_gene: str, id_gene: str) -> Geom:
            od, idd = _num(genes, od_gene), _num(genes, id_gene)
            if idd >= od:
                raise ValueError(f"{label}: inner diameter {idd:g} mm must be smaller than the outer diameter {od:g} mm")
            area = math.pi / 4.0 * (od * od - idd * idd)
            return Geom(id=gid, shape="cylinder", size=(od / 2.0, length, 0.0), pos=(0.0, 0.0, -length / 2.0),
                        layer="Structure", role="both", mass_g=area * length * density, mass_source="tube",
                        material="carbon_fibre_tube", label=f"{label} ({od:g} x {idd:g} mm CF tube)")

        def servo_geom(gid: str, pos: Vec3, size: Vec3, label: str) -> Geom:
            return Geom(id=gid, shape="box", size=size, pos=pos, layer="Actuators", role="visual",
                        mass_g=servo.mass_g, mass_source="component", component=servo_key, label=label)

        # ------------------------------------------------------------ dimensions
        A = val("trunk", "axle_spacing")
        rs = val("trunk", "rail_spacing")
        hx, sx = -A / 2.0, A / 2.0
        overhang = max(0.0, (_num(genes, "body_length") - A) / 2.0)
        block_w = rs + 2.0 * float(lay.get("block_side_margin_mm", 20))
        block_h = float(lay.get("block_height_mm", 80))
        max_od = max(_num(genes, g) for g in ("femur_od", "upper_leg_od"))
        leg_y = block_w / 2.0 + max_od / 2.0 + 2.0
        pad = _num(genes, "hoof_pad")
        pad_r = float(lay.get("hoof_pad_radius_mm", 15))
        fit = float(lay.get("joint_fitting_mm", 25)) + float(lay.get("fitting_clearance_mm", 3))

        Lf = val(f"leg.{REAR[0]}.femur", "length")
        Lt = val(f"leg.{REAR[0]}.tibia", "length")
        Lc = val(f"leg.{REAR[0]}.cannon", "length")
        Lu = val(f"leg.{FRONT[0]}.upper", "length")
        Lfc = val(f"leg.{FRONT[0]}.cannon", "length")
        af, at, ac = _num(genes, "femur_angle"), _num(genes, "tibia_angle"), _num(genes, "rear_cannon_angle")
        rad = u.deg_to_rad
        height = Lf * math.cos(rad(af)) + Lt * math.cos(rad(at)) + Lc * math.cos(rad(ac)) + pad
        # the back is level: the front angle is solved so the front hooves stand where the rear ones do
        need = height - pad
        theta_gene = _num(genes, "front_angle")
        infeasible: list[str] = []
        belt_failures: list[str] = []
        if need > Lu + Lfc:
            theta = 0.0
            infeasible.append(f"The front legs are {need - Lu - Lfc:.1f} mm too short to reach the ground with the back "
                              "level: the front hooves hang above it.")
            warnings.append(infeasible[-1])
        else:
            theta = u.rad_to_deg(math.acos(need / (Lu + Lfc)))
        if abs(theta - theta_gene) > 3.0:
            warnings.append(f"To keep the back level the front segments stand at {theta:.1f} deg from vertical, not "
                            f"about {theta_gene:g} deg as the gene says.")

        # ------------------------------------------------------------ belt catalog and drives (ADR-063)
        if gp.belt_catalog:  # type: ignore[attr-defined]
            catalog, cat_note = BeltCatalog.from_dict(gp.belt_catalog, origin="inlined project catalog"), ""  # type: ignore[attr-defined]
        else:
            catalog, cat_note = load_catalog(ctx.project_dir)
        if cat_note:
            warnings.append(f"Belt catalog: {cat_note}.")
        ratio_for: dict[str, float] = {}
        belted = ["stifle", "hock"] + (["carpus"] if bool(genes.get("carpus_belt", False)) else [])
        targets = cfg.get("belt_targets", {})

        def layout(drive: str) -> DriveLayout:
            seg_len, far = {
                "stifle": (Lf, Lf + float(lay.get("hip_block_reach_mm", 40))),
                "hock": (Lt, Lt - fit),
                "carpus": (Lu, Lu - fit),
            }[drive]
            return DriveLayout(
                drive=drive, joint_label=drive, segment={"stifle": "femur", "hock": "tibia", "carpus": "upper leg"}[drive],
                segment_length_mm=seg_len, near_limit_mm=fit, far_limit_mm=far, servo_length_mm=s_len,
                servo_width_mm=s_wid, output_axis_offset_mm=None if offset is None else float(offset),
                pulley_clearance_mm=float(lay.get("pulley_clearance_mm", 3)), min_teeth_in_mesh=6.0,
                tension_travel_mm=gp.tension_travel_mm,  # type: ignore[attr-defined]
                target=DriveTarget.model_validate(targets.get(drive) or {"kind": "C", "value": seg_len / 2}),
            )

        reports: dict[str, DriveReport] = {}
        chosen_by_default: list[str] = []
        auto = bool(gp.auto_belts)  # type: ignore[attr-defined]
        stifle_range = tuple(ranges.get("stifle", (-30.0, 80.0)))
        rel_stifle = ry(af + at)  # tibia frame on the femur at standing

        def hock_extra(rep: DriveReport) -> list[Check]:
            return [stifle_clearance_check(rep, reports.get("stifle"), rel_stifle, stifle_range, Lt, s_len, s_wid,
                                           float(lay.get("bracket_margin_mm", 3)), float(lay.get("belt_clearance_mm", 3)),
                                           offset is not None)]

        for drive in belted:
            lo_hi = ranges.get(drive, (-90.0, 90.0))
            extra = hock_extra if drive == "hock" else None
            if not auto:
                choice = belt_choice(genes, drive)
                try:
                    rep = evaluate_drive(catalog, layout(drive), choice, extra)
                except CatalogError as exc:
                    raise ValueError(f"Belt drive at the {drive}: {exc} (the genes name it; the catalog in use does not)") from exc
            else:
                ch, rep_d, why = choose_default(catalog, layout(drive), gp.default_system or None,  # type: ignore[attr-defined]
                                                gp.default_pulleys or None, extra=extra)  # type: ignore[attr-defined]
                if ch is None or rep_d is None:
                    # nothing passes: show the system's first offered length, marked as rejected
                    sysd = catalog.system(gp.default_system or catalog.default_system)  # type: ignore[attr-defined]
                    first = next((e for e in catalog.lengths_for(sysd) if catalog.length_status(sysd, e)[0]), None)
                    if first is None:
                        raise ValueError(f"Belt drive at the {drive}: {why}; add lengths to the catalog")
                    ch = BeltChoice(system=sysd.id, pulleys=gp.default_pulleys or catalog.default_pair,  # type: ignore[attr-defined]
                                    length=first.id)
                    rep_d = evaluate_drive(catalog, layout(drive), ch, extra)
                    warnings.append(f"Belt drive at the {drive}: no default possible ({why}).")
                rep = rep_d
                chosen_by_default.append(drive)
            reports[drive] = rep
            if not rep.ok:
                infeasible.append(rejection(rep))
                belt_failures.append(rejection(rep))
                warnings.append(rejection(rep) + ". Simulation is refused until a valid belt is chosen.")
            ratio_for[drive] = rep.ratio
            width = lo_hi[1] - lo_hi[0]
            if width > 360.0 / rep.ratio + 1e-9:
                raise ValueError(f"The {drive} range {lo_hi[0]:g} to {lo_hi[1]:g} deg spans {width:g} deg; a {rep.ratio:g}:1 "
                                 f"belt on a 360 deg servo allows at most {360.0 / rep.ratio:g} deg (config/feral_calf.yaml)")

        # ------------------------------------------------------------ assemble
        bodies: list[Body] = []
        joints: list[Joint] = []
        actuators: list[Actuator] = []
        transmissions: list[Transmission] = []
        springs: list[Spring] = []
        eff = float(gp.belt_efficiency)  # type: ignore[attr-defined]

        def lim(name: str, default: tuple[float, float]) -> tuple[float, float]:
            v = ranges.get(name)
            return (float(v[0]), float(v[1])) if v else default

        def actuate(k: str, name: str, joint_id: str) -> None:
            if name in ratio_for and (name != "carpus" or "carpus" in belted):
                tr = Transmission(id=f"tr.{k}.{name}", type="belt", ratio=ratio_for[name], efficiency=eff,
                                  motor_body=None)
                transmissions.append(tr)
                actuators.append(Actuator(id=f"act.{k}.{name}", joint=joint_id, component=servo_key, transmission=tr.id))
            else:
                actuators.append(Actuator(id=f"act.{k}.{name}", joint=joint_id, component=servo_key))

        # trunk
        trunk = Body(id="trunk", name="Body (hip block, rails, chest block)", pos=(0.0, 0.0, height))
        for bid, x, key, label in (("trunk.hip_block", hx, "hip_block_g", "Hip block"),
                                   ("trunk.chest_block", sx, "chest_block_g", "Chest block")):
            m = placeholder(key, label, "trunk")
            trunk.geoms.append(Geom(id=bid, shape="box", size=(2 * overhang, block_w, block_h), pos=(x, 0.0, 0.0),
                                    layer="Structure", role="both", mass_g=m or 0.0,
                                    mass_source="specified" if m is not None else "parametric",
                                    mass_note="" if m is not None else f"{label} mass not entered (counted as 0 g)",
                                    label=label))
        rail = str(genes["rail_type"])
        r_od, r_id, r_density = RAILS[rail]
        r_area = math.pi / 4.0 * (r_od * r_od - r_id * r_id)
        for n, y in ((1, rs / 2.0), (2, -rs / 2.0)):
            m = r_area * A * density if r_density else 0.0
            trunk.geoms.append(Geom(
                id=f"trunk.rail{n}", shape="cylinder", size=(r_od / 2.0, A, 0.0), pos=(0.0, y, 0.0),
                quat=quat_from_z_to((1.0, 0.0, 0.0)), layer="Structure", role="both", mass_g=m,
                mass_source="tube" if r_density else "parametric", material="carbon_fibre_tube" if r_density else None,
                mass_note="" if r_density else "aluminium density not entered: rail mass unknown (counted as 0 g)",
                label=f"Rail {n}: {RAIL_LABELS[rail]}"))
        if not r_density:
            missing.setdefault("aluminium_density", {"item": "aluminium_density", "label": "Aluminium rail density",
                                                     "qty": 2, "where": ["trunk"], "enter_in": "not entered anywhere yet"})
        head_x = sx + overhang + _num(genes, "head_forward")
        trunk.geoms.append(Geom(id="head.mass", shape="sphere", size=(25.0, 0.0, 0.0),
                                pos=(head_x, 0.0, _num(genes, "head_height")), layer="Structure", role="visual",
                                mass_g=_num(genes, "head_mass"), mass_source="specified",
                                label="Head + neck (lumped mass, PROVISIONAL)"))
        trunk.geoms += ph_geom("head.neck_rods", "neck_rods_g", "Neck rods", (sx + overhang + 20.0, 0.0, 30.0), "trunk")
        bat = cfg.get("battery", {})
        for n in range(int(bat.get("packs", 0))):
            y = rs / 2.0 if n % 2 == 0 else -rs / 2.0
            trunk.geoms.append(Geom(
                id=f"elec.battery{n + 1}", shape="sphere", size=(12.0, 0.0, 0.0),
                pos=(hx + _num(genes, "battery_forward"), y, -_num(genes, "battery_drop")), layer="Electronics",
                role="visual", mass_g=float(bat.get("pack_mass_g", 0.0)), mass_source="specified",
                label=f"{bat.get('description', 'Battery')} ({bat.get('pack_mass_g')} g as supplied; size not entered)"))
        trunk.geoms += ph_geom("elec.boards", "electronics_g", "Electronics", (0.0, 0.0, block_h / 2.0), "trunk",
                               layer="Electronics")
        trunk.geoms += ph_geom("skin.all", "skin_g", "Skin", (0.0, 0.0, 0.0), "trunk", layer="Skin")
        bodies.append(trunk)

        def belt_parts(upper: Body, lower: Body, k: str, drive: str, z_joint: float, od: float) -> None:
            """Driver servo, pulleys and belt of one drive. ``z_joint``: the driven axis in ``upper``'s frame."""
            rep = reports[drive]
            sy = SIDE[k]
            pair = catalog.pair(rep.choice.pulleys)
            c = rep.c_mm if rep.c_mm is not None else layout(drive).far_limit_mm - s_len / 2.0
            w = rep.width_mm
            y_belt = sy * (od / 2.0 + 2.0 + w / 2.0)
            y_servo = sy * (od / 2.0 + 2.0 + w + 2.0 + s_dep / 2.0)
            span = rep.servo_span_mm or (c - s_len / 2.0, c + s_len / 2.0)
            centre = (span[0] + span[1]) / 2.0 if offset is not None else c
            upper.geoms.append(servo_geom(f"act.{k}.{drive}.motor", (0.0, y_servo, z_joint + centre),
                                          (s_wid, s_dep, s_len), f"{servo.name} ({drive} driver, C {c:.1f} mm)"))
            cyl_y = quat_from_z_to((0.0, 1.0, 0.0))
            for gid, body, z, d, mkey in ((f"belt.{k}.{drive}.driver", upper, z_joint + c, rep.d1_mm, "driver_mass_g"),
                                          (f"belt.{k}.{drive}.driven", lower, 0.0, rep.d2_mm, "driven_mass_g")):
                m = getattr(pair, mkey)
                teeth = pair.driver_teeth if mkey == "driver_mass_g" else pair.driven_teeth
                if m is None:
                    row = missing.setdefault(f"pulley_{teeth}t", {"item": f"pulley_{teeth}t", "label": f"Pulley {teeth}T",
                                                                    "qty": 0, "where": [],
                                                                    "enter_in": f"catalog/pulleys.json {pair.id}.{mkey}"})
                    row["qty"] += 1
                    if body.id not in row["where"]:
                        row["where"].append(body.id)
                body.geoms.append(Geom(id=gid, shape="cylinder", size=(d / 2.0, w, 0.0), pos=(0.0, y_belt, z),
                                       quat=cyl_y, layer="Transmission", role="visual", mass_g=float(m or 0.0),
                                       mass_source="specified" if m is not None else "parametric",
                                       label=f"{teeth}T pulley, pitch diameter {d:.2f} mm"))
            # the two straight spans of the belt, fixed in the upper segment (both pulley axes are)
            r1, r2 = rep.d1_mm / 2.0, rep.d2_mm / 2.0
            ns = (r2 - r1) / c
            nx = math.sqrt(max(0.0, 1.0 - ns * ns))
            for n, sgn in ((1, 1.0), (2, -1.0)):
                p2 = (sgn * nx * r2, z_joint + ns * r2)
                p1 = (sgn * nx * r1, z_joint + c + ns * r1)
                L = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                upper.geoms.append(Geom(
                    id=f"belt.{k}.{drive}.span{n}", shape="box", size=(1.5, w, L),
                    pos=((p1[0] + p2[0]) / 2.0, y_belt, (p1[1] + p2[1]) / 2.0),
                    quat=quat_from_z_to((p1[0] - p2[0], 0.0, p1[1] - p2[1])), layer="Transmission", role="visual",
                    label=f"{rep.choice.system} belt, {rep.length_mm:g} mm ({rep.belt_teeth} teeth)"))
            upper.geoms += ph_geom(f"belt.{k}.{drive}.belt_mass", "belt_g", "Belt", (0.0, y_belt, z_joint + c / 2.0),
                                   upper.id, layer="Transmission")
            upper.geoms += ph_geom(f"act.{k}.{drive}.horn", "servo_horn_g", "Servo horn", (0.0, y_servo, z_joint + c),
                                   upper.id, layer="Actuators")
            if drive in ("hock", "carpus"):
                upper.geoms += ph_geom(f"act.{k}.{drive}.collar", "clamp_collar_g", "Clamp collar",
                                       (0.0, 0.0, z_joint + c), upper.id)

        def plugs(body: Body, length: float) -> None:
            for n, z in ((1, 0.0), (2, -length)):
                body.geoms += ph_geom(f"{body.id}.plug{n}", "tube_plug_g", "Tube plug", (0.0, 0.0, z), body.id)

        def hoof(body: Body, length: float, world_angle_fwd: float) -> None:
            # world straight down in this body's frame (the segment stands world_angle_fwd forward of vertical)
            d = quat_rotate(ry(world_angle_fwd), (0.0, 0.0, -1.0))
            c = (d[0] * (pad - pad_r), 0.0, -length + d[2] * (pad - pad_r))
            m = placeholder("hoof_pad_g", "Hoof pad", body.id)
            body.geoms.append(Geom(id=f"{body.id}.hoof", shape="sphere", size=(pad_r, 0.0, 0.0), pos=c,
                                   layer="Structure", role="both", foot=True, mass_g=m or 0.0,
                                   mass_source="specified" if m is not None else "parametric",
                                   mass_note="" if m is not None else "Hoof pad mass not entered (counted as 0 g)",
                                   label="Hoof pad"))

        def bearing(body: Body, joint_name: str) -> None:
            body.geoms += ph_geom(f"{body.id}.bearing", "bearing_g", "Bearing", (0.0, 0.0, 0.0), f"{joint_name}")

        # ------------------------------------------------------------ rear legs
        for k in REAR:
            sy = SIDE[k]
            name = LEG_NAMES[k]
            Lf_k, Lt_k, Lc_k = (val(f"leg.{k}.{p}", "length") for p in ("femur", "tibia", "cannon"))
            q_f = ry(-af)
            femur = Body(id=f"leg.{k}.femur", name=f"{name} femur", parent="trunk", pos=(hx, sy * leg_y, 0.0), quat=q_f)
            femur.geoms.append(tube(f"leg.{k}.femur.tube", "Femur", Lf_k, "femur_od", "femur_id"))
            plugs(femur, Lf_k)
            bearing(femur, f"joint.{k}.hip_abd")
            joints.append(Joint(id=f"joint.{k}.hip_abd", name=f"{name} hip ab/adduction", body=femur.id,
                                axis=quat_rotate(conj(q_f), (float(sy), 0.0, 0.0)), range_deg=lim("hip_abd", (-25, 25)),
                                group="leg", damping=jd, friction=jf))
            actuate(k, "hip_abd", f"joint.{k}.hip_abd")
            trunk.geoms.append(servo_geom(f"act.{k}.hip_abd.motor", (hx, sy * (block_w / 2.0 - s_wid / 2.0 - 2.0), 0.0),
                                          (s_dep, s_wid, s_len), f"{servo.name} (hip ab/ad, direct)"))
            trunk.geoms += ph_geom(f"act.{k}.hip_abd.horn", "servo_horn_g", "Servo horn", (hx, sy * block_w / 2.0, 0.0), "trunk",
                                   layer="Actuators")
            tibia = Body(id=f"leg.{k}.tibia", name=f"{name} tibia", parent=femur.id, pos=(0.0, 0.0, -Lf_k), quat=ry(af + at))
            tibia.geoms.append(tube(f"leg.{k}.tibia.tube", "Tibia", Lt_k, "tibia_od", "tibia_id"))
            plugs(tibia, Lt_k)
            bearing(tibia, f"joint.{k}.stifle")
            joints.append(Joint(id=f"joint.{k}.stifle", name=f"{name} stifle", body=tibia.id, axis=(0.0, 1.0, 0.0),
                                range_deg=lim("stifle", (-30, 80)), group="leg", damping=jd, friction=jf))
            actuate(k, "stifle", f"joint.{k}.stifle")
            cannon = Body(id=f"leg.{k}.cannon", name=f"{name} cannon", parent=tibia.id, pos=(0.0, 0.0, -Lt_k),
                          quat=ry(-ac - at))
            cannon.geoms.append(tube(f"leg.{k}.cannon.tube", "Cannon", Lc_k, "rear_cannon_od", "rear_cannon_id"))
            plugs(cannon, Lc_k)
            bearing(cannon, f"joint.{k}.hock")
            hoof(cannon, Lc_k, ac)
            joints.append(Joint(id=f"joint.{k}.hock", name=f"{name} hock", body=cannon.id, axis=(0.0, -1.0, 0.0),
                                range_deg=lim("hock", (-30, 80)), group="leg", damping=jd, friction=jf))
            actuate(k, "hock", f"joint.{k}.hock")
            belt_parts(femur, tibia, k, "stifle", -Lf_k, _num(genes, "femur_od"))
            belt_parts(tibia, cannon, k, "hock", -Lt_k, _num(genes, "tibia_od"))
            bodies += [femur, tibia, cannon]

        # ------------------------------------------------------------ front legs
        for k in FRONT:
            sy = SIDE[k]
            name = LEG_NAMES[k]
            Lu_k, Lfc_k = val(f"leg.{k}.upper", "length"), val(f"leg.{k}.cannon", "length")
            upper = Body(id=f"leg.{k}.upper", name=f"{name} upper leg", parent="trunk", pos=(sx, sy * leg_y, 0.0),
                         quat=ry(-theta))
            upper.geoms.append(tube(f"leg.{k}.upper.tube", "Upper leg", Lu_k, "upper_leg_od", "upper_leg_id"))
            plugs(upper, Lu_k)
            bearing(upper, f"joint.{k}.shoulder")
            joints.append(Joint(id=f"joint.{k}.shoulder", name=f"{name} shoulder", body=upper.id, axis=(0.0, 1.0, 0.0),
                                range_deg=lim("shoulder", (-60, 60)), group="leg", damping=jd, friction=jf))
            actuate(k, "shoulder", f"joint.{k}.shoulder")
            trunk.geoms.append(servo_geom(f"act.{k}.shoulder.motor", (sx, sy * (block_w / 2.0 - s_dep / 2.0 - 2.0), 0.0),
                                          (s_wid, s_dep, s_len), f"{servo.name} (shoulder, direct)"))
            trunk.geoms += ph_geom(f"act.{k}.shoulder.horn", "servo_horn_g", "Servo horn", (sx, sy * block_w / 2.0, 0.0),
                                   "trunk", layer="Actuators")
            cannon = Body(id=f"leg.{k}.cannon", name=f"{name} cannon", parent=upper.id, pos=(0.0, 0.0, -Lu_k),
                          quat=ry(2.0 * theta))
            cannon.geoms.append(tube(f"leg.{k}.cannon.tube", "Cannon", Lfc_k, "front_cannon_od", "front_cannon_id"))
            plugs(cannon, Lfc_k)
            bearing(cannon, f"joint.{k}.carpus")
            hoof(cannon, Lfc_k, -theta)
            joints.append(Joint(id=f"joint.{k}.carpus", name=f"{name} carpus", body=cannon.id, axis=(0.0, 1.0, 0.0),
                                range_deg=lim("carpus", (-10, 130)), group="leg", damping=jd, friction=jf))
            actuate(k, "carpus", f"joint.{k}.carpus")
            if "carpus" in belted:
                belt_parts(upper, cannon, k, "carpus", -Lu_k, _num(genes, "upper_leg_od"))
            else:
                od = _num(genes, "upper_leg_od")
                upper.geoms.append(servo_geom(f"act.{k}.carpus.motor", (0.0, sy * (od / 2.0 + 2.0 + s_dep / 2.0), -Lu_k),
                                              (s_wid, s_dep, s_len), f"{servo.name} (carpus, direct)"))
                upper.geoms += ph_geom(f"act.{k}.carpus.horn", "servo_horn_g", "Servo horn", (0.0, sy * od / 2.0, -Lu_k),
                                       upper.id, layer="Actuators")
            bodies += [upper, cannon]

        # ------------------------------------------------------------ springs (ADR-065)
        spring_meta: dict[str, Any] = {}
        for sname, (up_seg, low_seg) in SPRINGS.items():
            g = {f: _num(genes, f"spring_{sname}_{f}") for f in
                 ("k", "free_length", "upper_along", "upper_normal", "lower_along", "lower_normal")}
            on = bool(genes.get(f"spring_{sname}", True))
            spring_meta[sname] = {"enabled": on, **g}
            if not on:
                continue
            legs = FRONT if sname == "shoulder" else REAR
            joint_name = sname
            for k in legs:
                if up_seg is None:  # the shoulder: anchored on the chest block, relative to the shoulder axle
                    upper_body, upper_pos = "trunk", (sx + g["upper_normal"], SIDE[k] * leg_y, g["upper_along"])
                    seg_len = 0.0
                else:
                    upper_body = f"leg.{k}.{up_seg}"
                    seg_len = val(upper_body, "length")
                    upper_pos = (g["upper_normal"], 0.0, -seg_len + g["upper_along"])
                springs.append(Spring(
                    id=f"spring.{k}.{joint_name}", joint=f"joint.{k}.{joint_name}", upper_body=upper_body,
                    upper_pos=upper_pos, lower_body=f"leg.{k}.{low_seg}", lower_pos=(g["lower_normal"], 0.0, -g["lower_along"]),
                    k_n_per_mm=g["k"], free_length_mm=g["free_length"], label=f"{LEG_NAMES[k]} {joint_name} spring"))
                spring_mass = placeholder("spring_g", "Spring", f"joint.{k}.{joint_name}")
                if spring_mass is not None:
                    lower = next(b for b in bodies if b.id == f"leg.{k}.{low_seg}")
                    lower.geoms.append(Geom(id=f"spring.{k}.{joint_name}.mass", shape="sphere", size=(4.0, 0.0, 0.0),
                                            pos=(g["lower_normal"], 0.0, -g["lower_along"]), role="visual",
                                            mass_g=spring_mass, mass_source="specified", label="Spring (entered)"))

        # ------------------------------------------------------------ record
        provisional = provisional_values(genes, gp, cfg)
        res = 360.0 / float(servo.encoder_steps_per_rev) if servo.encoder_steps_per_rev else None
        spec = RobotSpec(
            name="feral_calf",
            bodies=bodies,
            joints=joints,
            actuators=actuators,
            transmissions=transmissions,
            springs=springs,
            metadata={
                "warnings": warnings,
                # generic: evolution rejects a candidate that lists reasons here (ADR-070)
                "infeasible": list(infeasible),
                # the same reasons by kind: only belt failures narrow a belt_bound gene's search range (ADR-070)
                "infeasible_by": {"belt": belt_failures, "other": [r for r in infeasible if r not in belt_failures]},
                "missing_masses": list(missing.values()),
                "feral": {
                    "standing_height_mm": round(height, 2),
                    "front_angle_deg": round(theta, 3),
                    "front_angle_gene_deg": theta_gene,
                    "leg_y_mm": round(leg_y, 2),
                    "axle_spacing_mm": A,
                    "belt_catalog": {"origin": catalog.origin, "digest": catalog.digest(), "note": cat_note},
                    "belt_drives": {d: {**r.model_dump(mode="json"), "default_chosen": d in chosen_by_default,
                                        "layout": layout(d).model_dump(mode="json")} for d, r in reports.items()},
                    "belts_ok": all(r.ok for r in reports.values()),
                    # why this body cannot be built as it is (evolution rejects such a candidate, ADR-070)
                    "infeasible": infeasible,
                    "belted": belted,
                    "springs": spring_meta,
                    "provisional": provisional,
                    "servo": {"component": servo_key, "name": servo.name, "stall_nm": servo.stall_torque_nm,
                              "rated_nm": servo.rated_torque_nm, "encoder_steps": servo.encoder_steps_per_rev,
                              "servo_resolution_deg": res, "output_axis_offset_mm": offset,
                              "unknown": list(servo.unknown)},
                    "joint_ranges_deg": {k: list(v) for k, v in ranges.items()},
                    # what the hock's clearance sweep needs to be re-run for another hock choice (belt_context)
                    "sweep": {"rel_stifle_deg": af + at, "stifle_range": list(stifle_range), "tibia_mm": Lt,
                              "servo_len": s_len, "servo_width": s_wid, "bracket": float(lay.get("bracket_margin_mm", 3)),
                              "clearance": float(lay.get("belt_clearance_mm", 3)), "offset_known": offset is not None},
                    "checks": {"sustained_fraction": gp.sustained_fraction,  # type: ignore[attr-defined]
                               "breaking_fraction": gp.breaking_fraction,  # type: ignore[attr-defined]
                               "rated_fraction": gp.rated_fraction,  # type: ignore[attr-defined]
                               "belt_efficiency": eff},
                },
            },
        )
        return spec


def stifle_clearance_check(
    hock: DriveReport,
    stifle: DriveReport | None,
    rel_standing: Quat,
    stifle_range: tuple[float, ...],
    tibia_len: float,
    servo_len: float,
    servo_width: float,
    bracket: float,
    clearance: float,
    offset_known: bool,
) -> Check:
    """The hock servo and its bracket against the stifle's driven pulley and
    belt, through the whole stifle range, in the tibia's plane (ADR-063)."""
    label = "Hock servo clears the stifle pulley and belt through the stifle's range"
    if stifle is None or stifle.c_mm is None or hock.c_mm is None:
        return Check(id="stifle_belt_clearance", label=label, status="unknown",
                     detail="the stifle drive has no valid geometry to check against")
    lo, hi = float(stifle_range[0]), float(stifle_range[1])
    n = max(2, int(math.ceil((hi - lo) / 2.5)) + 1)  # every 2.5 deg, both ends included
    angles = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    dirs = []
    for q in angles:
        rel = quat_mul(rel_standing, quat_axis_angle((0.0, 1.0, 0.0), q))
        d = quat_rotate(conj(rel), (0.0, 0.0, 1.0))  # up the femur, in the tibia frame
        dirs.append((d[0], d[2]))
    c = hock.c_mm
    if offset_known and hock.servo_span_mm is not None:
        a, b = hock.servo_span_mm
        spans = [(tibia_len - b, tibia_len - a)]
    else:  # the output axis position on the case is not known: every way the case could sit
        spans = [(tibia_len - c - servo_len, tibia_len - c), (tibia_len - c - servo_len / 2, tibia_len - c + servo_len / 2),
                 (tibia_len - c, tibia_len - c + servo_len)]
    res = clearance_sweep(angles, dirs, stifle.c_mm, stifle.d1_mm, stifle.d2_mm, (0.0, -1.0), spans,
                          servo_width / 2.0 + bracket, clearance, "the stifle belt")
    return Check(id="stifle_belt_clearance", label=label, status=res.status, detail=res.detail)


def provisional_values(genes: dict[str, GeneValue], gp: Any, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Every PROVISIONAL value in use, where it lives and what it is (ADR-066..068)."""
    from calflab.config import gene_definition_files

    gdef = gene_definition_files()["feral_calf"]
    out: list[dict[str, Any]] = []
    for g in gdef.genes:
        if g.provisional:
            out.append({"name": g.label or g.id, "value": genes.get(g.id), "unit": g.unit, "where": f"gene {g.id}"})
    for name, f in type(gp).model_fields.items():
        extra = f.json_schema_extra if isinstance(f.json_schema_extra, dict) else {}
        if extra.get("provisional"):
            out.append({"name": name, "value": getattr(gp, name), "unit": extra.get("unit"),
                        "where": f"Belts panel / morphology node param {name}"})
    for k, v in (cfg.get("layout") or {}).items():
        out.append({"name": k, "value": v, "unit": "mm" if k.endswith("_mm") else None, "where": f"config/feral_calf.yaml layout.{k}"})
    for k, v in (cfg.get("joint_ranges_deg") or {}).items():
        out.append({"name": f"{k} range", "value": v, "unit": "deg", "where": f"config/feral_calf.yaml joint_ranges_deg.{k}"})
    servo = cfg.get("servo") or {}
    for k in ("length_along_segment_mm", "width_across_segment_mm", "depth_sideways_mm"):
        if k in servo:
            out.append({"name": f"servo case {k} (orientation)", "value": servo[k], "unit": "mm",
                        "where": f"config/feral_calf.yaml servo.{k}"})
    return out


def belt_context(spec: RobotSpec, project_dir: Any) -> tuple[BeltCatalog, dict[str, DriveLayout], dict[str, Any]]:
    """The catalog, the layout of every drive and the extra checks of a built
    feral calf, to list and evaluate other choices for one drive (Belts panel)."""
    meta = spec.metadata.get("feral") or {}
    catalog = load_catalog(project_dir)[0]
    drives = meta.get("belt_drives", {})
    layouts = {d: DriveLayout.model_validate(r["layout"]) for d, r in drives.items()}
    extra: dict[str, Any] = {}
    sw = meta.get("sweep")
    if sw and "stifle" in drives:
        stifle = DriveReport.model_validate({k: v for k, v in drives["stifle"].items() if k in DriveReport.model_fields})

        def hock_extra(rep: DriveReport) -> list[Check]:
            return [stifle_clearance_check(rep, stifle, ry(sw["rel_stifle_deg"]), tuple(sw["stifle_range"]), sw["tibia_mm"],
                                           sw["servo_len"], sw["servo_width"], sw["bracket"], sw["clearance"],
                                           sw["offset_known"])]

        extra["hock"] = hock_extra
    return catalog, layouts, extra
