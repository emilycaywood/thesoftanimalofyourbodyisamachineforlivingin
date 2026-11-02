"""Belt drives built only from catalog entries (ADR-063, ADR-064).

A belt drive is three discrete references: a belt system, a pulley pair and a
belt length entry, all from the project's catalog (``catalog/belt_systems.json``,
``belt_lengths.json``, ``pulleys.json``). Everything else is derived from them:

* pitch diameter ``D = teeth x pitch / pi``;
* centre distance ``C`` from the belt pitch length ``L``::

      b = 2 L - pi (D1 + D2)
      C = (b + sqrt(b^2 - 8 (D2 - D1)^2)) / 8

* the driver servo's output axis sits at ``C`` from the driven joint axis,
  along the segment that carries the servo.

Nothing may set ``C`` or the servo position directly: no slider, field, drag,
fit or optimizer. A different ``C`` means a different catalog entry. A choice
that fails a check is rejected with the reason, never clamped. The physical
tensioning slot is a build tolerance that is reported, never used to reach a
geometry (``tension_travel_mm``).

Units: mm, N, degrees. D1 is the driver (servo) pulley, D2 the driven pulley.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from calflab import units as u

Status = Literal["pass", "fail", "unknown"]
CATALOG_FILES = ("belt_systems.json", "belt_lengths.json", "pulleys.json")


class CatalogError(ValueError):
    """The catalog files are missing or invalid, or a reference names nothing."""


class BeltChoiceError(ValueError):
    """A belt drive choice that fails a check. The message says which and why."""


# ====================================================================== geometry
def pitch_diameter(teeth: int, pitch_mm: float) -> float:
    """Pitch diameter (mm) of a toothed pulley: teeth x pitch / pi."""
    return teeth * pitch_mm / math.pi


def center_distance(length_mm: float, d1_mm: float, d2_mm: float) -> float:
    """Centre distance (mm) of an open two-pulley belt of pitch length ``length_mm``.

    ``b = 2L - pi (D1 + D2)``; ``C = (b + sqrt(b^2 - 8 (D2 - D1)^2)) / 8``.
    Raises ``ValueError`` when the belt is too short to go round both pulleys.
    """
    b = 2.0 * length_mm - math.pi * (d1_mm + d2_mm)
    disc = b * b - 8.0 * (d2_mm - d1_mm) ** 2
    if b <= 0 or disc < 0:
        raise ValueError(f"A {length_mm:g} mm belt is too short for pulleys of {d1_mm:.2f} and {d2_mm:.2f} mm")
    return (b + math.sqrt(disc)) / 8.0


def wrap_angle_driver(d1_mm: float, d2_mm: float, c_mm: float) -> float:
    """Wrap angle on the driver (smaller) pulley, radians: pi - 2 asin((D2 - D1) / 2C)."""
    return math.pi - 2.0 * math.asin((d2_mm - d1_mm) / (2.0 * c_mm))


def teeth_in_mesh(driver_teeth: int, wrap_rad: float) -> float:
    """Teeth engaged on the driver: driver teeth x wrap / 2 pi."""
    return driver_teeth * wrap_rad / (2.0 * math.pi)


def belt_tension_n(servo_torque_nm: float, d1_mm: float) -> float:
    """Effective belt pull (N) for a servo output torque (N*m): T = torque / (D1 / 2)."""
    return abs(servo_torque_nm) / u.mm_to_m(d1_mm / 2.0)


# ====================================================================== catalog
class BeltSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    profile: str = "GT2"
    pitch_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    construction: str | None = None
    #: None = not known (a required value still to be supplied): shown as "unknown", never guessed
    allowable_working_tension_n: float | None
    allowable_working_tension_derivation: str = ""
    breaking_strength_n: float | None
    breaking_strength_derivation: str = ""
    #: sources in belt_lengths.json whose lengths are confirmed in this system's width
    length_sources: list[str]
    sources: list[str] = []
    notes: str = ""

    @property
    def label(self) -> str:
        return f"{self.id} ({self.pitch_mm:g} mm pitch, {self.width_mm:g} mm wide)"


class LengthSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    pitch_mm: float
    widths_mm: list[float] | None
    construction: str | None = None
    url: str = ""
    range_note: str = ""
    listings: list[str] = []


class BeltLength(BaseModel):
    """One stock closed-loop belt. Its pitch length is a whole number of teeth."""

    model_config = ConfigDict(extra="forbid")

    id: str
    pitch_mm: float = Field(gt=0)
    pitch_length_mm: float = Field(gt=0)
    teeth: int | None = None
    source: str
    listings: list[str] = []
    purchase_confirmed: bool = False

    @model_validator(mode="after")
    def _whole_teeth(self) -> BeltLength:
        n = self.pitch_length_mm / self.pitch_mm
        if abs(n - round(n)) > 1e-9:
            raise ValueError(
                f"belt length {self.id!r}: {self.pitch_length_mm:g} mm is not a whole number of "
                f"{self.pitch_mm:g} mm teeth ({n:.3f})"
            )
        if self.teeth is not None and self.teeth != round(n):
            raise ValueError(f"belt length {self.id!r}: {self.teeth} teeth does not match {self.pitch_length_mm:g} mm")
        self.teeth = round(n)
        return self


class PulleyPair(BaseModel):
    """A discrete pair of standard pulleys. Pitch diameters are computed, never entered."""

    model_config = ConfigDict(extra="forbid")

    id: str
    driver_teeth: int = Field(gt=0)
    driven_teeth: int = Field(gt=0)
    pitch_mm: float = Field(gt=0)
    #: required values still to be entered (None = not entered: counted as 0 g and listed)
    driver_mass_g: float | None = None
    driven_mass_g: float | None = None

    @property
    def ratio(self) -> float:
        """Joint torque / servo torque (before efficiency); servo angle / joint angle."""
        return self.driven_teeth / self.driver_teeth

    @property
    def d1_mm(self) -> float:
        return pitch_diameter(self.driver_teeth, self.pitch_mm)

    @property
    def d2_mm(self) -> float:
        return pitch_diameter(self.driven_teeth, self.pitch_mm)

    @property
    def label(self) -> str:
        return (f"{self.driver_teeth}T / {self.driven_teeth}T ({self.pitch_mm:g} mm pitch, {self.ratio:g}:1, "
                f"D1 {self.d1_mm:.3f} / D2 {self.d2_mm:.3f} mm)")


class _SystemsFile(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: str
    systems: list[BeltSystem]


class _LengthsFile(BaseModel):
    model_config = ConfigDict(extra="allow")
    sources: list[LengthSource]
    lengths: list[BeltLength]


class _PulleysFile(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: str
    pairs: list[PulleyPair]


class BeltChoice(BaseModel):
    """The only things a belt drive stores: three catalog references."""

    model_config = ConfigDict(extra="forbid")

    system: str
    pulleys: str
    length: str


class BeltCatalog(BaseModel):
    systems: list[BeltSystem]
    default_system: str
    sources: list[LengthSource]
    lengths: list[BeltLength]
    pairs: list[PulleyPair]
    default_pair: str
    origin: str = ""  # where it was read from

    @model_validator(mode="after")
    def _refs(self) -> BeltCatalog:
        problems: list[str] = []
        for group, items in (("belt system", self.systems), ("length source", self.sources),
                             ("belt length", self.lengths), ("pulley pair", self.pairs)):
            seen: set[str] = set()
            for it in items:
                if it.id in seen:
                    problems.append(f"duplicate {group} id {it.id!r}")
                seen.add(it.id)
        src = {s.id: s for s in self.sources}
        for s in self.systems:
            for ref in s.length_sources:
                if ref not in src:
                    problems.append(f"belt system {s.id!r} names length source {ref!r}, which is not in belt_lengths.json")
        for e in self.lengths:
            if e.source not in src:
                problems.append(f"belt length {e.id!r} names source {e.source!r}, which is not listed")
            elif src[e.source].pitch_mm != e.pitch_mm:
                problems.append(f"belt length {e.id!r}: pitch {e.pitch_mm:g} mm differs from its source's")
        if self.default_system not in {s.id for s in self.systems}:
            problems.append(f"default belt system {self.default_system!r} is not in the catalog")
        if self.default_pair not in {p.id for p in self.pairs}:
            problems.append(f"default pulley pair {self.default_pair!r} is not in the catalog")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, directory: Path) -> BeltCatalog:
        """Read the three catalog files from ``directory``. Every problem is reported at once."""
        directory = Path(directory)
        data: dict[str, Any] = {}
        problems: list[str] = []
        for name in CATALOG_FILES:
            p = directory / name
            if not p.is_file():
                problems.append(f"{name} is missing")
                continue
            try:
                data[name] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"{name} is not valid JSON: {exc}")
        if problems:
            raise CatalogError(f"Belt catalog in {directory}: {'; '.join(problems)}")
        return cls.from_dict(data, origin=str(directory))

    @classmethod
    def from_dict(cls, data: dict[str, Any], origin: str = "") -> BeltCatalog:
        """Build from the parsed files (keys = file names); errors name the file and entry."""
        problems: list[str] = []
        parsed: dict[str, Any] = {}
        for name, model in (("belt_systems.json", _SystemsFile), ("belt_lengths.json", _LengthsFile),
                            ("pulleys.json", _PulleysFile)):
            try:
                parsed[name] = model.model_validate(data.get(name) or {})
            except ValidationError as exc:
                for err in exc.errors():
                    where = ".".join(str(x) for x in err["loc"])
                    problems.append(f"{name} {where}: {err['msg']}")
        if problems:
            raise CatalogError(f"Belt catalog {origin}: {'; '.join(problems)}")
        s, ln, p = parsed["belt_systems.json"], parsed["belt_lengths.json"], parsed["pulleys.json"]
        try:
            return cls(systems=s.systems, default_system=s.default, sources=ln.sources, lengths=ln.lengths,
                       pairs=p.pairs, default_pair=p.default, origin=origin)
        except ValidationError as exc:
            raise CatalogError(f"Belt catalog {origin}: {exc.errors()[0]['msg']}") from exc

    def digest(self) -> str:
        """SHA-256 of the catalog content (recorded with designs and runs)."""
        body = self.model_dump(mode="json", exclude={"origin"})
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    # ---------------------------------------------------------------- lookup
    def system(self, system_id: str) -> BeltSystem:
        for s in self.systems:
            if s.id == system_id:
                return s
        raise CatalogError(f"Unknown belt system {system_id!r}. Choose one of: {', '.join(x.id for x in self.systems)}")

    def pair(self, pair_id: str) -> PulleyPair:
        for p in self.pairs:
            if p.id == pair_id:
                return p
        raise CatalogError(f"Unknown pulley pair {pair_id!r}. Choose one of: {', '.join(x.id for x in self.pairs)}")

    def length(self, length_id: str) -> BeltLength:
        for e in self.lengths:
            if e.id == length_id:
                return e
        raise CatalogError(f"Unknown belt length entry {length_id!r}")

    def source(self, source_id: str) -> LengthSource:
        return next(s for s in self.sources if s.id == source_id)

    def pairs_for(self, system: BeltSystem) -> list[PulleyPair]:
        """Pulley pairs of the system's pitch."""
        return [p for p in self.pairs if p.pitch_mm == system.pitch_mm]

    def lengths_for(self, system: BeltSystem) -> list[BeltLength]:
        """Every length of the system's pitch, selectable or not, shortest first."""
        return sorted((e for e in self.lengths if e.pitch_mm == system.pitch_mm), key=lambda e: (e.pitch_length_mm, e.source))

    def length_status(self, system: BeltSystem, entry: BeltLength) -> tuple[bool, str]:
        """(selectable, reason). A length is offered only when its source covers the system's width."""
        if entry.pitch_mm != system.pitch_mm:
            return False, f"{entry.pitch_mm:g} mm pitch, the system is {system.pitch_mm:g} mm"
        if entry.source not in system.length_sources:
            src = self.source(entry.source)
            widths = "/".join(f"{w:g}" for w in src.widths_mm or []) or "unstated"
            return False, f"width unconfirmed: source {entry.source} ({src.label}) lists {widths} mm, the system is {system.width_mm:g} mm"
        return True, ""


