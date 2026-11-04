"""A physically feasible version of a clip that keeps its character (ADR-084).

The clip as retargeted is never changed: the adapted clip is a new one, with
the operations that made it and the raw clip's provenance. Four operations,
all on the clip's joint angles (relative to standing):

* **time scale** k: the clip plays k times slower (fps / k);
* **amplitude** per joint (left and right of a pair together): angles x a;
* a **low-pass cutoff** (zero-lag Butterworth, as the clip smoothing), which
  takes the sharpest accelerations out;
* a **range margin**: angles kept a few degrees inside each joint's range.

The search (deterministic, a few dozen physics plays):

1. Start from the kinematic bound: slow the clip until its fastest joint is
   within (1 - margin) of its servo's speed (the clip report's playable speed,
   with the margin), and keep it ``range_margin_deg`` inside the ranges.
2. Play it in physics (:mod:`calflab.behave.physics`) and take the worst
   violated limit (a fall first). Try the remedies for that limit (slower,
   smoother, smaller at the joint that limits, smaller overall) and keep the
   one that lowers the total excess most; ties go to the one that keeps more
   character.
3. Once every limit holds, **give back**: try playing faster and larger again,
   step by step, keeping a step only if every limit still holds and more of
   the character is kept.

It stops when every limit holds with the margin (and the body stands), or
after ``max_rounds``; then the best version found is returned, marked
feasible or not.

**Character kept** (my measure; the parts are reported apart): the movement
features of :mod:`calflab.behave.descriptors` of what the robot did in
physics during the clip, against the raw clip posed kinematically at its own
speed:

* quantity of motion (mean joint speed) adapted / raw;
* expressive range (spread of 1 s windows of motion) adapted / raw;
* rhythm: the raw tempo (period of the strongest repetition) / the adapted one;
* shape: exp(-(e / 15 deg)^2), with e the RMS difference between the joint
  angles the robot reached and the raw clip at the same point of the clip
  (time-warped, so slowing alone costs nothing here).

Each is capped at 1; the score is their geometric mean. Tracking error
against the adapted clip itself is reported too.

Not done: moving contact phases in time, and a trajectory optimisation.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.model.spec import RobotSpec
from calflab.project.motions import MotionClip
from calflab.schema import P

#: constraint key -> the time-strip row that says which joint is responsible
STRIP_KEY = {"envelope": "envelope", "joint_speed": "speed", "stall": "stall", "servo_sustained": "rated",
             "belt_sustained": "belt", "belt_breaking": "belt_breaking", "joint_limit": "joint_limit"}
SPEED_KEYS = ("envelope", "joint_speed")


class AdaptSettings(BaseModel):
    margin: float = P(0.2, ge=0.0, le=0.9, step=0.05,
                      desc="Safety margin kept on every limit (stall, rated, speed, envelope, belt tensions).")
    max_rounds: int = P(12, ge=1, le=60, desc="Rounds of the search (each plays two or three versions in physics).")
    max_slowdown: float = P(4.0, ge=1.0, le=10.0, step=0.25, desc="Slowest allowed: this many times the clip's duration.")
    min_amplitude: float = P(0.3, ge=0.0, le=1.0, step=0.05, desc="Smallest amplitude allowed at any joint.")
    slow_step: float = P(1.25, ge=1.05, le=2.0, step=0.05, advanced=True, desc="Slow-down per step.")
    amplitude_step: float = P(0.8, ge=0.5, le=0.95, step=0.05, advanced=True, desc="Amplitude factor per step.")
    first_cutoff_hz: float = P(3.0, unit="Hz", ge=0.5, le=10.0, advanced=True, desc="First low-pass cutoff tried.")
    range_margin_deg: float = P(2.0, unit="deg", ge=0.0, le=20.0, desc="Keep the clip this far inside each joint's range.")
    give_back_rounds: int = P(4, ge=0, le=20, advanced=True, desc="Rounds trying to give speed and amplitude back.")
    plant: bool = P(True, desc="Start from the clip planted: supporting hooves kept still, at least min_support "
                                       "hooves down, the centre of mass over them (calflab.behave.stance).")
    min_support: int = P(3, ge=0, le=4, desc="Hooves kept on the ground when planting (a fall may raise it to 4).")
    stability_margin_mm: float = P(15.0, unit="mm", ge=0.0, le=80.0, step=5.0,
                                   desc="Centre of mass this far inside the support polygon when planting (a fall may "
                                        "raise it; PROVISIONAL).")
    shape_scale_deg: float = P(15.0, unit="deg", ge=1.0, le=90.0, advanced=True,
                               desc="Shape kept = exp(-(RMS difference / this)^2).")


class Operations(BaseModel):
    """What turns the raw clip into the adapted one, applied in this order: amplitude, low-pass, range margin,
    planting (:func:`calflab.behave.stance.plant`), then time scale."""

    time_scale: float = 1.0
    amplitude: dict[str, float] = Field(default_factory=dict)  # per joint id; missing = 1
    cutoff_hz: float | None = None
    range_margin_deg: float = 0.0
    plant: bool = False
    min_support: int = 3  # hooves kept down when planting
    stability_margin_mm: float = 15.0  # centre of mass this far inside the support polygon when planting

    def describe(self) -> str:
        amp = {k.replace("joint.", ""): round(v, 2) for k, v in sorted(self.amplitude.items()) if abs(v - 1.0) > 1e-3}
        parts = [f"{self.time_scale:.2f}x slower" if self.time_scale > 1.0001 else "own speed"]
        if amp:
            parts.append("amplitude " + ", ".join(f"{k} {v}" for k, v in amp.items()))
        if self.cutoff_hz:
            parts.append(f"low-pass {self.cutoff_hz:.1f} Hz")
        if self.range_margin_deg:
            parts.append(f"{self.range_margin_deg:g} deg inside the ranges")
        if self.plant:
            parts.append(f"planted ({self.min_support} hooves down, centre of mass {self.stability_margin_mm:g} mm inside)")
        return "; ".join(parts)

    def joint_key(self) -> str:
        """Everything but the time scale: the operations that change the angles (planting is costly; cache on this)."""
        return self.model_copy(update={"time_scale": 1.0}).model_dump_json()


def twin(jid: str) -> str:
    """The joint on the other side (joint.hl.stifle <-> joint.hr.stifle)."""
    parts = jid.split(".")
    if len(parts) == 3 and len(parts[1]) == 2 and parts[1][1] in "lr":
        parts[1] = parts[1][0] + ("r" if parts[1][1] == "l" else "l")
    return ".".join(parts)


def apply(clip: MotionClip, ops: Operations, spec: RobotSpec, lib: Any = None,
          cache: dict[str, tuple[MotionClip, dict[str, Any]]] | None = None) -> MotionClip:
    """The adapted clip (a new object; ``clip`` is not touched). ``lib`` is needed to plant; ``cache`` keeps the
    angles per :meth:`Operations.joint_key`, so trying another time scale does not plant again."""
    key = ops.joint_key()
    if cache is not None and key in cache:
        shaped, info = cache[key]
    else:
        shaped, info = _shape(clip, ops, spec, lib)
        if cache is not None:
            cache[key] = (shaped, info)
    meta: dict[str, Any] = {"adapted_operations": ops.model_dump(mode="json")}
    if info:
        meta["stance"] = {k: v for k, v in info.items() if k not in ("support", "trunk_pose")}
        meta["stance"]["support"] = info.get("support")
    if shaped.meta.get("stance_paths"):
        meta["stance_paths"] = shaped.meta["stance_paths"]
    return MotionClip(id="", name=f"{clip.name} (feasible)", fps=clip.fps / max(ops.time_scale, 1e-6),
                      joints={j: list(v) for j, v in shaped.joints.items()}, source="adapted",
                      root_pos=list(clip.root_pos), root_quat=list(clip.root_quat), meta=meta)


def _shape(clip: MotionClip, ops: Operations, spec: RobotSpec, lib: Any) -> tuple[MotionClip, dict[str, Any]]:
    """Amplitude, low-pass and range margin at the clip's own fps, then planting. Returns the clip and the stance
    information (empty without planting)."""
    from calflab.behave.smoothing import lowpass, max_cutoff_hz
    from calflab.behave.stance import StanceSettings, plant

    rest = spec.rest_angles()
    fps = clip.fps
    joints: dict[str, list[float]] = {}
    for jid, vals in clip.joints.items():
        v = np.asarray(vals, dtype=float) * float(ops.amplitude.get(jid, 1.0))
        if ops.cutoff_hz and len(v) > 12 and ops.cutoff_hz < max_cutoff_hz(fps):
            v = lowpass(v, fps, ops.cutoff_hz)
        try:
            lo, hi = spec.joint(jid).range_deg
            r = rest.get(jid, 0.0)
            v = np.clip(v, lo - r + ops.range_margin_deg, hi - r - ops.range_margin_deg)
        except KeyError:
            pass
        joints[jid] = [round(float(x), 4) for x in v]
    shaped = clip.model_copy(update={"joints": joints, "meta": {}})
    if not ops.plant:
        return shaped, {}
    if lib is None:
        raise ValueError("Planting needs the component library")
    st = StanceSettings(min_support=ops.min_support, stability_margin_mm=ops.stability_margin_mm,
                        range_margin_deg=ops.range_margin_deg)
    return plant(shaped, spec, lib, st)


def initial(clip: MotionClip, spec: RobotSpec, lib: Any, s: AdaptSettings) -> Operations:
    """The kinematic starting point: slow enough for every servo with the margin, inside the ranges."""
    from calflab.behave.feasibility import clip_report

    rep = clip_report(clip, spec, lib)
    k = max(1.0, float(rep["max_speed_ratio"]) / max(1e-6, 1.0 - s.margin))
    return Operations(time_scale=min(s.max_slowdown, round(k, 3)), range_margin_deg=s.range_margin_deg,
                      plant=s.plant, min_support=s.min_support, stability_margin_mm=s.stability_margin_mm)


def character(raw_features: dict[str, Any], physics_features: dict[str, Any], shape_rms_deg: float | None,
              s: AdaptSettings) -> dict[str, Any]:
    """How much of the raw movement the robot kept (each part capped at 1) and their geometric mean."""
    def ratio(a: Any, b: Any) -> float | None:
        if a is None or b is None or b <= 1e-9:
            return None
        return float(min(1.0, max(0.0, a / b)))

    qom = ratio(physics_features.get("quantity_of_motion_deg_s"), raw_features.get("quantity_of_motion_deg_s"))
    rng = ratio(physics_features.get("expressive_range_deg_s"), raw_features.get("expressive_range_deg_s"))
    rt, at = raw_features.get("tempo_s"), physics_features.get("tempo_s")
    rhythm = ratio(rt, at) if rt and at else None
    shape = None if shape_rms_deg is None else float(math.exp(-((shape_rms_deg / s.shape_scale_deg) ** 2)))
    parts = [x for x in (qom, rng, rhythm, shape) if x is not None]
    score = float(np.exp(np.mean(np.log(np.maximum(parts, 1e-3))))) if parts else 0.0
    return {"quantity_of_motion": qom, "expressive_range": rng, "rhythm": rhythm, "shape": shape,
            "shape_rms_deg": shape_rms_deg, "score": score,
            "raw": {k: raw_features.get(k) for k in ("quantity_of_motion_deg_s", "expressive_range_deg_s", "tempo_s")},
            "adapted": {k: physics_features.get(k) for k in ("quantity_of_motion_deg_s", "expressive_range_deg_s", "tempo_s")}}


def badness(rep: dict[str, Any]) -> float:
    """Total excess over the limits (0 = every limit holds and the body stands)."""
    b = 0.0
    for c in rep["constraints"]:
        if c["violated"] and c["key"] != "fall" and c["limit"]:
            b += min(3.0, float(c["value"]) / float(c["limit"]) - 1.0)
    if rep.get("fell"):
        end = float(rep["timing"]["end_t"]) or 1.0
        b += 3.0 + (1.0 - min(1.0, float(rep.get("fall_time_s") or 0.0) / end))
    return round(b, 5)


def worst(rep: dict[str, Any]) -> tuple[str, str | None]:
    """The limit to fix next and the joint responsible (None for the whole body)."""
    if rep.get("fell"):
        return "fall", None
    bad = [c for c in rep["constraints"] if c["violated"] and c["key"] != "fall" and c["limit"]]
    if not bad:
        return "", None
    c = max(bad, key=lambda c: float(c["value"]) / float(c["limit"]))
    row = next((r for r in rep["strip"]["rows"] if r["key"] == STRIP_KEY.get(c["key"])), None)
    joint = f"joint.{row['peak_joint']}" if row and row.get("peak_joint") and row["peak_joint"] != "trunk" else None
    return c["key"], joint


def remedies(key: str, joint: str | None, ops: Operations, clip: MotionClip, s: AdaptSettings) -> list[tuple[str, Operations]]:
    """Versions to try against the limit ``key`` at ``joint``, each one step from ``ops``."""
    out: list[tuple[str, Operations]] = []

    def slower() -> None:
        if ops.time_scale * s.slow_step <= s.max_slowdown + 1e-9:
            out.append((f"slower ({ops.time_scale * s.slow_step:.2f}x)",
                        ops.model_copy(update={"time_scale": round(ops.time_scale * s.slow_step, 4)})))

    def smaller(joints: list[str], what: str) -> None:
        amp = dict(ops.amplitude)
        changed = False
        for j in joints:
            a = amp.get(j, 1.0) * s.amplitude_step
            if a >= s.min_amplitude - 1e-9:
                amp[j] = round(a, 4)
                changed = True
        if changed:
            out.append((f"smaller {what}", ops.model_copy(update={"amplitude": amp})))

    def smoother() -> None:
        c = s.first_cutoff_hz if not ops.cutoff_hz else ops.cutoff_hz * 0.75
        if c >= 0.5:
            out.append((f"low-pass {c:.1f} Hz", ops.model_copy(update={"cutoff_hz": round(c, 3)})))

    def steadier() -> None:
        if ops.plant and ops.min_support < 4:
            out.append(("keep more hooves down (4)", ops.model_copy(update={"min_support": 4})))
        if ops.plant and ops.stability_margin_mm + 10.0 <= 80.0:
            out.append((f"larger stability margin ({ops.stability_margin_mm + 10:g} mm)",
                        ops.model_copy(update={"stability_margin_mm": ops.stability_margin_mm + 10.0})))
        if not ops.plant:
            out.append(("plant the hooves", ops.model_copy(update={"plant": True})))

    every = list(clip.joints)
    pair = [joint, twin(joint)] if joint else []
    jname = (joint or "").replace("joint.", "")
    if key == "fall":
        steadier()
        smaller(every, "overall")
        slower()
        smoother()
    elif key in SPEED_KEYS:
        slower()
        smoother()
        if pair:
            smaller([j for j in pair if j in clip.joints], f"at {jname} (both sides)")
    elif key == "joint_limit":
        if pair:
            smaller([j for j in pair if j in clip.joints], f"at {jname} (both sides)")
        if ops.range_margin_deg + 3.0 <= 20.0:
            out.append((f"{ops.range_margin_deg + 3:g} deg inside the ranges",
                        ops.model_copy(update={"range_margin_deg": ops.range_margin_deg + 3.0})))
    elif key == "":  # the broad remedies, when nothing aimed at the limit helped
        slower()
        smoother()
        smaller(every, "overall")
    else:  # torque and belt limits
        if pair:
            smaller([j for j in pair if j in clip.joints], f"at {jname} (both sides)")
        slower()
        smaller(every, "overall")
    return out


def adapt(clip: MotionClip, spec: RobotSpec, lib: Any, play: Callable[[MotionClip], tuple[Any, dict[str, Any]]],
          s: AdaptSettings, progress: Callable[[str], None] | None = None,
          cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Search for a feasible version of ``clip``. ``play(clip) -> (rollout, report)`` plays a clip in physics with
    the margin. Returns the raw and adapted results, the steps taken and the adapted clip."""
    from calflab.behave.descriptors import movement_features
    from calflab.behave.physics import clip_part
    from calflab.behave.preview import preview_rollout

    raw_features = movement_features(preview_rollout(clip, spec), spec)
    tried: dict[str, dict[str, Any]] = {}
    shaped: dict[str, Any] = {}

    def evaluate(ops: Operations) -> dict[str, Any]:
        key = ops.model_dump_json()
        if key in tried:
            return tried[key]
        c = apply(clip, ops, spec, lib, shaped)
        c.id = (clip.id or "clip") + ".adapted"
        rollout, rep = play(c)
        part = clip_part(rollout, rep["timing"])
        shape = _shape_rms(rollout, rep, clip, spec, ops)
        ch = character(raw_features, movement_features(part, spec), shape, s)
        out = {"ops": ops, "clip": c, "rollout": rollout, "report": rep, "badness": badness(rep), "character": ch}
        tried[key] = out
        return out

    def note(msg: str) -> None:
        if progress is not None:
            progress(msg)

    note("playing the clip as retargeted")
    raw = evaluate(Operations())
    steps: list[dict[str, Any]] = [_step(0, "as retargeted", raw)]
    cur = evaluate(initial(clip, spec, lib, s))
    steps.append(_step(0, "kinematic start: within servo speed and ranges", cur))
    rnd = 0
    for rnd in range(1, s.max_rounds + 1):
        if cancelled is not None and cancelled():
            break
        if cur["badness"] <= 0:
            break
        key, joint = worst(cur["report"])
        options = remedies(key, joint, cur["ops"], clip, s)
        if not options:
            steps.append({**_step(rnd, f"no remedy left for {key}", cur), "limit": key, "joint": joint})
            break
        note(f"round {rnd}: {key}{' at ' + joint.replace('joint.', '') if joint else ''}; trying {len(options)} versions")
        results = [(label, evaluate(o)) for label, o in options]
        if min(r["badness"] for _lb, r in results) >= cur["badness"]:
            # nothing aimed at this limit helps: try the broad remedies too before taking a step back
            seen = {o.model_dump_json() for _lb, o in options}
            extra = [(lb, o) for lb, o in remedies("", None, cur["ops"], clip, s) if o.model_dump_json() not in seen]
            if extra:
                note(f"round {rnd}: no improvement; trying {len(extra)} broader versions")
                results += [(label, evaluate(o)) for label, o in extra]
        label, best = min(results, key=lambda x: (x[1]["badness"], -x[1]["character"]["score"]))
        steps.append({**_step(rnd, label, best), "limit": key, "joint": joint,
                      "tried": [{"action": lb, "badness": r["badness"], "character": round(r["character"]["score"], 3)}
                                for lb, r in results]})
        cur = best
    feasible = cur["badness"] <= 0
    if feasible and s.give_back_rounds:
        for g in range(1, s.give_back_rounds + 1):
            if cancelled is not None and cancelled():
                break
            ops = cur["ops"]
            options = []
            if ops.time_scale > 1.0:
                options.append(("faster", ops.model_copy(update={"time_scale": round(max(1.0, ops.time_scale / 1.1), 4)})))
            if any(v < 1.0 for v in ops.amplitude.values()):
                options.append(("larger", ops.model_copy(update={"amplitude": {k: round(min(1.0, v / 0.9), 4)
                                                                               for k, v in ops.amplitude.items()}})))
                pairs = sorted({min(j, twin(j)) for j, v in ops.amplitude.items() if v < 1.0 - 1e-6})
                for j in pairs:
                    amp = {k: (round(min(1.0, v / 0.8), 4) if k in (j, twin(j)) else v) for k, v in ops.amplitude.items()}
                    options.append((f"larger at {j.replace('joint.', '')} (both sides)",
                                    ops.model_copy(update={"amplitude": amp})))
            if not options:
                break
            note(f"giving back {g}: {', '.join(lb for lb, _ in options)}")
            results = [(lb, evaluate(o)) for lb, o in options]
            ok = [(lb, r) for lb, r in results if r["badness"] <= 0 and r["character"]["score"] > cur["character"]["score"]]
            if not ok:
                break
            label, cur = max(ok, key=lambda x: x[1]["character"]["score"])
            steps.append({**_step(rnd + g, f"give back: {label}", cur), "limit": "", "joint": None})
    adapted = cur["clip"]
    adapted.meta.update({"adapted_operations": cur["ops"].model_dump(mode="json"), "feasible": feasible,
                         "margin": s.margin})
    return {"raw": raw, "adapted": cur, "feasible": feasible, "steps": steps, "plays": len(tried),
            "raw_features": raw_features, "settings": s.model_dump(mode="json")}


