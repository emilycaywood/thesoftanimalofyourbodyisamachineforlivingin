"""3D lift: the robot's own skeleton fitted to 2D keypoints from one camera (ADR-080).

The 2D retarget (ADR-073) measures angles in the image plane, which is only
right in a true side view. This module recovers the pose in 3D instead: per
frame, the body's own skeleton (its forward kinematics, joint ranges and
standing pose, from the ``RobotSpec``) plus a camera are fitted so that the
projected landmarks match the tracked 2D keypoints, weighted by confidence.

**Model.** Weak perspective: ``uv = s * (R x)[:2] + t`` per frame, where
``x`` is a landmark in the trunk's frame (mm), ``s`` px per mm, ``t`` the
image position of the trunk origin, and

    R = Rz_cam(roll) Rx_cam(elevation) C0 Rz(heading) Ry(pitch) Rx(roll_trunk)

``C0`` is a camera level with the ground looking at the animal's left side
(animal forward = image left, up = image up). Camera elevation and roll are
one pair for the whole video (the camera is fixed); heading, trunk pitch and
trunk roll are the animal's, per frame. A camera that pans cannot be told
from an animal that turns: heading is relative to the camera's direction.

**Proportions.** The calf is not the robot. Per video, the trunk length, the
trunk width and the front legs are fitted as ratios to the robot's (the hind
leg is the reference, 1; the per-frame scale absorbs size). The width can
only be told from the length when the animal shows several yaws (or the
camera looks down); when the fit cannot tell (its relative uncertainty is
over 15 %), the width comes from ``prior.width_over_length`` (0.35, an
assumption about calves, PROVISIONAL) and the result says so.

**Ambiguities, handled explicitly** (each recorded per frame):

* *Toward or away* (the depth flip of the whole body). A symmetric body seen
  in weak perspective looks the same turned toward the camera with its left
  side near as turned away with its right side near, when the tracker's L/R
  labels are swapped. Both are kept per frame; a two-state Viterbi chooses,
  scoring the side tracked more confidently as the near one (the far legs
  are partly hidden) and charging for a jump in heading. Frames where the
  confidence cue is weak are marked ``ambiguous: depth``.
* *Limb flips.* After the fit, every leg's joints are searched on a grid
  inside their ranges with the trunk held; a second minimum as good as the
  chosen one, more than 20 deg away, marks the frame ``ambiguous: <leg>``.
  The chosen solution is the one continuous with the previous frame.
* *Unobservable joints.* A joint whose 10 deg change would move its
  landmarks by less than 2 % of the body length in the image (hip
  ab/adduction in a pure side view) is listed per frame; it holds near its
  prior instead of following noise.
* *Leg labels.* When a frame fits badly, swapping the L/R labels of one leg
  pair (the tracker confuses crossing legs) is tried and kept if it fits
  much better, recorded as ``swapped: hind`` / ``fore``.

**Reliability.** A frame is unreliable with too few confident points, a fit
residual over ``max_residual_bl`` body lengths, or a view within
``90 - max_view_yaw_deg`` of head-on or tail-on (where the legs' fore-aft
angles become depth). Unreliable frames are gaps for the segmentation.

Units: mm (body), px (image), degrees in and out, radians inside.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, Field

from calflab import units as u
from calflab.behave.keypoints import KeypointTracks
from calflab.model.spec import RobotSpec
from calflab.model.xform import quat_to_matrix

log = logging.getLogger(__name__)

N_POSE = 6  # heading, pitch, roll, log scale, tx, ty
N_GLOBAL = 5  # log trunk length, log trunk width, log front leg, camera elevation, camera roll; then fitted ``at``s
RATIO_NAMES = ("trunk_length", "trunk_width", "front_leg")


# ---------------------------------------------------------------------- the map
class LandmarkDef(BaseModel):
    """Where a tracked keypoint sits on the robot."""

    body: str
    #: a point in the body's frame (mm); default its origin (the joint)
    point: tuple[float, float, float] | None = None
    #: the body's hoof (its foot geom), else the end of its tube
    foot: bool = False
    #: another body: the landmark lies between the two origins, ``at`` of the way
    toward: str | None = None
    at: float = 0.0
    #: fit ``at`` per video within these bounds (where a tracker puts the point is not known); ``at`` starts it
    fit_at: tuple[float, float] | None = None
    weight: float = 1.0


class TieDef(BaseModel):
    """A joint that moves with another: its change = ``ratio`` x the other's."""

    to: str
    ratio: float = 1.0


class LiftPrior(BaseModel):
    #: the animal's hip-to-hip width over its hip-to-shoulder length (an assumption about calves, PROVISIONAL)
    width_over_length: float = 0.35
    #: spread of that ratio (log): the footage moves the width only when it pins it better than this
    width_sd: float = 0.2
    abduction_sd_deg: float = 15.0  # hip ab/adduction is pulled toward standing with this spread
    trunk_tilt_sd_deg: float = 10.0  # trunk pitch and roll about level
    joint_sd_deg: float = 60.0  # every joint, very weakly, toward standing
    segment_sd: float = 0.5  # log ratio of a segment to the robot's (a calf's legs are shorter for its trunk)


class LiftMap(BaseModel):
    """A 3D map: tracked names -> points on the robot (``config/retarget/<name>.yaml`` with ``kind: lift``).

    Keys with ``{S}`` are written once for both sides: ``{S}`` becomes the
    side's name (``side_names``), ``{s}`` in body or joint names ``l`` or
    ``r``, and a point's y is mirrored for the right side.
    """

    name: str
    kind: Literal["lift"] = "lift"
    description: str = ""
    body: str = ""
    side_names: dict[str, str] = Field(default_factory=lambda: {"left": "L", "right": "R"})
    landmarks: dict[str, LandmarkDef]
    ties: dict[str, TieDef] = Field(default_factory=dict)
    #: joint-name endings that are ab/adduction (prior toward standing, reported as such)
    abduction: list[str] = Field(default_factory=lambda: ["hip_abd"])
    prior: LiftPrior = Field(default_factory=LiftPrior)
    min_likelihood: float = 0.3
    _template: dict[str, str] = {}

    def expanded(self) -> tuple[dict[str, LandmarkDef], list[tuple[str, str]], dict[str, TieDef]]:
        """Landmarks for both sides, the left/right name pairs, and the ties (``joint.`` ids)."""
        out: dict[str, LandmarkDef] = {}
        pairs: list[tuple[str, str]] = []
        self._template: dict[str, str] = {}
        for key, d in self.landmarks.items():
            if "{S}" not in key and "{s}" not in d.body:
                out[key] = d
                self._template[key] = key
                continue
            names = []
            for side, s in (("left", "l"), ("right", "r")):
                name = key.replace("{S}", self.side_names.get(side, side[0].upper()))
                pt = d.point
                if pt is not None and side == "right":
                    pt = (pt[0], -pt[1], pt[2])
                out[name] = d.model_copy(update={"body": d.body.replace("{s}", s), "point": pt,
                                                 "toward": d.toward.replace("{s}", s) if d.toward else None})
                self._template[name] = key
                names.append(name)
            pairs.append((names[0], names[1]))
        ties: dict[str, TieDef] = {}
        for key, t in self.ties.items():
            for s in (["l", "r"] if "{s}" in key else [""]):
                ties[f"joint.{key.replace('{s}', s)}"] = TieDef(to=f"joint.{t.to.replace('{s}', s)}", ratio=t.ratio)
        return out, pairs, ties


def load_lift_map(name: str, project_dir: Path | None = None) -> LiftMap:
    from calflab.behave.retarget import map_dirs

    for d in map_dirs(project_dir):
        p = d / f"{name}.yaml"
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if data.get("kind") != "lift":
                raise KeyError(f"Map {name!r} is a 2D side-view map, not a 3D lift map (kind: lift)")
            return LiftMap.model_validate(data)
    raise KeyError(f"No 3D lift map {name!r} (looked in {', '.join(str(d) for d in map_dirs(project_dir))})")


class LiftSettings(BaseModel):
    """How the lift fits and when it trusts a frame (ADR-080). First guesses, tested on synthetic footage."""

    #: the camera's horizontal field of view, only for travel toward/away from the camera (PROVISIONAL)
    camera_hfov_deg: float = 60.0
    min_points: int = 6  # confident landmarks needed in a frame
    max_view_yaw_deg: float = 70.0  # beyond this from a side view (toward head-on / tail-on): unreliable
    max_residual_bl: float = 0.12  # RMS fit residual in body lengths over which a frame has failed
    relative_residual: float = 2.0  # ... or over this many times the video's own median (and 0.05)
    min_cue: float = 0.03  # near-minus-far confidence below this: toward/away rests on continuity alone
    joint_speed_sd_deg_s: float = 300.0  # temporal smoothness of the joints
    abduction_speed_sd_deg_s: float = 60.0  # ... of hip ab/adduction (seen edge-on, it follows noise otherwise)
    turn_speed_sd_deg_s: float = 150.0  # ... of heading, trunk pitch and roll
    scale_rate_sd: float = 1.0  # ... of the log image scale, per second (approach / retreat)
    noise_bl: float = 0.01  # expected keypoint noise, body lengths
    fit_proportions: bool = True
    max_width_rel_sd: float = 0.15  # width less certain than this: use the prior
    min_width_gain: float = 0.10  # ... or when fitting it lowers the residual by less than this share
    max_gap_frames: int = 10  # unreliable stretches up to this long are bridged; longer ones are gaps
    calibration_frames: int = 120
    window_frames: int = 400


# ---------------------------------------------------------------------- the skeleton, vectorised
_KK: dict[tuple[float, float, float], tuple[np.ndarray, np.ndarray]] = {}
_I3 = np.eye(3)


def _axis_rot(axis: np.ndarray, ang: np.ndarray) -> np.ndarray:
    """[B,3,3] rotations about one axis by angles [B] (rad) (Rodrigues; the axis's matrices are cached)."""
    key = (float(axis[0]), float(axis[1]), float(axis[2]))
    kk = _KK.get(key)
    if kk is None:
        a = axis / np.linalg.norm(axis)
        k = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
        kk = _KK[key] = (k, k @ k)
    s, c = np.sin(ang)[:, None, None], np.cos(ang)[:, None, None]
    return _I3 + s * kk[0] + (1.0 - c) * kk[1]