_CACHE: dict[str, tuple[tuple[tuple[str, float], ...], BeltCatalog]] = {}


def _stamp(directory: Path) -> tuple[tuple[str, float], ...]:
    return tuple((n, (directory / n).stat().st_mtime) for n in CATALOG_FILES if (directory / n).is_file())


def load_catalog(project_dir: Path | None) -> tuple[BeltCatalog, str]:
    """The project's belt catalog (``<project>/catalog``), or the repository's
    template (``config/belts``) when the project has none. Returns the catalog
    and a note that is non-empty when the template stood in. Re-read when a
    file changes; invalid files raise ``CatalogError`` naming every problem."""
    from calflab.paths import config_dir

    note = ""
    directory = Path(project_dir) / "catalog" if project_dir is not None else None
    if directory is None or not all((directory / n).is_file() for n in CATALOG_FILES):
        note = ("the repository's belt catalog (config/belts) is in use: "
                + ("this build has no project folder" if directory is None else f"{directory} has no belt catalog"))
        directory = config_dir() / "belts"
    stamp = _stamp(directory)
    hit = _CACHE.get(str(directory))
    if hit is None or hit[0] != stamp:
        hit = (stamp, BeltCatalog.load(directory))
        _CACHE[str(directory)] = hit
    return hit[1], note


