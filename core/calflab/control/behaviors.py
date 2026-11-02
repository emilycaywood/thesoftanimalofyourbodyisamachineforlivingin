"""Stochastic behaviors: a repertoire played with variation (ADR-073).

The robot does one *behavior* at a time and then chooses the next at random:

* ``clip``: a motion-library clip (e.g. retargeted from footage), played at
  a random speed and amplitude within ranges, optionally mirrored left/right;
* ``idle``: standing with slow random shifts (an Ornstein-Uhlenbeck
  process: small, smooth, mean-reverting), shared by the left and right leg
  of each pair so the body crouches, rises and leans rather than wobbling
  onto a diagonal (independent shifts of 2 deg tipped the feral calf over);
* ``gait``: another controller (``feral_motion`` walk, trot, lie_rise, or any
  controller key) for a random duration.

The next behavior follows the weights, or a transition table
(``transitions``: from name -> {to name: weight}), so sequences can be shaped
like a Markov chain. Each switch cross-fades over ``blend_s`` from the last
commanded pose. Every random draw comes from the run's seed, so a rollout is
reproducible; the episodes chosen are recorded in the rollout
(``meta.controller_log``). Commanded joint speed stays under a fraction of
each servo's speed at its joint, as in ``feral_motion``.

Clips are referred to by id; the lab inlines their angles into ``clips``
when the controller is evaluated (``resolve_params``), so jobs that run away
from the project folder (evolution workers) play the same clips.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab import units as u
from calflab.plugins import ControlInfo, Controller, Observation, register, registry
from calflab.schema import P


class BehaviorEntry(BaseModel):
    """One behavior of the repertoire."""

    name: str
    kind: Literal["clip", "idle", "gait"] = "idle"
    clip: str = ""  # motion-library id (kind clip)
    controller: dict[str, Any] = Field(default_factory=dict)  # {key, params} (kind gait)
    weight: float = Field(1.0, ge=0.0)
    duration_s: tuple[float, float] = (2.0, 5.0)  # idle and gait; a clip lasts its own length / speed x repeats
    speed: tuple[float, float] = (0.8, 1.2)  # clip time warp
    amplitude: tuple[float, float] = (0.85, 1.1)  # clip angle scale
    repeats: tuple[int, int] = (1, 1)  # clip loops
    mirror: bool = False  # a clip may play with left and right swapped


def _default_repertoire() -> list[dict[str, Any]]:
    return [
        {"name": "stand", "kind": "idle", "weight": 2.0, "duration_s": [2.0, 5.0]},
        {"name": "walk", "kind": "gait", "weight": 1.0, "duration_s": [6.0, 10.0],
         "controller": {"key": "feral_motion", "params": {"mode": "walk"}}},
        {"name": "trot", "kind": "gait", "weight": 0.5, "duration_s": [3.0, 6.0],
         "controller": {"key": "feral_motion", "params": {"mode": "trot"}}},
    ]


@register
class BehaviorsController(Controller):
    """A seeded random sequence of clips, idle moments and gaits."""

    key = "behaviors"
    label = "Stochastic behaviors"
    description = "Plays a repertoire of clips (e.g. from footage), idle moments and gaits in a random, seeded sequence."
    version = "1"

    class Params(BaseModel):
        repertoire: list[BehaviorEntry] = P(
            default_factory=lambda: [BehaviorEntry.model_validate(e) for e in _default_repertoire()], ui="json",
            desc="Behaviors to choose from: name, kind (clip, idle, gait), clip id or controller, weight, and the ranges "
                 "their duration, speed and amplitude are drawn from.",
        )
        transitions: dict[str, dict[str, float]] = P(
            default_factory=dict, ui="json",
            desc="Optional: from a behavior's name to the weights of the next ones (a Markov chain). Empty = the "
                 "repertoire's weights every time.",
        )
        start: str = P("", desc="The first behavior's name (empty = drawn like the others).")
        blend_s: float = P(0.6, unit="s", ge=0.0, le=3.0, step=0.1, desc="Cross-fade between behaviors.")
        idle_noise_deg: float = P(2.0, unit="deg", ge=0.0, le=15.0, step=0.5, desc="Idle: spread of the slow random shifts.")
        idle_tau_s: float = P(0.8, unit="s", ge=0.1, le=5.0, step=0.1, desc="Idle: how slowly the shifts wander.")
        speed_fraction: float = P(
            0.9, ge=0.0, le=1.0, step=0.05,
            desc="Commanded joint speed kept under this fraction of each servo's speed at its joint. 0 = no limit.",
        )
        clips: dict[str, Any] = P(
            default_factory=dict, ui="json", advanced=True,
            desc="Filled in by the lab from the motion library when the controller is evaluated; not edited.",
        )

    # ------------------------------------------------------------------ clips from the library
    @classmethod
    def resolve_params(cls, params: dict[str, Any], project_dir: Path | None) -> dict[str, Any]:
        """Inline the angles of every clip the repertoire names (from ``<project>/motions``)."""
        from calflab.project.motions import MotionClip
        from calflab.project.store import read_json, slugify

        out = dict(params)
        clips = dict(out.get("clips") or {})
        for e in out.get("repertoire") or []:
            cid = e.get("clip") if isinstance(e, dict) else getattr(e, "clip", "")
            kind = e.get("kind") if isinstance(e, dict) else getattr(e, "kind", "")
            if kind != "clip" or not cid or cid in clips:
                continue
            path = Path(project_dir) / "motions" / f"{slugify(cid)}.json" if project_dir else None
            if path is None or not path.is_file():
                raise ValueError(f"Behavior clip {cid!r} is not in the project's motion library")
            c = MotionClip.model_validate(read_json(path))
            clips[cid] = {"fps": c.fps, "joints": c.joints}
        out["clips"] = clips
        return out

    # ------------------------------------------------------------------ runtime
    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        super().reset(info, seed)
        p = self.params
        self.rng = np.random.default_rng(seed)
        self.entries: list[BehaviorEntry] = list(p.repertoire)  # type: ignore[attr-defined]
        if not self.entries:
            raise ValueError("The behavior repertoire is empty")
        self.by_name = {e.name: e for e in self.entries}
        self.idx = {jid: i for i, jid in enumerate(info.joint_ids)}
        # idle sway: one noise channel per joint of a left/right pair ("joint.fl.carpus" and "joint.fr.carpus" share one)
        groups: dict[str, int] = {}
        self.group = np.zeros(len(info.joint_ids), dtype=int)
        for i, jid in enumerate(info.joint_ids):
            parts = jid.split(".")
            key = f"{parts[1][0]}.{parts[2]}" if len(parts) == 3 and len(parts[1]) == 2 else jid
            self.group[i] = groups.setdefault(key, len(groups))
        self.noise = np.zeros(len(groups))
        self.prev: np.ndarray | None = None
        self.fade_from: np.ndarray | None = None
        self.episode: dict[str, Any] | None = None
        self.episodes: list[dict[str, Any]] = []
        self.sub: Controller | None = None

    def _choose(self) -> BehaviorEntry:
        p = self.params
        last = self.episode["name"] if self.episode else None
        if last is None and p.start:  # type: ignore[attr-defined]
            if p.start not in self.by_name:  # type: ignore[attr-defined]
                raise ValueError(f"Start behavior {p.start!r} is not in the repertoire")  # type: ignore[attr-defined]
            return self.by_name[p.start]  # type: ignore[attr-defined]
        table = p.transitions.get(last) if last else None  # type: ignore[attr-defined]
        names = list(table) if table else [e.name for e in self.entries]
        w = np.array([float(table[n]) if table else self.by_name[n].weight for n in names])
        if w.sum() <= 0:
            raise ValueError(f"No behavior can follow {last!r}: every weight is 0")
        return self.by_name[names[int(self.rng.choice(len(names), p=w / w.sum()))]]

    def _start(self, t: float) -> None:
        e = self._choose()
        ep: dict[str, Any] = {"name": e.name, "kind": e.kind, "t0": t}
        if e.kind == "clip":
            clip = self.params.clips.get(e.clip)  # type: ignore[attr-defined]
            if clip is None:
                raise ValueError(f"Clip {e.clip!r} was not resolved from the motion library")
            speed = float(self.rng.uniform(*e.speed))
            reps = int(self.rng.integers(e.repeats[0], e.repeats[1] + 1))
            frames = len(next(iter(clip["joints"].values()))) if clip["joints"] else 1
            ep.update(clip=e.clip, speed=speed, amplitude=float(self.rng.uniform(*e.amplitude)), repeats=reps,
                      mirror=bool(e.mirror and self.rng.random() < 0.5),
                      t1=t + reps * frames / (clip["fps"] * speed))
        else:
            ep["t1"] = t + float(self.rng.uniform(*e.duration_s))
            if e.kind == "gait":
                cls = registry.get("controller", str(e.controller.get("key", "feral_motion")))
                sub: Controller = cls(dict(e.controller.get("params", {})))  # type: ignore[assignment]
                sub.reset(self.info, int(self.rng.integers(0, 2**31 - 1)))
                self.sub = sub
        self.fade_from = self.prev.copy() if self.prev is not None else None
        self.episode = ep
        self.episodes.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in ep.items()})

    def _clip_pose(self, ep: dict[str, Any], t: float) -> np.ndarray:
        clip = self.params.clips[ep["clip"]]  # type: ignore[attr-defined]
        target = self.info.rest.copy()
        joints = clip["joints"]
        n = len(next(iter(joints.values()))) if joints else 1
        x = ((t - ep["t0"]) * clip["fps"] * ep["speed"]) % max(n, 1)
        i0 = int(math.floor(x))
        w = x - i0
        for jid, vals in joints.items():
            if ep["mirror"]:
                parts = jid.split(".")
                if len(parts) == 3 and len(parts[1]) == 2:
                    parts[1] = parts[1][0] + {"l": "r", "r": "l"}.get(parts[1][1], parts[1][1])
                    jid = ".".join(parts)
            i = self.idx.get(jid)
            if i is None:
                continue
            deg = (1 - w) * vals[i0 % n] + w * vals[(i0 + 1) % n]
            target[i] = self.info.rest[i] + u.deg_to_rad(ep["amplitude"] * deg)
        return target

    def act(self, obs: Observation) -> np.ndarray:
        p = self.params
        t = obs.t
        if self.episode is None or t >= self.episode["t1"]:
            self._start(t)
        ep = self.episode
        assert ep is not None
        if ep["kind"] == "clip":
            target = self._clip_pose(ep, t)
        elif ep["kind"] == "gait" and self.sub is not None:
            sub_obs = Observation(t=t - ep["t0"], q=obs.q, dq=obs.dq, trunk_quat=obs.trunk_quat,
                                  trunk_gyro=obs.trunk_gyro, foot_contact=obs.foot_contact)
            target = np.asarray(self.sub.act(sub_obs), dtype=float)  # type: ignore[attr-defined]
        else:  # idle: mean-reverting random shifts around the standing pose
            dt = self.info.control_dt
            tau = float(p.idle_tau_s)  # type: ignore[attr-defined]
            sigma = u.deg_to_rad(float(p.idle_noise_deg))  # type: ignore[attr-defined]
            self.noise += -self.noise * dt / tau + sigma * math.sqrt(2 * dt / tau) * self.rng.standard_normal(len(self.noise))
            target = self.info.rest + self.noise[self.group]
        blend = float(p.blend_s)  # type: ignore[attr-defined]
        if self.fade_from is not None and blend > 0 and t - ep["t0"] < blend:
            w = 0.5 - 0.5 * math.cos(math.pi * (t - ep["t0"]) / blend)
            target = (1 - w) * self.fade_from + w * target
        target = np.clip(target, self.info.lo, self.info.hi)
        frac = float(p.speed_fraction)  # type: ignore[attr-defined]
        if frac > 0 and self.info.speed_limit is not None:
            prev = self.info.rest if self.prev is None else self.prev
            step = np.asarray(self.info.speed_limit, dtype=float) * frac * self.info.control_dt
            target = prev + np.clip(target - prev, -step, step)
        self.prev = target.copy()
        return target

    def log(self) -> dict[str, Any]:
        """The behaviors chosen during the rollout, in order."""
        return {"episodes": list(self.episodes)}
