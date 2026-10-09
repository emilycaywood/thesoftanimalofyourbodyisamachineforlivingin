"""Component library: actuators, sensors, boards, batteries, materials.

Data lives in ``config/components/*.yaml`` (and may be extended by
``ComponentProvider`` plugins). Every entry carries ``source`` and
``verified``; the code never invents a spec and never sets ``verified``.

No value is filled in silently (ADR-051):

* a required value that is missing (or ``null``) makes the entry *incomplete*:
  it is listed by the audit, cannot be selected and is not in the library;
* an optional value that is missing takes the model's default and the field
  is recorded in ``defaulted``;
* a value the researcher could not find on a datasheet is entered as a best
  guess and named in the entry's ``guessed:`` list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from calflab.paths import config_dir

Kind = Literal["actuator", "sensor", "board", "battery", "material"]


class Component(BaseModel):
    """Common fields. Units: g, mm, USD."""

    model_config = ConfigDict(extra="allow")

    key: str
    kind: Kind
    name: str
    manufacturer: str = ""
    mass_g: float = 0.0
    dims_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    cost_usd: float = 0.0
    url: str = ""
    source: str
    verified: bool = False
    notes: str = ""
    #: spec fields whose values are guesses, not datasheet values (written by the researcher)
    guessed: list[str] = []
    #: spec fields the entry does not give, so the default of this model is in use (set by the loader)
    defaulted: list[str] = []


#: fields that describe an entry rather than specify it
META_FIELDS = frozenset({
    "key", "kind", "name", "manufacturer", "url", "source", "verified", "notes", "guessed", "defaulted",
    "protocol", "type", "interface", "role", "color",
})
_NOT_FOR_MATERIAL = frozenset({"mass_g", "dims_mm", "cost_usd"})  # a material is bought by the kg
_SKIN_ONLY = frozenset({"areal_density_g_cm2", "joint_stiffness_nm_per_rad_per_mm", "joint_damping_nms_per_rad_per_mm"})


class ActuatorSpec(Component):
    """Torque N*m and speed rpm at the output shaft; thermal model is first order."""

    kind: Literal["actuator"] = "actuator"
    stall_torque_nm: float
    stall_current_a: float
    no_load_speed_rpm: float
    voltage_v: float
    gear_ratio: float = 1.0
    idle_current_a: float = 0.05
    armature_kgm2: float = 0.005
    winding_resistance_ohm: float = 1.0
    r_thermal_k_per_w: float = 5.0
    c_thermal_j_per_k: float = 50.0
    max_temp_c: float = 80.0
    protocol: str = ""

    @property
    def torque_constant_nm_per_a(self) -> float:
        """Effective output torque per amp (stall torque / stall current)."""
        return self.stall_torque_nm / max(self.stall_current_a, 1e-9)


class SensorSpec(Component):
    kind: Literal["sensor"] = "sensor"
    type: str
    interface: str = ""
    current_ma: float = 0.0
    voltage_v: float = 3.3


class BoardSpec(Component):
    kind: Literal["board"] = "board"
    role: str = ""
    voltage_v: float = 5.0
    power_w: float = 0.0


class BatterySpec(Component):
    kind: Literal["battery"] = "battery"
    voltage_v: float
    capacity_mah: float
    max_current_a: float = 0.0

    @property
    def energy_wh(self) -> float:
        return self.voltage_v * self.capacity_mah / 1000.0


class MaterialSpec(Component):
    kind: Literal["material"] = "material"
    role: Literal["structure", "skin"] = "structure"
    density_g_cm3: float
    areal_density_g_cm2: float = 0.0
    joint_stiffness_nm_per_rad_per_mm: float = 0.0
    joint_damping_nms_per_rad_per_mm: float = 0.0
    cost_usd_per_kg: float = 0.0
    color: str = "#cccccc"


_MODELS: dict[str, type[Component]] = {
    "actuator": ActuatorSpec,
    "sensor": SensorSpec,
    "board": BoardSpec,
    "battery": BatterySpec,
    "material": MaterialSpec,
}


class Library:
    def __init__(self, components: list[Component], incomplete: dict[str, dict[str, Any]] | None = None):
        self._by_key: dict[str, Component] = {}
        #: entries that cannot be used yet: key -> {kind, name, missing, file}
        self.incomplete: dict[str, dict[str, Any]] = dict(incomplete or {})
        for c in components:
            if c.key in self._by_key:
                raise ValueError(f"Duplicate component key {c.key!r}")
            self._by_key[c.key] = c

    def get(self, key: str) -> Component:
        try:
            return self._by_key[key]
        except KeyError as exc:
            if key in self.incomplete:
                inc = self.incomplete[key]
                raise KeyError(
                    f"Component {key!r} is incomplete: enter {', '.join(inc['missing'])} in "
                    f"config/components/{inc['file']} (mark any value you had to guess in 'guessed:')."
                ) from exc
            raise KeyError(
                f"Unknown component {key!r}. Add it to config/components/*.yaml "
                "(with source: and verified: false)."
            ) from exc

    def has(self, key: str) -> bool:
        return key in self._by_key

    def actuator(self, key: str) -> ActuatorSpec:
        c = self.get(key)
        if not isinstance(c, ActuatorSpec):
            raise TypeError(f"{key!r} is a {c.kind}, not an actuator")
        return c

    def material(self, key: str) -> MaterialSpec:
        c = self.get(key)
        if not isinstance(c, MaterialSpec):
            raise TypeError(f"{key!r} is a {c.kind}, not a material")
        return c

    def battery(self, key: str) -> BatterySpec:
        c = self.get(key)
        if not isinstance(c, BatterySpec):
            raise TypeError(f"{key!r} is a {c.kind}, not a battery")
        return c

    def by_kind(self, kind: str) -> list[Component]:
        return [c for c in self._by_key.values() if c.kind == kind]

    def all(self) -> list[Component]:
        return list(self._by_key.values())

    def to_json(self) -> list[dict[str, Any]]:
        return [c.model_dump(mode="json") for c in self._by_key.values()]


def spec_fields(kind: str, role: str | None = None) -> list[str]:
    """Names of the fields that specify a component of this kind (a structure
    material has no skin coefficients)."""
    out = [f for f in _MODELS[kind].model_fields if f not in META_FIELDS]
    if kind == "material":
        out = [f for f in out if f not in _NOT_FOR_MATERIAL and (role == "skin" or f not in _SKIN_ONLY)]
    return out


def required_fields(kind: str, role: str | None = None) -> list[str]:
    """Spec fields an entry must give before it can be used: those without a
    default, and the mass (a missing mass must not count as 0 g)."""
    model = _MODELS[kind]
    return [f for f in spec_fields(kind, role) if model.model_fields[f].is_required() or f == "mass_g"]


class IncompleteComponent(ValueError):
    """An entry with required values still to be entered."""

    def __init__(self, key: str, missing: list[str]):
        super().__init__(f"Component {key!r} is incomplete: missing {', '.join(missing)}")
        self.key = key
        self.missing = missing


def parse_component(data: dict[str, Any]) -> Component:
    """Validate one YAML entry. ``null`` means "not entered yet": never a value."""
    key = data.get("key")
    kind = data.get("kind")
    model = _MODELS.get(str(kind))
    if model is None:
        raise ValueError(f"Component {key!r}: unknown kind {kind!r}")
    if "source" not in data:
        raise ValueError(f"Component {key!r} has no 'source:' field")
    given = {k: v for k, v in data.items() if v is not None and k != "defaulted"}
    fields = spec_fields(str(kind), given.get("role"))
    absent = [f for f in fields if f not in given]
    required = required_fields(str(kind), given.get("role"))
    missing = [f for f in absent if f in required]
    if missing:
        raise IncompleteComponent(str(key), missing)
    unknown = [f for f in given.get("guessed") or [] if f not in fields]
    if unknown:
        raise ValueError(f"Component {key!r}: 'guessed' names {unknown}, which are not spec fields of a {kind}")
    return model.model_validate({**given, "defaulted": absent})


def load_dir(directory: Path) -> tuple[list[Component], dict[str, dict[str, Any]]]:
    """Usable components, and the incomplete entries by key."""
    out: list[Component] = []
    incomplete: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            items = yaml.safe_load(fh) or []
        for item in items:
            try:
                out.append(parse_component(item))
            except IncompleteComponent as exc:
                incomplete[exc.key] = {"key": exc.key, "kind": item.get("kind"), "name": item.get("name") or exc.key,
                                       "missing": exc.missing, "file": path.name}
    return out, incomplete


def _stamp(directory: Path) -> tuple[tuple[str, float], ...]:
    return tuple((p.name, p.stat().st_mtime) for p in sorted(directory.glob("*.yaml")))


@lru_cache(maxsize=4)
def _load_cached(directory: str, stamp: tuple[tuple[str, float], ...]) -> Library:
    comps, incomplete = load_dir(Path(directory))
    try:  # plugin-provided components
        from calflab.plugins import registry

        for cls in registry.all("component").values():
            comps.extend(cls().components())  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - registry not ready during bootstrap
        pass
    return Library(comps, incomplete)


def library() -> Library:
    """The component library (reloaded automatically when the YAML changes)."""
    d = config_dir() / "components"
    return _load_cached(str(d), _stamp(d))