# ====================================================================== drive layout and checks
class DriveTarget(BaseModel):
    """What the default choice aims for: a centre distance or a belt length (mm)."""

    kind: Literal["C", "L"] = "C"
    value: float
    low: float | None = None  # a window the value must lie in (C only)
    high: float | None = None
    note: str = ""


class DriveLayout(BaseModel):
    """Where a belt drive sits, along the segment that carries its driver servo (mm).

    Distances are measured along the segment from the driven joint axis. The
    servo body may occupy ``[near_limit_mm, far_limit_mm]``: the near limit is
    the driven end's joint fitting plus clearance, the far limit the other
    end's (or, for a servo in the hip block, the end of the block).
    """

    drive: str  # "stifle", "hock", "carpus"
    joint_label: str
    segment: str  # body carrying the servo
    segment_length_mm: float
    near_limit_mm: float
    far_limit_mm: float
    servo_length_mm: float  # case length along the segment
    servo_width_mm: float  # case width across the segment, in the plane of the leg
    #: output axis to the nearer case end, along the case length; None = not entered (checks needing it are "unknown")
    output_axis_offset_mm: float | None = None
    pulley_clearance_mm: float = 3.0
    min_teeth_in_mesh: float = 6.0
    tension_travel_mm: float = 3.0
    target: DriveTarget


