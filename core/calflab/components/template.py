"""Blank component entries (``calflab components new``).

A new entry lists every spec field of its kind with no value, ``verified:
false`` and an empty ``guessed:`` list. Nothing is filled in for the
researcher: the entry is *incomplete*, and so not selectable, until the
required values are entered (ADR-051).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from calflab.components.library import _MODELS, required_fields, spec_fields
from calflab.paths import config_dir

#: kind -> file under config/components
FILES: dict[str, str] = {
    "actuator": "actuators.yaml",
    "sensor": "electronics.yaml",
    "board": "electronics.yaml",
    "battery": "electronics.yaml",
    "material": "materials.yaml",
}

#: unit and meaning of each spec field, written beside the blank value
HINTS: dict[str, str] = {
    "mass_g": "g",
    "dims_mm": "mm, housing [x, y, z]",
    "cost_usd": "USD",
    "stall_torque_nm": "N*m at the output, at voltage_v (1 kg.cm = 0.0981 N*m)",
    "stall_current_a": "A",
    "no_load_speed_rpm": "rpm at the output (60 deg in t seconds = 10 / t rpm); caps gait speed",
    "voltage_v": "V the figures above are given for",
    "gear_ratio": "",
    "idle_current_a": "A",
    "armature_kgm2": "kg*m^2, rotor inertia reflected to the output (rarely on a datasheet)",
    "winding_resistance_ohm": "ohm",
    "r_thermal_k_per_w": "K/W, winding to air (rarely on a datasheet)",
    "c_thermal_j_per_k": "J/K (rarely on a datasheet)",
    "max_temp_c": "degC",
    "current_ma": "mA",
    "power_w": "W, typical load",
    "capacity_mah": "mAh",
    "max_current_a": "A, continuous discharge",
    "density_g_cm3": "g/cm^3 (for a printed part: mass of a sample / its outer volume)",
    "areal_density_g_cm2": "g/cm^2 of base fabric",
    "joint_stiffness_nm_per_rad_per_mm": "N*m/rad per mm of thickness",
    "joint_damping_nms_per_rad_per_mm": "N*m*s/rad per mm of thickness",
    "cost_usd_per_kg": "USD per kg",
}

_EXTRA: dict[str, list[tuple[str, str]]] = {
    "actuator": [("protocol", '""')],
    "sensor": [("type", '""         # imu | fsr | touch | microphone | depth_camera'), ("interface", '""')],
    "board": [("role", '""')],
    "battery": [],
    "material": [("role", "structure  # structure | skin"), ("color", '"#c9c4b9"')],
}


def template(kind: str, key: str, name: str = "") -> tuple[str, list[str]]:
    """YAML text of a blank entry, and the fields that must be entered before it can be used."""
    if kind not in _MODELS:
        raise ValueError(f"Unknown kind {kind!r}. Use one of: {', '.join(_MODELS)}")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError(f"{key!r} is not a valid key: use lower-case letters, digits and underscores, e.g. ds3218")
    role = "structure" if kind == "material" else None
    fields = spec_fields(kind, role)
    required = required_fields(kind, role)
    lines = [
        f"- key: {key}",
        f"  kind: {kind}",
        f"  name: {yaml.safe_dump(name or key, default_style=chr(34)).strip()}",
        '  manufacturer: ""',
    ]
    lines += [f"  {field}: {value}" for field, value in _EXTRA[kind]]
    for f in fields:
        need = "REQUIRED" if f in required else "optional (blank = default assumed, and reported)"
        hint = HINTS.get(f, "")
        lines.append(f"  {f}: null".ljust(34) + f"# {hint + '; ' if hint else ''}{need}")
    lines += [
        '  url: ""                         # datasheet or product page',
        '  source: ""                      # which document the values come from (title, revision, date read)',
        "  guessed: []                     # names of fields whose value is your guess, not a datasheet value",
        "  verified: false                 # set to true yourself once every value is checked",
    ]
    return "\n".join(lines) + "\n", required


def add_component(kind: str, key: str, name: str = "", directory: Path | None = None) -> tuple[Path, list[str]]:
    """Append a blank entry for ``key`` to the YAML file of its kind. Returns
    the file and the fields that must be entered. Refuses an existing key."""
    text, required = template(kind, key, name)
    directory = directory or config_dir() / "components"
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            if any(item.get("key") == key for item in (yaml.safe_load(fh) or [])):
                raise ValueError(f"A component with key {key!r} already exists in {path.name}")
    path = directory / FILES[kind]
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    sep = "" if existing.endswith("\n\n") or not existing else ("\n" if existing.endswith("\n") else "\n\n")
    path.write_text(existing + sep + text, encoding="utf-8")
    return path, required
