"""Synthetic 'footage' for tests: the feral calf posed by forward kinematics and seen from its left side, written
as a DeepLabCut CSV in image pixels (y down). Retargeting it must give back the angles it was posed with."""

from __future__ import annotations

import math

from calflab.model.spec import RobotSpec

#: tracked landmark -> (body whose origin it is, or (body, local point mm))
LANDMARKS = {
    "hip": ("leg.hl.femur", None),
    "stifle": ("leg.hl.tibia", None),
    "hock": ("leg.hl.cannon", None),
    "hind_fetlock": ("leg.hl.cannon", "end"),
    "withers": ("leg.fl.upper", None),
    "shoulder": ("leg.fl.upper", None),
    "carpus": ("leg.fl.cannon", None),
    "fore_fetlock": ("leg.fl.cannon", "end"),
    "hind_hoof": ("leg.hl.cannon", "hoof"),
    "fore_hoof": ("leg.fl.cannon", "hoof"),
}


def pose_landmarks(spec: RobotSpec, angles: dict[str, float]) -> dict[str, tuple[float, float]]:
    """(x, z) in mm of every landmark with the joints at ``angles`` (deg, absolute)."""
    from calflab.model.xform import quat_rotate

    poses = spec.world_poses(angles)
    out = {}
    for name, (body, where) in LANDMARKS.items():
        bp, bq = poses[body]
        if where is None:
            p = bp
        else:
            b = spec.body(body)
            tube = next(g for g in b.geoms if g.id.endswith(".tube"))
            local = (0.0, 0.0, -tube.size[1]) if where == "end" else next(g for g in b.geoms if g.foot).pos
            r = quat_rotate(bq, local)
            p = (bp[0] + r[0], bp[1] + r[1], bp[2] + r[2])
        out[name] = (p[0], p[2])
    return out


def paw_angles(t: float) -> dict[str, float]:
    """Front-left pawing and a hind-left shift (deg relative to standing) at time t (s)."""
    s = math.sin(2 * math.pi * 0.5 * t)
    return {"joint.fl.shoulder": -15.0 * max(0.0, s), "joint.fl.carpus": 60.0 * max(0.0, s),
            "joint.hl.stifle": 8.0 * s, "joint.hl.hock": 6.0 * s}


def dlc_csv(spec: RobotSpec, seconds: float = 4.0, fps: float = 30.0, px_per_mm: float = 1.5) -> str:
    names = list(LANDMARKS)
    rows = ["scorer," + ",".join(["DLC_test"] * 3 * len(names)),
            "bodyparts," + ",".join(n for n in names for _ in range(3)),
            "coords," + ",".join(c for _ in names for c in ("x", "y", "likelihood"))]
    rest = spec.rest_angles()
    for f in range(int(seconds * fps)):
        angles = dict(rest)
        for j, v in paw_angles(f / fps).items():
            angles[j] = rest[j] + v
        lm = pose_landmarks(spec, angles)
        cells = []
        for n in names:
            x, z = lm[n]
            cells += [f"{200 + x * px_per_mm:.3f}", f"{900 - z * px_per_mm:.3f}", "0.99"]
        rows.append(f"{f}," + ",".join(cells))
    return "\n".join(rows) + "\n"
