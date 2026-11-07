"""Bounded geometry, pulleys chosen one by one, belt lengths feasible by construction, springs and the shoulder drive
as genes (session R11c, ADR-103). Used by ``map_elites_hardware`` when the preset's ``evaluation.hardware`` has a
``production`` block; without it the optimizer behaves exactly as in R11 (ADR-102).

Every dimension is in [0, 1] and decodes to a discrete step, so a body drawn twice is the same body (and its plays
are cached):

* **segment lengths** (``geometry``): +-``rel`` of the starting length on ``step_mm`` steps; the inter-segment
  ratios (``ratios``) must stay within +-``ratio_tolerance`` of the starting body's, else the body is rejected;
* **servo per joint pair**: as R11;
* **shoulder drive**: direct or belted (gene ``shoulder_belt``);
* **per belted drive**: belt system, driver pulley, driven pulley (single listed pulleys whose listings name the
  system's width; the pair id is ``<driver>+<driven>``, or the catalog's own pair id when it has those teeth), and a
  belt length index. The index decodes ONLY over the system's listed lengths that pass every belt check on this body
  (ADR-070 reinterpreted): nothing is adjusted after the fact, and a drive with no feasible listed length is rejected
  with the reason. C stays derived (ADR-063);
* **springs per site**: on/off, rate (``k_factors`` x the starting rate), preload (``preload_factors`` x the starting
  standing extension; free length = standing length - preload), the anchor on each segment along it
  (``along_steps_mm``) and across it (``normal_steps_mm``) relative to the starting anchors.

Checks with a recorded reason for every rejection: the ratios, the belt checks (in the generator), the servo budget,
and the springs (``spring_checks``): anchors on their segments, the spring line clear of the joint (tube radius +
``clearance_mm``) through the whole joint range, free length within the gene's range.

Not modelled (reported): lateral and angular placement of pulleys, belts and springs (the lab assumes one plane);
pulley clearance at the joint for its own diameter (needs that lateral stack).

Units: mm, N/mm, degrees.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.schema import P

SITES = ("hip_abd", "stifle", "hock", "shoulder", "carpus")
#: the two anchor coordinates that are evolved per site: (along gene suffix, across gene suffix) on each end
ANCHORS: dict[str, list[tuple[str, str]]] = {
    "stifle": [("upper_along", "along"), ("upper_normal", "normal"), ("lower_along", "along"), ("lower_normal", "normal")],
    "hock": [("upper_along", "along"), ("upper_normal", "normal"), ("lower_along", "along"), ("lower_normal", "normal")],
    "shoulder": [("upper_along", "along"), ("upper_normal", "normal"), ("lower_along", "along"),
                 ("lower_normal", "normal")],
    "carpus": [("upper_along", "along"), ("upper_normal", "normal"), ("lower_along", "along"), ("lower_normal", "normal")],
    "hip_abd": [("upper_inward", "normal"), ("lower_along", "along")],
}
#: segment above / below each site (None = the trunk), and the gene of each segment's length and tube diameter
SITE_SEGMENTS = {"stifle": ("femur", "tibia"), "hock": ("tibia", "rear_cannon"), "shoulder": (None, "upper_leg"),
                 "carpus": ("upper_leg", "front_cannon"), "hip_abd": (None, "femur")}
BELT_ORDER = ("stifle", "hock", "carpus", "shoulder")


class GeometrySpace(BaseModel):
    genes: list[str] = Field(default_factory=lambda: ["femur_length", "tibia_length", "rear_cannon_length",
                                                      "upper_leg_length", "front_cannon_length"])
    rel: float = P(0.10, ge=0.0, le=0.5, desc="Each length within +- this fraction of the starting body's.")
    step_mm: float = P(2.0, ge=0.5, le=20.0, unit="mm", desc="Length step.")
    ratios: list[list[str]] = Field(default_factory=lambda: [["tibia_length", "femur_length"],
                                                             ["rear_cannon_length", "tibia_length"],
                                                             ["front_cannon_length", "upper_leg_length"]],
                                    description="Inter-segment ratios (numerator, denominator) held near the start.")
    ratio_tolerance: float = P(0.05, ge=0.0, le=0.5, desc="Each ratio within +- this fraction of the starting one.")


class SpringSpace(BaseModel):
    sites: list[str] = Field(default_factory=lambda: list(SITES))
    switch: bool = P(True, desc="Evolve each site on/off.")
    k_factors: list[float] = Field(default_factory=lambda: [0.5, 0.75, 1.0, 1.5, 2.0])
    preload_factors: list[float] = Field(default_factory=lambda: [0.5, 1.0, 1.5])
    along_steps_mm: list[float] = Field(default_factory=lambda: [-15.0, 0.0, 15.0])
    normal_steps_mm: list[float] = Field(default_factory=lambda: [-10.0, 0.0, 10.0])
    clearance_mm: float = P(3.0, ge=0.0, le=20.0, unit="mm", desc="Spring line clear of the joint tube.")
    sweep_step_deg: float = P(5.0, ge=0.5, le=20.0, unit="deg")
    #: the far joint fitting an anchor must stay clear of, and how far above a joint an anchor may sit on a lever
    fitting_mm: float = P(28.0, ge=0.0, le=100.0, unit="mm")
    lever_mm: float = P(30.0, ge=0.0, le=100.0, unit="mm")
    #: what a spring line passing the joint closer than tube radius + clearance does: "flag" (reported, the body is
    #: judged) or "reject". Default flag (ADR-103): today's own stifle, hock and shoulder springs come within 1-8 mm
    #: of their axes somewhere in the PROVISIONAL joint ranges, so rejecting would reject the working body itself.
    line_check: str = P("flag", desc="'flag' or 'reject' a spring line that comes too close to its joint.")


class ProductionSettings(BaseModel):
    """``evaluation.hardware.production`` of a preset (R11c)."""

    geometry: GeometrySpace | None = Field(default_factory=GeometrySpace)
    springs: SpringSpace | None = Field(default_factory=SpringSpace)
    pulleys: str = P("singles", desc="'singles': driver and driven chosen separately from the listed pulleys.")
    feasible_lengths: bool = P(True, desc="Belt length decodes only over listed lengths that pass on this body.")
    shoulder_drive: bool = P(True, desc="Evolve the shoulder drive: direct or belted.")
    stop_rejected_fraction: float = P(0.5, ge=0.0, le=1.0, desc="Stop when more than this share of a generation's "
                                                                "draws is rejected.")


class Dim(BaseModel):
    name: str
    kind: str  # "ordinal" (Gaussian moves) or "choice" (redrawn)
    n: int


def _x(i: int, n: int) -> float:
    return (i + 0.5) / max(1, n)


def _i(x: float, n: int) -> int:
    return int(min(n - 1, max(0, int(float(np.clip(x, 0.0, 1.0)) * n))))


def standing_lengths(spec: Any) -> dict[str, float]:
    """Spring id -> anchor-to-anchor length (mm) in the standing pose."""
    from calflab.mech.statics import _world

    poses = spec.world_poses()
    return {sp.id: float(np.linalg.norm(np.subtract(_world(poses, sp.upper_body, sp.upper_pos),
                                                    _world(poses, sp.lower_body, sp.lower_pos)))) for sp in spec.springs}


def _line_seg_distance(j: np.ndarray, a: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> float:
    """Least distance (mm) from the axis line (point ``j``, unit ``a``) to the segment p0-p1."""
    best = math.inf
    for t in np.linspace(0.0, 1.0, 41):
        d = p0 + t * (p1 - p0) - j
        best = min(best, float(np.linalg.norm(d - np.dot(d, a) * a)))
    return best


def spring_checks(spec: Any, values: dict[str, Any], sp: SpringSpace) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Springs of a built feral calf: anchors on their segments, the spring line clear of the joint through the whole
    range, and per site the standing length, the largest extension and force over the range (left legs; the right
    mirror them). Returns (rejection reasons, per-site report)."""
    from calflab.mech.statics import _world, joint_frames

    reasons: list[str] = []
    flags: list[str] = []
    report: dict[str, dict[str, Any]] = {}
    fer = spec.metadata.get("feral") or {}
    block_h = 80.0
    overhang = max(0.0, (float(values.get("body_length", 760)) - float(values.get("axle_spacing", 550))) / 2.0)
    for site in SITES:
        if not bool(values.get(f"spring_{site}", False)):
            continue
        up_seg, low_seg = SITE_SEGMENTS[site]
        # anchors on their segments
        if site == "hip_abd":
            if float(values["spring_hip_abd_lower_along"]) > float(values["femur_length"]) - sp.fitting_mm:
                reasons.append(f"hip ab/ad spring: femur anchor {values['spring_hip_abd_lower_along']:g} mm down the "
                               f"femur is past its stifle fitting ({values['femur_length']:g} - {sp.fitting_mm:g} mm)")
            if float(values["spring_hip_abd_upper_down"]) > block_h / 2.0:
                reasons.append(f"hip ab/ad spring: block anchor {values['spring_hip_abd_upper_down']:g} mm below the "
                               f"axle is below the {block_h:g} mm hip block")
            if float(values["spring_hip_abd_upper_inward"]) > float(fer.get("leg_y_mm", 1e9)):
                reasons.append("hip ab/ad spring: block anchor inboard of the centre line")
        else:
            for end, seg in (("upper", up_seg), ("lower", low_seg)):
                along = float(values[f"spring_{site}_{end}_along"])
                if seg is None:  # the shoulder's chest-block anchor: up and forward of the axle
                    if abs(along) > block_h / 2.0 or abs(float(values[f"spring_{site}_{end}_normal"])) > overhang:
                        reasons.append(f"{site} spring: chest anchor ({along:g} mm up, "
                                       f"{values[f'spring_{site}_{end}_normal']:g} mm forward) is off the chest block")
                    continue
                L = float(values[f"{seg}_length"])
                if along > L - sp.fitting_mm or along < -sp.lever_mm:
                    reasons.append(f"{site} spring: {end} anchor {along:g} mm along the {seg.replace('_length', '')} "
                                   f"is off it (allowed -{sp.lever_mm:g} to {L - sp.fitting_mm:g} mm)")
        # the line through the joint's range (left leg)
        leg = "fl" if site in ("shoulder", "carpus") else "hl"
        sid = f"spring.{leg}.{site}"
        spring = next((s for s in spec.springs if s.id == sid), None)
        if spring is None:
            continue
        joint = next(j for j in spec.joints if j.id == spring.joint)
        lo, hi = joint.range_deg
        n = max(2, int(math.ceil((hi - lo) / sp.sweep_step_deg)) + 1)
        seg_gene = {"hip_abd": "femur_od", "stifle": "femur_od", "hock": "tibia_od", "shoulder": "upper_leg_od",
                    "carpus": "upper_leg_od"}[site]
        need = float(values.get(seg_gene, 15.0)) / 2.0 + sp.clearance_mm
        worst = (math.inf, 0.0)
        lengths = []
        for q in np.linspace(lo, hi, n):
            poses = spec.world_poses({joint.id: float(q)})
            jp, ax = joint_frames(spec, poses)[joint.id]
            pa = np.asarray(_world(poses, spring.upper_body, spring.upper_pos))
            pb = np.asarray(_world(poses, spring.lower_body, spring.lower_pos))
            a = np.asarray(ax, float)
            a = a / (np.linalg.norm(a) or 1.0)
            dist = _line_seg_distance(np.asarray(jp, float), a, pa, pb)
            if dist < worst[0]:
                worst = (dist, float(q))
            lengths.append(float(np.linalg.norm(pa - pb)))
        L0, k = float(spring.free_length_mm), float(spring.k_n_per_mm)
        ext = max(lengths) - L0
        report[site] = {"standing_mm": round(standing_lengths(spec)[sid], 1), "free_mm": L0, "k_n_per_mm": k,
                        "max_length_mm": round(max(lengths), 1), "max_extension_mm": round(ext, 1),
                        "peak_force_n": round(k * max(0.0, ext), 1), "min_line_gap_mm": round(worst[0], 1),
                        "at_deg": round(worst[1], 1), "range_deg": [lo, hi]}
        report[site]["line_clear"] = worst[0] >= need
        if worst[0] < need:
            (reasons if sp.line_check == "reject" else flags).append(
                f"{site} spring line comes {worst[0]:.1f} mm from the joint axis at {worst[1]:.0f} deg "
                           f"(needs {need:.1f}: tube radius + {sp.clearance_mm:g} mm)")
    if flags:
        report["_flags"] = flags  # type: ignore[assignment]
    return reasons, report


