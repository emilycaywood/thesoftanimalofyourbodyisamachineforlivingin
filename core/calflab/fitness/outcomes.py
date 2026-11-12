"""Four behaviours defined by their outcome, not their motion (ADR-110, session R15).

Each ``measure_<behaviour>(ro, spec, task)`` reads a rollout and returns plain numbers, a ``score`` (higher is better)
and ``gates``: named pass/fail tests that stop the obvious ways of scoring without doing the behaviour. A play
``holds`` when every gate passes and it stays within the servo, belt and joint limits at the suite's margin (judged
elsewhere, ``calflab.evolve.outcomes``). The four fitness terms below turn those numbers into a preset's terms.

* **suckle**: push the head forward into a fixed block (at the head's standing height, ahead of it) and keep pressing
  lightly: a forward lean is enough (Emily, 2026-11-11). Score = -(mean + worst)/2 servo effort over the press window
  (as stand). Gates: pressing (20th-percentile force at least ``contact_n``, in contact most of the window), steady
  (coefficient of variation), the hooves do not slip (net travel), the body is not propped up by the
  block (centre of mass inside the hooves' support polygon), the head does not lean down on the block, nothing but
  the head touches it, no fall.
* **trot**: travel forward on flat ground for a minute. Score = the slowest 5 s window's forward speed (mm/s), less the
  sideways drift rate. Gates: a useful speed, the trunk stays up (no crawl), heading kept, no fall, hooves do not
  shuffle (slide while loaded). The footfall pattern is recorded (phases, duty factors, a label), not required.
* **stand**: hold a standing posture with the least sustained servo effort. Score = -(mean + worst) / 2 of each
  servo's mean |torque| / its rated torque over the window. Gates: standing height, only hooves on the floor, no
  drift, no fall.
* **lie**: get the trunk down to lying height under control. Score = 1 - 0.5 x peak descent speed / its limit - 0.5 x
  peak body-floor force / its limit (+ ``rise_bonus`` if it stands again). Gates: lying height reached and held, not
  tipped, descent speed and impact under their limits.

Units: forces N (shares of body weight where named ``_bw``), lengths mm, speeds mm/s, angles deg, times s.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.plugins import FitnessTerm, register
from calflab.schema import P

G = 9.81
BEHAVIOURS = ("suckle", "trot", "stand", "lie")


# ====================================================================== task settings (all PROVISIONAL, ADR-110)
class SuckleTask(BaseModel):
    gap_mm: float = P(10.0, unit="mm", ge=0.0, le=100.0, desc="Block face ahead of the head's front when standing.")
    height_mm: float = P(0.0, unit="mm", ge=-200.0, le=200.0,
                         desc="Block centre above the head's standing centre (the udder height stand-in).")
    half_mm: tuple[float, float, float] = P((20.0, 60.0, 40.0), unit="mm", desc="Block half extents (x, y, z).")
    press_from_s: float = P(4.0, unit="s", ge=0.0, le=30.0, desc="The press window starts here (after the approach).")
    contact_n: float = P(0.25, unit="N", ge=0.0, le=10.0,
                         desc="Forward head force that counts as pressing; also the gate on its 20th percentile (a "
                              "light, steady lean is enough: Emily, 2026-11-11).")
    min_contact: float = P(0.9, ge=0.0, le=1.0, desc="Gate: share of the window pressing.")
    max_cv: float = P(0.3, ge=0.0, le=2.0, desc="Gate: largest std / mean of the forward force.")
    max_slip_mm: float = P(30.0, unit="mm", ge=0.0, le=100.0,
                           desc="Gate: largest net horizontal travel of a loaded hoof over the press window (30 mm: "
                                "loosened from 10 for the simulator's soft-contact creep, ADR-110).")
    min_com_margin_mm: float = P(10.0, unit="mm", ge=-50.0, le=100.0,
                                 desc="Gate: centre of mass at least this far inside the hooves' support polygon "
                                      "(less = the block holds the body up).")
    max_down_bw: float = P(0.1, ge=0.0, le=1.0, desc="Gate: head leaning down on the block, share of body weight.")
    max_other_n: float = P(1.0, unit="N", ge=0.0, le=100.0, desc="Gate: force on the block from anything but the head.")
    max_tilt_deg: float = P(30.0, unit="deg", ge=5.0, le=90.0, desc="Gate (fall): trunk tilt.")


class TrotTask(BaseModel):
    from_s: float = P(4.0, unit="s", ge=0.0, le=30.0, desc="Judged from here (after the rhythm has grown).")
    min_speed_mm_s: float = P(100.0, unit="mm/s", ge=0.0, le=2000.0, desc="Gate: the slowest 5 s window's speed.")
    window_s: float = P(5.0, unit="s", ge=1.0, le=20.0, desc="Steadiness window.")
    min_height: float = P(0.8, ge=0.3, le=1.0, desc="Gate: trunk never under this share of its standing height.")
    max_heading_deg: float = P(30.0, unit="deg", ge=1.0, le=180.0, desc="Gate: heading change over the play.")
    max_slip_per_m: float = P(150.0, unit="mm/m", ge=0.0, le=1000.0,
                              desc="Gate: hoof sliding while loaded per metre travelled (shuffling).")
    drift_weight: float = P(0.5, ge=0.0, le=5.0, desc="Score: sideways drift rate subtracted this many times.")
    max_tilt_deg: float = P(30.0, unit="deg", ge=5.0, le=90.0, desc="Gate (fall): trunk tilt.")


class StandTask(BaseModel):
    from_s: float = P(4.0, unit="s", ge=0.0, le=30.0, desc="Judged from here (after the posture is reached).")
    min_height: float = P(0.85, ge=0.3, le=1.0, desc="Gate: mean trunk height as a share of standing.")
    max_drift_mm: float = P(20.0, unit="mm", ge=0.0, le=500.0, desc="Gate: trunk travel over the window.")
    max_body_floor_n: float = P(1.0, unit="N", ge=0.0, le=100.0, desc="Gate: any non-hoof part on the floor.")
    max_tilt_deg: float = P(10.0, unit="deg", ge=1.0, le=90.0, desc="Gate: trunk tilt.")


class LieTask(BaseModel):
    lying_height: float = P(0.5, ge=0.2, le=0.9, desc="Gate: trunk at or under this share of standing (R13's 0.5).")
    lying_hold_s: float = P(2.0, unit="s", ge=0.2, le=30.0, desc="Gate: ... for at least this long.")
    max_descent_mm_s: float = P(300.0, unit="mm/s", ge=10.0, le=3000.0, desc="Gate: peak trunk descent speed.")
    max_impact_bw: float = P(2.0, ge=0.1, le=20.0, desc="Gate: peak non-hoof floor force, share of body weight.")
    min_resting_bw: float = P(0.25, ge=0.0, le=1.0,
                              desc="Gate: while lying, the floor carries at least this share of body weight through "
                                   "parts other than the hooves (lying, not a held crouch on folded legs).")
    max_tilt_deg: float = P(30.0, unit="deg", ge=5.0, le=90.0, desc="Gate (tipping): trunk tilt at any time.")
    rise_bonus: float = P(0.5, ge=0.0, le=2.0, desc="Score added when the body stands again at the end (a bonus).")
    smooth_s: float = P(0.1, unit="s", ge=0.0, le=1.0, desc="Descent speed taken over this window.")


TASKS: dict[str, type[BaseModel]] = {"suckle": SuckleTask, "trot": TrotTask, "stand": StandTask, "lie": LieTask}


# ====================================================================== helpers
def _rot(q: np.ndarray) -> np.ndarray:
    """[T, 4] (w, x, y, z) -> [T, 3, 3]."""
    w, x, y, z = (q[:, i].astype(float) for i in range(4))
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], -2)


def trunk(ro: Any, spec: Any) -> dict[str, np.ndarray]:
    """Trunk series from the controller start: t (s), pos (m), up_z, tilt (deg), yaw (rad, unwrapped)."""
    m = ro.t >= 0
    i = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
    q = ro.body_quat[m, i].astype(float)
    R = _rot(q)
    up = R[:, 2, 2]
    yaw = np.unwrap(np.arctan2(R[:, 1, 0], R[:, 0, 0]))
    return {"t": ro.t[m], "pos": ro.body_pos[m, i].astype(float), "up_z": up,
            "tilt": np.degrees(np.arccos(np.clip(up, -1, 1))), "yaw": yaw}


def hooves(ro: Any, spec: Any) -> np.ndarray:
    """World positions (m) of the hoof geoms [T, F, 3] from the controller start, in ``ro.foot_geoms`` order."""
    m = ro.t >= 0
    out = []
    for gid in ro.foot_geoms:
        body = next(b for b in spec.bodies if any(g.id == gid for g in b.geoms))
        geom = next(g for g in body.geoms if g.id == gid)
        bi = ro.body_ids.index(body.id)
        R = _rot(ro.body_quat[m, bi])
        off = np.asarray(geom.pos, float) / 1000.0
        out.append(ro.body_pos[m, bi].astype(float) + R @ off)
    return np.stack(out, 1) if out else np.zeros((int(m.sum()), 0, 3))


def loaded(ro: Any, threshold_n: float = 2.0) -> np.ndarray:
    """[T, F] hoof carries more than ``threshold_n`` (from the controller start)."""
    return np.asarray(ro.foot_force[ro.t >= 0], float) > threshold_n


def slip_mm(hp: np.ndarray, load: np.ndarray) -> np.ndarray:
    """Per hoof, the horizontal distance slid (mm) while loaded in consecutive frames."""
    if len(hp) < 2:
        return np.zeros(hp.shape[1] if hp.ndim == 3 else 0)
    d = np.linalg.norm(np.diff(hp[:, :, :2], axis=0), axis=-1) * 1000.0
    both = load[1:] & load[:-1]
    return np.sum(np.where(both, d, 0.0), axis=0)


def slip_net_mm(hp: np.ndarray, load: np.ndarray) -> np.ndarray:
    """Per hoof, the largest horizontal distance (mm) from where it was first loaded in the window, over the frames it
    is loaded. Net travel, so contact jitter does not add up (``slip_mm`` sums the path)."""
    out = np.zeros(hp.shape[1] if hp.ndim == 3 else 0)
    for i in range(len(out)):
        idx = np.nonzero(load[:, i])[0]
        if len(idx):
            d = np.linalg.norm(hp[idx, i, :2] - hp[idx[0], i, :2], axis=-1) * 1000.0
            out[i] = float(np.max(d))
    return out


def _hull(pts: np.ndarray) -> np.ndarray:
    """Convex hull (counter-clockwise) of a few 2-D points (monotone chain)."""
    p = sorted({(float(a), float(b)) for a, b in pts})
    if len(p) <= 2:
        return np.asarray(p, float)

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[tuple[float, float]] = []
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.asarray(lower[:-1] + upper[:-1], float)


def support_margin(point: np.ndarray, feet: np.ndarray) -> float:
    """Signed distance (same units) from ``point`` (2-D) to the edge of the support polygon of ``feet`` (2-D), positive
    inside. Fewer than three feet: -inf."""
    if len(feet) < 3:
        return -math.inf
    h = _hull(feet)
    if len(h) < 3:
        return -math.inf
    best = math.inf
    for k in range(len(h)):
        a, b = h[k], h[(k + 1) % len(h)]
        e = b - a
        n = np.array([-e[1], e[0]]) / max(1e-12, float(np.linalg.norm(e)))  # inward for counter-clockwise
        best = min(best, float(np.dot(point - a, n)))
    return best


def probe(ro: Any, name: str) -> np.ndarray:
    """[T, 3] force (N, world) of a contact probe from the controller start; zeros if it was not recorded."""
    m = ro.t >= 0
    if ro.probe_force is None or name not in ro.probe_ids:
        return np.zeros((int(m.sum()), 3))
    return np.asarray(ro.probe_force[m, ro.probe_ids.index(name)], float)


def weight_n(ro: Any) -> float:
    return float(ro.meta.get("total_mass_kg") or 0.0) * G


def stand_height_m(ro: Any) -> float:
    return float(ro.meta.get("root_height") or 0.0)


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None or not math.isfinite(float(x)) else round(float(x), nd)


# ====================================================================== suckle
def measure_suckle(ro: Any, spec: Any, task: SuckleTask) -> dict[str, Any]:
    tr = trunk(ro, spec)
    t = tr["t"]
    win = t >= task.press_from_s
    bw = weight_n(ro)
    f_head = probe(ro, "head_block")  # force on the head from the block
    push = -f_head[:, 0]  # forward force of the head on the block
    down = -f_head[:, 2]  # the head pressing down on the block (the block carrying weight)
    other = np.linalg.norm(probe(ro, "body_block"), axis=-1)
    hp = hooves(ro, spec)
    load = loaded(ro)
    out: dict[str, Any] = {"window_s": round(float(t[win][-1] - t[win][0]), 2) if win.sum() > 1 else 0.0}
    if win.sum() < 2:
        return {**out, "score": -1.0, "gates": {"window": False}, "holds": False}
    pw = push[win]
    p20 = float(np.percentile(pw, 20))
    mean = float(np.mean(pw))
    cv = float(np.std(pw) / mean) if mean > 1e-6 else math.inf
    contact = float(np.mean(pw > task.contact_n))
    slip = slip_net_mm(hp[win], load[win])
    com = np.asarray(ro.com[ro.t >= 0], float)[win, :2]
    margins = []
    for k in range(0, int(win.sum()), 5):  # every 0.1 s at 50 Hz
        feet = hp[win][k][load[win][k]][:, :2]
        margins.append(support_margin(com[k], feet) * 1000.0)
    com_margin = float(np.min(margins)) if margins else -math.inf
    tilt = float(np.max(tr["tilt"]))
    gates = {"pressing": contact >= task.min_contact and p20 >= task.contact_n, "steady": cv <= task.max_cv,
             "no_slip": float(np.max(slip)) <= task.max_slip_mm, "not_propped": com_margin >= task.min_com_margin_mm,
             "not_leaning_down": float(np.percentile(down[win], 80)) <= task.max_down_bw * bw,
             "head_only": float(np.max(other)) <= task.max_other_n, "upright": tilt <= task.max_tilt_deg}
    eff = servo_effort(ro, spec, task.press_from_s)
    vals = list(eff.values()) or [math.inf]
    e_mean, e_max = float(np.mean(vals)), float(np.max(vals))
    score = -(e_mean + e_max) / 2.0  # a light lean is enough: the least effort that keeps the press (as stand)
    out.update({"push_p20_n": _r(p20), "push_mean_n": _r(mean), "push_peak_n": _r(float(np.max(pw))),
                "push_cv": _r(cv), "push_p20_bw": _r(p20 / bw if bw > 0 else 0.0, 4), "contact_frac": _r(contact),
                "effort_mean": _r(e_mean, 4), "effort_max": _r(e_max, 4),
                "worst": max(eff, key=lambda k: eff[k]) if eff else None,
                "down_p80_n": _r(float(np.percentile(down[win], 80))), "other_peak_n": _r(float(np.max(other))),
                "slip_max_mm": _r(float(np.max(slip)), 1), "com_margin_mm": _r(com_margin, 1),
                "tilt_max_deg": _r(tilt, 1), "weight_n": _r(bw, 2), "score": round(score, 4), "gates": gates,
                "holds": all(gates.values())})
    return out


# ====================================================================== trot
def footfall(ro: Any, spec: Any, from_s: float) -> dict[str, Any]:
    """Duty factor per hoof, each hoof's touchdown phase relative to the hind-left (cycles, 0..1), the diagonal lag
    and a label.

    The stride period is the median interval between the hind-left's touchdowns. When the two sides alternate (the
    hind-right and the front-left each about half a cycle after their other-side partner, within 0.15), the label
    follows the **diagonal lag** (front-right after hind-left, front-left after hind-right; circular, 0..0.5): up to
    0.18 ``trot``, 0.18-0.32 ``walk`` (four beats), over 0.32 ``pace``. Front pair and hind pair each together and
    half a cycle apart: ``bound``. No stepping: ``stand``. Else ``other``."""
    m = ro.t >= from_s
    load = np.asarray(ro.foot_force[m], float) > 2.0
    t = ro.t[m]
    names = [g.split(".")[1] if g.count(".") >= 1 else g for g in ro.foot_geoms]
    duty = {n: _r(float(np.mean(load[:, i])) if len(load) else None) for i, n in enumerate(names)}
    tds = {n: t[1:][load[1:, i] & ~load[:-1, i]] for i, n in enumerate(names)}
    if "hl" not in tds or len(tds["hl"]) < 3:
        return {"duty": duty, "period_s": None, "phase": {}, "label": "stand" if all(
            (v or 0) > 0.95 for v in duty.values()) else "other"}
    per = float(np.median(np.diff(tds["hl"])))
    phase: dict[str, float | None] = {}
    for n, td in tds.items():
        if len(td) < 2 or per <= 0:
            phase[n] = None
            continue
        ph = []
        for x in td:
            prev = tds["hl"][tds["hl"] <= x]
            if len(prev):
                ph.append(((x - prev[-1]) / per) % 1.0)
        if ph:
            a = np.angle(np.mean(np.exp(2j * np.pi * np.asarray(ph))))
            phase[n] = round(float((a / (2 * np.pi)) % 1.0), 3)
        else:
            phase[n] = None

    def diff(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        d = abs(a - b) % 1.0
        return min(d, 1.0 - d)

    label = "other"
    hl, fl, hr, fr = 0.0, phase.get("fl"), phase.get("hr"), phase.get("fr")
    lag = None
    side_h, side_f = diff(hr, hl), diff(fl, fr)
    if side_h is not None and side_f is not None and side_h >= 0.35 and side_f >= 0.35:
        d1, d2 = diff(fr, hl), diff(fl, hr)
        lag = round(0.5 * (d1 + d2), 3) if d1 is not None and d2 is not None else None
        if lag is not None:
            label = "trot" if lag <= 0.18 else ("walk" if lag <= 0.32 else "pace")
    elif side_h is not None and side_f is not None and side_h <= 0.15 and side_f <= 0.15:
        fh = diff(fl, hl)
        if fh is not None and fh >= 0.35:
            label = "bound"
    return {"duty": duty, "period_s": round(per, 3), "phase": phase, "diagonal_lag": lag, "label": label}


def measure_trot(ro: Any, spec: Any, task: TrotTask) -> dict[str, Any]:
    tr = trunk(ro, spec)
    t, pos = tr["t"], tr["pos"]
    m = t >= task.from_s
    if m.sum() < 2:
        return {"score": -1000.0, "gates": {"window": False}, "holds": False}
    tw, pw = t[m], pos[m]
    dur = float(tw[-1] - tw[0])
    dx, dy = float(pw[-1, 0] - pw[0, 0]), float(pw[-1, 1] - pw[0, 1])
    speeds = []
    edges = np.arange(tw[0], tw[-1] - task.window_s + 1e-9, task.window_s)
    for a in edges:
        sel = (tw >= a) & (tw <= a + task.window_s)
        if sel.sum() >= 2:
            speeds.append((pw[sel][-1, 0] - pw[sel][0, 0]) * 1000.0 / float(tw[sel][-1] - tw[sel][0]))
    v_min = float(np.min(speeds)) if speeds else dx * 1000.0 / max(dur, 1e-6)
    hp = hooves(ro, spec)
    load = loaded(ro)
    slip = float(np.sum(slip_mm(hp[m], load[m])))
    dist_m = max(1e-3, abs(dx))
    height = float(np.min(pos[:, 2])) / max(1e-6, stand_height_m(ro))
    heading = float(np.degrees(np.max(np.abs(tr["yaw"] - tr["yaw"][0]))))
    drift = abs(dy) * 1000.0 / max(dur, 1e-6)
    speed = dx * 1000.0 / max(dur, 1e-6)
    score = v_min - task.drift_weight * drift
    gates = {"useful_speed": v_min >= task.min_speed_mm_s, "stays_up": height >= task.min_height,
             "heading": heading <= task.max_heading_deg, "no_shuffle": slip / dist_m <= task.max_slip_per_m,
             "upright": float(np.max(tr["tilt"])) <= task.max_tilt_deg}
    return {"speed_mm_s": _r(speed, 1), "speed_min_mm_s": _r(v_min, 1),
            "speed_cv": _r(float(np.std(speeds) / max(1e-6, abs(np.mean(speeds))))) if speeds else None,
            "drift_mm_s": _r(drift, 1), "heading_max_deg": _r(heading, 1), "height_min": _r(height),
            "slip_mm_per_m": _r(slip / dist_m, 1), "tilt_max_deg": _r(float(np.max(tr["tilt"])), 1),
            "footfall": footfall(ro, spec, task.from_s), "judged_s": round(dur, 2), "score": round(score, 2),
            "gates": gates, "holds": all(gates.values())}


# ====================================================================== stand
def servo_effort(ro: Any, spec: Any, from_s: float) -> dict[str, float]:
    """Per actuator, the mean |servo torque| / rated torque over the window (servo torque = joint torque / belt
    ratio x efficiency). Rated torques come from the spec's servo metadata (library values, unverified)."""
    m = ro.t >= from_s
    acts = {a.id: a for a in spec.actuators}
    trans = {tt.id: tt for tt in spec.transmissions}
    servos = (spec.metadata.get("feral") or {}).get("servos") or {}
    out = {}
    for k, aid in enumerate(ro.actuator_ids):
        a = acts[aid]
        tr = trans.get(a.transmission) if a.transmission else None
        gain = (tr.ratio * tr.efficiency) if tr else 1.0
        group = a.joint.split(".")[-1]
        rated = (servos.get(group) or {}).get("rated_nm")
        if not rated or not m.any():
            continue
        out[a.joint.replace("joint.", "")] = round(float(np.mean(np.abs(ro.torque[m, k]))) / gain / float(rated), 4)
    return out