class Check(BaseModel):
    id: str
    label: str
    status: Status
    detail: str = ""


class DriveReport(BaseModel):
    """Everything derived from one belt choice. Read-only: nothing here is an input."""

    drive: str
    joint_label: str
    choice: BeltChoice
    system_label: str
    pitch_mm: float
    width_mm: float
    length_mm: float
    belt_teeth: int
    length_source: str
    length_selectable: bool
    length_reason: str
    purchase_confirmed: bool
    driver_teeth: int
    driven_teeth: int
    ratio: float
    d1_mm: float
    d2_mm: float
    c_mm: float | None
    #: servo output axis: from the driven joint axis (= C) and from the segment's other joint axis
    servo_axis_from_driven_mm: float | None
    servo_axis_from_far_mm: float | None
    #: the servo case along the segment (from the driven axis): as placed, or the bounds it may take if the offset is unknown
    servo_span_mm: tuple[float, float] | None
    wrap_deg: float | None
    teeth_in_mesh: float | None
    tension_travel_mm: float
    c_with_travel_mm: tuple[float, float] | None
    allowable_working_tension_n: float | None
    breaking_strength_n: float | None
    checks: list[Check]
    ok: bool  # no check failed (an "unknown" check does not fail)
    unknown: list[str] = []  # labels of checks that could not be decided


