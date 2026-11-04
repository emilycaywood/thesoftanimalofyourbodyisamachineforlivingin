"""Reading a calf's movement: behaviours, their character, and a semi-Markov model of them (ADR-085).

This is the first half of *interpretation, not copy*: instead of replaying the
calf's joint angles, the lab reads **what the calf does** (which behaviour,
when, for how long) and **how** (tempo, amplitude, weight, vigour, direction),
in terms a robot with other joints can perform. Everything here is explicit
and recorded; nothing is judged by eye in the UI.

**Signals** (:mod:`calflab.behave.signals`): joint angles relative to standing,
trunk heading, pitch, roll and path, hoof heights. The same code reads a robot
rollout, so the calf and the robot are compared by one reader.

**Contact.** From a rollout, a hoof is down when it carries more than 1 N. From
a video, a hoof is in swing while its tracked paw moves over the ground: its
image speed minus the background's is over ``swing_bl_s`` body lengths per
second (down again under ``stance_bl_s``). Hoof heights from the lift are not
used for contact: the calf's proportions on the robot's skeleton make them
drift by 70-90 mm while the paws stand still (214239, frames 24-60). Without
tracks (synthetic signals), a hoof counts as lifted ``lift_mm`` above its own
low of the surrounding ``baseline_s`` (down under ``down_mm``). Lifts shorter
than ``min_lift_s`` are noise.

**Behaviours**, by explicit rules on those signals (thresholds PROVISIONAL):

* *stepping bouts*: frames with a hoof lifted, joined across all-down gaps
  shorter than ``join_s``. A bout is
  * ``other`` (fast: trot, canter, bucking) when two or more hooves are up in
    over ``fast_two_up`` of it, or its trunk speed is over ``fast_bl_s`` body
    lengths per second;
  * ``step`` with at most ``step_max_lifts`` lifts;
  * ``turn`` when it turns at least ``turn_min_deg`` and travels less than
    ``turn_bl_per_90`` body lengths per 90 deg turned;
  * else ``walk``;
* between bouts, with all hooves down: ``weight_shift`` where the joints or
  the trunk's tilt move (over ``still_qom_deg_s`` / ``still_tilt_deg_s``),
  else ``stand``;
* frames the lift could not read for longer than ``max_gap_frames`` are a
  gap: no behaviour, and the semi-Markov chain is broken there.

Each stretch keeps its evidence (frames, the features the rule used, the
rule) and a confidence (the share of reliable frames times how clearly the
deciding feature cleared its threshold).

**Character per behaviour**: duration, tempo (stride period, or the strongest
repetition of the activity), phrasing (bursts and pauses), amplitude per joint
group, quantity of motion, footfall order and duty factor, trunk sway (roll,
pitch, heave, lateral), turn, lean, and how abruptly it starts and stops.

**Model**: behaviours as states of a semi-Markov chain: transition counts
between consecutive stretches (no self-transitions; a gap breaks the chain),
pooled over videos with each video's counts kept, smoothed with
``alpha`` (PROVISIONAL), and per state a log-normal duration fit (stretches cut
by a video's end or a gap are *censored* and only used when nothing else is
there). ``support`` says in plain words how far the footage carries this.

Units: s, mm (at the robot's leg length), deg.
"""

from __future__ import annotations

import math
import time
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from calflab.behave.signals import LEGS, MotionSignals
from calflab.schema import P

BEHAVIOURS = ("stand", "weight_shift", "step", "walk", "turn", "other")
LABELS = {"stand": "Stand", "weight_shift": "Weight shift", "step": "Step", "walk": "Walk", "turn": "Turn",
          "other": "Other (fast)"}
SCHEMA_VERSION = 1