def _rx(a: np.ndarray) -> np.ndarray:
    return _axis_rot(np.array([1.0, 0.0, 0.0]), a)


def _ry(a: np.ndarray) -> np.ndarray:
    return _axis_rot(np.array([0.0, 1.0, 0.0]), a)


def _rz(a: np.ndarray) -> np.ndarray:
    return _axis_rot(np.array([0.0, 0.0, 1.0]), a)


C0 = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])  # world -> camera, level, left side near


def camera_matrix(elev: float, roll: float) -> np.ndarray:
    return (_rz(np.array([roll])) @ _rx(np.array([elev])))[0] @ C0  # elevation + = looking down


def rotation(cam: np.ndarray, heading: np.ndarray, pitch: np.ndarray, roll: np.ndarray) -> np.ndarray:
    """[B,3,3] trunk frame -> camera. ``cam`` [3,3] or [B,3,3]."""
    return cam @ _rz(heading) @ _ry(pitch) @ _rx(roll)


class Skeleton:
    """The landmarks of a map on a body, as a function of the fitted joints and segment ratios."""

    def __init__(self, spec: RobotSpec, lmap: LiftMap):
        lms, self.pairs, ties = lmap.expanded()
        self.names = list(lms)
        self.weight = np.array([d.weight for d in lms.values()])
        self.bodies = [b.id for b in spec.bodies]
        bid = {b: i for i, b in enumerate(self.bodies)}
        root = spec.root.id
        missing = sorted({d.body for d in lms.values()} - set(bid))
        if missing:
            raise ValueError(f"Map {lmap.name}: bodies not on this robot: {', '.join(missing)}")
        self.parent = [bid[b.parent] if b.parent else -1 for b in spec.bodies]
        self.pos = np.array([b.pos for b in spec.bodies], dtype=float)
        self.rot = np.array([quat_to_matrix(b.quat) for b in spec.bodies], dtype=float)

        def group(body: str) -> str:
            if body == root:
                return "trunk"
            if body.startswith("leg.f"):
                return "front"
            return "hind" if body.startswith("leg.h") else "other"

        self.group = [group(b) for b in self.bodies]
        self.parent_group = ["none" if p < 0 else self.group[p] for p in self.parent]
        # joints: every hinge; free ones are fitted, tied ones follow, others hold their standing angle
        hinges = [j for j in spec.joints if j.type == "hinge"]
        self.joint_ids = [j.id for j in hinges]
        self.rest = np.array([u.deg_to_rad(j.rest_deg) for j in hinges])
        self.lo = np.array([u.deg_to_rad(j.range_deg[0]) for j in hinges])
        self.hi = np.array([u.deg_to_rad(j.range_deg[1]) for j in hinges])
        self.body_joints: list[list[tuple[np.ndarray, int]]] = [[] for _ in self.bodies]
        for k, j in enumerate(hinges):
            self.body_joints[bid[j.body]].append((np.array(j.axis, dtype=float), k))
        # landmark terms: sum of c * (P_body + R_body p); roles: a leg's root joint or its hoof
        self.terms: list[list[tuple[int, np.ndarray, float]]] = []
        self.role: list[tuple[str, str]] = []
        # landmarks whose place between two joints is fitted per video (one value per left/right pair)
        self.fit_keys: list[str] = []
        self.fit_of: list[int] = []
        fit_lo, fit_hi, fit_init = [], [], []
        for name, d in lms.items():
            key = lmap._template.get(name, name)
            if d.toward and d.fit_at:
                if key not in self.fit_keys:
                    self.fit_keys.append(key)
                    fit_lo.append(d.fit_at[0])
                    fit_hi.append(d.fit_at[1])
                    fit_init.append(min(max(d.at, d.fit_at[0]), d.fit_at[1]))
                self.fit_of.append(self.fit_keys.index(key))
            else:
                self.fit_of.append(-1)
        self.fit_lo, self.fit_hi, self.fit_init = np.array(fit_lo), np.array(fit_hi), np.array(fit_init)
        for d in lms.values():
            b = bid[d.body]
            g = group(d.body)
            if d.foot:
                self.role.append(("foot", g))
            elif d.point is None and spec.body(d.body).parent == root:  # at or below a leg's root joint
                self.role.append(("root", g))
            else:
                self.role.append(("", g))
            if d.toward:
                self.terms.append([(b, np.zeros(3), 1.0 - d.at), (bid[d.toward], np.zeros(3), d.at)])
                continue
            p = np.array(d.point if d.point is not None else (0.0, 0.0, 0.0), dtype=float)
            if d.foot:
                body = spec.body(d.body)
                feet = [g for g in body.geoms if g.foot]
                tube = [g for g in body.geoms if g.id.endswith(".tube")]
                if feet:
                    p = np.array(feet[0].pos, dtype=float)
                elif tube:
                    p = np.array((0.0, 0.0, -tube[0].size[1]))
            self.terms.append([(b, p, 1.0)])
        # which joints move some landmark (ancestors of landmark bodies)
        needed: set[int] = set()
        for t in self.terms:
            for b, _, _ in t:
                while b >= 0:
                    needed.add(b)
                    b = self.parent[b]
        self.needed = sorted(needed)
        moving = [k for b in self.needed for _, k in self.body_joints[b]]
        self.tie = {self.joint_ids.index(a): (self.joint_ids.index(t.to), t.ratio) for a, t in ties.items()
                    if a in self.joint_ids and t.to in self.joint_ids}
        self.free = [k for k in moving if k not in self.tie]
        self.free_ids = [self.joint_ids[k] for k in self.free]
        abd = tuple(lmap.abduction)
        self.is_abd = np.array([self.joint_ids[k].endswith(abd) for k in self.free])
        # bounds of the free joints (relative to standing), narrowed so tied joints stay in range too
        lo = self.lo[self.free] - self.rest[self.free]
        hi = self.hi[self.free] - self.rest[self.free]
        for a, (m, r) in self.tie.items():
            i = self.free.index(m) if m in self.free else None
            if i is None or r == 0:
                continue
            tlo, thi = (self.lo[a] - self.rest[a]) / r, (self.hi[a] - self.rest[a]) / r
            lo[i], hi[i] = max(lo[i], min(tlo, thi)), min(hi[i], max(tlo, thi))
        self.free_lo, self.free_hi = lo, hi
        # legs: free joints and landmarks of each leg (``leg.hl`` ...)
        self.legs: dict[str, tuple[list[int], list[int]]] = {}
        for i, k in enumerate(self.free):
            leg = self.joint_ids[k].split(".")[1]
            self.legs.setdefault(leg, ([], []))[0].append(i)
        for li, t in enumerate(self.terms):
            leg_of = {self.bodies[b].split(".")[1] for b, _, _ in t if self.bodies[b].startswith("leg.")}
            for leg in leg_of & set(self.legs):
                self.legs[leg][1].append(li)
        # mirror: free joint i <-> its other-side twin; landmark pairs
        self.mirror_joint = []
        for k in self.free:
            jid = self.joint_ids[k]
            parts = jid.split(".")
            if len(parts) > 2 and len(parts[1]) == 2 and parts[1][1] in "lr":
                twin = ".".join([parts[0], parts[1][0] + {"l": "r", "r": "l"}[parts[1][1]], *parts[2:]])
                self.mirror_joint.append(self.free_ids.index(twin) if twin in self.free_ids else self.free.index(k))
            else:
                self.mirror_joint.append(self.free.index(k))
        self.swap = np.arange(len(self.names))
        for na, nb in self.pairs:
            ia, ib = self.names.index(na), self.names.index(nb)
            self.swap[ia], self.swap[ib] = ib, ia
        self.side_of = np.zeros(len(self.names))  # +1 left, -1 right, 0 midline
        for na, nb in self.pairs:
            self.side_of[self.names.index(na)] = 1.0
            self.side_of[self.names.index(nb)] = -1.0
        # robot measures: hip-to-shoulder length and hip-to-hip width (mm)
        roots = {g: [self.pos[i] for i, b in enumerate(self.bodies) if self.parent[i] == bid[root] and self.group[i] == g]
                 for g in ("hind", "front")}
        if roots["hind"] and roots["front"]:
            self.length_mm = float(abs(np.mean([p[0] for p in roots["front"]]) - np.mean([p[0] for p in roots["hind"]])))
            ys = [p[1] for p in roots["hind"]]
            self.width_mm = float(max(ys) - min(ys)) or 1.0
        else:
            self.length_mm, self.width_mm = 500.0, 150.0
        self.feet = [(bid[b.id], np.array(g.pos, dtype=float), float(g.size[0])) for b in spec.bodies for g in b.geoms
                     if g.foot]

    @property
    def n(self) -> int:
        return len(self.free)

    @property
    def n_global(self) -> int:
        return N_GLOBAL + len(self.fit_keys)

    def initial_globals(self) -> np.ndarray:
        g = np.zeros(self.n_global)
        g[N_GLOBAL:] = self.fit_init
        return g

    def full_angles(self, d: np.ndarray) -> np.ndarray:
        """[B, all hinge joints] absolute angles (rad) from free deltas [B, n]."""
        a = np.repeat(self.rest[None], d.shape[0], axis=0)
        a[:, self.free] += d
        for t, (m, r) in self.tie.items():
            a[:, t] = self.rest[t] + r * (a[:, m] - self.rest[m])
        return a

    def _scales(self, ratios: np.ndarray) -> dict[str, np.ndarray]:
        r = np.exp(np.asarray(ratios, dtype=float))  # [3]: log length, log width, log front
        return {"trunk": np.array([r[0], r[1], 1.0]), "hind": np.ones(3), "front": np.full(3, r[2]),
                "other": np.ones(3), "none": np.ones(3)}

    def body_frames(self, d: np.ndarray, ratios: np.ndarray, bodies: list[int] | None = None
                    ) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
        """World (trunk-frame) positions [B,3] and rotations [B,3,3] of the needed bodies."""
        ang = self.full_angles(d)
        sc = self._scales(ratios)
        B = d.shape[0]
        P: dict[int, np.ndarray] = {}
        R: dict[int, np.ndarray] = {}
        for i in (self.needed if bodies is None else bodies):
            rl = np.repeat(self.rot[i][None], B, axis=0)
            for axis, k in self.body_joints[i]:
                rl = rl @ _axis_rot(axis, ang[:, k])
            p = self.parent[i]
            if p < 0:
                P[i], R[i] = np.zeros((B, 3)), rl
            else:
                P[i] = P[p] + np.einsum("bij,j->bi", R[p], self.pos[i] * sc[self.group[p]])
                R[i] = R[p] @ rl
        return P, R

    def points(self, d: np.ndarray, glob: np.ndarray) -> np.ndarray:
        """[B, L, 3] landmarks in the trunk frame (mm). ``glob``: log ratios (3), camera (2, unused), fitted ats."""
        ratios = glob[:3]
        P, R = self.body_frames(d, ratios)
        sc = self._scales(ratios)
        out = np.zeros((d.shape[0], len(self.terms), 3))
        for li, t in enumerate(self.terms):
            k = self.fit_of[li]
            for ti, (b, p, c) in enumerate(t):
                if k >= 0 and len(glob) > N_GLOBAL + k:
                    c = (1.0 - glob[N_GLOBAL + k]) if ti == 0 else glob[N_GLOBAL + k]
                out[:, li] += c * (P[b] + np.einsum("bij,j->bi", R[b], p * sc[self.group[b]]))
        return out

    def ground_height(self, d: np.ndarray, pitch: np.ndarray, roll: np.ndarray) -> np.ndarray:
        """[B] height of the trunk origin above the lowest hoof (mm), the robot at its own proportions."""
        if not self.feet:
            return np.full(d.shape[0], float("nan"))
        P, R = self.body_frames(d, np.zeros(3), sorted({b for b, _, _ in self.feet} | set(self.needed)))
        tilt = _ry(pitch) @ _rx(roll)
        z = []
        for b, p, r in self.feet:
            if b not in P:
                continue
            w = P[b] + np.einsum("bij,j->bi", R[b], p)
            z.append(np.einsum("bij,bj->bi", tilt, w)[:, 2] - r)
        return -np.min(np.array(z), axis=0)


