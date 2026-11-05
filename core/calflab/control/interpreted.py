"""A performance from a reading: behaviours, durations and parameters drawn from the calf's model (ADR-085).

Each *state* is a read behaviour interpreted as a motion primitive (its
controller and parameters, from :mod:`calflab.behave.interpret`), with the
duration distribution the reading fitted for it (log-normal) and, per
parameter, a range it is varied in (the calf's own spread, never past what the
interpretation found within the limits). The controller:

1. starts in a state drawn from ``initial`` (or ``start``);
2. draws its duration and parameters (seeded);
3. when the duration is over, waits for the primitive's next **safe phase**
   (every hoof down; at most ``max_wait_s``, then it switches anyway and logs
   that), draws the next state from ``transitions`` (no self-transitions: a
   semi-Markov chain) and cross-fades into it over ``blend_s``;
4. records every episode (state, primitive, parameters drawn, start, end, how
   long it waited for a safe phase) in the rollout (``meta.controller_log``).

With ``variation`` (ADR-098, :mod:`calflab.control.variation`) movement also varies *within* a state: posture
drift and noise, each cycle's tempo and amplitude, switches before an all-hooves-down window, and the length of
each cross-fade, every one bounded; ``variation.mode = "extremes"`` plays the bounds (coverage). Without it the
controller is exactly as before (no draws are added to its random stream).

Commanded joint speed stays under ``speed_fraction`` of each servo's speed at
its joint, as in the other controllers (the primitives' own caps are turned
off so only one applies). Units: s, deg.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.plugins import ControlInfo, Controller, Observation, register, registry
from calflab.schema import P


class StateDuration(BaseModel):
    log_mean: float = 0.0  # ln(s)
    log_sd: float = 0.5
    min_s: float = 0.5
    max_s: float = 30.0


class InterpretedState(BaseModel):
    name: str
    primitive: str = ""
    controller: dict[str, Any] = Field(default_factory=dict)  # {key, params}
    period_s: float = 1.0
    offset_s: float = 0.0
    safe: list[tuple[float, float]] = Field(default_factory=lambda: [(0.0, 1.0)])
    one_shot: bool = False
    duration: StateDuration = Field(default_factory=StateDuration)
    #: controller parameter -> (low, high) factor it is multiplied by, drawn per episode; "offsets"/"lift" scale a pose
    vary: dict[str, tuple[float, float]] = Field(default_factory=dict)
    #: variation within the movement (ADR-098): drift, noise (posture, share of the reference), tempo, amp
    within: dict[str, float] = Field(default_factory=dict)


@register
class InterpretedController(Controller):
    """Plays a reading's behaviours as the robot's own primitives, switching at safe phases."""

    key = "interpreted"
    label = "Interpreted behaviours"
    description = ("Behaviours, durations and parameters drawn from a reading of footage (a semi-Markov model), each "
                   "played as one of the body's own motion primitives; switches only where every hoof is down.")
    version = "1"

    class Params(BaseModel):
        states: list[InterpretedState] = P(default_factory=list, ui="json",
                                           desc="Filled in by the interpretation: one per behaviour read.")
        transitions: dict[str, dict[str, float]] = P(default_factory=dict, ui="json",
                                                     desc="From a state to the probabilities of the next.")
        initial: dict[str, float] = P(default_factory=dict, ui="json", desc="Probabilities of the first state.")
        start: str = P("", desc="The first state's name (empty = drawn from initial).")
        blend_s: float = P(0.6, unit="s", ge=0.0, le=3.0, step=0.1, desc="Cross-fade between states.")
        max_wait_s: float = P(4.0, unit="s", ge=0.0, le=30.0, step=0.5,
                              desc="Longest wait for a safe phase before switching anyway (logged).")
        speed_fraction: float = P(0.9, ge=0.0, le=1.0, step=0.05,
                                  desc="Commanded joint speed kept under this fraction of each servo's speed.")
        variation: dict[str, Any] = P(default_factory=dict, ui="json",
                                      desc="Variation within a movement (ADR-098): basis, axes, drift_hz, "
                                           "switch_slack, blend_var, mode (draw / extremes), step_s. Empty = none.")

    @classmethod
    def fits(cls, spec: Any) -> bool:
        return bool(spec.actuators)

    def reset(self, info: ControlInfo, seed: int = 0) -> None:
        super().reset(info, seed)
        p = self.params
        self.rng = np.random.default_rng(seed)
        self.states = {s.name: s for s in p.states}  # type: ignore[attr-defined]
        self.prev: np.ndarray | None = None
        self.fade_from: np.ndarray | None = None
        self.sub: Controller | None = None
        self.ep: dict[str, Any] | None = None
        self.episodes: list[dict[str, Any]] = []
        var = dict(p.variation or {})  # type: ignore[attr-defined]
        self.var: dict[str, Any] | None = var or None
        if self.var is not None:
            from calflab.control.variation import Signals

            self.seed = int(seed)
            self.signals = Signals(seed, float(var.get("drift_hz", 0.25)))
            self.extremes = var.get("mode") == "extremes"
            idx = {j: i for i, j in enumerate(self.info.joint_ids)}
            self.basis = {a: {idx[j]: float(v) for j, v in d.items() if j in idx}
                          for a, d in (var.get("basis") or {}).items()}
            self.axes = {a: float(w) for a, w in (var.get("axes") or {}).items()}
            self.switches = 0
            self.amp_from = {"drift": 0.0, "noise": 0.0}
            self.t_last = 0.0
            self.tau = 0.0
            self.blend = 0.0

    # ------------------------------------------------------------------ draws
    def _draw(self, probs: dict[str, float], exclude: str | None = None) -> str:
        names = [n for n in probs if n in self.states and n != exclude and probs[n] > 0]
        if not names:
            names = [n for n in self.states if n != exclude] or list(self.states)
            w = np.ones(len(names))
        else:
            w = np.array([float(probs[n]) for n in names])
        return names[int(self.rng.choice(len(names), p=w / w.sum()))]

    def _start(self, t: float, name: str, waited: float = 0.0) -> None:
        st = self.states[name]
        d = st.duration
        dur = float(np.clip(math.exp(self.rng.normal(d.log_mean, d.log_sd)), d.min_s, d.max_s))
        if self.var is not None:
            self._vary_start(t, st)
        if st.one_shot:
            dur = max(dur, st.offset_s + st.period_s)
            n = max(1, round((dur - st.offset_s) / st.period_s))
            dur = st.offset_s + st.period_s * n
            if self.var is not None:  # whole cycles at their own tempo, no longer than the cycles at tempo 1 (or one)
                real = [st.offset_s + float(np.sum(st.period_s / self.rates[:k])) for k in range(1, n + 1)]
                fit = [r for r in real if r <= max(d.max_s, dur) + 1e-9]
                dur = fit[-1] if fit else real[0]
        params = dict(st.controller.get("params") or {})
        drawn: dict[str, float] = {}
        for k, (lo, hi) in st.vary.items():
            f = float(math.exp(self.rng.uniform(math.log(max(lo, 1e-6)), math.log(max(hi, 1e-6)))))
            drawn[k] = round(f, 4)
            v = params.get(k)
            if isinstance(v, dict):
                params[k] = {j: x * f for j, x in v.items()}
            elif isinstance(v, int | float) and not isinstance(v, bool) and v > 0:  # (a negative is a sentinel)
                params[k] = v * f
        params["speed_fraction"] = 0.0  # one cap, ours
        cls = registry.get("controller", str(st.controller.get("key", "feral_motion")))
        sub: Controller = cls(params)  # type: ignore[assignment]
        sub.reset(self.info, int(self.rng.integers(0, 2**31 - 1)))
        self.sub = sub
        self.fade_from = self.prev.copy() if self.prev is not None else None
        if self.ep is not None:
            self.ep["t1"] = round(t, 4)
            self.ep["waited_s"] = round(waited, 4)
        self.ep = {"name": name, "primitive": st.primitive, "t0": round(t, 4), "planned_s": round(dur, 4),
                   "factors": drawn}
        if self.var is not None:
            self.ep["blend_s"] = round(self.blend, 4)
        self.episodes.append(self.ep)
        self.end = t + dur
        self.state = st
        self.t0 = t

    def _safe(self, t: float) -> bool:
        st = self.state
        local = t - self.t0 if self.var is None else self.tau
        if local < st.offset_s or st.period_s <= 0:
            return True
        ph = ((local - st.offset_s) / st.period_s) % 1.0
        if st.one_shot and local >= st.offset_s + st.period_s * 0.999:
            return True
        if self.var is not None and not st.one_shot:
            slack = float(self.var.get("switch_slack", 0.0))
            if slack > 0:
                if self.extremes:  # the earliest phase allowed, and no later
                    return any(0.0 <= (ph - (a - slack)) % 1.0 <= 0.04 for a, _b in st.safe)
                return any(0.0 <= (ph - (a - slack)) % 1.0 <= (b - a + slack) + 1e-9 for a, b in st.safe)
        return any(a - 1e-9 <= ph <= b + 1e-9 for a, b in st.safe)

    # ------------------------------------------------------------------ variation within a movement (ADR-098)
    def _vary_start(self, t: float, st: InterpretedState) -> None:
        """Per episode: each cycle's tempo and amplitude, the cross-fade into it; the posture amplitudes in effect
        are cross-faded from the last state's. Draws come from their own stream (seed, episode)."""
        assert self.var is not None
        n = 256
        tempo, amp = float(st.within.get("tempo", 0.0)), float(st.within.get("amp", 0.0))
        if self.extremes:
            u_t = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)  # fastest, slowest, ...
            v_a = np.ones(n)  # the largest
            wb = -1.0 if self.switches % 2 == 0 else 1.0  # shortest, longest, ...
        else:
            rng = np.random.default_rng([self.seed, 9173, len(self.episodes)])
            u_t, v_a, wb = rng.uniform(-1, 1, n), rng.uniform(-1, 1, n), float(rng.uniform(-1, 1))
        first = self.ep is None
        if not first:
            self.amp_from = self._amp_now(t)
            self.switches += 1
        self.rates = np.exp(tempo * u_t)
        self.amps = 1.0 + amp * v_a
        blend = float(self.params.blend_s) * math.exp(float(self.var.get("blend_var", 0.0)) * wb)  # type: ignore[attr-defined]
        self.blend = 0.0 if first else float(np.clip(blend, 0.1, 3.0))
        self.tau = 0.0
        self.t_last = t
        self._within_to = {"drift": float(st.within.get("drift", 0.0)), "noise": float(st.within.get("noise", 0.0))}

    def _amp_now(self, t: float) -> dict[str, float]:
        """The posture amplitudes in effect at ``t``: cross-faded from the last state's to this one's."""
        to = self._within_to
        if self.blend > 0 and t - self.t0 < self.blend:
            k = 0.5 - 0.5 * math.cos(math.pi * (t - self.t0) / self.blend)
            return {a: (1 - k) * self.amp_from[a] + k * to[a] for a in to}
        return dict(to)

    def _cycle(self) -> int:
        st = self.state
        if self.tau < st.offset_s or st.period_s <= 0:
            return -1
        return min(255, int((self.tau - st.offset_s) / st.period_s))

    def _posture(self, t: float) -> np.ndarray:
        """Joint offsets (rad) of the posture drift and noise at ``t``."""
        from calflab.control.variation import extremes_value

        assert self.var is not None
        out = np.zeros(len(self.info.joint_ids))
        amp = self._amp_now(t)
        ramp = min(1.0, max(0.0, t / 1.0))  # in from the standing start
        step = float(self.var.get("step_s", 2.0))
        for axis, basis in self.basis.items():
            k = self.axes.get(axis, 0.0)
            if k <= 0 or not basis:
                continue
            v = (extremes_value(axis, t, step, amp["drift"], amp["noise"]) if self.extremes
                 else self.signals.value(axis, t, amp["drift"], amp["noise"]))
            for i, deg in basis.items():
                out[i] += math.radians(deg) * k * v * ramp
        return out

    # ------------------------------------------------------------------ runtime
    def act(self, obs: Observation) -> np.ndarray:
        p = self.params
        t = obs.t
        if not self.states:  # nothing interpreted yet: stand
            return np.clip(self.info.rest.copy(), self.info.lo, self.info.hi)
        if self.var is not None and self.ep is not None:  # the episode's own clock: each cycle at its own tempo
            k = self._cycle()
            self.tau += max(0.0, t - self.t_last) * (float(self.rates[k]) if k >= 0 else 1.0)
            self.t_last = t
        if self.ep is None:
            first = p.start if p.start in self.states else self._draw(p.initial or {})  # type: ignore[attr-defined]
            self._start(t, first)
        elif t >= self.end:
            waited = t - self.end
            if self._safe(t) or waited >= float(p.max_wait_s):  # type: ignore[attr-defined]
                if not self._safe(t):
                    self.ep["unsafe_switch"] = True  # type: ignore[index]
                row = p.transitions.get(self.state.name)  # type: ignore[attr-defined]
                if row is not None and not any(v > 0 for v in row.values()):
                    # every way out was dropped as over a limit: carry on with the same primitive (not restarted)
                    d = self.state.duration
                    self.end = t + float(np.clip(math.exp(self.rng.normal(d.log_mean, d.log_sd)), d.min_s, d.max_s))
                    assert self.ep is not None
                    self.ep["extended"] = int(self.ep.get("extended", 0)) + 1
                else:
                    nxt = self._draw(row or p.initial or {}, exclude=self.state.name)  # type: ignore[attr-defined]
                    self._start(t, nxt, waited)
        assert self.sub is not None
        local = t - self.t0 if self.var is None else self.tau
        sub_obs = Observation(t=local, q=obs.q, dq=obs.dq, trunk_quat=obs.trunk_quat, trunk_gyro=obs.trunk_gyro,
                              foot_contact=obs.foot_contact)
        target = np.asarray(self.sub.act(sub_obs), dtype=float)
        blend = float(p.blend_s)  # type: ignore[attr-defined]
        if self.var is not None:
            k = self._cycle()
            if k >= 0:
                target = self.info.rest + float(self.amps[k]) * (target - self.info.rest)
            target = target + self._posture(t)
            blend = self.blend
        if self.fade_from is not None and blend > 0 and t - self.t0 < blend:
            w = 0.5 - 0.5 * math.cos(math.pi * (t - self.t0) / blend)
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
        return {"episodes": [dict(e) for e in self.episodes]}

    def cycle_period_s(self) -> float:
        return 2.0