def _servo_fit(layout: DriveLayout, c: float) -> tuple[Status, str, tuple[float, float]]:
    """Does the servo case lie between the near and far limits with its axis at ``c``?

    With the output-axis offset known, the case is placed in whichever
    orientation fits (shaft end toward or away from the driven joint). Unknown:
    it surely fits if it fits for every offset (``max room >= length`` and
    ``min room >= length / 2``), surely does not if the window is shorter than
    the case; otherwise unknown.
    """
    ls = layout.servo_length_mm
    room_down, room_up = c - layout.near_limit_mm, layout.far_limit_mm - c
    o = layout.output_axis_offset_mm
    window = f"window {layout.near_limit_mm:.1f}-{layout.far_limit_mm:.1f} mm from the {layout.joint_label} axis"
    if o is not None:
        spans = [(c - o, c + ls - o), (c - (ls - o), c + o)]
        best = max(spans, key=lambda s: min(s[0] - layout.near_limit_mm, layout.far_limit_mm - s[1]))
        fits = best[0] >= layout.near_limit_mm and best[1] <= layout.far_limit_mm
        detail = f"case {best[0]:.1f}-{best[1]:.1f} mm, {window}"
        return ("pass" if fits else "fail"), detail, best
    span = (c - ls, c + ls)
    if room_down < 0 or room_up < 0 or room_down + room_up < ls:
        return "fail", f"the {ls:g} mm case cannot fit with its axis at {c:.1f} mm ({window})", (c - ls / 2, c + ls / 2)
    if max(room_down, room_up) >= ls and min(room_down, room_up) >= ls / 2:
        return "pass", f"fits for any output-axis position ({window})", span
    return ("unknown",
            f"fits only for some output-axis positions on the case: enter servo.output_axis_offset_mm ({window}; "
            f"room {room_down:.1f} mm toward the {layout.joint_label}, {room_up:.1f} mm away)", span)


ExtraChecks = Callable[["DriveReport"], list[Check]]


def evaluate_drive(
    catalog: BeltCatalog, layout: DriveLayout, choice: BeltChoice, extra: ExtraChecks | None = None
) -> DriveReport:
    """Derive C and the servo position from a choice and run every check.
    Unknown ids raise ``CatalogError``; failed checks are reported, not raised.
    ``extra`` adds checks that need more than this drive (e.g. the hock servo
    against the stifle belt through the stifle's range); it runs only when C exists."""
    system = catalog.system(choice.system)
    pair = catalog.pair(choice.pulleys)
    entry = catalog.length(choice.length)
    selectable, reason = catalog.length_status(system, entry)
    checks: list[Check] = []
    d1, d2 = pair.d1_mm, pair.d2_mm
    checks.append(Check(id="pitch", label="Pulleys match the belt pitch",
                        status="pass" if pair.pitch_mm == system.pitch_mm else "fail",
                        detail=f"pulleys {pair.pitch_mm:g} mm, belt {system.pitch_mm:g} mm"))
    checks.append(Check(id="length_source", label="Length offered in this belt's width",
                        status="pass" if selectable else "fail", detail=reason or f"source {entry.source}"))
    c: float | None
    try:
        c = center_distance(entry.pitch_length_mm, d1, d2)
    except ValueError as exc:
        c = None
        checks.append(Check(id="geometry", label="Belt goes round both pulleys", status="fail", detail=str(exc)))
    wrap = tim = None
    span = None
    if c is not None:
        need = (d1 + d2) / 2.0 + layout.pulley_clearance_mm
        checks.append(Check(id="pulley_gap", label="Pulleys do not touch",
                            status="pass" if c > need else "fail",
                            detail=f"C {c:.1f} mm, needs more than (D1 + D2) / 2 + {layout.pulley_clearance_mm:g} = {need:.1f} mm"))
        wrap = wrap_angle_driver(d1, d2, c)
        tim = teeth_in_mesh(pair.driver_teeth, wrap)
        checks.append(Check(id="teeth_in_mesh", label=f"At least {layout.min_teeth_in_mesh:g} teeth in mesh on the driver",
                            status="pass" if tim >= layout.min_teeth_in_mesh else "fail",
                            detail=f"{tim:.1f} teeth (wrap {u.rad_to_deg(wrap):.1f} deg on {pair.driver_teeth}T)"))
        status, detail, span = _servo_fit(layout, c)
        checks.append(Check(id="servo_on_segment", label="Servo case on its segment, clear of both joint fittings",
                            status=status, detail=detail))
    report = DriveReport(
        drive=layout.drive,
        joint_label=layout.joint_label,
        choice=choice,
        system_label=system.label,
        pitch_mm=system.pitch_mm,
        width_mm=system.width_mm,
        length_mm=entry.pitch_length_mm,
        belt_teeth=int(entry.teeth or 0),
        length_source=entry.source,
        length_selectable=selectable,
        length_reason=reason,
        purchase_confirmed=entry.purchase_confirmed,
        driver_teeth=pair.driver_teeth,
        driven_teeth=pair.driven_teeth,
        ratio=pair.ratio,
        d1_mm=d1,
        d2_mm=d2,
        c_mm=c,
        servo_axis_from_driven_mm=c,
        servo_axis_from_far_mm=(layout.segment_length_mm - c) if c is not None else None,
        servo_span_mm=span,
        wrap_deg=u.rad_to_deg(wrap) if wrap is not None else None,
        teeth_in_mesh=tim,
        tension_travel_mm=layout.tension_travel_mm,
        c_with_travel_mm=(c - layout.tension_travel_mm, c + layout.tension_travel_mm) if c is not None else None,
        allowable_working_tension_n=system.allowable_working_tension_n,
        breaking_strength_n=system.breaking_strength_n,
        checks=checks,
        ok=True,
    )
    if extra is not None and c is not None:
        report.checks.extend(extra(report))
    report.ok = all(ch.status != "fail" for ch in report.checks)
    report.unknown = [ch.label for ch in report.checks if ch.status == "unknown"]
    return report