class ReadingSettings(BaseModel):
    """Thresholds of the reading (all PROVISIONAL first guesses, ADR-085)."""

    cutoff_hz: float = P(4.0, unit="Hz", ge=0.5, le=12.0, desc="Low-pass on the lifted signals before reading.")
    swing_bl_s: float = P(0.5, unit="1/s", ge=0.05, le=5.0,
                          desc="A tracked paw moving over the ground faster than this (body lengths/s) is in swing.")
    stance_bl_s: float = P(0.3, unit="1/s", ge=0.0, le=5.0, desc="... and in stance again below this (hysteresis).")
    lift_mm: float = P(40.0, unit="mm", ge=5.0, le=200.0, desc="A hoof counts as lifted this far above its own low.")
    down_mm: float = P(20.0, unit="mm", ge=0.0, le=200.0, desc="... and down again below this (hysteresis).")
    baseline_s: float = P(1.5, unit="s", ge=0.3, le=6.0, desc="Window of a hoof's own lowest height (lift only).")
    min_lift_s: float = P(0.1, unit="s", ge=0.0, le=1.0, desc="Shorter lifts are noise.")
    join_s: float = P(0.5, unit="s", ge=0.0, le=3.0, desc="Lifts closer than this belong to one stepping bout.")
    still_qom_deg_s: float = P(8.0, unit="deg/s", ge=0.0, le=100.0, desc="Joints slower than this on average: still.")
    still_tilt_deg_s: float = P(4.0, unit="deg/s", ge=0.0, le=60.0, desc="Trunk pitch/roll slower than this: still.")
    min_stretch_s: float = P(0.4, unit="s", ge=0.0, le=3.0, desc="Shorter stretches join their neighbour.")
    step_max_lifts: int = P(2, ge=1, le=6, desc="A bout with at most this many lifts is a step.")
    turn_min_deg: float = P(30.0, unit="deg", ge=5.0, le=180.0, desc="A bout turning this much may be a turn...")
    turn_bl_per_90: float = P(1.0, ge=0.0, le=10.0, desc="... when it travels less than this many body lengths "
                                                         "per 90 deg turned.")
    turning_deg_s: float = P(20.0, unit="deg/s", ge=1.0, le=360.0,
                             desc="Within a bout, turning faster than this (over 1 s) starts a new part of it.")
    fast_two_up: float = P(0.4, ge=0.0, le=1.0, desc="Two or more hooves up in more than this share: fast (other).")
    fast_bl_s: float = P(1.5, unit="1/s", ge=0.0, le=10.0, desc="Trunk faster than this (body lengths/s): fast.")
    max_gap_frames: int = P(10, ge=0, le=100, desc="Unreliable runs longer than this are gaps (not read).")
    alpha: float = P(0.5, ge=0.0, le=5.0, desc="Transition smoothing: added to every count of the chain.")
    default_log_sd: float = P(0.5, ge=0.05, le=3.0, desc="Duration spread (log) used when a behaviour has one stretch.")
    min_reliable: float = P(0.6, ge=0.0, le=1.0, desc="A video with fewer reliable frames is not read (unusable).")
    min_body_px: float = P(120.0, unit="px", ge=0.0, le=2000.0, desc="A body smaller than this in the image is not read.")
    camera_moves_bl_s: float = P(0.15, unit="1/s", ge=0.0, le=10.0,
                                 desc="Background moving faster than this (body lengths/s): the camera moves, and "
                                      "the trunk's travel is not read.")


# ---------------------------------------------------------------------- stored records
class Evidence(BaseModel):
    rule: str
    features: dict[str, Any] = Field(default_factory=dict)


class Stretch(BaseModel):
    video: str
    start: int  # signal frame (= video frame for a lift)
    end: int
    t0: float
    t1: float
    behaviour: str
    confidence: float
    evidence: Evidence
    #: cut by the video's start or end or by a gap: its true duration is at least this
    censored: bool = False
    features: dict[str, Any] = Field(default_factory=dict)
    #: the researcher's affect tags of accepted clips cut from these frames (never inferred)
    affect: list[dict[str, Any]] = Field(default_factory=list)


class VideoReading(BaseModel):
    file: str
    sha256: str = ""
    usable: bool
    reasons: list[str] = Field(default_factory=list)
    frames: int = 0
    fps: float = 0.0
    seconds: float = 0.0
    seconds_read: float = 0.0
    camera: dict[str, Any] = Field(default_factory=dict)
    proportions: dict[str, Any] = Field(default_factory=dict)
    lift: dict[str, Any] = Field(default_factory=dict)
    stretches: int = 0


class Duration(BaseModel):
    n: int
    censored: int
    values_s: list[float]
    log_mean: float | None = None
    log_sd: float | None = None
    median_s: float | None = None
    mean_s: float | None = None
    note: str = ""


class SemiMarkov(BaseModel):
    """Behaviours as states; transitions between consecutive stretches; a duration distribution per state."""

    states: list[str]
    counts: dict[str, dict[str, int]]
    per_video: dict[str, dict[str, dict[str, int]]]
    alpha: float
    probabilities: dict[str, dict[str, float]]
    intervals_90: dict[str, dict[str, tuple[float, float]]]
    initial: dict[str, float]
    durations: dict[str, Duration]
    durations_per_video: dict[str, dict[str, list[float]]]


class Reading(BaseModel):
    schema_version: int = SCHEMA_VERSION
    kind: Literal["reading"] = "reading"
    id: str
    created: str
    settings: ReadingSettings
    provenance: dict[str, Any]
    videos: list[VideoReading]
    stretches: list[Stretch]
    behaviours: dict[str, dict[str, Any]]
    model: SemiMarkov
    support: dict[str, Any]
    gaps: list[dict[str, Any]]


