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

**Composition** (ADR-078): a clip entry may name its clips by the
researcher's affect tags (``select``) instead of an id; it then plays one of
the matching clips each time. Five groups of parameters with a kinematic
meaning shape the whole performance:

* *tempo*: clip speed, the gaits' clock and the idle sway's pace;
* *amplitude*: clip angles and the idle sway's size;
* *stillness*: the share of idle behaviors and their noise;
* *smoothness*: the cross-fade time and a low-pass filter on the commands;
* *phrasing*: the chance to repeat the last behavior, and pauses (the pose
  held) between behaviors.

An optional ``affect_curve`` sets any of these over time (keyframes,
interpolated), and can steer the choice of clips toward a target valence or
arousal *as tagged by the researcher*. The lab never infers affect: targets
only weigh clips by the tags a person gave them.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab import units as u
from calflab.plugins import ControlInfo, Controller, Observation, VectorDim, register, registry
from calflab.schema import P


class ClipSelect(BaseModel):
    """Clips chosen by the researcher's affect tags: every condition given must hold."""

    words: list[str] = Field(default_factory=list)
    valence: tuple[float, float] | None = None
    arousal: tuple[float, float] | None = None


#: composition parameters an affect-curve keyframe may set
CURVE_PARAMS = ("tempo", "amplitude", "idle_share", "idle_noise_deg", "blend_s", "lowpass_hz", "repeat_prob",
                "pause_prob")


class Keyframe(BaseModel):
    """A point of the affect curve: parameters to reach at ``t_s`` (unset = as the controller's)."""

    t_s: float = Field(0.0, ge=0.0)
    label: str = ""  # the researcher's name for this moment (e.g. calm, agitated); not interpreted
    tempo: float | None = None
    amplitude: float | None = None
    idle_share: float | None = None
    idle_noise_deg: float | None = None
    blend_s: float | None = None
    lowpass_hz: float | None = None
    repeat_prob: float | None = None
    pause_prob: float | None = None
    #: steer clip choice toward clips the researcher tagged near these values
    target_valence: float | None = None
    target_arousal: float | None = None