def rejection(report: DriveReport) -> str:
    """The message for a rejected choice: every failed check with its numbers."""
    failed = [f"{ch.label}: {ch.detail}" for ch in report.checks if ch.status == "fail"]
    c = f"{report.c_mm:.1f} mm" if report.c_mm is not None else "none"
    return (f"Belt drive at the {report.joint_label} rejected ({report.choice.system}, {report.choice.pulleys}, "
            f"{report.choice.length}; C = {c}): " + "; ".join(failed))


def validate_drive(
    catalog: BeltCatalog, layout: DriveLayout, choice: BeltChoice, extra: ExtraChecks | None = None
) -> DriveReport:
    """``evaluate_drive``, raising ``BeltChoiceError`` if any check fails."""
    report = evaluate_drive(catalog, layout, choice, extra)
    if not report.ok:
        raise BeltChoiceError(rejection(report))
    return report


def choose_default(
    catalog: BeltCatalog,
    layout: DriveLayout,
    system_id: str | None = None,
    pair_id: str | None = None,
    extra: ExtraChecks | None = None,
) -> tuple[BeltChoice | None, DriveReport | None, str]:
    """The selectable length whose derived C (or length) is closest to the
    layout's target while passing every check. (None, None, why) if none does."""
    system = catalog.system(system_id or catalog.default_system)
    pair = catalog.pair(pair_id or catalog.default_pair)
    best: tuple[float, BeltChoice, DriveReport] | None = None
    tried = 0
    t = layout.target
    for entry in catalog.lengths_for(system):
        if not catalog.length_status(system, entry)[0]:
            continue
        tried += 1
        choice = BeltChoice(system=system.id, pulleys=pair.id, length=entry.id)
        rep = evaluate_drive(catalog, layout, choice, extra)
        if not rep.ok or rep.c_mm is None:
            continue
        if t.kind == "C":
            if (t.low is not None and rep.c_mm < t.low) or (t.high is not None and rep.c_mm > t.high):
                continue
            err = abs(rep.c_mm - t.value)
        else:
            err = abs(rep.length_mm - t.value)
        if best is None or err < best[0]:
            best = (err, choice, rep)
    if best is None:
        why = (f"no length of {system.id} is offered in its width" if tried == 0
               else f"none of the {tried} lengths offered for {system.id} with {pair.id} passes every check"
               + (f" within C {t.low:g}-{t.high:g} mm" if t.kind == "C" and t.low is not None and t.high is not None else ""))
        return None, None, why
    return best[1], best[2], ""