# ---------------------------------------------------------------------- contact
def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    out, i, n = [], 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _running_min(v: np.ndarray, w: int) -> np.ndarray:
    h = max(1, w // 2)
    return np.array([np.min(v[max(0, i - h):i + h + 1]) for i in range(len(v))])


def lifted_from_heights(sig: MotionSignals, s: ReadingSettings) -> dict[str, np.ndarray]:
    """Per leg, frames with the hoof lifted (from heights: above its own recent low, with hysteresis)."""
    out = {}
    w = max(3, int(round(s.baseline_s * sig.fps)))
    min_n = int(round(s.min_lift_s * sig.fps))
    for leg, h in sig.hoof_mm.items():
        rel = h - _running_min(h, w) if sig.source == "lift" else h
        up = np.zeros(len(h), dtype=bool)
        state = False
        for i, x in enumerate(rel):
            state = x > s.lift_mm if not state else x > s.down_mm
            up[i] = state
        for a, b in _runs(up):
            if b - a < max(1, min_n):
                up[a:b] = False
        out[leg] = up
    return out


def lifted_from_speed(sig: MotionSignals, s: ReadingSettings) -> dict[str, np.ndarray]:
    """Per leg, frames with the hoof in swing: its paw moving over the ground in the image (with hysteresis)."""
    out = {}
    min_n = int(round(s.min_lift_s * sig.fps))
    for leg, v in (sig.hoof_speed_bl_s or {}).items():
        up = np.zeros(len(v), dtype=bool)
        state = False
        for i, x in enumerate(v):
            state = x > s.swing_bl_s if not state else x > s.stance_bl_s
            up[i] = state
        for a, b in _runs(up):
            if b - a < max(1, min_n):
                up[a:b] = False
        out[leg] = up
    return out


def lifted(sig: MotionSignals, s: ReadingSettings) -> tuple[dict[str, np.ndarray], str]:
    """Swing per leg and how it was found."""
    if sig.hoof_speed_bl_s:
        return lifted_from_speed(sig, s), "tracked paw speed over the ground"
    return lifted_from_heights(sig, s), "hoof height above its own low"


def lifted_from_contact(foot_force: np.ndarray, legs: list[str], fps: float = 50.0, min_s: float = 0.1
                        ) -> dict[str, np.ndarray]:
    """Per leg, frames with the hoof carrying 1 N or less (a rollout's contact forces, [F, legs]). Touches and
    lifts shorter than ``min_s`` (a hoof chattering on the floor) are ignored, as lifts are in footage."""
    n = max(1, int(round(min_s * fps)))
    out = {}
    for k, leg in enumerate(legs):
        up = foot_force[:, k] <= 1.0
        for a, b in _runs(~up):  # short touches inside a swing
            if b - a < n and a > 0 and b < len(up):
                up[a:b] = True
        for a, b in _runs(up):  # short lifts
            if b - a < n:
                up[a:b] = False
        out[leg] = up
    return out


# ---------------------------------------------------------------------- per-frame quantities
def _frame(sig: MotionSignals) -> dict[str, np.ndarray]:
    fps = sig.fps
    J = np.stack(list(sig.joints.values()), axis=1) if sig.joints else np.zeros((sig.frames, 1))
    qom = np.mean(np.abs(np.gradient(J, axis=0)), axis=1) * fps
    tilt = np.hypot(np.gradient(sig.pitch_deg), np.gradient(sig.roll_deg)) * fps
    speed = np.linalg.norm(np.gradient(sig.root_mm[:, :2], axis=0), axis=1) * fps
    turn = np.gradient(sig.heading_deg) * fps
    return {"qom": qom, "tilt": tilt, "speed": speed, "turn": turn}


def _clean_turn(sig: MotionSignals, a: int, b: int) -> float:
    """Heading change over [a, b) summed only across steps between reliable frames (a turn through frames the lift
    could not read is not counted: that is how 213625's 364 deg in 0.9 s arose)."""
    h = sig.heading_deg[a:b]
    r = sig.reliable[a:b]
    d = np.diff(h)
    ok = r[1:] & r[:-1]
    return float(np.sum(d[ok]))


def _group(jid: str) -> str:
    part = jid.split(".")[-1]
    if part == "hip_abd":
        return "hip_abd"
    return "hind" if jid.split(".")[1].startswith("h") else "fore"


def _period(x: np.ndarray, fps: float, lo_s: float = 0.3, hi_s: float = 3.0) -> tuple[float | None, float]:
    x = x - x.mean()
    e = float(np.sum(x * x))
    lo, hi = int(round(lo_s * fps)), min(int(round(hi_s * fps)), len(x) // 2)
    if e <= 1e-9 or hi <= lo + 1:
        return None, 0.0
    ac = np.array([np.sum(x[: len(x) - k] * x[k:]) / e * len(x) / (len(x) - k) for k in range(hi + 1)])
    k = lo + int(np.argmax(ac[lo:hi]))
    return (k / fps, float(max(0.0, min(1.0, ac[k])))) if ac[k] > 0.3 else (None, float(max(0.0, ac[k])))


def _footfall(onsets: list[tuple[float, str]]) -> dict[str, Any]:
    """Order of lift onsets and the pattern it shows."""
    seq = [leg for _t, leg in sorted(onsets)]
    nxt = {"hl": {"fl": "lateral", "fr": "diagonal"}, "hr": {"fr": "lateral", "fl": "diagonal"}}
    votes: dict[str, int] = {}
    for (t1, a), (t2, b) in zip(sorted(onsets), sorted(onsets)[1:], strict=False):
        if a in nxt and b in nxt[a] and t2 - t1 > 0.1:
            votes[nxt[a][b]] = votes.get(nxt[a][b], 0) + 1
        if {a, b} in ({"hl", "fr"}, {"hr", "fl"}) and abs(t2 - t1) <= 0.1:
            votes["diagonal pairs"] = votes.get("diagonal pairs", 0) + 1
    pattern = max(votes, key=lambda k: votes[k]) if votes else ("single" if len(seq) <= 1 else "irregular")
    return {"order": "-".join(seq[:16]), "pattern": pattern, "votes": votes}


def stretch_features(sig: MotionSignals, up: dict[str, np.ndarray], a: int, b: int, camera_moves: bool
                     ) -> dict[str, Any]:
    """What can be interpreted (not copied) from frames [a, b): see the module docstring. None = not read."""
    fps = sig.fps
    fr = _frame(sig.cut(a, b))
    dur = (b - a) / fps
    out: dict[str, Any] = {"duration_s": round(dur, 3), "qom_deg_s": round(float(np.mean(fr["qom"])), 2)}
    amp: dict[str, list[float]] = {}
    for j, v in sig.joints.items():
        seg = v[a:b]
        amp.setdefault(_group(j), []).append(float(np.percentile(seg, 90) - np.percentile(seg, 10)))
    out["amplitude_deg"] = {g: round(float(np.mean(v)), 2) for g, v in amp.items()}
    out["amplitude_mean_deg"] = round(float(np.mean([x for v in amp.values() for x in v])), 2) if amp else 0.0
    onsets = []
    duty = {}
    lift_peak = {}
    for leg in LEGS:
        if leg not in up:
            continue
        u_ = up[leg][a:b]
        duty[leg] = round(float(1.0 - np.mean(u_)), 3)
        for s0, _s1 in _runs(u_):
            if s0 > 0 or (a > 0 and not up[leg][a - 1]):
                onsets.append(((a + s0) / fps, leg))
        h = sig.hoof_mm.get(leg)
        if h is not None and u_.any():
            lift_peak[leg] = round(float(np.max(h[a:b][u_]) - np.min(h[a:b])), 1)
    out["lifts"] = len(onsets)
    out["step_rate_hz"] = round(len(onsets) / dur, 3) if dur > 0 else 0.0
    out["duty_factor"] = duty
    out["lift_height_mm"] = lift_peak
    n_up = np.sum([up[leg][a:b] for leg in up], axis=0) if up else np.zeros(b - a)
    out["two_up_fraction"] = round(float(np.mean(n_up >= 2)), 3)
    out["footfall"] = _footfall(onsets)
    by_leg: dict[str, list[float]] = {}
    for t, leg in onsets:
        by_leg.setdefault(leg, []).append(t)
    strides = [d for ts in by_leg.values() for d in np.diff(sorted(ts)) if d > 0]
    if strides:
        out["tempo_s"], out["tempo_source"] = round(float(np.median(strides)), 3), "stride period"
    else:
        per, reg = _period(fr["qom"], fps)
        out["tempo_s"], out["tempo_source"] = (round(per, 3) if per else None), "activity repetition"
        out["tempo_regularity"] = round(reg, 3)
    act = fr["qom"] > max(2.0 * float(np.median(fr["qom"])), 8.0)
    bursts = [r for r in _runs(act) if r[1] - r[0] >= 2]
    out["bursts_per_s"] = round(len(bursts) / dur, 3) if dur > 0 else 0.0
    pauses = [(q[0] - p[1]) / fps for p, q in zip(bursts, bursts[1:], strict=False)]
    out["pause_s"] = round(float(np.mean(pauses)), 3) if pauses else None
    pitch, roll = sig.pitch_deg[a:b], sig.roll_deg[a:b]
    out["roll_range_deg"] = round(float(np.percentile(roll, 95) - np.percentile(roll, 5)), 2)
    out["pitch_range_deg"] = round(float(np.percentile(pitch, 95) - np.percentile(pitch, 5)), 2)
    z = sig.root_mm[a:b, 2]
    out["heave_mm"] = round(float(np.percentile(z, 95) - np.percentile(z, 5)), 1)
    out["lean_roll_deg"] = round(float(np.mean(roll) - np.median(sig.roll_deg)), 2)
    out["lean_pitch_deg"] = round(float(np.mean(pitch) - np.median(sig.pitch_deg)), 2)
    lean = []
    if abs(out["lean_roll_deg"]) >= 1.0:
        lean.append("right side down" if out["lean_roll_deg"] > 0 else "left side down")
    if abs(out["lean_pitch_deg"]) >= 1.0:
        lean.append("nose down" if out["lean_pitch_deg"] > 0 else "nose up")
    out["lean"] = ", ".join(lean) or "level"
    turn = _clean_turn(sig, a, b)
    out["turn_deg"] = round(turn, 1)
    out["turn_rate_deg_s"] = round(turn / dur, 2) if dur > 0 else 0.0
    out["turn_direction"] = "left" if turn > 5 else "right" if turn < -5 else "none"
    if camera_moves:
        out["travel_mm"] = out["speed_mm_s"] = out["lateral_sway_mm"] = None
    else:
        xy = sig.root_mm[a:b, :2]
        out["travel_mm"] = round(float(np.linalg.norm(xy[-1] - xy[0])), 1)
        out["speed_mm_s"] = round(out["travel_mm"] / dur, 1) if dur > 0 else 0.0
        hd = math.radians(float(np.mean(sig.heading_deg[a:b])))
        lat = (xy - xy.mean(axis=0)) @ np.array([-math.sin(hd), math.cos(hd)])
        out["lateral_sway_mm"] = round(float(np.percentile(lat, 95) - np.percentile(lat, 5)), 1)
    q = fr["qom"]
    top = float(np.percentile(q, 75)) if len(q) else 0.0
    rise = np.flatnonzero(q >= 0.63 * top)
    out["onset_s"] = round(float(rise[0]) / fps, 3) if len(rise) and top > 0 else None
    out["offset_s"] = round(float(len(q) - 1 - rise[-1]) / fps, 3) if len(rise) and top > 0 else None
    out["abruptness"] = (round(1.0 / max(out["onset_s"], 1.0 / fps), 2) if out["onset_s"] is not None else None)
    if sig.head_bl_s is not None:
        out["head_motion_bl_s"] = round(float(np.mean(sig.head_bl_s[a:b])), 3)
    return out


# ---------------------------------------------------------------------- labelling
def label(sig: MotionSignals, up: dict[str, np.ndarray], s: ReadingSettings, camera_moves: bool = False,
          video: str = "") -> list[Stretch]:
    """Stretches of one recording, in order, each with its rule, evidence and confidence."""
    F, fps = sig.frames, sig.fps
    bad = ~sig.reliable
    gap = np.zeros(F, dtype=bool)
    for a, b in _runs(bad):
        if b - a > s.max_gap_frames:
            gap[a:b] = True
    any_up = np.any(np.stack([up[k] for k in up]), axis=0) if up else np.zeros(F, dtype=bool)
    any_up &= ~gap
    # stepping bouts: lifts joined across short all-down gaps, never across a reading gap
    bouts = _runs(any_up)
    joined: list[list[int]] = []
    for a, b in bouts:
        if joined and (a - joined[-1][1]) / fps < s.join_s and not gap[joined[-1][1]:a].any():
            joined[-1][1] = b
        else:
            joined.append([a, b])
    lab = np.array(["stand"] * F, dtype=object)
    fr = _frame(sig)
    blen = max(sig.body_length_mm, 1e-9)
    segs: list[tuple[int, int, str, str, dict[str, Any], float]] = []
    # a bout may change character without a pause (a turn running into a gallop): split it where the share of two
    # hooves up (over 1 s) crosses the fast threshold, or the turn rate (over 1 s) crosses ``turning_deg_s``
    n_up = np.sum([up[k] for k in up], axis=0) if up else np.zeros(F)
    w1 = max(1, int(round(fps)))
    k1 = np.ones(w1) / w1
    two = np.convolve((n_up >= 2).astype(float), k1, mode="same") > s.fast_two_up
    turning = np.abs(np.convolve(fr["turn"], k1, mode="same")) > s.turning_deg_s
    regime = two.astype(int) * 2 + turning.astype(int)
    min_part = max(1, int(round(0.6 * fps)))
    parts: list[tuple[int, int]] = []
    for a, b in joined:
        r = regime[a:b].copy()
        changed = True
        while changed:  # parts shorter than 0.6 s join the longer neighbour
            changed = False
            rr = [(c, d) for v in np.unique(r) for c, d in _runs(r == v)]
            rr.sort()
            for i, (c, d) in enumerate(rr):
                if d - c < min_part and len(rr) > 1:
                    nb = [rr[m] for m in (i - 1, i + 1) if 0 <= m < len(rr)]
                    tgt = max(nb, key=lambda q: q[1] - q[0])
                    r[c:d] = r[tgt[0]]
                    changed = True
                    break
        cuts = [a] + [a + i for i in range(1, b - a) if r[i] != r[i - 1]] + [b]
        parts.extend(zip(cuts[:-1], cuts[1:], strict=True))
    for a, b in parts:
        f = stretch_features(sig, up, a, b, camera_moves)
        sp = f.get("speed_mm_s")
        sp_bl = None if sp is None else sp / blen
        turn = abs(f["turn_deg"])
        if f["two_up_fraction"] > s.fast_two_up or (sp_bl is not None and sp_bl > s.fast_bl_s):
            beh = "other"
            why = (f"two or more hooves up in {f['two_up_fraction']:.0%} (> {s.fast_two_up:.0%})"
                   + (f", trunk {sp_bl:.2f} body lengths/s" if sp_bl is not None else ""))
            margin = max(f["two_up_fraction"] / max(s.fast_two_up, 1e-9), (sp_bl or 0) / max(s.fast_bl_s, 1e-9))
        elif f["lifts"] <= s.step_max_lifts:
            beh, why = "step", f"{f['lifts']} lift(s) (<= {s.step_max_lifts})"
            margin = 1.5
        elif turn >= s.turn_min_deg and (f.get("travel_mm") is None
                                         or f["travel_mm"] / blen < s.turn_bl_per_90 * turn / 90.0):
            beh = "turn"
            why = (f"turned {f['turn_deg']:+.0f} deg (>= {s.turn_min_deg:g})"
                   + ("" if f.get("travel_mm") is None else f", travelled {f['travel_mm'] / blen:.2f} body lengths"))
            margin = turn / s.turn_min_deg
        else:
            beh = "walk"
            why = f"{f['lifts']} lifts" + (f", turned {f['turn_deg']:+.0f} deg" if turn else "")
            margin = f["lifts"] / (s.step_max_lifts + 1)
        segs.append((a, b, beh, why, f, margin))
        lab[a:b] = beh
    # all hooves down: still or shifting weight
    moving = (fr["qom"] > s.still_qom_deg_s) | (fr["tilt"] > s.still_tilt_deg_s)
    win = max(1, int(round(0.5 * fps)))
    moving = np.convolve(moving.astype(float), np.ones(win) / win, mode="same") > 0.5
    covered = np.zeros(F, dtype=bool)
    for a, b, *_ in segs:
        covered[a:b] = True
    for a, b in _runs(~covered & ~gap):
        for c, d in _runs(moving[a:b]):
            lab[a + c:a + d] = "weight_shift"
        for c, d in _runs(~moving[a:b]):
            lab[a + c:a + d] = "stand"
    lab[gap] = "gap"
    # stretches, short ones absorbed by the longer neighbour (never across a gap or into a bout)
    min_n = int(round(s.min_stretch_s * fps))
    changed = True
    while changed:
        changed = False
        runs = []
        i = 0
        while i < F:
            j = i
            while j < F and lab[j] == lab[i]:
                j += 1
            runs.append((i, j, lab[i]))
            i = j
        for k, (a, b, beh) in enumerate(runs):
            if beh == "gap" or b - a >= min_n or beh in ("step", "walk", "turn", "other"):
                continue
            near = [runs[m] for m in (k - 1, k + 1) if 0 <= m < len(runs) and runs[m][2] != "gap"]
            if not near:
                continue
            into = max(near, key=lambda r: r[1] - r[0])
            lab[a:b] = into[2]
            changed = True
            break
    bout_info = {(a, b): (beh, why, f, m) for a, b, beh, why, f, m in segs}
    out: list[Stretch] = []
    i = 0
    while i < F:
        j = i
        while j < F and lab[j] == lab[i]:
            j += 1
        beh = str(lab[i])
        if beh != "gap":
            f = stretch_features(sig, up, i, j, camera_moves)
            rel = float(np.mean(sig.reliable[i:j]))
            if beh in ("stand", "weight_shift"):
                q = float(np.mean(fr["qom"][i:j]))
                tl = float(np.mean(fr["tilt"][i:j]))
                if beh == "stand":
                    why = f"all hooves down; joints {q:.1f} deg/s, trunk tilt {tl:.1f} deg/s (still)"
                    margin = 2.0 - max(q / max(s.still_qom_deg_s, 1e-9), tl / max(s.still_tilt_deg_s, 1e-9))
                else:
                    why = f"all hooves down; joints {q:.1f} deg/s or trunk tilt {tl:.1f} deg/s moving"
                    margin = max(q / max(s.still_qom_deg_s, 1e-9), tl / max(s.still_tilt_deg_s, 1e-9))
            else:
                info = bout_info.get((i, j)) or max(
                    (v for (a2, b2), v in bout_info.items() if v[0] == beh and min(b2, j) > max(a2, i)),
                    key=lambda v: v[2].get("duration_s", 0.0), default=None)
                why = info[1] if info else f"stepping bout ({f['lifts']} lifts)"
                margin = info[3] if info else 1.0
            conf = rel * float(np.clip(0.5 + 0.5 * (margin - 1.0), 0.3, 1.0))
            censored = i == 0 or j == F or (i > 0 and lab[i - 1] == "gap") or (j < F and lab[j] == "gap")
            vf = sig.video_frame
            out.append(Stretch(
                video=video, start=int(vf[i]) if vf is not None else i, end=int(vf[j - 1]) + 1 if vf is not None else j,
                t0=round(i / fps, 3), t1=round(j / fps, 3), behaviour=beh, confidence=round(conf, 3),
                evidence=Evidence(rule=why, features={k: f.get(k) for k in (
                    "lifts", "two_up_fraction", "turn_deg", "travel_mm", "speed_mm_s", "qom_deg_s", "duration_s")}
                    | {"reliable_fraction": round(rel, 3)}),
                censored=censored, features=f))
        i = j
    return out


# ---------------------------------------------------------------------- the model
def _beta_interval(k: float, n: float, alpha: float, k_states: int) -> tuple[float, float]:
    from scipy.stats import beta

    a = k + alpha
    b = (n - k) + alpha * max(1, k_states - 2)
    return float(beta.ppf(0.05, a, b)), float(beta.ppf(0.95, a, b))


def fit_model(stretches: list[Stretch], s: ReadingSettings) -> SemiMarkov:
    states = list(BEHAVIOURS)
    K = len(states)
    counts = {a: dict.fromkeys(states, 0) for a in states}
    per_video: dict[str, dict[str, dict[str, int]]] = {}
    first: dict[str, int] = dict.fromkeys(states, 0)
    by_video: dict[str, list[Stretch]] = {}
    for st in stretches:
        by_video.setdefault(st.video, []).append(st)
    for v, sts in by_video.items():
        pv = per_video.setdefault(v, {})
        sts = sorted(sts, key=lambda x: x.start)
        prev: Stretch | None = None
        for st in sts:
            if prev is not None and st.start == prev.end:  # consecutive (no gap between)
                counts[prev.behaviour][st.behaviour] += 1
                pv.setdefault(prev.behaviour, {}).setdefault(st.behaviour, 0)
                pv[prev.behaviour][st.behaviour] += 1
            else:
                first[st.behaviour] += 1
            prev = st
    probs: dict[str, dict[str, float]] = {}
    ints: dict[str, dict[str, tuple[float, float]]] = {}
    for a in states:
        row = {b: counts[a][b] + (s.alpha if b != a else 0.0) for b in states}
        row[a] = 0.0
        tot = sum(row.values())
        n = sum(counts[a].values())
        probs[a] = {b: round(row[b] / tot, 4) if tot > 0 else 0.0 for b in states}
        ints[a] = {b: tuple(round(x, 3) for x in _beta_interval(counts[a][b], n, s.alpha, K)) for b in states if b != a}  # type: ignore[misc]
    tot_first = sum(first.values()) + s.alpha * K
    initial = {b: round((first[b] + s.alpha) / tot_first, 4) for b in states}
    durations: dict[str, Duration] = {}
    dpv: dict[str, dict[str, list[float]]] = {}
    for b in states:
        vals = [(st.t1 - st.t0, st.censored) for st in stretches if st.behaviour == b]
        for st in stretches:
            if st.behaviour == b:
                dpv.setdefault(st.video, {}).setdefault(b, []).append(round(st.t1 - st.t0, 3))
        full = [d for d, c in vals if not c]
        use = full if full else [d for d, _c in vals]
        note = "" if full or not vals else "only censored stretches: their lengths are lower bounds"
        if not use:
            durations[b] = Duration(n=0, censored=0, values_s=[], note="not seen")
            continue
        lv = np.log(np.maximum(use, 1e-3))
        sd = float(np.std(lv, ddof=1)) if len(use) >= 2 else s.default_log_sd
        if len(use) < 2:
            note = (note + "; " if note else "") + f"one stretch: spread {s.default_log_sd} (log) assumed"
        mu = float(np.mean(lv))
        durations[b] = Duration(n=len(vals), censored=sum(c for _d, c in vals), values_s=[round(d, 3) for d, _c in vals],
                                log_mean=round(mu, 4), log_sd=round(sd, 4), median_s=round(math.exp(mu), 3),
                                mean_s=round(math.exp(mu + sd * sd / 2), 3), note=note)
    return SemiMarkov(states=states, counts=counts, per_video=per_video, alpha=s.alpha, probabilities=probs,
                      intervals_90=ints, initial=initial, durations=durations, durations_per_video=dpv)


FEATURE_KEYS = ("duration_s", "qom_deg_s", "amplitude_mean_deg", "tempo_s", "step_rate_hz", "two_up_fraction",
                "roll_range_deg", "pitch_range_deg", "heave_mm", "lateral_sway_mm", "turn_rate_deg_s", "speed_mm_s",
                "lean_roll_deg", "lean_pitch_deg", "bursts_per_s", "abruptness", "head_motion_bl_s")


def behaviour_summary(stretches: list[Stretch]) -> dict[str, dict[str, Any]]:
    """Per behaviour: count, time, share, and every feature's mean, spread and count (weighted by duration)."""
    total = sum(st.t1 - st.t0 for st in stretches) or 1.0
    out: dict[str, dict[str, Any]] = {}
    for b in BEHAVIOURS:
        sts = [st for st in stretches if st.behaviour == b]
        secs = sum(st.t1 - st.t0 for st in sts)
        feats: dict[str, Any] = {}
        for k in FEATURE_KEYS:
            vals = [(st.features.get(k), st.t1 - st.t0) for st in sts if st.features.get(k) is not None]
            if not vals:
                continue
            x = np.array([v for v, _w in vals], dtype=float)
            w = np.array([w for _v, w in vals], dtype=float)
            m = float(np.average(x, weights=w))
            sd = float(math.sqrt(np.average((x - m) ** 2, weights=w))) if len(x) > 1 else None
            feats[k] = {"mean": round(m, 3), "sd": None if sd is None else round(sd, 3), "n": len(x)}
        patterns: dict[str, int] = {}
        for st in sts:
            p = (st.features.get("footfall") or {}).get("pattern")
            if p and st.features.get("lifts", 0) >= 2:
                patterns[p] = patterns.get(p, 0) + 1
        turns = [st.features.get("turn_direction") for st in sts]
        out[b] = {"label": LABELS[b], "n": len(sts), "seconds": round(secs, 3), "share": round(secs / total, 4),
                  "videos": sorted({st.video for st in sts}), "features": feats, "footfall_patterns": patterns,
                  "turn_directions": {d: turns.count(d) for d in ("left", "right", "none") if turns.count(d)},
                  "mean_confidence": round(float(np.mean([st.confidence for st in sts])), 3) if sts else None}
    return out


def support_statement(videos: list[VideoReading], stretches: list[Stretch], model: SemiMarkov,
                      notes: list[str] | None = None) -> dict[str, Any]:
    """How far this footage carries the model, in numbers and plain words."""
    total = sum(v.seconds for v in videos)
    read = sum(v.seconds_read for v in videos)
    usable = [v for v in videos if v.usable]
    trans = sum(sum(r.values()) for r in model.counts.values())
    seen_pairs = sum(1 for r in model.counts.values() for c in r.values() if c > 0)
    possible = len(model.states) * (len(model.states) - 1)
    per_beh = {b: d.n for b, d in model.durations.items()}
    widths = [hi - lo for r in model.intervals_90.values() for lo, hi in r.values()]
    observed = [b for b, n in per_beh.items() if n > 0]
    lines = [
        f"{total:.1f} s of footage in {len(videos)} videos; {len(usable)} usable, {read:.1f} s of them read "
        f"(the rest are gaps the lift could not read).",
        f"{len(stretches)} stretches of {len(observed)} behaviours "
        + ", ".join(f"{LABELS[b].lower()} {per_beh[b]}" for b in observed) + ".",
        f"{trans} transitions between consecutive stretches: {seen_pairs} of {possible} possible kinds seen at least once. "
        f"The 90 % intervals of the transition probabilities are {np.median(widths):.2f} wide in the median: the "
        "chain's structure is a sketch, not a measurement.",
        "Enough to say which behaviours occur, roughly in what shares, and the order of magnitude of their durations "
        "and character (tempo, amplitude, sway). Not enough for: transition probabilities, duration distributions' "
        "shapes, differences between individual calves, or anything about rare behaviours.",
        *(notes or []),
    ]
    return {"seconds_total": round(total, 2), "seconds_read": round(read, 2), "videos_usable": len(usable),
            "stretches": len(stretches), "transitions": trans, "transition_kinds_seen": seen_pairs,
            "transition_kinds_possible": possible, "median_interval_width": round(float(np.median(widths)), 3)
            if widths else None, "per_behaviour": per_beh, "lines": lines}


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")