# ---------------------------------------------------------------------- projection and residuals
def project(sk: Skeleton, x: np.ndarray, glob: np.ndarray) -> np.ndarray:
    """[B, L, 2] image points for pose vectors x [B, 6+n] (rad, log px/mm, px)."""
    X = sk.points(x[:, N_POSE:], glob)
    cam = camera_matrix(glob[3], glob[4])
    R = rotation(cam, x[:, 0], x[:, 1], x[:, 2])
    Y = np.einsum("bij,blj->bli", R, X)
    return np.exp(x[:, 3])[:, None, None] * Y[:, :, :2] + x[:, None, 4:6]


class _Frame:
    """Observations of one frame, in the order of the skeleton's landmarks."""

    def __init__(self, obs: np.ndarray, w: np.ndarray):
        self.obs = obs
        self.w = w


def _priors(sk: Skeleton, x: np.ndarray, prior: LiftPrior) -> np.ndarray:
    """[B, k] prior residuals of pose vectors: trunk tilt, ab/adduction and joints toward standing."""
    d = x[:, N_POSE:]
    tilt = u.deg_to_rad(prior.trunk_tilt_sd_deg)
    sd = np.where(sk.is_abd, u.deg_to_rad(prior.abduction_sd_deg), u.deg_to_rad(prior.joint_sd_deg))
    return np.concatenate([x[:, 1:3] / tilt, d / sd[None]], axis=1)


def _data_res(sk: Skeleton, x: np.ndarray, glob: np.ndarray, fr: _Frame, sigma: float) -> np.ndarray:
    uv = project(sk, x, glob)
    r = (uv - fr.obs[None]) * np.sqrt(fr.w)[None, :, None] / sigma
    return np.nan_to_num(r).reshape(x.shape[0], -1)


def _frame_residuals(sk: Skeleton, x: np.ndarray, glob: np.ndarray, fr: _Frame, sigma: float, prev: np.ndarray | None,
                     step: np.ndarray, prior: LiftPrior) -> np.ndarray:
    parts = [_data_res(sk, x, glob, fr, sigma), _priors(sk, x, prior)]
    if prev is not None:
        dv = x - prev[None]
        dv[:, 0] = (dv[:, 0] + math.pi) % (2 * math.pi) - math.pi
        parts.append(np.concatenate([dv[:, :4], dv[:, N_POSE:]], axis=1) / step[None])
    return np.concatenate(parts, axis=1)


def _bounds(sk: Skeleton) -> tuple[np.ndarray, np.ndarray]:
    t = u.deg_to_rad(60.0)
    lo = np.concatenate([[-np.inf, -t, -t, -np.inf, -np.inf, -np.inf], sk.free_lo])
    hi = np.concatenate([[np.inf, t, t, np.inf, np.inf, np.inf], sk.free_hi])
    return lo, hi


def _steps(npar: int) -> np.ndarray:
    """Finite-difference steps of a pose vector: rad, log scale, px, rad."""
    h = np.full(npar, 1e-4)
    h[3] = 1e-5
    h[4:6] = 1e-2
    return h


def _solve_frame(sk: Skeleton, x0: np.ndarray, glob: np.ndarray, fr: _Frame, sigma: float, prev: np.ndarray | None,
                 step: np.ndarray, prior: LiftPrior, max_nfev: int = 60) -> tuple[np.ndarray, float]:
    from scipy.optimize import least_squares

    lo, hi = _bounds(sk)
    x0 = np.clip(x0, lo + 1e-9, hi - 1e-9)
    h = _steps(x0.size)

    def fun(x: np.ndarray) -> np.ndarray:
        return _frame_residuals(sk, x[None], glob, fr, sigma, prev, step, prior)[0]

    def jac(x: np.ndarray) -> np.ndarray:
        X = np.repeat(x[None], x.size + 1, axis=0)
        X[1:] += np.diag(h)
        R = _frame_residuals(sk, X, glob, fr, sigma, prev, step, prior)
        return ((R[1:] - R[0][None]) / h[:, None]).T

    res = least_squares(fun, x0, jac=jac, bounds=(lo, hi), loss="soft_l1", f_scale=2.0, max_nfev=max_nfev,
                        x_scale="jac")
    return res.x, float(res.cost)


def _closed_form_st(q: np.ndarray, o: np.ndarray, w: np.ndarray) -> tuple[float, np.ndarray, float]:
    """Best scale and translation for o ~ s q + t (weights w); returns (s, t, weighted SSE)."""
    ok = (w > 0) & ~np.isnan(o[:, 0])
    if ok.sum() < 3:
        return 1.0, np.zeros(2), float("inf")
    ww = w[ok][:, None]
    qm = (q[ok] * ww).sum(0) / ww.sum()
    om = (o[ok] * ww).sum(0) / ww.sum()
    qc, oc = q[ok] - qm, o[ok] - om
    den = float((ww * qc * qc).sum())
    s = float((ww * qc * oc).sum()) / den if den > 0 else 1.0
    if s <= 0:
        return 1.0, np.zeros(2), float("inf")
    t = om - s * qm
    return s, t, float((ww * (s * q[ok] + t - o[ok]) ** 2).sum())


def _global_init(sk: Skeleton, glob: np.ndarray, fr: _Frame, sigma: float, step: np.ndarray, prior: LiftPrior
                 ) -> tuple[np.ndarray, float]:
    """Fit a frame from scratch: 12 headings with the robot standing, the best three refined."""
    X = sk.points(np.zeros((1, sk.n)), glob)[0]
    cam = camera_matrix(glob[3], glob[4])
    starts = []
    for hd in u.deg_to_rad(np.arange(0.0, 360.0, 30.0)):
        R = rotation(cam, np.array([hd]), np.zeros(1), np.zeros(1))[0]
        s, t, sse = _closed_form_st((X @ R.T)[:, :2], fr.obs, fr.w)
        starts.append((sse, np.concatenate([[hd, 0.0, 0.0, math.log(max(s, 1e-6)), t[0], t[1]], np.zeros(sk.n)])))
    starts.sort(key=lambda z: z[0])
    best: tuple[np.ndarray, float] | None = None
    for _, x0 in starts[:3]:
        x, c = _solve_frame(sk, x0, glob, fr, sigma, None, step, prior)
        if best is None or c < best[1]:
            best = (x, c)
    assert best is not None
    return best


def mirror_pose(sk: Skeleton, x: np.ndarray) -> np.ndarray:
    """The mirror-image pose (depth flipped, left and right exchanged): same projection with L/R labels swapped,
    exactly so while the camera is level."""
    m = x.copy()
    m[..., 0] = -x[..., 0]
    m[..., 2] = -x[..., 2]
    m[..., N_POSE:] = x[..., N_POSE:][..., sk.mirror_joint]
    return m


# ---------------------------------------------------------------------- the whole video
def _observations(tracks: KeypointTracks, sk: Skeleton, lmap: LiftMap) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """obs [F, L, 2] (NaN = not seen), weights [F, L] and raw likelihoods [F, L] of the map's landmarks."""
    F, L = tracks.frames, len(sk.names)
    obs = np.full((F, L, 2), np.nan)
    lk = np.zeros((F, L))
    for i, n in enumerate(sk.names):
        if tracks.has(n):
            obs[:, i] = tracks.point(n)
            lk[:, i] = np.nan_to_num(tracks.likelihood[:, tracks.index(n)])
    ok = (lk >= lmap.min_likelihood) & ~np.isnan(obs[:, :, 0])
    w = np.where(ok, lk * sk.weight[None], 0.0)
    return np.where(ok[..., None], obs, np.nan), w, lk


