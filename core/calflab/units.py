"""Unit conversion. This is the ONLY module allowed to convert between the
design units used in files, API payloads and the UI (mm, g, degrees) and the SI
units used inside the simulator (m, kg, rad).

Everything else calls ``to_si`` / ``from_si`` or the named helpers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

#: Design-unit -> SI multiplier. Units not listed are already SI (factor 1).
_TO_SI: dict[str, float] = {
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
    "mm2": 1e-6,
    "cm2": 1e-4,
    "mm3": 1e-9,
    "cm3": 1e-6,
    "g": 1e-3,
    "kg": 1.0,
    "deg": math.pi / 180.0,
    "rad": 1.0,
    "deg/s": math.pi / 180.0,
    "rpm": 2.0 * math.pi / 60.0,
    "rad/s": 1.0,
    "g/cm3": 1000.0,
    "g/cm2": 10.0,
    "kg.cm": 0.0980665,  # kgf*cm -> N*m
    "Nm": 1.0,
    "N": 1.0,
    "Nm/rad": 1.0,
    "Nm.s/rad": 1.0,
    "s": 1.0,
    "ms": 1e-3,
    "Hz": 1.0,
    "V": 1.0,
    "A": 1.0,
    "mA": 1e-3,
    "W": 1.0,
    "Wh": 3600.0,
    "mAh": 3.6,  # -> coulomb
    "C": 1.0,
    "": 1.0,
}

DESIGN_UNITS = {"length": "mm", "mass": "g", "angle": "deg"}


def known_units() -> list[str]:
    return sorted(_TO_SI)


def to_si(value: float, unit: str | None) -> float:
    """Convert ``value`` expressed in ``unit`` to SI."""
    return value * _factor(unit)


def from_si(value: float, unit: str | None) -> float:
    """Convert an SI ``value`` to ``unit``."""
    return value / _factor(unit)


def _factor(unit: str | None) -> float:
    if unit is None:
        return 1.0
    try:
        return _TO_SI[unit]
    except KeyError as exc:
        raise ValueError(f"Unknown unit {unit!r}. Known: {', '.join(known_units())}") from exc


def mm_to_m(v: float) -> float:
    return v * 1e-3


def m_to_mm(v: float) -> float:
    return v * 1e3


def g_to_kg(v: float) -> float:
    return v * 1e-3


def kg_to_g(v: float) -> float:
    return v * 1e3


def deg_to_rad(v: float) -> float:
    return v * math.pi / 180.0


def rad_to_deg(v: float) -> float:
    return v * 180.0 / math.pi


def vec_mm_to_m(v: Iterable[float]) -> tuple[float, ...]:
    return tuple(x * 1e-3 for x in v)


def vec_m_to_mm(v: Iterable[float]) -> tuple[float, ...]:
    return tuple(x * 1e3 for x in v)