def measure_stand(ro: Any, spec: Any, task: StandTask) -> dict[str, Any]:
    tr = trunk(ro, spec)
    t, pos = tr["t"], tr["pos"]
    m = t >= task.from_s
    if m.sum() < 2:
        return {"score": -10.0, "gates": {"window": False}, "holds": False}
    eff = servo_effort(ro, spec, task.from_s)
    vals = list(eff.values()) or [math.inf]
    e_mean, e_max = float(np.mean(vals)), float(np.max(vals))
    height = float(np.mean(pos[m, 2])) / max(1e-6, stand_height_m(ro))
    drift = float(np.linalg.norm(pos[m][-1, :2] - pos[m][0, :2])) * 1000.0
    body_floor = float(np.max(np.linalg.norm(probe(ro, "body_floor")[m], axis=-1)))
    gates = {"standing": height >= task.min_height, "hooves_only": body_floor <= task.max_body_floor_n,
             "no_drift": drift <= task.max_drift_mm, "upright": float(np.max(tr["tilt"][m])) <= task.max_tilt_deg}
    score = -(e_mean + e_max) / 2.0
    return {"effort_mean": _r(e_mean, 4), "effort_max": _r(e_max, 4), "effort": eff,
            "worst": max(eff, key=lambda k: eff[k]) if eff else None, "height": _r(height),
            "drift_mm": _r(drift, 1), "body_floor_n": _r(body_floor, 2), "judged_s": round(float(t[m][-1] - t[m][0]), 2),
            "score": round(score, 4), "gates": gates, "holds": all(gates.values())}