class BehaviorEntry(BaseModel):
    """One behavior of the repertoire."""

    name: str
    kind: Literal["clip", "idle", "gait"] = "idle"
    clip: str = ""  # motion-library id (kind clip)
    select: ClipSelect | None = None  # kind clip without an id: one of the clips with these tags
    controller: dict[str, Any] = Field(default_factory=dict)  # {key, params} (kind gait)
    weight: float = Field(1.0, ge=0.0)
    duration_s: tuple[float, float] = (2.0, 5.0)  # idle and gait; a clip lasts its own length / speed x repeats
    speed: tuple[float, float] = (0.8, 1.2)  # clip time warp
    amplitude: tuple[float, float] = (0.85, 1.1)  # clip angle scale
    repeats: tuple[int, int] = (1, 1)  # clip loops
    mirror: bool = False  # a clip may play with left and right swapped
    #: the repertoire fitness requires this clip (imitation averaged over required clips, ADR-079)
    required: bool = False
    imitation_weight: float = Field(1.0, ge=0.0)


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
        tempo: float = P(1.0, ge=0.25, le=3.0, step=0.05, group="Composition",
                         desc="Tempo: clip speed, the gaits' clock and the idle sway's pace (1 = as given).")
        amplitude: float = P(1.0, ge=0.0, le=2.0, step=0.05, group="Composition",
                             desc="Amplitude: scales clip angles and the idle sway (1 = as given).")
        idle_share: float = P(-1.0, ge=-1.0, le=1.0, step=0.05, group="Composition",
                              desc="Stillness: chance that the next behavior is an idle one (-1 = the weights decide).")
        lowpass_hz: float = P(0.0, unit="Hz", ge=0.0, le=20.0, step=0.5, group="Composition",
                              desc="Smoothness: low-pass filter on the commands (0 = off; lower = smoother).")
        repeat_prob: float = P(0.0, ge=0.0, le=1.0, step=0.05, group="Composition",
                               desc="Phrasing: chance that a behavior plays again right away.")
        pause_prob: float = P(0.0, ge=0.0, le=1.0, step=0.05, group="Composition",
                              desc="Phrasing: chance of a pause (the pose held) between behaviors.")
        pause_s: tuple[float, float] = P((0.5, 1.5), unit="s", ui="json", group="Composition",
                                         desc="Phrasing: how long a pause lasts (drawn in this range, divided by tempo).")
        affect_curve: list[Keyframe] = P(
            default_factory=list, ui="json", group="Composition",
            desc="Optional keyframes {t_s, label, tempo, amplitude, idle_share, idle_noise_deg, blend_s, lowpass_hz, "
                 "repeat_prob, pause_prob, target_valence, target_arousal}: the parameters move between them over the "
                 "run; targets favour clips you tagged near those values.",
        )
        target_width: float = P(0.25, ge=0.05, le=2.0, step=0.05, group="Composition", advanced=True,
                                desc="How sharply a valence/arousal target favours clips tagged near it.")
        play_required_first: bool = P(False, advanced=True,
                                      desc="Play every required clip once (in a seeded order) before choosing freely.")
        clips: dict[str, Any] = P(
            default_factory=dict, ui="json", advanced=True,
            desc="Filled in by the lab from the motion library when the controller is evaluated; not edited.",
        )
        pools: dict[str, list[str]] = P(
            default_factory=dict, ui="json", advanced=True,
            desc="Filled in by the lab: the clips each tag-selected entry may play; not edited.",
        )

    # ------------------------------------------------------------------ clips from the library
    @classmethod
    def resolve_params(cls, params: dict[str, Any], project_dir: Path | None) -> dict[str, Any]:
        """Inline the angles of every clip the repertoire names (from ``<project>/motions``)."""
        from calflab.project.motions import MotionClip
        from calflab.project.store import read_json, slugify

        out = dict(params)
        clips = dict(out.get("clips") or {})
        pools = dict(out.get("pools") or {})
        library: list[MotionClip] | None = None

        def load(cid: str) -> MotionClip:
            path = Path(project_dir) / "motions" / f"{slugify(cid)}.json" if project_dir else None
            if path is None or not path.is_file():
                raise ValueError(f"Behavior clip {cid!r} is not in the project's motion library")
            return MotionClip.model_validate(read_json(path))

        def inline(c: MotionClip) -> None:
            clips[c.id] = {"fps": c.fps, "joints": c.joints,
                           "affect": c.affect.model_dump(mode="json") if c.affect else None}

        for raw in out.get("repertoire") or []:
            e = raw if isinstance(raw, dict) else raw.model_dump()
            if e.get("kind") != "clip":
                continue
            cid = e.get("clip")
            if cid:
                if cid not in clips:
                    inline(load(cid))
                continue
            sel = e.get("select")
            if sel is None or e["name"] in pools:
                continue
            if library is None:
                d = Path(project_dir) / "motions" if project_dir else None
                library = ([MotionClip.model_validate(read_json(f)) for f in sorted(d.glob("*.json"))]
                           if d and d.is_dir() else [])
            cond = ClipSelect.model_validate(sel)
            match = [c for c in library if c.affect is not None
                     and c.affect.matches(cond.words or None, cond.valence, cond.arousal)]
            if not match:
                raise ValueError(f"Behavior {e['name']!r}: no clip in the motion library has the tags "
                                 f"{cond.model_dump(exclude_none=True)}")
            for c in match:
                if c.id not in clips:
                    inline(c)
            pools[e["name"]] = [c.id for c in match]
        out["clips"] = clips
        out["pools"] = pools
        return out

    # ------------------------------------------------------------------ inner loop: per-clip playback limits (ADR-079)
    @classmethod
    def vector_dims_for(cls, params: dict[str, Any], spec: Any = None) -> list[VectorDim]:
        """Two numbers per clip entry: the top of its speed range, up to what the body's servos can follow
        (``clip_report``'s playable speed on this body), and the top of its amplitude range (up to 1 = the clip
        as recorded). Each range is then [0.8 x top, top]."""
        dims = []
        for raw in params.get("repertoire") or []:
            e = raw if isinstance(raw, dict) else raw.model_dump()
            if e.get("kind") != "clip":
                continue
            top = cls._playable(params, e, spec)
            dims.append(VectorDim(f"speed:{e['name']}", min(0.2, top), top))
            dims.append(VectorDim(f"amplitude:{e['name']}", 0.3, 1.0))
        return dims

    @staticmethod
    def _playable(params: dict[str, Any], e: dict[str, Any], spec: Any) -> float:
        if spec is None:
            return 1.0
        from calflab.behave.feasibility import clip_report
        from calflab.components import library
        from calflab.project.motions import MotionClip

        ids = [e["clip"]] if e.get("clip") else list((params.get("pools") or {}).get(e["name"], []))
        tops = []
        for cid in ids:
            c = (params.get("clips") or {}).get(cid)
            if c:
                tops.append(clip_report(MotionClip(name=cid, fps=c["fps"], joints=c["joints"]), spec, library())["playable_speed"])
        return max(0.05, min(tops)) if tops else 1.0

    @classmethod
    def params_from_vector_for(cls, base: dict[str, Any], x: np.ndarray, spec: Any = None) -> dict[str, Any]:
        out = dict(base)
        dims = cls.vector_dims_for(base, spec)
        vals = {d.name: d.lo + float(v) * (d.hi - d.lo) for d, v in zip(dims, np.clip(x, 0.0, 1.0), strict=True)}
        rep = []
        for raw in base.get("repertoire") or []:
            e = dict(raw if isinstance(raw, dict) else raw.model_dump())
            if f"speed:{e['name']}" in vals:
                s, a = vals[f"speed:{e['name']}"], vals[f"amplitude:{e['name']}"]
                e["speed"] = [round(0.8 * s, 4), round(s, 4)]
                e["amplitude"] = [round(0.8 * a, 4), round(a, 4)]
            rep.append(e)
        out["repertoire"] = rep
        return out

    @classmethod
    def vector_from_params_for(cls, params: dict[str, Any], spec: Any = None) -> np.ndarray:
        dims = cls.vector_dims_for(params, spec)
        by = {}
        for raw in params.get("repertoire") or []:
            e = raw if isinstance(raw, dict) else raw.model_dump()
            by[f"speed:{e['name']}"] = float(e.get("speed", (1.0, 1.0))[1])
            by[f"amplitude:{e['name']}"] = float(e.get("amplitude", (1.0, 1.0))[1])
        return np.clip(np.array([(by.get(d.name, d.hi) - d.lo) / ((d.hi - d.lo) or 1.0) for d in dims]), 0.0, 1.0)

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
        self.filtered: np.ndarray | None = None
        self.fade_from: np.ndarray | None = None
        self.episode: dict[str, Any] | None = None
        self.episodes: list[dict[str, Any]] = []
        self.sub: Controller | None = None
        self.curve = sorted(p.affect_curve, key=lambda k: k.t_s)  # type: ignore[attr-defined]
        self.last_behavior: str | None = None
        self.held = info.rest.copy()
        self._static_mod = self.mod(0.0)
        for e in self.entries:
            if e.kind == "clip" and not e.clip and e.name not in p.pools:  # type: ignore[attr-defined]
                raise ValueError(f"Behavior {e.name!r} selects clips by tag, but they were not resolved from the "
                                 "motion library")
        required = [e.name for e in self.entries if e.required]
        self.queue: list[str] = ([required[i] for i in self.rng.permutation(len(required))]
                                 if p.play_required_first else [])  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ composition
    def mod(self, t: float) -> dict[str, Any]:
        """Composition parameters in effect at time t: the controller's, moved by the affect curve."""
        p = self.params
        out: dict[str, Any] = {k: float(getattr(p, k)) for k in CURVE_PARAMS}
        out["target_valence"] = out["target_arousal"] = None
        out["label"] = ""
        if not self.curve:
            return out
        before = [k for k in self.curve if k.t_s <= t]
        after = [k for k in self.curve if k.t_s > t]
        a = before[-1] if before else None
        b = after[0] if after else None
        for name in (*CURVE_PARAMS, "target_valence", "target_arousal"):
            va = getattr(a, name) if a is not None else None
            vb = getattr(b, name) if b is not None else None
            if va is not None and vb is not None and b is not None and a is not None and b.t_s > a.t_s:
                w = (t - a.t_s) / (b.t_s - a.t_s)
                out[name] = (1 - w) * va + w * vb
            elif va is not None:
                out[name] = va
            elif vb is not None and a is None and name.startswith("target_"):
                out[name] = vb
        out["label"] = a.label if a is not None else ""
        return out

    def _clip_score(self, clip_id: str, m: dict[str, Any]) -> float:
        """How well a clip's tags match the curve's targets (1 = no target or exact)."""
        aff = (self.params.clips.get(clip_id) or {}).get("affect") or {}  # type: ignore[attr-defined]
        w = 1.0
        width = float(self.params.target_width)  # type: ignore[attr-defined]
        for key in ("valence", "arousal"):
            target = m.get(f"target_{key}")
            if target is None:
                continue
            v = aff.get(key)
            # an untagged clip is neither near nor far: it keeps a small chance
            w *= 0.05 if v is None else math.exp(-(((float(v) - target) / width) ** 2))
        return w

    def _entry_clips(self, e: BehaviorEntry) -> list[str]:
        return [e.clip] if e.clip else list(self.params.pools.get(e.name, []))  # type: ignore[attr-defined]

    def _choose(self, m: dict[str, Any]) -> BehaviorEntry:
        p = self.params
        last = self.last_behavior
        if self.queue:
            return self.by_name[self.queue.pop(0)]
        if last is None and p.start:  # type: ignore[attr-defined]
            if p.start not in self.by_name:  # type: ignore[attr-defined]
                raise ValueError(f"Start behavior {p.start!r} is not in the repertoire")  # type: ignore[attr-defined]
            return self.by_name[p.start]  # type: ignore[attr-defined]
        if last is not None and m["repeat_prob"] > 0 and self.rng.random() < m["repeat_prob"]:
            return self.by_name[last]
        table = p.transitions.get(last) if last else None  # type: ignore[attr-defined]
        names = list(table) if table else [e.name for e in self.entries]
        w = np.array([float(table[n]) if table else self.by_name[n].weight for n in names])
        if m["target_valence"] is not None or m["target_arousal"] is not None:
            for i, n in enumerate(names):
                e = self.by_name[n]
                if e.kind == "clip":
                    w[i] *= max((self._clip_score(c, m) for c in self._entry_clips(e)), default=1.0)
        share = m["idle_share"]
        if share >= 0:
            idle = np.array([self.by_name[n].kind == "idle" for n in names])
            if idle.any() and (~idle).any() and w[idle].sum() > 0 and w[~idle].sum() > 0:
                w = np.where(idle, share * w / w[idle].sum(), (1 - share) * w / w[~idle].sum())
        if w.sum() <= 0:
            raise ValueError(f"No behavior can follow {last!r}: every weight is 0")
        return self.by_name[names[int(self.rng.choice(len(names), p=w / w.sum()))]]

    def _start(self, t: float) -> None:
        m = self.mod(t)
        p = self.params
        pausing = (self.episode is not None and self.episode["kind"] != "pause" and m["pause_prob"] > 0
                   and self.rng.random() < m["pause_prob"])
        if pausing:  # phrasing: hold the pose for a moment between behaviors
            lo, hi = p.pause_s  # type: ignore[attr-defined]
            pause = {"name": "pause", "kind": "pause", "t0": t, "t1": t + float(self.rng.uniform(lo, hi)) / m["tempo"]}
            self._begin(pause, m)
            return
        e = self._choose(m)
        self.last_behavior = e.name
        ep: dict[str, Any] = {"name": e.name, "kind": e.kind, "t0": t}
        if e.kind == "clip":
            pool = self._entry_clips(e)
            if len(pool) > 1:
                w = np.array([self._clip_score(c, m) for c in pool])
                cid = pool[int(self.rng.choice(len(pool), p=w / w.sum()))]
            else:
                cid = pool[0]
            clip = self.params.clips.get(cid)  # type: ignore[attr-defined]
            if clip is None:
                raise ValueError(f"Clip {cid!r} was not resolved from the motion library")
            speed = float(self.rng.uniform(*e.speed)) * m["tempo"]
            reps = int(self.rng.integers(e.repeats[0], e.repeats[1] + 1))
            frames = len(next(iter(clip["joints"].values()))) if clip["joints"] else 1
            ep.update(clip=cid, speed=speed, amplitude=float(self.rng.uniform(*e.amplitude)) * m["amplitude"],
                      repeats=reps, mirror=bool(e.mirror and self.rng.random() < 0.5),
                      t1=t + reps * frames / (clip["fps"] * speed))
        else:
            ep["t1"] = t + float(self.rng.uniform(*e.duration_s))
            if e.kind == "gait":
                cls = registry.get("controller", str(e.controller.get("key", "feral_motion")))
                sub: Controller = cls(dict(e.controller.get("params", {})))  # type: ignore[assignment]
                sub.reset(self.info, int(self.rng.integers(0, 2**31 - 1)))
                self.sub = sub
                ep["tempo"] = m["tempo"]
        self._begin(ep, m)

    def _begin(self, ep: dict[str, Any], m: dict[str, Any]) -> None:
        self.fade_from = self.prev.copy() if self.prev is not None else None
        self.held = self.prev.copy() if self.prev is not None else self.info.rest.copy()
        self.episode = ep
        ep["blend_s"] = m["blend_s"]
        logged = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in ep.items()}
        logged["composition"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items() if v is not None
                                 and v != ""}
        self.episodes.append(logged)

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
        m = self.mod(t) if self.curve else self._static_mod
        if ep["kind"] == "clip":
            target = self._clip_pose(ep, t)
        elif ep["kind"] == "pause":
            target = self.held.copy()
        elif ep["kind"] == "gait" and self.sub is not None:
            sub_obs = Observation(t=(t - ep["t0"]) * ep.get("tempo", 1.0), q=obs.q, dq=obs.dq,
                                  trunk_quat=obs.trunk_quat, trunk_gyro=obs.trunk_gyro, foot_contact=obs.foot_contact)
            target = np.asarray(self.sub.act(sub_obs), dtype=float)  # type: ignore[attr-defined]
        else:  # idle: mean-reverting random shifts around the standing pose
            dt = self.info.control_dt
            tau = float(p.idle_tau_s) / m["tempo"]  # type: ignore[attr-defined]
            sigma = u.deg_to_rad(m["idle_noise_deg"]) * m["amplitude"]
            self.noise += -self.noise * dt / tau + sigma * math.sqrt(2 * dt / tau) * self.rng.standard_normal(len(self.noise))
            target = self.info.rest + self.noise[self.group]
        blend = float(ep.get("blend_s", p.blend_s))  # type: ignore[attr-defined,arg-type]
        if self.fade_from is not None and blend > 0 and t - ep["t0"] < blend:
            w = 0.5 - 0.5 * math.cos(math.pi * (t - ep["t0"]) / blend)
            target = (1 - w) * self.fade_from + w * target
        if m["lowpass_hz"] > 0:  # smoothness: first-order low-pass on the commands
            a = 1.0 - math.exp(-2.0 * math.pi * m["lowpass_hz"] * self.info.control_dt)
            self.filtered = target.copy() if self.filtered is None else self.filtered + a * (target - self.filtered)
            target = self.filtered.copy()
        target = np.clip(target, self.info.lo, self.info.hi)
        frac = float(p.speed_fraction)  # type: ignore[attr-defined]
        if frac > 0 and self.info.speed_limit is not None:
            prev = self.info.rest if self.prev is None else self.prev
            step = np.asarray(self.info.speed_limit, dtype=float) * frac * self.info.control_dt
            target = prev + np.clip(target - prev, -step, step)
        self.prev = target.copy()
        return target

    def log(self) -> dict[str, Any]:
        """The behaviors chosen during the rollout, in order, each with the composition in effect when it began."""
        return {"episodes": list(self.episodes)}