def drive_options(
    catalog: BeltCatalog, layout: DriveLayout, choice: BeltChoice, extra: ExtraChecks | None = None
) -> dict[str, Any]:
    """What the three dropdowns of one drive offer, with every option's derived
    values and check result for the current system and pulley pair."""
    system = catalog.system(choice.system)
    pair_ok = [p.id for p in catalog.pairs_for(system)]
    systems = []
    for s in catalog.systems:
        n_sel = sum(1 for e in catalog.lengths_for(s) if catalog.length_status(s, e)[0])
        systems.append({
            "id": s.id, "label": s.label, "pitch_mm": s.pitch_mm, "width_mm": s.width_mm,
            "allowable_working_tension_n": s.allowable_working_tension_n,
            "breaking_strength_n": s.breaking_strength_n, "lengths_offered": n_sel,
            "pulley_pairs": len(catalog.pairs_for(s)), "notes": s.notes,
            "usable": n_sel > 0 and bool(catalog.pairs_for(s)),
            "why_not": "" if n_sel and catalog.pairs_for(s) else
            ("no lengths confirmed in this width" if not n_sel else f"no {s.pitch_mm:g} mm pitch pulley pair in pulleys.json"),
        })
    pairs = [{"id": p.id, "label": p.label, "ratio": p.ratio, "d1_mm": p.d1_mm, "d2_mm": p.d2_mm,
              "usable": p.id in pair_ok,
              "masses_missing": [k for k in ("driver_mass_g", "driven_mass_g") if getattr(p, k) is None]}
             for p in catalog.pairs]
    lengths = []
    for e in catalog.lengths_for(system):
        selectable, reason = catalog.length_status(system, e)
        row: dict[str, Any] = {
            "id": e.id, "length_mm": e.pitch_length_mm, "teeth": e.teeth, "source": e.source,
            "source_label": catalog.source(e.source).label, "listings": e.listings,
            "purchase_confirmed": e.purchase_confirmed, "selectable": selectable, "reason": reason,
            "c_mm": None, "ok": False, "failed": [], "unknown": [],
        }
        if choice.pulleys in pair_ok and selectable:
            rep = evaluate_drive(catalog, layout, BeltChoice(system=system.id, pulleys=choice.pulleys, length=e.id), extra)
            row.update(c_mm=rep.c_mm, ok=rep.ok,
                       failed=[c.label for c in rep.checks if c.status == "fail" and c.id != "length_source"],
                       unknown=rep.unknown)
        elif choice.pulleys in pair_ok:  # not offered in this width: its C is shown, its checks are not run
            pair = catalog.pair(choice.pulleys)
            try:
                row["c_mm"] = center_distance(e.pitch_length_mm, pair.d1_mm, pair.d2_mm)
            except ValueError:
                pass
        lengths.append(row)
    return {"systems": systems, "pairs": pairs, "lengths": lengths}


# ====================================================================== clearance through a joint's range
def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _inside(poly: list[tuple[float, float]], p: tuple[float, float]) -> bool:
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0:
            return False
    return True