class ProductionSpace:
    """Every R11c gene as a dimension in [0, 1]; ``realise`` turns a vector into gene values, building the body to
    find the feasible belt lengths and the springs' standing lengths."""

    def __init__(self, gdef: Any, hw: Any, catalog: Any, start: dict[str, Any], start_spec: Any,
                 build: Callable[[dict[str, Any]], Any]) -> None:
        self.gdef, self.hw, self.cat, self.start = gdef, hw, catalog, dict(start)
        self.pr = ProductionSettings.model_validate(hw.production)
        self.build = build
        self.dims: list[Dim] = []
        # geometry
        self.geo: dict[str, list[float]] = {}
        if self.pr.geometry:
            g = self.pr.geometry
            for gid in g.genes:
                v0 = float(start[gid])
                lo, hi = v0 * (1 - g.rel), v0 * (1 + g.rel)
                k0 = math.ceil((lo - v0) / g.step_mm - 1e-9)
                k1 = math.floor((hi - v0) / g.step_mm + 1e-9)
                self.geo[gid] = [round(v0 + k * g.step_mm, 3) for k in range(k0, k1 + 1)]
                self.dims.append(Dim(name=gid, kind="ordinal", n=len(self.geo[gid])))
        self.n_ordinal = len(self.dims)
        # servos
        self.servo_genes = [f"servo_{p}" for p in ("hip_abd", "stifle", "hock", "shoulder", "carpus") if gdef.has(f"servo_{p}")]
        for gname in self.servo_genes:
            self.dims.append(Dim(name=gname, kind="choice", n=len(hw.servo_choices)))
        if self.pr.shoulder_drive and gdef.has("shoulder_belt"):
            self.dims.append(Dim(name="shoulder_belt", kind="choice", n=2))
        # belts
        allowed = set(hw.belt_systems) if hw.belt_systems else None
        self.systems = [s for s in catalog.systems if catalog.pulleys_for(s) and (allowed is None or s.id in allowed)]
        self.excluded_systems = [s.id for s in catalog.systems if not catalog.pulleys_for(s)]
        self.lengths = {s.id: [e for e in catalog.lengths_for(s) if catalog.length_status(s, e)[0]] for s in self.systems}
        self.systems = [s for s in self.systems if self.lengths[s.id]]
        self.pulleys = {s.id: catalog.pulleys_for(s) for s in self.systems}
        self.max_lengths = max((len(v) for v in self.lengths.values()), default=1)
        self.drives = [d for d in BELT_ORDER if d in hw.drives or (d == "shoulder" and self.pr.shoulder_drive)]
        for d in self.drives:
            n_p = max(len(v) for v in self.pulleys.values())
            self.dims += [Dim(name=f"belt_{d}_system", kind="choice", n=len(self.systems)),
                          Dim(name=f"belt_{d}_driver", kind="choice", n=n_p),
                          Dim(name=f"belt_{d}_driven", kind="choice", n=n_p),
                          Dim(name=f"belt_{d}_length", kind="choice", n=self.max_lengths)]
        # springs: the starting values, and the starting standing extension per site (an off site: the gene file's)
        self.spring_base: dict[str, dict[str, float]] = {}
        sp = self.pr.springs
        if sp:
            on_all = {**start, **{f"spring_{s}": True for s in sp.sites}}
            ref = build(on_all)
            st = standing_lengths(ref.spec)
            for s in sp.sites:
                leg = "fl" if s in ("shoulder", "carpus") else "hl"
                base = {f: float(start[f"spring_{s}_{f}"]) for f, _ in ANCHORS[s]}
                base["k"] = float(start[f"spring_{s}_k"])
                base["ext"] = st.get(f"spring.{leg}.{s}", 0.0) - float(start[f"spring_{s}_free_length"])
                self.spring_base[s] = base
                if sp.switch:
                    self.dims.append(Dim(name=f"spring_{s}", kind="choice", n=2))
                self.dims += [Dim(name=f"spring_{s}_k", kind="choice", n=len(sp.k_factors)),
                              Dim(name=f"spring_{s}_preload", kind="choice", n=len(sp.preload_factors))]
                for f, kind in ANCHORS[s]:
                    steps = sp.along_steps_mm if kind == "along" else sp.normal_steps_mm
                    self.dims.append(Dim(name=f"spring_{s}_{f}", kind="choice", n=len(steps)))
        self.start_spec = start_spec

    @property
    def names(self) -> list[str]:
        return [d.name for d in self.dims]

    def __len__(self) -> int:
        return len(self.dims)

    # ------------------------------------------------------------------ encode
    def pair_singles(self, pair_id: str) -> tuple[int, int] | None:
        """Driver and driven teeth of a pair id (a catalog pair or two singles)."""
        try:
            p = self.cat.pair(pair_id)
        except Exception:
            return None
        return p.driver_teeth, p.driven_teeth

    def encode(self, values: dict[str, Any]) -> np.ndarray:
        """The vector of a body (the belt length index is found among the lengths feasible for it)."""
        out: list[float] = []
        idx = {d.name: k for k, d in enumerate(self.dims)}
        x = np.full(len(self.dims), 0.5)
        for gid, grid in self.geo.items():
            v = float(values[gid])
            x[idx[gid]] = _x(int(np.argmin([abs(v - g) for g in grid])), len(grid))
        ch = self.hw.servo_choices
        for gname in self.servo_genes:
            sv = values.get(gname)
            x[idx[gname]] = _x(ch.index(sv), len(ch)) if sv in ch else _x(0, len(ch))
        if "shoulder_belt" in idx:
            x[idx["shoulder_belt"]] = _x(int(bool(values.get("shoulder_belt", False))), 2)
        design = None
        for d in self.drives:
            sid = values.get(f"belt_{d}_system")
            si = next((i for i, s in enumerate(self.systems) if s.id == sid), 0)
            s = self.systems[si]
            x[idx[f"belt_{d}_system"]] = _x(si, len(self.systems))
            teeth = self.pair_singles(str(values.get(f"belt_{d}_pulleys", ""))) or (s and (30, 60))
            pl = self.pulleys[s.id]
            n_p = self.dims[idx[f"belt_{d}_driver"]].n
            for role, t in (("driver", teeth[0]), ("driven", teeth[1])):
                j = next((i for i, p in enumerate(pl) if p.teeth == t), 0)
                # spread the system's pulleys over the whole dimension (n_p slots)
                x[idx[f"belt_{d}_{role}"]] = (j + 0.5) / len(pl) if n_p else 0.5
            if design is None:
                design = self.build(values)
            feas = self.feasible(design.spec, d, values, s.id, str(values.get(f"belt_{d}_pulleys")))
            li = next((i for i, e in enumerate(feas[0]) if e.id == values.get(f"belt_{d}_length")), 0)
            x[idx[f"belt_{d}_length"]] = (li + 0.5) / max(1, len(feas[0]))
        sp = self.pr.springs
        if sp:
            for s in sp.sites:
                b = self.spring_base[s]
                if f"spring_{s}" in idx:
                    x[idx[f"spring_{s}"]] = _x(int(bool(values.get(f"spring_{s}", False))), 2)
                kf = float(values.get(f"spring_{s}_k", b["k"])) / (b["k"] or 1.0)
                x[idx[f"spring_{s}_k"]] = _x(int(np.argmin([abs(kf - f) for f in sp.k_factors])), len(sp.k_factors))
                x[idx[f"spring_{s}_preload"]] = _x(sp.preload_factors.index(1.0) if 1.0 in sp.preload_factors else 0,
                                                   len(sp.preload_factors))
                for f, kind in ANCHORS[s]:
                    steps = sp.along_steps_mm if kind == "along" else sp.normal_steps_mm
                    dv = float(values.get(f"spring_{s}_{f}", b[f])) - b[f]
                    x[idx[f"spring_{s}_{f}"]] = _x(int(np.argmin([abs(dv - t) for t in steps])), len(steps))
        out = list(x)
        return np.asarray(out, dtype=float)

    # ------------------------------------------------------------------ the feasible lengths of a drive
    def feasible(self, spec: Any, drive: str, values: dict[str, Any], system_id: str, pair_id: str,
                 stifle_choice: Any = None) -> tuple[list[Any], str]:
        """The system's listed lengths that pass every belt check of ``drive`` on this body (shortest first), and a
        summary of why the others fail."""
        from calflab.mech.belts import BeltChoice, DriveLayout, DriveReport, evaluate_drive
        from calflab.morphology.feral import ry, stifle_clearance_check

        fer = spec.metadata.get("feral") or {}
        drives = fer.get("belt_drives") or {}
        if drive not in drives:
            return [], f"the {drive} is not belted on this body"
        layout = DriveLayout.model_validate(drives[drive]["layout"])
        extra = None
        if drive == "hock":
            sw: dict[str, Any] = fer.get("sweep") or {}
            st_choice = stifle_choice or BeltChoice.model_validate(drives["stifle"]["choice"])
            st_rep = evaluate_drive(self.cat, DriveLayout.model_validate(drives["stifle"]["layout"]), st_choice)

            def extra(rep: DriveReport) -> list[Any]:
                return [stifle_clearance_check(rep, st_rep, ry(sw["rel_stifle_deg"]), tuple(sw["stifle_range"]),
                                               sw["tibia_mm"], sw["servo_len"], sw["servo_width"], sw["bracket"],
                                               sw["clearance"], sw["offset_known"])]
        ok: list[Any] = []
        fails: dict[str, int] = {}
        for e in self.lengths.get(system_id, []):
            rep = evaluate_drive(self.cat, layout, BeltChoice(system=system_id, pulleys=pair_id, length=e.id), extra)
            if rep.ok:
                ok.append(e)
            else:
                for c in rep.checks:
                    if c.status == "fail":
                        fails[c.label] = fails.get(c.label, 0) + 1
        why = "; ".join(f"{k} ({v})" for k, v in sorted(fails.items(), key=lambda kv: -kv[1]))
        return ok, why

    # ------------------------------------------------------------------ decode
    def pair_id(self, system_id: str, driver: Any, driven: Any) -> str:
        """The catalog's own pair id when it has these teeth (today's bodies stay bit-identical), else
        ``<driver>+<driven>``."""
        for p in self.cat.pairs:
            if p.pitch_mm == driver.pitch_mm and p.driver_teeth == driver.teeth and p.driven_teeth == driven.teeth:
                return str(p.id)
        return self.cat.pair_of(driver.id, driven.id)

    def realise(self, x: np.ndarray, base: dict[str, Any]) -> tuple[dict[str, Any], Any, list[str], dict[str, Any]]:
        """(gene values, built design or None, rejection reasons, extra report) of a vector."""
        from calflab.mech.belts import BeltChoice

        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        v = dict(base)
        reasons: list[str] = []
        for k, d in enumerate(self.dims):
            name = d.name
            if name in self.geo:
                v[name] = self.geo[name][_i(x[k], d.n)]
            elif name in self.servo_genes:
                v[name] = self.hw.servo_choices[_i(x[k], d.n)]
            elif name == "shoulder_belt":
                v[name] = bool(_i(x[k], 2))
        # ratios
        g = self.pr.geometry
        if g:
            for num, den in g.ratios:
                r0 = float(self.start[num]) / float(self.start[den])
                r = float(v[num]) / float(v[den])
                if abs(r / r0 - 1.0) > g.ratio_tolerance + 1e-9:
                    reasons.append(f"ratio {num.replace('_length', '')}/{den.replace('_length', '')} {r:.3f} is "
                                   f"{(r / r0 - 1) * 100:+.1f}% from the starting {r0:.3f} (allowed "
                                   f"+-{g.ratio_tolerance * 100:g}%)")
        # springs (anchors and rates; free lengths need the built body)
        idx = {d.name: i for i, d in enumerate(self.dims)}
        sp = self.pr.springs
        preload: dict[str, float] = {}
        if sp:
            for s in sp.sites:
                b = self.spring_base[s]
                if f"spring_{s}" in idx:
                    v[f"spring_{s}"] = bool(_i(x[idx[f"spring_{s}"]], 2))
                v[f"spring_{s}_k"] = round(b["k"] * sp.k_factors[_i(x[idx[f"spring_{s}_k"]], len(sp.k_factors))], 4)
                preload[s] = sp.preload_factors[_i(x[idx[f"spring_{s}_preload"]], len(sp.preload_factors))]
                for f, kind in ANCHORS[s]:
                    steps = sp.along_steps_mm if kind == "along" else sp.normal_steps_mm
                    v[f"spring_{s}_{f}"] = round(b[f] + steps[_i(x[idx[f"spring_{s}_{f}"]], len(steps))], 3)
        # belts: system and pulleys; a placeholder length (any listed one) until the body says which pass
        picks: dict[str, tuple[Any, str, float]] = {}
        for drive in self.drives:
            s = self.systems[_i(x[idx[f"belt_{drive}_system"]], len(self.systems))]
            pl = self.pulleys[s.id]
            a = pl[_i(x[idx[f"belt_{drive}_driver"]], len(pl))]
            b2 = pl[_i(x[idx[f"belt_{drive}_driven"]], len(pl))]
            pid = self.pair_id(s.id, a, b2)
            v[f"belt_{drive}_system"], v[f"belt_{drive}_pulleys"] = s.id, pid
            lens = self.lengths[s.id]
            cur = v.get(f"belt_{drive}_length")
            if cur not in {e.id for e in lens}:
                v[f"belt_{drive}_length"] = lens[len(lens) // 2].id
            picks[drive] = (s, pid, float(x[idx[f"belt_{drive}_length"]]))
        if reasons:
            return v, None, reasons, {}
        d1 = self.build(v)
        fer = d1.spec.metadata.get("feral") or {}
        belted = set(fer.get("belted") or [])
        feas_n: dict[str, int] = {}
        stifle_choice = None
        for drive in self.drives:
            if drive not in belted:
                continue
            s, pid, xl = picks[drive]
            ok, why = self.feasible(d1.spec, drive, v, s.id, pid, stifle_choice)
            feas_n[drive] = len(ok)
            if not ok:
                reasons.append(f"{drive}: no listed {s.id} length passes the belt checks with {pid} on this body "
                               f"({len(self.lengths[s.id])} listed; failing: {why})")
                continue
            e = ok[_i(xl, len(ok))]
            v[f"belt_{drive}_length"] = e.id
            if drive == "stifle":
                stifle_choice = BeltChoice(system=s.id, pulleys=pid, length=e.id)
        if reasons:
            return v, None, reasons, {"feasible_lengths": feas_n}
        # free lengths from the standing length of this body
        if sp:
            st = standing_lengths(d1.spec)
            for s in sp.sites:
                if not v.get(f"spring_{s}", False):
                    continue
                leg = "fl" if s in ("shoulder", "carpus") else "hl"
                L = st.get(f"spring.{leg}.{s}")
                if L is None:
                    continue
                free = round(L - preload[s] * self.spring_base[s]["ext"], 1)
                gene = self.gdef.gene(f"spring_{s}_free_length")
                if not (float(gene.min) <= free <= float(gene.max)):
                    reasons.append(f"{s} spring: free length {free:g} mm outside {gene.min:g}-{gene.max:g} mm")
                v[f"spring_{s}_free_length"] = free
        if reasons:
            return v, None, reasons, {"feasible_lengths": feas_n}
        d2 = self.build(v)
        sreasons, srep = spring_checks(d2.spec, v, sp) if sp else ([], {})
        return v, d2, sreasons, {"feasible_lengths": feas_n, "springs": srep}


def spring_sites_added(values: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    """Spring sites on in this body that are off in the starting body."""
    base = (baseline or {}).get("spring_sites") or []
    return [s for s in SITES if bool(values.get(f"spring_{s}", False)) and s not in base]