# ====================================================================== lie
def measure_lie(ro: Any, spec: Any, task: LieTask) -> dict[str, Any]:
    tr = trunk(ro, spec)
    t, pos = tr["t"], tr["pos"]
    if len(t) < 3:
        return {"score": -10.0, "gates": {"window": False}, "holds": False}
    h0 = stand_height_m(ro)
    frac = pos[:, 2] / max(1e-6, h0)
    low = frac <= task.lying_height
    # the longest stretch at lying height
    best = run = 0.0
    dt = float(np.median(np.diff(t)))
    for v in low:
        run = run + dt if v else 0.0
        best = max(best, run)
    n = max(1, int(round(task.smooth_s / dt)))
    z = pos[:, 2]
    vz = (z[n:] - z[:-n]) / (n * dt) if len(z) > n else np.zeros(1)
    descent = float(max(0.0, -float(np.min(vz)))) * 1000.0
    bw = weight_n(ro)
    impact = float(np.max(np.linalg.norm(probe(ro, "body_floor"), axis=-1))) / bw if bw > 0 else 0.0
    tilt = float(np.max(tr["tilt"]))
    risen = bool(frac[-1] >= 0.85 and tr["up_z"][-1] > 0.9)
    hoof_impact = max((s for (_t, _f, s) in ro.impacts), default=0.0) * 1000.0
    bf = np.linalg.norm(probe(ro, "body_floor"), axis=-1)
    resting = float(np.median(bf[low])) / bw if bw > 0 and low.any() else 0.0
    gates = {"lay_down": best >= task.lying_hold_s, "resting": resting >= task.min_resting_bw,
             "not_tipped": tilt <= task.max_tilt_deg, "slow_descent": descent <= task.max_descent_mm_s,
             "soft_landing": impact <= task.max_impact_bw}
    score = 1.0 - 0.5 * descent / task.max_descent_mm_s - 0.5 * impact / task.max_impact_bw
    if risen and gates["lay_down"]:
        score += task.rise_bonus
    return {"lying_min": _r(float(np.min(frac))), "lying_held_s": round(best, 2), "resting_bw": _r(resting), "descent_peak_mm_s": _r(descent, 1),
            "impact_peak_bw": _r(impact), "hoof_impact_peak_mm_s": _r(hoof_impact, 1), "tilt_max_deg": _r(tilt, 1),
            "risen": risen, "score": round(score, 4), "gates": gates, "holds": all(gates.values())}


