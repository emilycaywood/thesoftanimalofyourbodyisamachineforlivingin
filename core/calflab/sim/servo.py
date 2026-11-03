"""The servo's torque-speed envelope (ADR-084).

A DC-motor servo's available torque falls linearly with speed, from stall
torque at rest to zero at its no-load speed:

    tau_available(omega) = tau_stall * (1 - |omega| / omega_0)

in the *driving* quadrant (torque and speed in the same direction). In the
*braking* quadrant (torque against the motion) the servo is taken to resist up
to its stall torque; a real motor brakes harder than that, so this is the
cautious side. Above its no-load speed a servo cannot drive any further.

Only the library's ``stall_torque_nm`` and ``no_load_speed_rpm`` are used:
nothing else of the curve is on a datasheet here. Everything is at the joint
(a belt multiplies torque by ratio x efficiency and divides speed by the
ratio; the fractions are the same on both sides).

Units: N*m, rad/s; ``use`` is a fraction (1 = on the envelope).
"""

from __future__ import annotations

import numpy as np


def available_torque(omega: np.ndarray, stall: np.ndarray, no_load: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Most positive and most negative torque a servo can give at joint speed ``omega`` (rad/s).

    Returns ``(hi, lo)`` with ``hi >= 0 >= lo``: driving forward at positive speed is limited by the curve,
    braking (torque against the motion) by stall torque.
    """
    w = np.asarray(omega, dtype=float)
    s = np.asarray(stall, dtype=float)
    w0 = np.maximum(np.asarray(no_load, dtype=float), 1e-9)
    drive = s * np.clip(1.0 - np.abs(w) / w0, 0.0, 1.0)
    hi = np.where(w > 0, drive, s)
    lo = np.where(w < 0, -drive, -s)
    return hi, lo


def envelope_use(torque: np.ndarray, omega: np.ndarray, stall: np.ndarray, no_load: np.ndarray) -> np.ndarray:
    """How much of the envelope an operating point uses: |tau|/stall + |omega|/omega_0 when driving, |tau|/stall
    when braking. 1 = on the curve (the servo cannot give more), 1 - m = inside it with a margin m."""
    tau = np.asarray(torque, dtype=float)
    w = np.asarray(omega, dtype=float)
    s = np.maximum(np.asarray(stall, dtype=float), 1e-9)
    w0 = np.maximum(np.asarray(no_load, dtype=float), 1e-9)
    driving = tau * w > 0
    return np.abs(tau) / s + np.where(driving, np.abs(w) / w0, 0.0)
