"""Component library: actuators, sensors, boards, batteries, materials.

Data lives in ``config/components/*.yaml`` (and may be extended by
``ComponentProvider`` plugins). Every entry carries ``source`` and
``verified``; the code never invents a spec and never sets ``verified``.
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
    def __init__(self, components: list[Component]):
        self._by_key: dict[str, Component] = {}
        for c in components:
            if c.key in self._by_key:
                raise ValueError(f"Duplicate component key {c.key!r}")
            self._by_key[c.key] = c

    def get(self, key: str) -> Component:
        try:
            return self._by_key[key]
        except KeyError as exc:
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


def parse_component(data: dict[str, Any]) -> Component:
    kind = data.get("kind")
    model = _MODELS.get(str(kind))
    if model is None:
        raise ValueError(f"Component {data.get('key')!r}: unknown kind {kind!r}")
    if "source" not in data:
        raise ValueError(f"Component {data.get('key')!r} has no 'source:' field")
    return model.model_validate(data)


def load_dir(directory: Path) -> list[Component]:
    out: list[Component] = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            items = yaml.safe_load(fh) or []
        for item in items:
            out.append(parse_component(item))
    return out


def _stamp(directory: Path) -> tuple[tuple[str, float], ...]:
    return tuple((p.name, p.stat().st_mtime) for p in sorted(directory.glob("*.yaml")))


@lru_cache(maxsize=4)
def _load_cached(directory: str, stamp: tuple[tuple[str, float], ...]) -> Library:
    comps = load_dir(Path(directory))
    try:  # plugin-provided components
        from calflab.plugins import registry

        for cls in registry.all("component").values():
            comps.extend(cls().components())
    except Exception:  # pragma: no cover - registry not ready during bootstrap
        pass
    return Library(comps)


def library() -> Library:
    """The component library (reloaded automatically when the YAML changes)."""
    d = config_dir() / "components"
    return _load_cached(str(d), _stamp(d))