def _step(rnd: int, action: str, r: dict[str, Any]) -> dict[str, Any]:
    rep = r["report"]
    return {"round": rnd, "action": action, "operations": r["ops"].describe(), "badness": r["badness"],
            "fell": rep["fell"], "violations": rep["safety"]["violations"],
            "tracking_rms_deg": rep["tracking_rms_deg"], "character": round(r["character"]["score"], 3)}


def _shape_rms(rollout: Any, rep: dict[str, Any], raw: MotionClip, spec: RobotSpec, ops: Operations) -> float | None:
    """RMS (deg) of the angles reached minus the raw clip at the same point of the clip (time-warped)."""
    from calflab import units as u

    tm = rep["timing"]
    m = (rollout.t >= tm["clip_t0"]) & (rollout.t < tm["clip_t1"])
    if not m.any():
        return None
    rest = spec.rest_angles()
    frame = (rollout.t[m] - tm["clip_t0"]) * raw.fps / max(ops.time_scale, 1e-6)
    idx = np.arange(raw.frames, dtype=float)
    errs = []
    for jid, vals in raw.joints.items():
        if jid not in rollout.joint_ids:
            continue
        lo, hi = spec.joint(jid).range_deg
        ref = np.clip(rest[jid] + np.interp(frame, idx, np.asarray(vals, dtype=float)), lo, hi)
        got = u.rad_to_deg(rollout.q[m, rollout.joint_ids.index(jid)].astype(float))
        errs.append(got - ref)
    return float(np.sqrt(np.mean(np.concatenate(errs) ** 2))) if errs else None
