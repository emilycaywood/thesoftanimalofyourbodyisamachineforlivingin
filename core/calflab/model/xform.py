"""Small rigid-transform helpers. Quaternions are (w, x, y, z), unit length.

Angles passed to these helpers are in **degrees** (design units) unless the
function name says ``rad``.
"""

from __future__ import annotations

import math

import numpy as np

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def quat_axis_angle(axis: Vec3, angle_deg: float) -> Quat:
    a = np.asarray(axis, dtype=float)
    n = float(np.linalg.norm(a))
    if n == 0.0:
        return IDENTITY
    a = a / n
    h = math.radians(angle_deg) / 2.0
    s = math.sin(h)
    return (math.cos(h), float(a[0] * s), float(a[1] * s), float(a[2] * s))


def quat_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def quat_rotate(q: Quat, v: Vec3) -> Vec3:
    m = quat_to_matrix(q)
    r = m @ np.asarray(v, dtype=float)
    return (float(r[0]), float(r[1]), float(r[2]))


def quat_to_matrix(q: Quat) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def quat_from_z_to(direction: Vec3) -> Quat:
    """Shortest rotation taking the local +Z axis onto ``direction``."""
    d = np.asarray(direction, dtype=float)
    n = float(np.linalg.norm(d))
    if n == 0.0:
        return IDENTITY
    d = d / n
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(z, d))
    if c > 1.0 - 1e-12:
        return IDENTITY
    if c < -1.0 + 1e-12:
        return (0.0, 1.0, 0.0, 0.0)
    axis = np.cross(z, d)
    return quat_axis_angle((float(axis[0]), float(axis[1]), float(axis[2])), math.degrees(math.acos(c)))


def quat_euler_xyz(rx_deg: float, ry_deg: float, rz_deg: float) -> Quat:
    """Extrinsic X then Y then Z rotation (i.e. ``Rz * Ry * Rx``)."""
    qx = quat_axis_angle((1, 0, 0), rx_deg)
    qy = quat_axis_angle((0, 1, 0), ry_deg)
    qz = quat_axis_angle((0, 0, 1), rz_deg)
    return quat_mul(qz, quat_mul(qy, qx))


def compose(
    p1: Vec3, q1: Quat, p2: Vec3, q2: Quat
) -> tuple[Vec3, Quat]:
    """Pose of frame 2 (given in frame 1) expressed in frame 1's parent."""
    r = quat_rotate(q1, p2)
    return (p1[0] + r[0], p1[1] + r[1], p1[2] + r[2]), quat_mul(q1, q2)


def matrix4(p: Vec3, q: Quat) -> list[list[float]]:
    """Row-major 4x4 transform."""
    m = np.eye(4)
    m[:3, :3] = quat_to_matrix(q)
    m[:3, 3] = p
    return [[float(v) for v in row] for row in m]