MEASURES = {"suckle": measure_suckle, "trot": measure_trot, "stand": measure_stand, "lie": measure_lie}


def measure(behaviour: str, ro: Any, spec: Any, task: dict[str, Any] | BaseModel | None = None) -> dict[str, Any]:
    """The outcome of one play of ``behaviour`` (see the module docstring)."""
    t = task if isinstance(task, BaseModel) else TASKS[behaviour].model_validate(task or {})
    fn: Any = MEASURES[behaviour]
    return fn(ro, spec, t)  # type: ignore[no-any-return]


# ====================================================================== fitness terms
class _OutcomeTerm(FitnessTerm):
    behaviour = ""

    class Params(BaseModel):
        fail_value: float = P(-1.0, ge=-100.0, le=0.0, desc="Value when the play does not hold (a gate or a limit).")
        scale: float = P(1.0, ge=0.0, le=1000.0, desc="The behaviour's score is divided by this.")

    def evaluate(self, metrics: dict[str, Any], context: dict[str, Any]) -> float:
        """Reads ``metrics["outcome"][behaviour]`` (``calflab.evolve.outcomes`` puts it there): the score / scale when
        the play holds, else ``fail_value``."""
        p = self.params
        o = (metrics.get("outcome") or {}).get(self.behaviour) or {}
        if not o or not o.get("holds") or not o.get("within", True):
            return float(p.fail_value)  # type: ignore[attr-defined]
        return float(o.get("score", 0.0)) / max(1e-9, float(p.scale))  # type: ignore[attr-defined]


@register
class SuckleTerm(_OutcomeTerm):
    key = "outcome_suckle"
    label = "Suckling (steady head push)"
    description = "A light, steady head press on a fixed block at the least servo effort, when every gate holds."
    behaviour = "suckle"


@register
class TrotTerm(_OutcomeTerm):
    key = "outcome_trot"
    label = "Travel forward (any gait)"
    description = "Slowest 5 s window's forward speed less sideways drift (mm/s), when every gate holds."
    behaviour = "trot"


@register
class StandTerm(_OutcomeTerm):
    key = "outcome_stand"
    label = "Standing at least effort"
    description = "Minus the mean and worst servo sustained effort (|torque| / rated), when every gate holds."
    behaviour = "stand"


@register
class LieTerm(_OutcomeTerm):
    key = "outcome_lie"
    label = "Lying down under control"
    description = "1 - peak descent speed and impact against their limits (+ a bonus for rising), when gates hold."
    behaviour = "lie"