def _seg_dist(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def polygon_gap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Distance (mm) between two convex polygons (counter-clockwise); <= 0 when they overlap."""
    if any(_inside(a, p) for p in b) or any(_inside(b, p) for p in a):
        return 0.0
    best = math.inf
    for P, Q in ((a, b), (b, a)):
        for p in P:
            for i in range(len(Q)):
                best = min(best, _seg_dist(p, Q[i], Q[(i + 1) % len(Q)]))
    return best


def belt_envelope(c_mm: float, d1_mm: float, d2_mm: float, direction: tuple[float, float], n: int = 48) -> list[tuple[float, float]]:
    """2D convex outline of an open belt round a driven pulley at the origin
    (pitch diameter D2) and a driver at ``C`` along ``direction`` (D1)."""
    ux, uy = direction
    pts: list[tuple[float, float]] = []
    for k in range(n):
        a = 2 * math.pi * k / n
        pts.append((d2_mm / 2 * math.cos(a), d2_mm / 2 * math.sin(a)))
        pts.append((c_mm * ux + d1_mm / 2 * math.cos(a), c_mm * uy + d1_mm / 2 * math.sin(a)))
    return _convex_hull(pts)


def rectangle(s0: float, s1: float, half_width: float, axis: tuple[float, float]) -> list[tuple[float, float]]:
    """A rectangle from ``s0`` to ``s1`` along unit ``axis`` (from the origin), ``half_width`` either side."""
    ax, ay = axis
    nx, ny = -ay, ax
    corners = [(s0, -half_width), (s1, -half_width), (s1, half_width), (s0, half_width)]
    return _convex_hull([(s * ax + w * nx, s * ay + w * ny) for s, w in corners])


class SweepResult(BaseModel):
    status: Status
    detail: str
    min_gap_mm: float | None  # with the case placed most favourably (offset unknown) or as placed
    worst_angle_deg: float | None
    first_contact_deg: float | None = None  # first joint angle (from the start of the range) at which they touch
    samples: int = 0


def clearance_sweep(
    angles_deg: list[float],
    upper_dirs: list[tuple[float, float]],
    belt_c_mm: float,
    belt_d1_mm: float,
    belt_d2_mm: float,
    servo_axis: tuple[float, float],
    servo_spans: list[tuple[float, float]],
    servo_half_width_mm: float,
    clearance_mm: float,
    label: str,
) -> SweepResult:
    """Clearance between a servo case fixed in the lower segment and the belt
    of the joint above it, through that joint's range.

    Everything is in the lower segment's 2D frame (the plane of the leg), with
    the joint axis at the origin. ``upper_dirs[i]`` is the direction of the
    segment above (where that belt's driver sits) at ``angles_deg[i]``. The
    servo case lies along ``servo_axis`` from ``s0`` to ``s1`` mm; give several
    ``servo_spans`` when its placement is not known: the check then passes
    only if every span clears, fails if even the most favourable one does not.
    """
    gaps: list[list[float]] = []
    for d in upper_dirs:
        env = belt_envelope(belt_c_mm, belt_d1_mm, belt_d2_mm, d)
        gaps.append([polygon_gap(env, rectangle(s0, s1, servo_half_width_mm, servo_axis)) for s0, s1 in servo_spans])
    n_spans = len(servo_spans)
    worst_each = [min(g[k] for g in gaps) for k in range(n_spans)]

    def clear_limits(k: int) -> tuple[float | None, float | None]:
        """First angle above and below 0 (the standing pose) at which span ``k`` comes under the clearance."""
        up = next((angles_deg[i] for i in range(len(gaps)) if angles_deg[i] >= 0 and gaps[i][k] < clearance_mm), None)
        down = next((angles_deg[i] for i in reversed(range(len(gaps))) if angles_deg[i] <= 0 and gaps[i][k] < clearance_mm), None)
        return up, down

    # the most favourable placement: the largest worst gap, then the widest clear range around standing
    def score(k: int) -> tuple[float, float]:
        up, down = clear_limits(k)
        width = (up if up is not None else angles_deg[-1] + 1) - (down if down is not None else angles_deg[0] - 1)
        return (min(worst_each[k], clearance_mm), width)

    best_k = max(range(n_spans), key=score)
    best_gap = worst_each[best_k]
    all_ok = all(w >= clearance_mm for w in worst_each)
    worst_i = min(range(len(gaps)), key=lambda i: gaps[i][best_k])
    up, down = clear_limits(best_k)
    first = up if up is not None else down
    rng = f"{angles_deg[0]:.0f} to {angles_deg[-1]:.0f} deg"
    if all_ok:
        status: Status = "pass"
        detail = f"at least {min(worst_each):.1f} mm through {rng} (needs {clearance_mm:g} mm)"
    elif best_gap >= clearance_mm:
        status = "unknown"
        detail = (f"clears by {best_gap:.1f} mm through {rng} only for some positions of the output axis on the case; "
                  "enter servo.output_axis_offset_mm")
    else:
        status = "fail"
        where = []
        if up is not None:
            where.append(f"from {up:.0f} deg of flexion")
        if down is not None:
            where.append(f"from {down:.0f} deg (extension)")
        detail = (f"{label} comes within {clearance_mm:g} mm of the case "
                  + (" and ".join(where) if where else "throughout")
                  + f" even placed most favourably (closest {best_gap:.1f} mm at {angles_deg[worst_i]:.0f} deg); range {rng}")
    return SweepResult(status=status, detail=detail, min_gap_mm=round(best_gap, 2),
                       worst_angle_deg=angles_deg[worst_i], first_contact_deg=first, samples=len(angles_deg))