def _smooth(v: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or v.size == 0:
        return v
    pad = np.pad(v, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, np.ones(n) / n, "valid")


def _wrap(a: np.ndarray | float) -> Any:
    return (np.asarray(a) + math.pi) % (2 * math.pi) - math.pi


def _viterbi(unary: np.ndarray, switch: np.ndarray) -> np.ndarray:
    """States (0/1) minimising sum of unary [F,2] plus switch[t] when the state changes into frame t."""
    F = unary.shape[0]
    cost = unary[0].copy()
    back = np.zeros((F, 2), dtype=int)
    for t in range(1, F):
        new = np.empty(2)
        for s in (0, 1):
            stay, move = cost[s], cost[1 - s] + switch[t]
            back[t, s] = s if stay <= move else 1 - s
            new[s] = min(stay, move) + unary[t, s]
        cost = new
    out = np.zeros(F, dtype=int)
    out[-1] = int(np.argmin(cost))
    for t in range(F - 1, 0, -1):
        out[t - 1] = back[t, out[t]]
    return out


def _global_solve(sk: Skeleton, X0: np.ndarray, g0: np.ndarray, frames: list[_Frame], sigma: float, step: np.ndarray,
                  prior: LiftPrior, free_globals: list[int], temporal: bool, g_prior: Callable[[np.ndarray], np.ndarray],
                  max_nfev: int = 40, width_tie: float | None = None) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    """Refine every frame's pose (and the chosen globals) together. Returns poses, globals, cost, m, n."""
    from scipy.optimize import least_squares

    F, npar = X0.shape
    ng = len(free_globals)
    L = len(sk.names)
    obs = np.stack([f.obs for f in frames])
    w = np.stack([f.w for f in frames])
    n_prior = _priors(sk, X0[:1], prior).shape[1]
    n_temp = 4 + sk.n
    n_gp = len(g_prior(g0))

    def unpack(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        g = g0.copy()
        g[free_globals] = z[:ng]
        if width_tie is not None:  # the width follows the length (a prior ratio)
            g[1] = g[0] + width_tie
        return z[ng:].reshape(F, npar), g

    def fun(z: np.ndarray) -> np.ndarray:
        X, g = unpack(z)
        uv = project(sk, X, g)
        data = np.nan_to_num((uv - obs) * np.sqrt(w)[:, :, None] / sigma).reshape(-1)
        parts = [data, _priors(sk, X, prior).reshape(-1)]
        if temporal and F > 1:
            dv = X[1:] - X[:-1]
            dv[:, 0] = _wrap(dv[:, 0])
            parts.append((np.concatenate([dv[:, :4], dv[:, N_POSE:]], axis=1) / step[None]).reshape(-1))
        parts.append(g_prior(g))
        return np.concatenate(parts)

    m = F * L * 2 + F * n_prior + ((F - 1) * n_temp if temporal and F > 1 else 0) + n_gp
    n = ng + F * npar
    hx = _steps(npar)
    hg = 1e-4
    tcols = [0, 1, 2, 3] + list(range(N_POSE, npar))
    rows_t = np.arange(n_temp)
    p0 = F * L * 2
    t0 = p0 + F * n_prior
    gp0 = t0 + ((F - 1) * n_temp if temporal and F > 1 else 0)
    # the fixed parts of the Jacobian: temporal differences are linear
    t_rows: list[np.ndarray] = []
    t_cols: list[np.ndarray] = []
    t_vals: list[np.ndarray] = []
    if temporal and F > 1:
        for f in range(F - 1):
            r = t0 + f * n_temp + rows_t
            t_rows += [r, r]
            t_cols += [ng + f * npar + np.array(tcols), ng + (f + 1) * npar + np.array(tcols)]
            t_vals += [-1.0 / step, 1.0 / step]

    def jac(z: np.ndarray) -> Any:
        from scipy.sparse import coo_matrix

        X, g = unpack(z)
        Xp = np.repeat(X[:, None], npar + 1, axis=1)
        Xp[:, 1:] += np.diag(hx)[None]
        uvp = project(sk, Xp.reshape(-1, npar), g).reshape(F, npar + 1, L, 2)
        rd = np.nan_to_num((uvp - obs[:, None]) * np.sqrt(w)[:, None, :, None] / sigma).reshape(F, npar + 1, L * 2)
        Jd = (rd[:, 1:] - rd[:, :1]) / hx[None, :, None]  # [F, npar, L*2]
        pr = _priors(sk, Xp.reshape(-1, npar), prior).reshape(F, npar + 1, n_prior)
        Jp = (pr[:, 1:] - pr[:, :1]) / hx[None, :, None]  # [F, npar, n_prior]
        rows, cols, vals = [], [], []
        fr = np.arange(F)[:, None, None]
        kk = np.arange(npar)[None, :, None]
        rr = np.arange(L * 2)[None, None, :]
        rows.append((fr * L * 2 + rr + 0 * kk).ravel())
        cols.append((ng + fr * npar + kk + 0 * rr).ravel())
        vals.append(Jd.ravel())
        rp = np.arange(n_prior)[None, None, :]
        rows.append((p0 + fr * n_prior + rp + 0 * kk).ravel())
        cols.append((ng + fr * npar + kk + 0 * rp).ravel())
        vals.append(Jp.ravel())
        if ng:
            r0 = rd[:, 0].reshape(-1)
            gz = z[:ng]
            gp_0 = g_prior(g)
            for k in range(ng):
                z2 = z.copy()
                z2[k] = gz[k] + hg
                _, g2 = unpack(z2)
                rd2 = np.nan_to_num((project(sk, X, g2) - obs) * np.sqrt(w)[:, :, None] / sigma).reshape(-1)
                rows.append(np.arange(F * L * 2))
                cols.append(np.full(F * L * 2, k))
                vals.append((rd2 - r0) / hg)
                if n_gp:
                    rows.append(gp0 + np.arange(n_gp))
                    cols.append(np.full(n_gp, k))
                    vals.append((g_prior(g2) - gp_0) / hg)
        rows += t_rows
        cols += t_cols
        vals += t_vals
        return coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(m, n)).tocsr()

    lo1, hi1 = _bounds(sk)
    glo = np.concatenate([[math.log(0.4), math.log(0.15), math.log(0.4), -u.deg_to_rad(75), -u.deg_to_rad(30)],
                          sk.fit_lo])
    ghi = np.concatenate([[math.log(2.5), math.log(4.0), math.log(2.5), u.deg_to_rad(75), u.deg_to_rad(30)],
                          sk.fit_hi])
    lo = np.concatenate([glo[free_globals], np.tile(lo1, F)])
    hi = np.concatenate([ghi[free_globals], np.tile(hi1, F)])
    z0 = np.clip(np.concatenate([g0[free_globals], X0.reshape(-1)]), lo + 1e-9, hi - 1e-9)
    res = least_squares(fun, z0, jac=jac, bounds=(lo, hi), loss="soft_l1", f_scale=2.0, max_nfev=max_nfev,
                        tr_solver="lsmr", x_scale="jac")
    X, g = unpack(res.x)
    return X, g, float(res.cost), m, n


class LiftResult(BaseModel):
    """Everything the lift found; per-frame lists have one entry per frame. JSON-able (stored per video)."""

    map: str
    fps: float
    frames: int
    joint_ids: list[str]
    joints_deg: dict[str, list[float]]  # absolute joint angles of the fitted robot skeleton
    heading_deg: list[float]  # unwrapped; + = turning left (counter-clockwise seen from above)
    pitch_deg: list[float]  # trunk, nose down +
    roll_deg: list[float]
    view_yaw_deg: list[float]  # from the nearest side view; + = turned toward the camera
    near_side: list[str]
    scale_px_per_mm: list[float]
    root_mm: list[tuple[float, float, float]]  # trunk origin in a ground frame fixed to the camera (z = height)
    residual_px: list[float | None]  # None = no confident point
    residual_bl: list[float | None]
    points: list[int]
    state: list[str]  # ok | ambiguous | unreliable | missing
    reasons: list[list[str]]
    ambiguous: list[list[str]]
    unobservable: list[list[str]]
    hypothesis: list[int]  # +1 labels as tracked, -1 left/right exchanged (the depth flip)
    swapped: list[list[str]]  # leg pairs whose labels were exchanged in this frame
    legs_seen: dict[str, list[bool]] = Field(default_factory=dict)  # leg -> at least two of its points tracked
    camera: dict[str, Any]
    proportions: dict[str, Any]
    summary: dict[str, Any]
    settings: dict[str, Any]

    def reliable(self) -> np.ndarray:
        return np.array([s in ("ok", "ambiguous") for s in self.state])


def lift(tracks: KeypointTracks, lmap: LiftMap, spec: RobotSpec, settings: LiftSettings | None = None,
         report: Callable[[float, str], None] | None = None, cancelled: Callable[[], bool] | None = None) -> LiftResult:
    """Fit the body's skeleton and a camera to every frame of tracked keypoints."""
    s = settings or LiftSettings()
    sk = Skeleton(spec, lmap)
    prior = lmap.prior
    F, fps = tracks.frames, tracks.fps
    if F == 0:
        raise ValueError("No frames to lift")
    obs, w, lk = _observations(tracks, sk, lmap)
    npts = (w > 0).sum(axis=1)
    usable = np.where(npts >= max(3, s.min_points))[0]
    if usable.size == 0:
        raise ValueError(f"No frame has {s.min_points} confident landmarks of map {lmap.name}")
    step = np.concatenate([np.full(3, u.deg_to_rad(s.turn_speed_sd_deg_s) / fps), [s.scale_rate_sd / fps],
                           np.where(sk.is_abd, u.deg_to_rad(s.abduction_speed_sd_deg_s),
                                    u.deg_to_rad(s.joint_speed_sd_deg_s)) / fps])

    def say(frac: float, msg: str) -> None:
        if report is not None:
            report(frac, msg)
        if cancelled is not None and cancelled():
            from calflab.plugins import TrackerCancelled

            raise TrackerCancelled("cancelled")

    w_rel = math.log(prior.width_over_length * sk.length_mm / sk.width_mm)  # the prior's log(width ratio / length ratio)
    g = sk.initial_globals()
    if s.fit_proportions:
        g[:3] = _initial_ratios(sk, obs, w, w_rel, g)
    L_idx = [sk.names.index(a) for a, _ in sk.pairs]
    R_idx = [sk.names.index(b) for _, b in sk.pairs]
    win = max(1, int(round(fps * 0.5)))
    cue = _smooth(lk[:, L_idx].mean(axis=1) - lk[:, R_idx].mean(axis=1), win) if L_idx else np.zeros(F)
    x_prev: np.ndarray | None = None
    perm_prev: np.ndarray | None = None
    sigma_hint: float | None = None
    width_source, width_sd = "fitted", None
    rounds = 2 if s.fit_proportions else 1
    for rnd in range(rounds):
        # ---- A: frame by frame, labels as tracked, camera level (the trunk's tilt takes the camera's for now)
        ga = g.copy()
        ga[3:5] = 0.0
        def say_a(frac: float, msg: str, r: int = rnd) -> None:
            say((0.05 + 0.4 * frac) / rounds + 0.45 * r / rounds, msg)

        x_a, perm, swapped, body_px, sigma = _stage_a(sk, ga, obs, w, npts, step, prior, s, x_prev, say_a, sigma_hint,
                                                      perm_prev)
        perm_prev = perm.copy()
        sigma_hint = sigma
        # ---- B: toward or away (labels as tracked vs exchanged with the mirror pose), by confidence and continuity
        near_left = np.cos(x_a[:, 0]) > 0  # under "as tracked", the robot's near side
        support = np.where(near_left, cue, -cue)  # + = the tracker's more confident side is near
        unary = np.stack([-support / 0.05, support / 0.05], axis=1)
        jump = np.abs(_wrap(2 * x_a[:, 0])) / u.deg_to_rad(10.0)
        hyp = np.where(_viterbi(unary, 3.0 + jump) == 0, 1, -1)
        X = x_a.copy()
        flip = hyp < 0
        X[flip] = mirror_pose(sk, x_a[flip])
        perm[flip] = perm[flip][:, sk.swap]
        frames = [_Frame(obs[f][perm[f]], w[f][perm[f]]) for f in range(F)]
        say(0.45 + 0.1 * (rnd + 1) / rounds, "Fitting proportions and camera")
        # ---- C1: proportions and camera from a sample of good frames
        g_old = g.copy()
        g, X, width_source, width_sd, g_alt = _calibrate(sk, X, g, frames, usable, sigma, step, prior, s, w_rel, body_px)
        x_prev = X.copy()
        x_prev[flip] = mirror_pose(sk, X[flip])  # back to the labels as tracked, which the next round starts from
        if rnd + 1 < rounds and np.max(np.abs(np.delete(g - g_old, [3, 4]))) < 0.05:
            break  # the proportions barely moved: no second round needed
    say(0.7, "Smoothing over time")
    # ---- C2: every frame with proportions and camera fixed, smoothed over time (in windows)
    X_in = X
    X = _windows(sk, X_in, g, frames, sigma, step, prior, s.window_frames)
    if width_source == "fitted" and g_alt is not None:
        # the width the footage chose must also fit the whole smoothed video clearly better than the prior's
        X2 = _windows(sk, X_in, g_alt, frames, sigma, step, prior, s.window_frames)
        rf, rp = _rms_px(sk, X, g, frames), _rms_px(sk, X2, g_alt, frames)
        log.info("width over the video: free %.2f px, prior %.2f px", rf, rp)
        if (rp - rf) / max(rp, 1e-9) < s.min_width_gain:
            X, g, width_source = X2, g_alt, "prior"
    say(0.85, "Checking ambiguities")
    # ---- D: diagnostics
    return _finish(sk, lmap, tracks, s, X, g, frames, hyp, swapped, cue, npts, sigma, body_px, width_source,
                   width_sd, step, prior)


def _initial_ratios(sk: Skeleton, obs: np.ndarray, w: np.ndarray, w_rel: float, g0: np.ndarray) -> np.ndarray:
    """Log ratios (trunk length, width, front leg) from the tracked segment lengths against the robot's: the
    90th percentile of hip-to-shoulder and root-to-hoof distances over the video (foreshortening only shortens)."""
    rest = sk.points(np.zeros((1, sk.n)), g0)[0]
    out = np.zeros(3)

    def seg(a: list[int], b: list[int]) -> tuple[float, float]:
        img, rob = [], []
        for i, j in zip(a, b, strict=False):
            ok = (w[:, i] > 0) & (w[:, j] > 0)
            if ok.sum() >= 3:
                img.append(np.percentile(np.linalg.norm(obs[ok, i] - obs[ok, j], axis=1), 90))
                rob.append(np.linalg.norm(rest[i] - rest[j]))
        return (float(np.mean(img)), float(np.mean(rob))) if img else (float("nan"), float("nan"))

    roots = {g: [i for i, r in enumerate(sk.role) if r == ("root", g)] for g in ("hind", "front")}
    feet = {g: [i for i, r in enumerate(sk.role) if r == ("foot", g)] for g in ("hind", "front")}

    def same_side(a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
        pa = [(i, j) for i in a for j in b if sk.side_of[i] == sk.side_of[j]]
        return [i for i, _ in pa], [j for _, j in pa]

    hind_img, hind_rob = seg(*same_side(roots["hind"], feet["hind"]))
    trunk_img, trunk_rob = seg(*same_side(roots["hind"], roots["front"]))
    front_img, front_rob = seg(*same_side(roots["front"], feet["front"]))
    if all(math.isfinite(v) and v > 0 for v in (hind_img, hind_rob, trunk_img, trunk_rob)):
        out[0] = math.log((trunk_img / hind_img) / (trunk_rob / hind_rob))
    if all(math.isfinite(v) and v > 0 for v in (hind_img, hind_rob, front_img, front_rob)):
        out[2] = math.log((front_img / hind_img) / (front_rob / hind_rob))
    out = np.clip(out, math.log(0.45), math.log(2.4))
    out[1] = out[0] + w_rel
    return out


def _stage_a(sk: Skeleton, glob: np.ndarray, obs: np.ndarray, w: np.ndarray, npts: np.ndarray, step: np.ndarray,
             prior: LiftPrior, s: LiftSettings, x_init: np.ndarray | None, say: Callable[[float, str], None],
             sigma_hint: float | None = None, perm_init: np.ndarray | None = None
             ) -> tuple[np.ndarray, np.ndarray, list[list[str]], float, float]:
    """Each frame in turn, from the previous one (or ``x_init``), a fresh start where that fits badly, and a
    leg pair's labels exchanged where that fits much better. Returns poses, landmark permutations, swapped leg
    pairs, the median body length in px and the noise scale."""
    F = obs.shape[0]
    usable = np.where(npts >= max(3, s.min_points))[0]
    x_a = np.zeros((F, N_POSE + sk.n))
    swapped: list[list[str]] = [[] for _ in range(F)]
    perm = np.tile(np.arange(len(sk.names)), (F, 1)) if perm_init is None else perm_init.copy()
    if perm_init is not None:  # a later round keeps the leg pairs found exchanged
        leg_of = {tuple(sorted(idx.tolist())): pair for pair, idx in _leg_pairs(sk).items()}
        for f in range(F):
            for key, pair in leg_of.items():
                if np.any(perm[f][list(key)] != np.array(key)):
                    swapped[f].append(pair)
    first = int(usable[0])
    if x_init is not None:
        x0 = x_init[first]
    else:
        x0, _ = _global_init(sk, glob, _Frame(obs[first], w[first]), 1.0, step, prior)
    body_px = math.exp(x0[3]) * sk.length_mm * math.exp(glob[0])
    sigma = max(1.0, s.noise_bl * body_px, sigma_hint or 0.0)
    prev: np.ndarray | None = None
    leg_pairs = _leg_pairs(sk)
    for f in range(F):
        if f % 10 == 0:
            say(f / F, f"Lifting frame {f}/{F}")
        if npts[f] < 3:
            x_a[f] = prev if prev is not None else x0
            continue
        fr = _Frame(obs[f][perm[f]], w[f][perm[f]])
        if prev is None and x_init is None:
            x, c = _global_init(sk, glob, fr, sigma, step, prior)
        elif x_init is not None:  # a later round: refine the previous round's answer
            x, c = _solve_frame(sk, x_init[f], glob, fr, sigma, prev, step, prior, max_nfev=30)
        else:
            start = prev
            assert start is not None
            x, c = _solve_frame(sk, start, glob, fr, sigma, prev, step, prior, max_nfev=30)
            # the same frame turned the other way (toward / away with the labels kept): a flip the noise invites
            other = start.copy()
            other[0] = -start[0] if abs(math.cos(start[0])) > 0.5 else math.pi - start[0]
            x2, c2 = _solve_frame(sk, other, glob, fr, sigma, prev, step, prior, max_nfev=30)
            if c2 < c:
                x, c = x2, c2
            if _rms_bl(sk, x, glob, fr, body_px) > s.max_residual_bl:
                x2, _ = _global_init(sk, glob, fr, sigma, step, prior)
                x2, c2 = _solve_frame(sk, x2, glob, fr, sigma, prev, step, prior)  # judged with continuity too
                if c2 < c * 0.8:
                    x, c = x2, c2
        if x_init is None and _rms_bl(sk, x, glob, fr, body_px) > s.max_residual_bl:
            for pair, idx in leg_pairs.items():  # the tracker may have exchanged a pair of legs
                if (w[f][idx] > 0).sum() < len(idx):
                    continue
                p2 = np.arange(len(sk.names))
                p2[idx] = sk.swap[idx]
                fr2 = _Frame(obs[f][p2], w[f][p2])
                x2, c2 = _solve_frame(sk, x, glob, fr2, sigma, prev, step, prior)
                if c2 < 0.7 * c:
                    x, c, fr = x2, c2, fr2
                    perm[f] = p2
                    swapped[f].append(pair)
        x_a[f] = x
        prev = x
    body_px = float(np.median(np.exp(x_a[usable, 3]))) * sk.length_mm * math.exp(glob[0])
    # the noise scale: the expected keypoint noise, or what the footage shows if that is larger (real trackers
    # are noisier than the setting; otherwise the data would overpower every prior and smoothness)
    seen = float(np.median([_rms_bl(sk, x_a[f], glob, _Frame(obs[f][perm[f]], w[f][perm[f]]), body_px)
                            for f in usable])) * body_px
    return x_a, perm, swapped, body_px, max(1.0, s.noise_bl * body_px, seen)


def _calibrate(sk: Skeleton, X: np.ndarray, g: np.ndarray, frames: list[_Frame], usable: np.ndarray, sigma: float,
               step: np.ndarray, prior: LiftPrior, s: LiftSettings, w_rel: float, body_px: float
               ) -> tuple[np.ndarray, np.ndarray, str, float | None, np.ndarray | None]:
    """Proportions and camera elevation/roll from a sample of good frames; whether the width is pinned."""
    g_level = g.copy()
    g_level[3:5] = 0.0
    good = [f for f in usable if _rms_bl(sk, X[f], g_level, frames[f], body_px)
            < 2 * s.max_residual_bl]
    if len(good) < 5:
        good = list(usable)
    pick = np.unique(np.array(good)[np.linspace(0, len(good) - 1, min(len(good), s.calibration_frames)).astype(int)])
    sub = [frames[f] for f in pick]

    ats = list(range(N_GLOBAL, sk.n_global))

    def g_prior_free(gg: np.ndarray) -> np.ndarray:
        return np.concatenate([[gg[0] / prior.segment_sd, gg[2] / prior.segment_sd,
                                (gg[1] - gg[0] - w_rel) / prior.width_sd], (gg[N_GLOBAL:] - sk.fit_init) / 0.5])

    def g_prior_fixed(gg: np.ndarray) -> np.ndarray:
        return np.concatenate([[gg[0] / prior.segment_sd, gg[2] / prior.segment_sd], (gg[N_GLOBAL:] - sk.fit_init) / 0.5])

    free_g = ([0, 1, 2, 3, 4] if s.fit_proportions else [3, 4]) + ats
    X_in, g_in = X[pick].copy(), g.copy()
    Xc, g, c0, m, n = _global_solve(sk, X[pick], g, sub, sigma, step, prior, free_g, False, g_prior_free)
    width_source, width_sd = "fitted", None
    g_alt: np.ndarray | None = None
    if s.fit_proportions:
        # how well does the footage pin the width? profile the cost along log width
        dz = 0.2
        costs = []
        for sgn in (-1.0, 1.0):
            g2 = g.copy()
            g2[1] += sgn * dz
            _, _, c2, _, _ = _global_solve(sk, Xc, g2, sub, sigma, step, prior, [0, 2, 3, 4] + ats, False,
                                           g_prior_free, max_nfev=15)
            costs.append(c2)
        # what the footage alone says: the profile's curvature less the prior's own
        curv = max((costs[0] + costs[1] - 2 * c0) / dz ** 2 - 1.0 / prior.width_sd ** 2, 1e-9)
        noise = max(1.0, 2 * c0 / max(m - n, 1))
        width_sd = math.sqrt(noise / curv)
        # and does a free width fit clearly better than the prior's? (systematic misfit can feign a pinned width)
        gp = g_in.copy()  # from where the free fit started, not from its answer (a separate basin)
        gp[1] = gp[0] + w_rel
        Xp, gp, _, _, _ = _global_solve(sk, X_in, gp, sub, sigma, step, prior, [0, 2, 3, 4] + ats, False,
                                        g_prior_fixed, width_tie=w_rel)
        rms_free, rms_prior = _rms_px(sk, Xc, g, sub), _rms_px(sk, Xp, gp, sub)
        gain = (rms_prior - rms_free) / max(rms_prior, 1e-9)
        log.info("width: free %.3f px vs prior %.3f px (gain %.3f), data sd %.3f", rms_free, rms_prior, gain, width_sd)
        if width_sd > min(s.max_width_rel_sd, prior.width_sd) or gain < s.min_width_gain:
            width_source = "prior"
            Xc, g = Xp, gp
        else:
            g_alt = gp  # checked again on the whole smoothed video
    else:
        width_source = "robot"
    X = X.copy()
    X[pick] = Xc
    return g, X, width_source, width_sd, g_alt


def _rms_px(sk: Skeleton, X: np.ndarray, g: np.ndarray, frames: list[_Frame]) -> float:
    obs = np.stack([f.obs for f in frames])
    ok = np.stack([f.w for f in frames]) > 0
    e = np.linalg.norm(project(sk, X, g) - obs, axis=2)
    return float(np.sqrt(np.mean(e[ok] ** 2))) if ok.any() else float("nan")


def _leg_pairs(sk: Skeleton) -> dict[str, np.ndarray]:
    """Landmark indices of each left/right leg pair that has its own landmarks (hind, fore)."""
    out: dict[str, list[int]] = {}
    for a, b in sk.pairs:
        ia, ib = sk.names.index(a), sk.names.index(b)
        legs = [leg for leg, (_, lms) in sk.legs.items() if ia in lms]
        if legs:
            key = {"h": "hind", "f": "fore"}.get(legs[0][0], legs[0][0])
            out.setdefault(key, []).extend([ia, ib])
    return {k: np.array(v) for k, v in out.items()}


def _rms_bl(sk: Skeleton, x: np.ndarray, glob: np.ndarray, fr: _Frame, body_px: float) -> float:
    uv = project(sk, x[None], glob)[0]
    ok = fr.w > 0
    if not ok.any():
        return float("inf")
    e = np.linalg.norm(uv[ok] - fr.obs[ok], axis=1)
    return float(np.sqrt(np.mean(e ** 2)) / max(body_px, 1e-9))


def _windows(sk: Skeleton, X: np.ndarray, g: np.ndarray, frames: list[_Frame], sigma: float, step: np.ndarray,
             prior: LiftPrior, size: int) -> np.ndarray:
    F = X.shape[0]
    out = X.copy()
    overlap = min(30, size // 4)
    start = 0
    while start < F:
        end = min(F, start + size)
        Xw, _, _, _, _ = _global_solve(sk, out[start:end], g, frames[start:end], sigma, step, prior, [], True,
                                       lambda gg: np.zeros(0))
        keep = start if start == 0 else start + overlap // 2
        out[keep:end] = Xw[keep - start:]
        if end >= F:
            break
        start = end - overlap
    return out


def _finish(sk: Skeleton, lmap: LiftMap, tracks: KeypointTracks, s: LiftSettings, X: np.ndarray, g: np.ndarray,
            frames: list[_Frame], hyp: np.ndarray, swapped: list[list[str]], cue: np.ndarray, npts: np.ndarray,
            sigma: float, body_px_med: float, width_source: str, width_sd: float | None, step: np.ndarray,
            prior: LiftPrior) -> LiftResult:
    F, fps = X.shape[0], tracks.fps
    obs = np.stack([f.obs for f in frames])
    w = np.stack([f.w for f in frames])
    uv = project(sk, X, g)
    err = np.linalg.norm(uv - obs, axis=2)
    res_px = np.array([float(np.sqrt(np.mean(err[f][w[f] > 0] ** 2))) if (w[f] > 0).any() else float("nan")
                       for f in range(F)])
    body_px = np.exp(X[:, 3]) * sk.length_mm * math.exp(g[0])
    res_bl = res_px / body_px
    heading = np.unwrap(X[:, 0])
    view_yaw = np.arctan2(np.sin(X[:, 0]), np.abs(np.cos(X[:, 0])))
    # observability of each free joint: image motion of a 10 deg change, in body lengths
    h = u.deg_to_rad(10.0)
    unobs: list[list[str]] = [[] for _ in range(F)]
    for i in range(sk.n):
        Xp = X.copy()
        Xp[:, N_POSE + i] = np.clip(Xp[:, N_POSE + i] + h, sk.free_lo[i], sk.free_hi[i])
        Xm = X.copy()
        Xm[:, N_POSE + i] = np.clip(Xm[:, N_POSE + i] - h, sk.free_lo[i], sk.free_hi[i])
        mv = np.linalg.norm(project(sk, Xp, g) - project(sk, Xm, g), axis=2).max(axis=1) / 2.0
        for f in np.where(mv / body_px < 0.02)[0]:
            unobs[f].append(sk.free_ids[i])
    # limb flips: a second minimum within a leg's ranges, far from the chosen angles
    amb: list[list[str]] = [[] for _ in range(F)]
    for leg, (ji, li) in sk.legs.items():
        if not li:
            continue
        grids = [np.linspace(sk.free_lo[j], sk.free_hi[j], max(3, int(round(
            u.rad_to_deg(sk.free_hi[j] - sk.free_lo[j]) / (5.0 if len(ji) <= 2 else 10.0))) + 1)) for j in ji]
        shape = tuple(len(gr) for gr in grids)
        mesh = np.stack(np.meshgrid(*grids, indexing="ij"), axis=-1).reshape(-1, len(ji))
        for f in range(F):
            wl = w[f][li]
            if (wl > 0).sum() < 2:
                continue
            Xg = np.repeat(X[f][None], mesh.shape[0], axis=0)
            Xg[:, [N_POSE + j for j in ji]] = mesh
            pg = project(sk, Xg, g)[:, li]
            cg = np.nansum(((pg - obs[f][li][None]) ** 2).sum(axis=2) * wl[None], axis=1) / sigma ** 2
            c_star = float(np.nansum(((uv[f][li] - obs[f][li]) ** 2).sum(axis=1) * wl) / sigma ** 2)
            # a second basin (a local minimum of the grid), far from the chosen angles and nearly as good
            from scipy.ndimage import minimum_filter

            local = (cg.reshape(shape) <= minimum_filter(cg.reshape(shape), size=3, mode="nearest")).reshape(-1)
            far = np.abs(mesh - X[f][[N_POSE + j for j in ji]][None]).max(axis=1) > u.deg_to_rad(20.0)
            alt = far & local
            if alt.any() and float(cg[alt].min()) <= c_star + 4.0:
                amb[f].append(leg)
    # reliability: a frame fails where its residual stands out from the video's own (or is plainly too large)
    med_bl = float(np.nanmedian(res_bl)) if np.any(~np.isnan(res_bl)) else 0.0
    res_limit = min(s.max_residual_bl, max(0.05, s.relative_residual * med_bl))
    state: list[str] = []
    reasons: list[list[str]] = []
    ambiguous: list[list[str]] = []
    for f in range(F):
        why = []
        if npts[f] == 0:
            state.append("missing")
            reasons.append(["no animal points"])
            ambiguous.append([])
            continue
        if npts[f] < s.min_points:
            why.append(f"{int(npts[f])} confident points (need {s.min_points})")
        if not np.isnan(res_bl[f]) and res_bl[f] > res_limit:
            why.append(f"fit residual {res_bl[f]:.3f} body lengths (limit {res_limit:.3f})")
        if abs(u.rad_to_deg(view_yaw[f])) > s.max_view_yaw_deg:
            why.append(f"{'head' if view_yaw[f] > 0 else 'tail'}-on: {abs(u.rad_to_deg(view_yaw[f])):.0f} deg "
                       f"from a side view (limit {s.max_view_yaw_deg:g})")
        a = []
        if sk.pairs and abs(cue[f]) < s.min_cue:
            a.append("depth")
        a += [f"leg {leg}" for leg in amb[f]]
        state.append("unreliable" if why else ("ambiguous" if a else "ok"))
        reasons.append(why)
        ambiguous.append(a)
    # where the animal is: the trunk origin from the camera (weak perspective + an assumed field of view for depth)
    size = tracks.image_size
    sc = np.exp(X[:, 3])
    cam = camera_matrix(g[3], g[4])
    if size:
        f_px = (size[0] / 2.0) / math.tan(u.deg_to_rad(s.camera_hfov_deg) / 2.0)
        cx, cy = size[0] / 2.0, -size[1] / 2.0
        pc = np.stack([(X[:, 4] - cx) / sc, (X[:, 5] - cy) / sc, -f_px / sc], axis=1)
        depth_note = (f"Travel toward or away from the camera assumes a {s.camera_hfov_deg:g} deg horizontal field of "
                      "view (PROVISIONAL): it scales with that guess.")
    else:
        pc = np.stack([X[:, 4] / sc, X[:, 5] / sc, np.zeros(F)], axis=1)
        depth_note = "The image size is unknown, so travel toward or away from the camera is not measured."
    pw = pc @ cam  # camera -> world (cam is orthonormal: inverse = transpose)
    height = sk.ground_height(X[:, N_POSE:], X[:, 1], X[:, 2])
    root = [(float(pw[f, 0]), float(pw[f, 1]), float(height[f])) for f in range(F)]
    joints = sk.full_angles(X[:, N_POSE:])
    rel = np.array([st in ("ok", "ambiguous") for st in state])
    # camera: fixed unless the trunk's pitch or roll wander (which a tilting camera would cause)
    tilt_sd = float(np.std(u.rad_to_deg(X[rel, 1]))) if rel.any() else float("nan")
    roll_sd = float(np.std(u.rad_to_deg(X[rel, 2]))) if rel.any() else float("nan")
    fixed = not (tilt_sd > 8.0 or roll_sd > 8.0)
    camera = {
        "model": "weak perspective",
        "elevation_deg": round(u.rad_to_deg(float(g[3])), 2),
        "roll_deg": round(u.rad_to_deg(float(g[4])), 2),
        "hfov_deg_assumed": s.camera_hfov_deg,
        "fixed": fixed,
        "trunk_pitch_sd_deg": None if math.isnan(tilt_sd) else round(tilt_sd, 2),
        "trunk_roll_sd_deg": None if math.isnan(roll_sd) else round(roll_sd, 2),
        "note": ("Assumed fixed; the fit agrees (the trunk's pitch and roll stay steady)." if fixed else
                 "Assumed fixed, but the trunk's pitch or roll wander by more than 8 deg: the camera may tilt or "
                 "roll, or the animal does. A panning camera cannot be told from the animal turning."),
        "depth_note": depth_note,
        "perspective_note": ("Weak perspective: the body's depth is small against its distance. Full perspective "
                             "needs the lens's focal length, which one uncalibrated video does not give."),
    }
    r = np.exp(g[:3])
    proportions = {
        "trunk_length": round(float(r[0]), 3), "trunk_width": round(float(r[1]), 3), "front_leg": round(float(r[2]), 3),
        "hind_leg": 1.0,
        "width_over_length": round(float(r[1] / r[0] * sk.width_mm / sk.length_mm), 3),
        "width_source": width_source,
        "width_rel_sd": None if width_sd is None else round(width_sd, 3),
        "fitted": s.fit_proportions,
        "note": ("Segments of the animal against the robot's, relative to the hind leg (1). "
                 + ("The width was fitted from the footage." if width_source == "fitted" else
                    f"The footage does not pin the width (uncertainty {width_sd:.0%}); it comes from the prior "
                    f"width/length {prior.width_over_length:g} of a calf (PROVISIONAL)." if width_sd is not None else
                    "Proportions were not fitted (the robot's own).")),
        "px_per_mm_median": round(float(np.median(sc[rel])) if rel.any() else float(np.median(sc)), 4),
        # where the fit put landmarks whose place on the robot is not known (0 = the first joint, 1 = the second)
        "landmark_at": {k: round(float(g[N_GLOBAL + i]), 3) for i, k in enumerate(sk.fit_keys)},
    }
    vy = u.rad_to_deg(view_yaw)
    hd = u.rad_to_deg(heading)
    summary = {
        "reliable_fraction": round(float(np.mean(rel)), 3),
        "ambiguous_fraction": round(float(np.mean([st == "ambiguous" for st in state])), 3),
        "median_view_yaw_deg": round(float(np.median(vy[rel])), 1) if rel.any() else None,
        "view_yaw_range_deg": [round(float(vy.min()), 1), round(float(vy.max()), 1)],
        "heading_range_deg": [round(float(hd.min() - hd[0]), 1), round(float(hd.max() - hd[0]), 1)],
        "near_side": "left" if np.mean(np.cos(X[rel if rel.any() else slice(None), 0]) > 0) >= 0.5 else "right",
        "hypothesis_switches": int(np.sum(np.diff(hyp) != 0)),
        "labels_exchanged_fraction": round(float(np.mean(hyp < 0)), 3),
        "legs_swapped_frames": int(sum(1 for x in swapped if x)),
        "median_residual_px": round(float(np.nanmedian(res_px)), 2),
        # where the robot's skeleton cannot follow the tracked points (a map assumption to check, or noise)
        "landmark_residual_px": {n: round(float(np.median(err[w[:, i] > 0, i])), 1) for i, n in enumerate(sk.names)
                                 if (w[:, i] > 0).any()},
        "unobservable_fraction": {j: round(float(np.mean([j in x for x in unobs])), 3) for j in sk.free_ids},
        "body_px_median": round(body_px_med, 1),
    }
    return LiftResult(
        map=lmap.name, fps=fps, frames=F, joint_ids=sk.joint_ids,
        joints_deg={j: [round(u.rad_to_deg(float(v)), 3) for v in joints[:, k]] for k, j in enumerate(sk.joint_ids)},
        heading_deg=[round(float(v), 3) for v in hd], pitch_deg=[round(u.rad_to_deg(float(v)), 3) for v in X[:, 1]],
        roll_deg=[round(u.rad_to_deg(float(v)), 3) for v in X[:, 2]], view_yaw_deg=[round(float(v), 2) for v in vy],
        near_side=["left" if c > 0 else "right" for c in np.cos(X[:, 0])],
        scale_px_per_mm=[round(float(v), 5) for v in sc], root_mm=root,
        residual_px=[round(float(v), 2) if not np.isnan(v) else None for v in res_px],
        residual_bl=[round(float(v), 4) if not np.isnan(v) else None for v in res_bl],
        points=[int(v) for v in npts], state=state, reasons=reasons, ambiguous=ambiguous, unobservable=unobs,
        hypothesis=[int(v) for v in hyp], swapped=swapped,
        legs_seen={leg: [bool((w[f][li] > 0).sum() >= min(2, len(li))) for f in range(F)]
                   for leg, (_, li) in sk.legs.items() if li},
        camera=camera, proportions=proportions, summary=summary,
        settings=s.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------- from a lift to clips
def _interp_gaps(v: np.ndarray, bad: np.ndarray) -> np.ndarray:
    """Values in ``bad`` frames replaced by linear interpolation between the good ones (held at the ends)."""
    if not bad.any() or bad.all():
        return v
    idx = np.arange(v.size)
    return np.interp(idx, idx[~bad], v[~bad])


def ground_heights(spec: RobotSpec, angles: dict[str, np.ndarray], pitch_deg: np.ndarray, roll_deg: np.ndarray
                   ) -> np.ndarray:
    """Height (mm) of the trunk origin above the lowest hoof, the robot posed at ``angles`` (absolute deg per
    joint and frame) and tilted by the trunk's pitch and roll."""
    n = len(pitch_deg)
    rest = spec.rest_angles()
    feet = [(b.id, g.pos, g.size[0]) for b in spec.bodies for g in b.geoms if g.foot]
    out = np.full(n, spec.root.pos[2])
    if not feet:
        return out
    tilt = _ry(u.deg_to_rad(np.asarray(pitch_deg))) @ _rx(u.deg_to_rad(np.asarray(roll_deg)))
    for f in range(n):
        full = {j: float(angles[j][f]) if j in angles else v for j, v in rest.items()}
        poses = spec.world_poses(full, root_pos=(0.0, 0.0, 0.0))
        zs = []
        for bid, gp, r in feet:
            bp, bq = poses[bid]
            p = np.array(bp) + quat_to_matrix(bq) @ np.array(gp)
            zs.append((tilt[f] @ p)[2] - r)
        out[f] = -min(zs)
    return out


def lift_clip(res: LiftResult, spec: RobotSpec, standing: int | None, name: str = "video") -> Any:
    """The whole video as a motion clip for this body: joint angles relative to the reference (the animal's
    standing frame, or, without one, the robot's own standing pose) applied to the robot's standing pose; the
    trunk's heading, pitch and roll; and its path on the ground. Unreliable frames are interpolated over.
    Per-frame lift data the cutting needs is kept in ``meta``."""
    from calflab.project.motions import MotionClip

    F = res.frames
    bad = ~res.reliable()
    rest = spec.rest_angles()
    hinge = {j.id for j in spec.joints if j.type == "hinge"}
    rel: dict[str, np.ndarray] = {}
    played: dict[str, np.ndarray] = {}
    for j in res.joint_ids:
        if j not in hinge:
            continue
        v = _interp_gaps(np.asarray(res.joints_deg[j], dtype=float), bad)
        ref = v[standing] if standing is not None else rest[j]
        rel[j] = v - ref
        played[j] = rest[j] + rel[j]
    heading = _interp_gaps(np.asarray(res.heading_deg, dtype=float), bad)
    pitch = _interp_gaps(np.asarray(res.pitch_deg, dtype=float), bad)
    roll = _interp_gaps(np.asarray(res.roll_deg, dtype=float), bad)
    if standing is not None:
        pitch, roll = pitch - pitch[standing], roll - roll[standing]
    xy = np.array([(p[0], p[1]) for p in res.root_mm], dtype=float)
    xy = np.stack([_interp_gaps(xy[:, 0], bad), _interp_gaps(xy[:, 1], bad)], axis=1)
    z = ground_heights(spec, played, pitch, roll)
    reference = (f"the animal's standing frame {standing}" if standing is not None else
                 "the robot's own standing pose (the video has no still stretch)")
    return MotionClip(
        name=name, fps=res.fps, joints={k: [round(float(x), 4) for x in v] for k, v in sorted(rel.items())},
        root_pos=[(float(xy[f, 0]), float(xy[f, 1]), float(z[f])) for f in range(F)],
        root_quat=_quats(heading - heading[0], pitch, roll), source="footage",
        meta={"lift": {"heading_deg": [round(float(v), 3) for v in heading], "pitch_deg": [round(float(v), 3) for v in pitch],
                       "roll_deg": [round(float(v), 3) for v in roll], "legs_seen": res.legs_seen,
                       "state": res.state, "near_side": res.summary.get("near_side", "left")},
              "reference": reference, "standing_frame": standing, "frames": F},
    )


def _quats(heading_deg: np.ndarray, pitch_deg: np.ndarray, roll_deg: np.ndarray) -> list[tuple[float, float, float, float]]:
    """(w, x, y, z) of Rz(heading) Ry(pitch) Rx(roll), per frame."""
    out = []
    for h, p, r in zip(u.deg_to_rad(heading_deg), u.deg_to_rad(pitch_deg), u.deg_to_rad(roll_deg), strict=True):
        ch, sh = math.cos(h / 2), math.sin(h / 2)
        cp, sp = math.cos(p / 2), math.sin(p / 2)
        cr, sr = math.cos(r / 2), math.sin(r / 2)
        out.append((ch * cp * cr + sh * sp * sr, ch * cp * sr - sh * sp * cr, ch * sp * cr + sh * cp * sr,
                    sh * cp * cr - ch * sp * sr))
    return out


def cut_lift(full: Any, start: int, end: int, name: str, far_side: str = "tracked", period_s: float | None = None
             ) -> Any:
    """Frames [start, end) of a lifted video as a clip: heading and ground path start at zero facing +x.

    ``far_side``: ``tracked`` keeps every leg as fitted, except a leg seen in under half the frames, which
    takes its other-side twin (half a period later in a gait); ``copy``, ``half_cycle`` or ``hold`` replace the
    far legs as the 2D mode does."""
    from calflab.project.motions import MotionClip

    if not 0 <= start < end <= full.frames:
        raise ValueError(f"Frame range {start}-{end} is outside the video (0-{full.frames})")
    lm = full.meta["lift"]
    near = "l" if lm.get("near_side", "left") == "left" else "r"
    far = "r" if near == "l" else "l"
    joints = {k: np.asarray(v[start:end], dtype=float) for k, v in full.joints.items()}
    period_frames = int(round((period_s or 0.0) * full.fps))
    seen = lm.get("legs_seen", {})
    legs: dict[str, str] = dict.fromkeys(seen, "tracked")
    for k in list(joints):
        leg, part = k.removeprefix("joint.").split(".", 1)
        if len(leg) != 2 or leg[1] not in "lr":
            continue
        twin_leg = leg[0] + ("r" if leg[1] == "l" else "l")
        twin = f"joint.{twin_leg}.{part}"
        if twin not in joints:
            continue
        frac = float(np.mean(seen[leg][start:end])) if leg in seen else 1.0
        frac_twin = float(np.mean(seen[twin_leg][start:end])) if twin_leg in seen else 1.0
        replace = (far_side in ("copy", "half_cycle", "hold") and leg[1] == far) or (
            far_side == "tracked" and frac < 0.5 <= frac_twin)
        if not replace:
            continue
        src = full.joints[twin][start:end]
        mode = far_side if far_side != "tracked" else ("half_cycle" if period_frames >= 2 else "copy")
        if mode == "hold":
            joints[k] = np.zeros(end - start)
        elif mode == "half_cycle":
            if period_frames < 2:
                raise ValueError("far_side half_cycle needs the gait's period")
            joints[k] = np.roll(np.asarray(src, dtype=float), period_frames // 2)
        else:
            joints[k] = np.asarray(src, dtype=float)
        legs[leg] = f"{mode} from {twin_leg}" + (f" (seen in {frac:.0%} of the frames)" if far_side == "tracked" else "")
    heading = np.asarray(lm["heading_deg"][start:end])
    h0 = u.deg_to_rad(heading[0])
    pos = np.array(full.root_pos[start:end], dtype=float)
    d = pos[:, :2] - pos[0, :2]
    c, s_ = math.cos(-h0), math.sin(-h0)
    xy = np.stack([c * d[:, 0] - s_ * d[:, 1], s_ * d[:, 0] + c * d[:, 1]], axis=1)
    quats = _quats(heading - heading[0], np.asarray(lm["pitch_deg"][start:end]), np.asarray(lm["roll_deg"][start:end]))
    states = lm.get("state", [])[start:end]
    return MotionClip(
        name=name, fps=full.fps, joints={k: [round(float(x), 4) for x in v] for k, v in sorted(joints.items())},
        root_pos=[(float(xy[i, 0]), float(xy[i, 1]), float(pos[i, 2])) for i in range(end - start)],
        root_quat=quats, source="footage",
        meta={"frames": end - start, "frame_range": [start, end], "far_side": far_side, "period_s": period_s,
              "near_side": "left" if near == "l" else "right", "legs": legs, "mode": "3d",
              "turn_deg": round(float(heading[-1] - heading[0]), 2),
              "heading_range_deg": [round(float(heading.min() - heading[0]), 2), round(float(heading.max() - heading[0]), 2)],
              "travel_mm": round(float(np.hypot(*(xy[-1] - xy[0]))), 1),
              "unreliable_frames": int(sum(1 for st in states if st in ("unreliable", "missing"))),
              "reference": full.meta.get("reference"), "standing_frame": full.meta.get("standing_frame")},
    )


# ---------------------------------------------------------------------- maps side by side
def compare_lifts(results: dict[str, LiftResult]) -> dict[str, Any]:
    """Lifts of one video with different maps, side by side (ADR-082): per map the reliable and ambiguous shares
    (and what made frames ambiguous), the median residual of every landmark (same tracks, so the same points),
    and the hind angles (stifle, hock) over the frames every map calls reliable. Degrees, px."""
    names = list(results)
    if not names:
        raise ValueError("No lifts to compare")
    frames = {r.frames for r in results.values()}
    if len(frames) != 1:
        raise ValueError(f"The lifts are of different lengths ({sorted(frames)} frames): not the same video")
    F = frames.pop()
    both = np.all(np.stack([r.reliable() for r in results.values()]), axis=0)
    summary, ambiguous, hind = {}, {}, {}
    for n, r in results.items():
        st = np.asarray(r.state)
        reasons: dict[str, float] = {}
        for a in r.ambiguous:
            for why in a:
                reasons[why] = reasons.get(why, 0.0) + 1.0 / F
        hind_only = np.mean([bool(a) and all(w in ("leg hl", "leg hr") for w in a) for a in r.ambiguous])
        summary[n] = {"reliable_fraction": round(float(np.mean(r.reliable())), 3),
                      "ambiguous_fraction": round(float(np.mean(st == "ambiguous")), 3),
                      "unreliable_fraction": round(float(np.mean(np.isin(st, ["unreliable", "missing"]))), 3),
                      "median_residual_px": r.summary.get("median_residual_px"),
                      "body_px_median": r.summary.get("body_px_median"),
                      "landmark_at": r.proportions.get("landmark_at", {}),
                      "proportions": {k: r.proportions.get(k) for k in ("trunk_length", "trunk_width", "front_leg")}}
        ambiguous[n] = {"by_reason": {k: round(v, 3) for k, v in sorted(reasons.items())},
                        "only_hind_legs": round(float(hind_only), 3)}
        rows = {}
        for j in r.joint_ids:
            if not j.startswith("joint.h") or j.endswith("hip_abd"):
                continue
            v = np.asarray(r.joints_deg[j], dtype=float)[both]
            if v.size == 0:
                continue
            rows[j] = {"mean": round(float(v.mean()), 1), "sd": round(float(v.std()), 1),
                       "p5": round(float(np.percentile(v, 5)), 1), "p95": round(float(np.percentile(v, 95)), 1)}
        for side in ("l", "r"):
            s_, h_ = f"joint.h{side}.stifle", f"joint.h{side}.hock"
            if s_ in r.joints_deg and h_ in r.joints_deg and both.any():
                d = (np.asarray(r.joints_deg[h_]) - np.asarray(r.joints_deg[s_]))[both]
                rows[f"hock - stifle ({side})"] = {"rms": round(float(np.sqrt(np.mean(d ** 2))), 1)}
        hind[n] = rows
    lms = sorted({k for r in results.values() for k in r.summary.get("landmark_residual_px", {})})
    return {
        "maps": names, "frames": F, "frames_reliable_in_all": int(both.sum()),
        "summary": summary, "ambiguous": ambiguous,
        "landmark_residual_px": {k: {n: r.summary.get("landmark_residual_px", {}).get(k) for n, r in results.items()}
                                 for k in lms},
        "hind_angles_deg": hind,
        "note": ("Residuals: median distance (px) between each tracked point and the fitted skeleton's, over the frames "
                 "where the point is confident. Hind angles: absolute joint angles of the fitted robot skeleton "
                 "(0 = standing) over the frames every map calls reliable."),
    }
