"""Hardware chosen by the loads of behaviour (session R11, ADR-102).

The body evolves, including its hardware: the servo model per joint pair (``servo_<joint>``, library actuators only)
and each belt drive as three catalog ids (belt system, pulley pair, belt length). The centre distance C is never a
gene: it is derived when the body is built, every belt check runs, and a body whose drive fails a check is rejected
before anything is simulated (ADR-063, ADR-070). Selection uses the loads that a suite of behaviours puts on the
body, played in physics with every limit lowered by the margin (0.2) on three randomised seeds:

* **screen**: the quick trot grid (cycle x stride), the walk, the turn and ``lie_rise``. Every play runs on seed 0;
  a play that holds there is re-played on the other seeds (one that fails on seed 0 cannot hold on all);
* **performance**: R6c's and R7's safe behaviours for 60 s each on every seed, only for a body that passes the
  screen: its best screen play's worst-seed margin reaches ``screen_min_margin`` (-0.25) and at least
  ``screen_min_held`` (0) screen plays hold. R10's bodies show the screen does not predict the minutes (today's body
  holds no quick-grid play and 32 of 33 minutes), so the screen only drops bodies far from holding anything.

Every play is cached on disk per body (a hash of the built spec, the play, the seed and the compile options).

Per body the result says: which behaviours stay within limits and their headroom; the fastest trot within limits on
every seed; per joint, which limit binds (joint speed, sustained servo torque, sustained belt tension, the
torque-speed envelope, stall) and in how many plays that joint and limit stopped the play; and what the hardware
costs, read from the catalogs and the component library only:

* new servos per model (a pair whose model differs from the starting body's counts two), against a budget that
  rejects a body over it (never repaired);
* distinct new pulley sizes (sizes the starting body does not use) and new belt lengths;
* mass, and the masses that are not entered (reported, never guessed: counted 0 g as everywhere, ADR-068);
* servo current where the library has a stall current; servos without one are counted as unknown;
* parts not in a catalog (R8's 45T and 30T/45T what-if pulley pairs, only when ``what_if_pulleys`` is on).

Units: mm, g, s, mm/s, N, A; uses (``speed``, ``torque`` ...) are value / margin-lowered limit (1 = at the limit,
> 1 = over it); margins are ``1 - value / limit`` over the margin-lowered limit (0 = exactly at margin 0.2).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.plugins import BehaviorDescriptor, ComputeBackend, Optimizer, Task, register, registry
from calflab.schema import P

#: joint pairs that carry a servo gene in the feral calf (ADR-101)
PAIRS = ("hip_abd", "stifle", "hock", "shoulder", "carpus")
#: the kinds of limit a joint can bind on, in the order they are shown
LIMITS = ("speed", "torque", "belt", "envelope", "stall")
LIMIT_LABELS = {"speed": "joint speed", "torque": "sustained servo torque", "belt": "sustained belt tension",
                "envelope": "torque-speed envelope", "stall": "stall torque"}
CACHE_VERSION = 2  # 2: plays record spring peaks and belt means (R11c)

#: R8's what-if pulley pairs (ADR-099). NOT in any catalog: offered only when ``what_if_pulleys`` is on, always
#: flagged as what-ifs. Masses are not known (null, counted 0 g and listed as missing).
WHAT_IF_PAIRS: list[dict[str, Any]] = [
    {"id": "45T-45T-whatif", "driver_teeth": 45, "driven_teeth": 45, "pitch_mm": 2, "driver_mass_g": None,
     "driven_mass_g": None},
    {"id": "30T-45T-whatif", "driver_teeth": 30, "driven_teeth": 45, "pitch_mm": 2, "driver_mass_g": None,
     "driven_mass_g": None},
]
WHAT_IF_NOTE = "R8 what-if (ADR-099): commercially listed GT2 10 mm pulleys, not in the catalog; masses unknown"


# ====================================================================== settings (the preset's evaluation.hardware)
class SeedBody(BaseModel):
    """A body the search starts from: gene values over the starting genome."""

    label: str
    values: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class Performance(BaseModel):
    """One of the safe behaviours played for ``performance_s`` (R6c, R7): an evolved candidate's controller."""

    label: str
    ref: str = Field(description="<run id>:<candidate id suffix>")
    #: filled when a run starts (the lab reads the candidate): {key, params}
    controller: dict[str, Any] | None = None


class HardwareSettings(BaseModel):
    """What ``evaluation.hardware`` of a preset holds. ``baseline``, ``catalog`` and ``cache_dir`` and the
    performances' controllers are filled by the lab when a run starts."""

    margin: float = P(0.2, ge=0.0, le=0.9, desc="Safety margin on every limit.")
    servo_choices: list[str] = Field(default_factory=lambda: ["sts3215_c018", "sts3250_c002"],
                                     description="Library actuators a joint pair may get.")
    servo_budget: dict[str, int] = Field(default_factory=lambda: {"sts3250_c002": 4},
                                         description="Most new servos per model (a pair counts two). A body over it "
                                                     "is rejected, never repaired.")
    drives: list[str] = Field(default_factory=lambda: ["stifle", "hock", "carpus"])
    belt_systems: list[str] | None = Field(None, description="Belt systems allowed (None = every catalog system with "
                                                             "a pulley pair of its pitch).")
    what_if_pulleys: bool = P(False, desc="Also offer R8's 45T/45T and 30T/45T pairs, which are NOT in the catalog "
                                          "(flagged as what-ifs everywhere).")
    # ---- the screen
    trot_cycles_s: list[float] = Field(default_factory=lambda: [0.4, 0.45, 0.5, 0.6, 0.8])
    trot_strides: list[float] = Field(default_factory=lambda: [0.5, 1.0, 1.5, 2.0])
    trot_lift: float = 0.6
    screen_extra: list[str] = Field(default_factory=lambda: ["walk", "turn", "lie_rise"],
                                    description="Primitives played at their defaults besides the trot grid.")
    screen_min_held: int = P(0, ge=0, le=50, desc="Screen plays that must hold on every seed before the "
                                                 "performances are played.")
    screen_min_margin: float = P(-0.25, ge=-5.0, le=1.0, desc="The best screen play's worst-seed margin must reach "
                                                             "this before the performances are played (R10: screen "
                                                             "margins do not predict the minutes, so the screen only "
                                                             "drops bodies far from holding anything).")
    # ---- the performances
    performances: list[Performance] = Field(default_factory=list)
    performance_s: float = P(60.0, ge=5.0, le=600.0, unit="s", desc="Length of each performance.")
    # ---- selection
    cost_weights: dict[str, float] = Field(
        default_factory=lambda: {"servos": 1.0, "pulley_sizes": 0.25, "what_if": 0.5, "mass_kg": 1.0},
        description="Cost index = servos x new servos / budget + pulley_sizes x new sizes + what_if (if any part "
                    "is not in a catalog) + mass_kg x added kg.")
    cost_weight: float = P(0.1, ge=0.0, le=5.0, desc="Fitness lost per unit of the cost index (within a cell).")
    seeds_bodies: list[SeedBody] = Field(default_factory=list)
    # ---- R11c (ADR-103): bounded geometry, single pulleys, feasible lengths, springs, shoulder drive
    production: dict[str, Any] | None = Field(None, description="calflab.evolve.production.ProductionSettings; None "
                                                                "= R11's space (ADR-102).")
    servo_denominator: int | None = Field(None, description="Servo term of the cost index = new servos / this "
                                                            "(None = the budget's total, as R11).")
    # ---- R13 (ADR-107): lying down and rising as a constraint
    lie_rise_gate: dict[str, Any] | None = Field(
        None, description="calflab.evolve.lie_rise.LieRiseSearch: before the screen, each body's lie_rise is "
                          "optimised (cached per body); a body whose best version does not hold on every seed plays "
                          "nothing else. None = no gate.")
    # ---- R14 (ADR-108): the mass model every body is built with
    mass_model: str | None = Field(None, description="Gene mass_model set on every body of the run (the start, the "
                                                     "seed bodies, every draw), e.g. explicit_v1. None = each "
                                                     "genome's own value (as_entered for every stored body).")
    # ---- filled when a run starts
    baseline: dict[str, Any] | None = None
    catalog: dict[str, Any] | None = None
    cache_dir: str = ""


# ====================================================================== the hardware genes
class HardwareSpace:
    """The servo and belt genes as ordinal dimensions in [0, 1]. Decoding picks catalog ids only; a belt length is
    picked among the lengths the chosen system's catalog sources list, a pulley pair among the pairs of its pitch.
    Nothing is repaired: a choice that fails a belt check is rejected when the body is built."""

    def __init__(self, gdef: Any, hw: HardwareSettings, catalog: Any, start: dict[str, Any], servos: bool = True,
                 belts: bool = True) -> None:
        self.hw = hw
        self.cat = catalog
        self.servo_genes = [f"servo_{p}" for p in PAIRS if servos and gdef.has(f"servo_{p}")] if servos else []
        self.drives = [d for d in hw.drives if belts and gdef.has(f"belt_{d}_pulleys")
                       and (d != "carpus" or bool(start.get("carpus_belt", True)))] if belts else []
        allowed = set(hw.belt_systems) if hw.belt_systems else None
        self.systems = [s for s in catalog.systems if catalog.pairs_for(s) and (allowed is None or s.id in allowed)]
        if self.drives and not self.systems:
            raise ValueError("No belt system in the catalog has a pulley pair of its pitch")
        self.lengths = {s.id: sorted(catalog.lengths_for(s), key=lambda e: (e.teeth, e.id)) for s in self.systems}
        self.pairs = {s.id: sorted(catalog.pairs_for(s), key=lambda p: (p.ratio, p.driver_teeth, p.id))
                      for s in self.systems}

    @property
    def names(self) -> list[str]:
        out = list(self.servo_genes)
        for d in self.drives:
            out += [f"belt_{d}_system", f"belt_{d}_pulleys", f"belt_{d}_length"]
        return out

    def __len__(self) -> int:
        return len(self.names)

    @staticmethod
    def _x(i: int, n: int) -> float:
        return (i + 0.5) / max(1, n)

    @staticmethod
    def _i(x: float, n: int) -> int:
        return int(min(n - 1, max(0, int(float(np.clip(x, 0.0, 1.0)) * n))))

    def encode(self, values: dict[str, Any]) -> np.ndarray:
        out: list[float] = []
        ch = self.hw.servo_choices
        for g in self.servo_genes:
            v = values.get(g)
            out.append(self._x(ch.index(v), len(ch)) if v in ch else 0.5 / len(ch))
        for d in self.drives:
            sid = values.get(f"belt_{d}_system")
            si = next((i for i, s in enumerate(self.systems) if s.id == sid), 0)
            s = self.systems[si]
            pairs, lens = self.pairs[s.id], self.lengths[s.id]
            pi = next((i for i, p in enumerate(pairs) if p.id == values.get(f"belt_{d}_pulleys")), 0)
            li = next((i for i, e in enumerate(lens) if e.id == values.get(f"belt_{d}_length")), 0)
            out += [self._x(si, len(self.systems)), self._x(pi, len(pairs)), self._x(li, len(lens))]
        return np.asarray(out, dtype=float)

    def decode(self, x: np.ndarray, values: dict[str, Any]) -> dict[str, Any]:
        out = dict(values)
        ch = self.hw.servo_choices
        k = 0
        for g in self.servo_genes:
            out[g] = ch[self._i(x[k], len(ch))]
            k += 1
        for d in self.drives:
            s = self.systems[self._i(x[k], len(self.systems))]
            pairs, lens = self.pairs[s.id], self.lengths[s.id]
            out[f"belt_{d}_system"] = s.id
            out[f"belt_{d}_pulleys"] = pairs[self._i(x[k + 1], len(pairs))].id
            out[f"belt_{d}_length"] = lens[self._i(x[k + 2], len(lens))].id
            k += 3
        return out


def catalog_with_what_ifs(files: dict[str, Any], on: bool) -> dict[str, Any]:
    """The inlined catalog files, with R8's what-if pulley pairs appended when ``on`` (in memory only; the project's
    catalog files are never written)."""
    if not on:
        return files
    out = json.loads(json.dumps(files))
    have = {p["id"] for p in out["pulleys.json"]["pairs"]}
    out["pulleys.json"]["pairs"] += [dict(p) for p in WHAT_IF_PAIRS if p["id"] not in have]
    return out


# ====================================================================== constraints and costs
def servo_count(values: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, int]:
    """New servos per model: two per pair whose model differs from the starting body's."""
    base = (baseline or {}).get("servos") or {}
    out: dict[str, int] = {}
    for p in PAIRS:
        v = values.get(f"servo_{p}")
        if v is None or v == base.get(p, "sts3215_c018"):
            continue
        out[str(v)] = out.get(str(v), 0) + 2
    return out


def budget_reasons(values: dict[str, Any], hw: HardwareSettings) -> list[str]:
    """Why a body breaks the hardware constraints (empty = it does not): the servo budget, servos outside the
    allowed choices, what-if pulleys when they are off."""
    out = []
    for p in PAIRS:
        v = values.get(f"servo_{p}")
        if v is not None and v not in hw.servo_choices and v != ((hw.baseline or {}).get("servos") or {}).get(p):
            out.append(f"servo {v} on the {p} pair is not one of the allowed choices {hw.servo_choices}")
    for model, n in servo_count(values, hw.baseline).items():
        cap = hw.servo_budget.get(model)
        if cap is not None and n > cap:
            out.append(f"servo budget: {n} new {model} > {cap}")
    if not hw.what_if_pulleys:
        for d in hw.drives:
            if str(values.get(f"belt_{d}_pulleys", "")).endswith("-whatif"):
                out.append(f"{d}: pulley pair {values[f'belt_{d}_pulleys']} is a what-if and what-ifs are off")
    return out


def pulley_sizes(spec: Any) -> dict[str, list[str]]:
    """Per pulley size ('2 mm 40T') the drives that use it, on a built body."""
    out: dict[str, list[str]] = {}
    for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items():
        for t in (r.get("driver_teeth"), r.get("driven_teeth")):
            if t is None:
                continue
            out.setdefault(f"{float(r['pitch_mm']):g} mm {int(t)}T", []).append(d)
    return out


def baseline_of(spec: Any, values: dict[str, Any]) -> dict[str, Any]:
    """What the starting body already has: servo per pair, pulley sizes, belt lengths, mass (g)."""
    drives = (spec.metadata.get("feral") or {}).get("belt_drives") or {}
    return {"servos": {p: values.get(f"servo_{p}") for p in PAIRS if f"servo_{p}" in values},
            "spring_sites": [s for s in ("hip_abd", "stifle", "hock", "shoulder", "carpus")
                             if bool(values.get(f"spring_{s}", False))],
            "pulley_sizes": sorted(pulley_sizes(spec)),
            "belt_lengths": sorted({str(values.get(f"belt_{d}_length")) for d in drives}),
            "mass_g": round(float(spec.total_mass_g()), 1)}


def hardware_costs(spec: Any, values: dict[str, Any], hw: HardwareSettings, lib: Any) -> dict[str, Any]:
    """The hardware's costs, from the catalogs and the component library only (unknowns listed, never guessed)."""
    base = hw.baseline or {}
    feral = spec.metadata.get("feral") or {}
    drives = feral.get("belt_drives") or {}
    sizes = pulley_sizes(spec)
    new_sizes = sorted(s for s in sizes if s not in set(base.get("pulley_sizes") or []))
    pieces = sum(2 * len(sizes[s]) for s in new_sizes)  # left + right per drive using that size
    new_lengths = sorted({str(values.get(f"belt_{d}_length")) for d in drives}
                         - set(base.get("belt_lengths") or []))
    what_if = [f"{d}: {values.get(f'belt_{d}_pulleys')}" for d in drives
               if str(values.get(f"belt_{d}_pulleys", "")).endswith("-whatif")]
    servos = servo_count(values, hw.baseline)
    budget_total = hw.servo_denominator or sum(hw.servo_budget.values()) or 1
    from calflab.evolve.production import spring_sites_added

    sites_added = spring_sites_added(values, hw.baseline) if hw.production else []
    unknown: list[str] = []
    unverified: set[str] = set()
    cost_usd = 0.0
    cost_unknown: set[str] = set()
    for model, n in servos.items():
        c = lib.actuator(model)
        if c.cost_usd is None or "cost_usd" in (c.defaulted or []) or "cost_usd" in (c.unknown or []):
            cost_unknown.add(model)  # a library default is not a price
        else:
            cost_usd += float(c.cost_usd) * n
    no_current: set[str] = set()
    for p in PAIRS:
        v = values.get(f"servo_{p}")
        if v is None:
            continue
        c = lib.actuator(v)
        if not c.verified:
            unverified.add(str(v))
        if c.stall_current_a is None or "stall_current_a" in (c.defaulted or []):
            no_current.add(str(v))
    unknown += [f"{v} stall current (its current is not counted)" for v in sorted(no_current)]
    missing = list(spec.metadata.get("missing_masses") or [])
    unknown += [f"mass of {m.get('label', m.get('item'))} (0 g)" for m in missing if isinstance(m, dict)]
    mass = float(spec.total_mass_g())
    added_kg = (mass - float(base.get("mass_g", mass))) / 1000.0
    w = hw.cost_weights
    index = (w.get("servos", 1.0) * sum(servos.values()) / budget_total + w.get("pulley_sizes", 0.25) * len(new_sizes)
             + (w.get("what_if", 0.5) if what_if else 0.0) + w.get("mass_kg", 1.0) * max(0.0, added_kg)
             + w.get("spring_sites", 0.25) * len(sites_added))
    return {
        "new_servos": servos, "new_servos_total": sum(servos.values()), "servo_budget": dict(hw.servo_budget),
        "new_pulley_sizes": new_sizes, "new_pulleys": pieces, "new_belt_lengths": new_lengths,
        "mass_g": round(mass, 1), "added_mass_g": round(added_kg * 1000.0, 1) + 0.0,
        "masses_not_entered": len(missing), "not_in_catalog": what_if, "unverified_servos": sorted(unverified),
        "new_servo_cost_usd": round(cost_usd, 2) if not cost_unknown else None,
        "cost_unknown_for": sorted(cost_unknown), "unknown": unknown, "cost_index": round(index, 4),
        "spring_sites_added": sites_added, "servo_denominator": budget_total,
    }


def drive_rows(spec: Any, values: dict[str, Any]) -> list[dict[str, Any]]:
    """Per belt drive: the three catalog ids and what is derived from them (C, ratio), and whether it is a what-if."""
    out = []
    for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items():
        pid = str(values.get(f"belt_{d}_pulleys", ""))
        out.append({"drive": d, "system": values.get(f"belt_{d}_system"), "pulleys": pid,
                    "length": values.get(f"belt_{d}_length"), "ratio": r.get("ratio"),
                    "c_mm": None if r.get("c_mm") is None else round(float(r["c_mm"]), 1), "ok": bool(r.get("ok")),
                    "what_if": pid.endswith("-whatif")})
    return out


# ====================================================================== plays
def screen_plays(hw: HardwareSettings) -> list[dict[str, Any]]:
    """The screen: the trot grid, then the extra primitives at their defaults."""
    out = [{"key": f"trot {c:g}/{st:g}", "primitive": "trot",
            "params": {"cycle_s": c, "stride": st, "lift": hw.trot_lift, "turn": 0.0}}
           for c in hw.trot_cycles_s for st in hw.trot_strides]
    return out + [{"key": k, "primitive": k, "params": {}} for k in hw.screen_extra]


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _cache_get(cache: Path | None, key: str) -> dict[str, Any] | None:
    if cache is None:
        return None
    f = cache / f"{key}.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _cache_put(cache: Path | None, key: str, rec: dict[str, Any]) -> None:
    if cache is None:
        return
    cache.mkdir(parents=True, exist_ok=True)
    tmp = cache / f"{key}.{time.perf_counter_ns()}.tmp"
    tmp.write_text(json.dumps(rec, default=float), encoding="utf-8")
    tmp.replace(cache / f"{key}.json")


def compile_options(doc: dict[str, Any], ev: Any) -> dict[str, Any]:
    """The physics review's compile options (derating 1, torque-speed servos) with the preset's randomisation."""
    from calflab.behave.physics import compile_params
    from calflab.behave.study import randomization

    return {**compile_params(doc), "randomization": randomization(ev.randomize, ev.friction, ev.mass_scale)}


def per_joint(ro: Any, spec: Any, lib: Any, margin: float, window_s: float = 2.0) -> dict[str, dict[str, Any]]:
    """Per joint, each limit's use (value / margin-lowered limit; 1 = at it) and the one that binds (the largest)."""
    from calflab.behave.interpret import _checks
    from calflab.mech.limits import servo_columns
    from calflab.mech.loads import analyse

    c = _checks(spec)
    keep = 1.0 - margin
    checks = {**c, "rated_fraction": c["rated_fraction"] * keep, "breaking_fraction": c["breaking_fraction"] * keep}
    belts = {d: dict(r) for d, r in ((spec.metadata.get("feral") or {}).get("belt_drives") or {}).items()}
    for r in belts.values():
        if r.get("allowable_working_tension_n") is not None:
            r["allowable_working_tension_n"] = float(r["allowable_working_tension_n"]) * keep
    rows = {r["joint"].replace("joint.", ""): r for r in analyse(ro, spec, lib, window_s, checks, belts)["summary"]}
    env = {col["joint"].replace("joint.", ""): float(np.max(col["use"])) for col in servo_columns(ro, spec, lib)
           if len(col["use"])}
    lim = np.asarray(ro.meta.get("speed_limit") or [], dtype=float)
    m = ro.t >= 0
    acts = {a.id: a for a in spec.actuators}
    out: dict[str, dict[str, Any]] = {}
    for k, aid in enumerate(ro.actuator_ids):
        j = acts[aid].joint.replace("joint.", "")
        r = rows.get(j, {})
        sp = (float(np.max(np.abs(ro.dq[m][:, k])) / (lim[k] * keep)) if len(lim) == ro.dq.shape[1] and m.any()
              else None)
        tq = (float(r["above_rated_fraction_of_cycle"]) / c["sustained_fraction"]
              if isinstance(r.get("above_rated_fraction_of_cycle"), int | float) else None)
        bt = (float(r["above_allowable_fraction_of_cycle"]) / c["sustained_fraction"]
              if isinstance(r.get("above_allowable_fraction_of_cycle"), int | float) else None)
        st = float(r["pct_stall_peak"]) / 100.0 / keep if isinstance(r.get("pct_stall_peak"), int | float) else None
        en = env[j] / keep if j in env else None
        vals = {"speed": sp, "torque": tq, "belt": bt, "envelope": en, "stall": st}
        known = {n: v for n, v in vals.items() if v is not None}
        out[j] = {**{n: (None if v is None else round(v, 3)) for n, v in vals.items()},
                  "binds": max(known, key=lambda n: known[n]) if known else None,
                  "belt_peak_n": None if r.get("belt_tension_peak_n") is None else round(float(r["belt_tension_peak_n"]), 1),
                  "belt_mean_n": None if r.get("belt_tension_mean_n") is None else round(float(r["belt_tension_mean_n"]), 1)}
    return out


def current_of(ro: Any, spec: Any, lib: Any) -> dict[str, Any]:
    """Servo current (A) where the library has a stall current: |servo torque| / (stall torque / stall current) +
    idle current. Servos without a stall current are counted as unknown, not estimated."""
    trans = {tr.id: tr for tr in spec.transmissions}
    acts = {a.id: a for a in spec.actuators}
    m = ro.t >= 0
    total = np.zeros(int(m.sum()))
    known = 0
    for i, aid in enumerate(ro.actuator_ids):
        a = acts[aid]
        c = lib.actuator(a.component)
        if c.stall_current_a is None or not m.any():
            continue
        tr = trans.get(a.transmission) if a.transmission else None
        g = (tr.ratio * tr.efficiency) if tr else 1.0
        total += np.abs(ro.torque[m, i].astype(float)) / g / (c.stall_torque_nm / c.stall_current_a) + (c.idle_current_a or 0.0)
        known += 1
    return {"known_servos": known, "unknown_servos": len(ro.actuator_ids) - known,
            "known_peak_a": round(float(total.max()), 2) if known and len(total) else None,
            "known_mean_a": round(float(total.mean()), 2) if known and len(total) else None}


def judge_play(ro: Any, spec: Any, lib: Any, margin: float, t0: float, t1: float) -> dict[str, Any]:
    """One play judged: within every limit at the margin, the headroom, the closest limit, the speed over [t0, t1)
    (mm/s, trunk), per-joint uses, current."""
    from calflab.behave.interpret import judge

    j = judge(ro, spec, lib, margin)
    known = {k: v for k, v in j["constraints"].items() if v.get("margin") is not None}
    closest = min(known, key=lambda k: known[k]["margin"]) if known else None
    trunk = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
    mm = (ro.t >= t0) & (ro.t < t1)
    speed = 0.0
    if mm.sum() >= 2:
        p = ro.body_pos[mm, trunk, :2]
        speed = float(np.linalg.norm(p[-1] - p[0])) * 1000.0 / max(1e-6, float(ro.t[mm][-1] - ro.t[mm][0]))
    return {"within": bool(j["within_limits"]), "fell": bool(j["fell"]), "margin": j["margin"],
            "violations": list(j["violations"]), "closest": closest, "speed_mm_s": round(speed, 1),
            "joints": per_joint(ro, spec, lib, margin), "current": current_of(ro, spec, lib),
            "springs": spring_peaks(ro)}


def spring_peaks(ro: Any) -> dict[str, float]:
    """Largest spring force (N) per spring site over a play (both sides)."""
    if ro.spring_force is None or not len(ro.spring_ids):
        return {}
    m = ro.t >= 0
    f = np.asarray(ro.spring_force, float)
    out: dict[str, float] = {}
    for i, sid in enumerate(ro.spring_ids):
        site = sid.split(".")[-1]
        if m.any() and f.ndim == 2 and f.shape[1] > i:
            out[site] = round(max(out.get(site, 0.0), float(np.max(f[m, i]))), 1)
    return out


def play_primitive_seed(play: dict[str, Any], spec: Any, lib: Any, copts: dict[str, Any], seed: int,
                        margin: float) -> dict[str, Any]:
    """A screen play (a primitive) on one seed, judged."""
    from calflab.behave.interpret import InterpretSettings
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    prim = registry.get("motion_primitive", play["primitive"])(play["params"])  # type: ignore[call-arg]
    s = InterpretSettings(margin=margin, seed=seed)
    key, params = prim.controller(spec, lib)  # type: ignore[attr-defined]
    off, per = float(prim.warmup_s()), float(prim.period_s())  # type: ignore[attr-defined]
    length = per if prim.one_shot else s.cycles * per  # type: ignore[attr-defined]
    t1 = off + min(max(length, s.min_play_s), s.max_play_s)
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
    settings = SimSettings(duration_s=round(t1 + 0.3, 3), control_hz=50.0, record_hz=50.0, settle_s=0.4,
                           start_pose="stand", stop_on_fall=True, seed=seed)
    ro = run_rollout(cm, registry.get("controller", key)(params), settings, lib)  # type: ignore[arg-type]
    return {**judge_play(ro, spec, lib, margin, off, t1), "controller": {"key": key, "params": params}}


def play_performance_seed(perf: dict[str, Any], spec: Any, lib: Any, copts: dict[str, Any], seed: int,
                          margin: float, seconds: float) -> dict[str, Any]:
    """A performance (an evolved behaviour's controller) for ``seconds`` on one seed, judged over the whole play."""
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    ctrl = perf["controller"]
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(copts), seed)
    settings = SimSettings(duration_s=seconds, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                           stop_on_fall=True, seed=seed)
    ro = run_rollout(cm, registry.get("controller", ctrl["key"])(ctrl["params"]), settings, lib)  # type: ignore[arg-type]
    return judge_play(ro, spec, lib, margin, 0.0, seconds)


# ====================================================================== tasks (run in workers)
def _build(payload: dict[str, Any]) -> tuple[Any, Any]:
    from calflab.components import library
    from calflab.design import build_design
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override

    design = build_design(Genome.model_validate(payload["genome"]),
                          [Override.model_validate(o) for o in payload.get("overrides", [])],
                          payload.get("generator", "feral_calf"), payload.get("generator_params"))
    return design, library()


def rejection(design: Any, hw: HardwareSettings) -> list[str]:
    """Why a built body is rejected before any play: a failing build check (a belt drive, ADR-070) or the hardware
    constraints (the servo budget). Never repaired."""
    from calflab.evolve.constraints import infeasible

    return infeasible(design.spec) + budget_reasons(dict(design.genome.values), hw)


def screen_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Task: build one body; if it is accepted, play the screen (seed 0, then the other seeds for what held).

    Payload: genome, overrides, generator, generator_params, compile, evaluation (EvaluationSettings dump), hardware
    (HardwareSettings dump)."""
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins

    load_plugins()
    design, lib = _build(payload)
    hw = HardwareSettings.model_validate(payload["hardware"])
    reasons = rejection(design, hw)
    if reasons:  # never simulated (ADR-070, ADR-102)
        return {"infeasible": reasons, "mass_g": design.spec.total_mass_g(), "evals": 0}
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    cache = Path(hw.cache_dir) if hw.cache_dir else None
    spec_key = _digest(design.spec.model_dump(mode="json"))
    seeds = list(ev.seeds) or [0]
    t = time.perf_counter()
    plays: list[dict[str, Any]] = []
    evals = hits = 0
    gate = lie_rise_gate(payload, hw, seeds, cache, spec_key, copts) if hw.lie_rise_gate is not None else None
    if gate is not None and not gate["held"]:  # lies down and rises within limits, or plays nothing else (ADR-107)
        return {"spec_key": spec_key, "plays": [], "lie_rise": gate, "evals": gate["new_plays"], "cache_hits": 0,
                "costs": hardware_costs(design.spec, dict(design.genome.values), hw, lib),
                "drives": drive_rows(design.spec, dict(design.genome.values)),
                "mass_g": design.spec.total_mass_g(), "seconds": round(time.perf_counter() - t, 1)}
    for play in screen_plays(hw):
        per_seed = []
        for k, seed in enumerate(seeds):
            key = _digest({"v": CACHE_VERSION, "spec": spec_key, "play": play, "seed": seed, "copts": copts,
                           "margin": hw.margin, "kind": "screen"})
            rec = _cache_get(cache, key)
            if rec is None:
                rec = play_primitive_seed(play, design.spec, lib, copts, seed, hw.margin)
                _cache_put(cache, key, rec)
                evals += 1
            else:
                hits += 1
            per_seed.append({"seed": seed, **rec})
            if k == 0 and not rec["within"]:
                break  # a play that fails on the first seed cannot hold on every seed
        plays.append({"key": play["key"], "primitive": play["primitive"], "params": play["params"],
                      "held": len(per_seed) == len(seeds) and all(p["within"] for p in per_seed), "seeds": per_seed})
    out_gate = {} if gate is None else {"lie_rise": gate}
    evals += 0 if gate is None else int(gate["new_plays"])
    return {"spec_key": spec_key, "plays": plays, **out_gate, "evals": evals, "cache_hits": hits,
            "costs": hardware_costs(design.spec, dict(design.genome.values), hw, lib),
            "drives": drive_rows(design.spec, dict(design.genome.values)),
            "mass_g": design.spec.total_mass_g(), "seconds": round(time.perf_counter() - t, 1)}


def lie_rise_gate(payload: dict[str, Any], hw: HardwareSettings, seeds: list[int], cache: Path | None,
                  spec_key: str, copts: dict[str, Any]) -> dict[str, Any]:
    """The body's lie_rise optimised as in session R13 (``calflab.evolve.lie_rise.optimise``, plays run here one
    after another), cached per body and gate settings. Returns held / worst-seed margin / the best version / plays."""
    from calflab.evolve.lie_rise import LieRiseSearch, optimise

    s = LieRiseSearch.model_validate(hw.lie_rise_gate or {})
    key = _digest({"v": CACHE_VERSION, "spec": spec_key, "copts": copts, "margin": hw.margin, "seeds": seeds,
                   "gate": s.model_dump(mode="json"), "kind": "lie_rise_gate"})
    rec = _cache_get(cache, key)
    if rec is not None:
        return {**rec, "new_plays": 0, "cached": True}
    r = optimise(payload, seeds, hw.margin, s, cache=str(cache.parent / "lie_rise") if cache else None)
    best = r["best"]
    rec = {"held": bool(best["held"]), "worst_margin": best["worst"], "params": best["params"],
           "start_margin": r["start"]["worst"], "plays": r["plays"], "new_plays": r["new_plays"],
           "closest": [x.get("closest") for x in best["seeds"]],
           "moves": [{"move": m["move"], "joint": m["joint"], "limit": m["limit"], "margin": m["margin"]}
                     for m in (best["seeds"][0].get("moves") or [])] if best["seeds"] else []}
    _cache_put(cache, key, rec)
    return {**rec, "cached": False}


def perform_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Task: one performance on every seed for one body. Payload as ``screen_task`` plus ``performance`` (index)."""
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins

    load_plugins()
    design, lib = _build(payload)
    hw = HardwareSettings.model_validate(payload["hardware"])
    if rejection(design, hw):
        return {"error": "rejected body reached a performance"}
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    perf = hw.performances[int(payload["performance"])].model_dump(mode="json")
    cache = Path(hw.cache_dir) if hw.cache_dir else None
    spec_key = _digest(design.spec.model_dump(mode="json"))
    seeds = []
    evals = 0
    for seed in list(ev.seeds) or [0]:
        key = _digest({"v": CACHE_VERSION, "spec": spec_key, "perf": perf, "seed": seed, "copts": copts,
                       "margin": hw.margin, "seconds": hw.performance_s, "kind": "performance"})
        rec = _cache_get(cache, key)
        if rec is None:
            rec = play_performance_seed(perf, design.spec, lib, copts, seed, hw.margin, hw.performance_s)
            _cache_put(cache, key, rec)
            evals += 1
        seeds.append({"seed": seed, **rec})
    return {"label": perf["label"], "seeds": seeds, "evals": evals}


# ====================================================================== summary of one body
#: fitness of a body that fails the lie_rise gate: this + 0.5 x its lie_rise worst-seed margin (>= -3) - cost term;
#: below every body that passes (whose fitness is headroom >= -1 less the cost term)
GATE_FAIL_BASE = -3.0


def _clip(v: float | None, lo: float = -1.0, hi: float = 0.5) -> float:
    return lo if v is None else float(min(hi, max(lo, v)))


def summarise(screen: dict[str, Any], performances: list[dict[str, Any]] | None, hw: HardwareSettings,
              n_seeds: int) -> dict[str, Any]:
    """Selection numbers, the binding limit per joint and the tables the Evolve panel shows (no logic in the web)."""
    plays = screen["plays"]
    trots = [p for p in plays if p["primitive"] == "trot"]
    held_trots = [p for p in trots if p["held"]]
    fastest = max(held_trots, key=lambda p: min(s["speed_mm_s"] for s in p["seeds"]), default=None)
    trot_speed = min(s["speed_mm_s"] for s in fastest["seeds"]) if fastest else 0.0
    screen_held = sum(1 for p in plays if p["held"])
    extra = {p["key"]: p for p in plays if p["primitive"] != "trot"}

    def worst(p: dict[str, Any]) -> float | None:
        ms = [s["margin"] for s in p["seeds"] if s.get("margin") is not None]
        return min(ms) if ms else None

    best = max((m for m in (worst(p) for p in plays) if m is not None), default=None)
    gate = screen.get("lie_rise")  # R13 (ADR-107): the body's own evolved lie_rise must hold on every seed
    passed = (screen_held >= hw.screen_min_held and best is not None and best >= hw.screen_min_margin
              and (gate is None or bool(gate["held"])))

    perf_rows = []
    minutes = 0
    played = performances is not None
    for r in performances or []:
        held = sum(1 for s in r["seeds"] if s["within"])
        minutes += held
        perf_rows.append({"label": r["label"], "held": held, "of": len(r["seeds"]),
                          "worst_margin": worst(r), "closest": [s.get("closest") for s in r["seeds"]],
                          "seeds": [{k: s.get(k) for k in ("seed", "within", "fell", "margin", "closest")} for s in r["seeds"]]})
    # per joint: the largest use of each limit over every play and seed, which binds, and how often it stopped a play
    all_seeds = [s for p in plays for s in p["seeds"]] + [s for r in performances or [] for s in r["seeds"]]
    joints: dict[str, dict[str, Any]] = {}
    stops: dict[str, dict[str, int]] = {}
    for s in all_seeds:
        top: tuple[float, str, str] | None = None
        for j, u in (s.get("joints") or {}).items():
            row = joints.setdefault(j, {lim: None for lim in LIMITS})
            for lim in LIMITS:
                v = u.get(lim)
                if v is not None and (row[lim] is None or v > row[lim]):
                    row[lim] = v
                if v is not None and v > 1.0 and (top is None or v > top[0]):
                    top = (v, j, lim)
        if top is not None and not s.get("within", True):
            stops.setdefault(top[1], {}).setdefault(top[2], 0)
            stops[top[1]][top[2]] += 1
    joint_rows = []
    for j in sorted(joints):
        row = joints[j]
        known = {k: v for k, v in row.items() if v is not None}
        b = max(known, key=lambda k: known[k]) if known else None
        st = stops.get(j, {})
        joint_rows.append({"joint": j, **{k: row[k] for k in LIMITS}, "binds": b,
                           "binds_label": LIMIT_LABELS.get(b or "", ""), "stopped_plays": sum(st.values()),
                           "stopped_by": max(st, key=lambda k: st[k]) if st else None})
    stoppers = sorted(((j["joint"], j["stopped_by"], j["stopped_plays"]) for j in joint_rows if j["stopped_plays"]),
                      key=lambda x: -x[2])
    head_screen = ([_clip(worst(extra[k])) for k in extra] + [_clip(worst(fastest)) if fastest else -1.0]
                   + ([_clip(gate["worst_margin"])] if gate is not None else []))
    head_perf = [_clip(r["worst_margin"]) for r in perf_rows] if played else [-1.0]
    headroom = 0.5 * float(np.mean(head_screen)) + 0.5 * float(np.mean(head_perf))
    cost = screen["costs"]
    fitness = headroom - hw.cost_weight * float(cost["cost_index"])
    if gate is not None and not gate["held"]:
        # R13 (ADR-107): a body that does not lie down and rise within limits ranks below every body that does, and
        # by how close it comes; otherwise every such body sits in the (0 minutes, no trot) cell, judged by cost
        fitness = GATE_FAIL_BASE + 0.5 * max(-3.0, float(gate["worst_margin"])) - hw.cost_weight * float(
            cost["cost_index"])
    current = [s["current"]["known_peak_a"] for s in all_seeds if (s.get("current") or {}).get("known_peak_a") is not None]
    # belt tension per drive (both sides, every play and seed) and spring force per site, from the simulation (R11c)
    belt_loads: dict[str, dict[str, float]] = {}
    spring_sim: dict[str, float] = {}
    for s in all_seeds:
        for j, u in (s.get("joints") or {}).items():
            drive = j.split(".")[-1]
            if u.get("belt_peak_n") is not None:
                row = belt_loads.setdefault(drive, {"peak_n": 0.0, "mean_n": 0.0})
                row["peak_n"] = max(row["peak_n"], float(u["belt_peak_n"]))
                row["mean_n"] = max(row["mean_n"], float(u.get("belt_mean_n") or 0.0))
        for site, f in (s.get("springs") or {}).items():
            spring_sim[site] = max(spring_sim.get(site, 0.0), float(f))
    out = {
        "passed_screen": passed, "screen_held": screen_held, "screen_plays": len(plays),
        "screen_best_margin": None if best is None else round(best, 4),
        "performances_played": played, "minutes_held": minutes,
        "minutes_of": len(hw.performances) * n_seeds, "trot_speed_mm_s": round(trot_speed, 1),
        "fastest_trot": fastest["key"] if fastest else None, "trots_held": [p["key"] for p in held_trots],
        "screen": {k: {"held": p["held"], "worst_margin": worst(p),
                       "closest": [s.get("closest") for s in p["seeds"]]} for k, p in extra.items()},
        "performances": perf_rows, "joints": joint_rows, "stoppers": [list(x) for x in stoppers],
        "costs": cost, "drives": screen["drives"], "headroom": round(headroom, 4),
        "fitness": round(fitness, 4), "known_current_peak_a": max(current) if current else None,
        "belt_loads": belt_loads, "spring_peaks_sim_n": spring_sim,
    }
    if gate is not None:
        out["screen"]["lie_rise (evolved)"] = {"held": bool(gate["held"]), "worst_margin": gate["worst_margin"],
                                               "closest": gate.get("closest") or []}
        out["lie_rise_evolved"] = {k: gate.get(k) for k in ("held", "worst_margin", "params", "start_margin",
                                                            "moves")}
    out["tables"] = tables(out, hw)
    return out


def _f(v: Any, nd: int = 2) -> str:
    if v is None:
        return "unknown"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def tables(s: dict[str, Any], hw: HardwareSettings) -> list[dict[str, Any]]:
    """Ready-to-show tables {title, columns, rows (strings), warn (row indexes)} for the Evolve panel."""
    c = s["costs"]
    hw_rows = [[p, str(m), "new" if m != ((hw.baseline or {}).get("servos") or {}).get(p) else ""]
               for p, m in ((k.replace("servo_", ""), v) for k, v in (s.get("servo_genes") or {}).items())]
    belts = [[d["drive"], f"{d['pulleys']}{' (WHAT-IF)' if d['what_if'] else ''}", str(d["length"]),
              _f(d["ratio"], 2), _f(d["c_mm"], 1), str(d["system"])] for d in s["drives"]]
    joints = [[j["joint"], *[("-" if k == "belt" and j[k] is None else _f(j[k])) for k in LIMITS],
               j["binds_label"] or "-",
               f"{j['stopped_plays']} ({LIMIT_LABELS.get(j['stopped_by'] or '', '')})" if j["stopped_plays"] else "0"]
              for j in s["joints"]]
    warn = [i for i, j in enumerate(s["joints"]) if j["stopped_plays"]]
    perf = [[r["label"], f"{r['held']}/{r['of']}", _f(r["worst_margin"]),
             ", ".join(sorted({str(x) for x in r["closest"] if x}))] for r in s["performances"]]
    screen = [[k, "yes" if v["held"] else "no", _f(v["worst_margin"]), ", ".join(sorted({str(x) for x in v["closest"]
                                                                                         if x}))]
              for k, v in s["screen"].items()]
    screen.append(["fastest trot within", s["fastest_trot"] or "none", f"{s['trot_speed_mm_s']:.0f} mm/s",
                   f"{len(s['trots_held'])} trot settings hold"])
    screen.append(["screen", "passed" if s["passed_screen"] else "screened out", _f(s["screen_best_margin"]),
                   f"best play's worst-seed margin against {hw.screen_min_margin:+.2f}"])
    costs = [["new servos", ", ".join(f"{n} x {m}" for m, n in c["new_servos"].items()) or "none",
              f"budget {', '.join(f'{n} {m}' for m, n in c['servo_budget'].items())}"],
             ["new pulley sizes", ", ".join(c["new_pulley_sizes"]) or "none", f"{c['new_pulleys']} pulleys"],
             ["new belt lengths", ", ".join(c["new_belt_lengths"]) or "none", ""],
             ["mass", f"{c['mass_g']:.0f} g", f"{c['added_mass_g'] + 0.0:+.0f} g; {c['masses_not_entered']} masses "
                                               "not entered (0 g)"],
             ["servo current (known servos)", _f(s["known_current_peak_a"]) + " A peak",
              "servos without a stall current are not counted"],
             ["not in a catalog", ", ".join(c["not_in_catalog"]) or "none", WHAT_IF_NOTE if c["not_in_catalog"] else ""],
             ["new servo cost", _f(c["new_servo_cost_usd"]) + (" USD" if c["new_servo_cost_usd"] is not None else ""),
              ("no cost entered for " + ", ".join(c["cost_unknown_for"])) if c["cost_unknown_for"] else ""],
             ["unknown", f"{len(c['unknown'])} values", "; ".join(c["unknown"][:6])],
             ["cost index", _f(c["cost_index"], 3), "the costs weighted (preset cost_weights)"]]
    if c.get("spring_sites_added"):
        costs.insert(-1, ["spring sites added", ", ".join(c["spring_sites_added"]), ""])
    loads = [[d, f"{v['peak_n']:.0f}", f"{v['mean_n']:.0f}"] for d, v in sorted((s.get("belt_loads") or {}).items())]
    loads += [[f"spring: {k}", f"{v:.0f}", ""] for k, v in sorted((s.get("spring_peaks_sim_n") or {}).items())]
    prod = s.get("production") or {}
    spr = [[k, f"{r['k_n_per_mm']:g}", f"{r['free_mm']:g}", f"{r['standing_mm']:g}", f"{r['max_extension_mm']:g}",
            f"{r['peak_force_n']:g}", f"{r['min_line_gap_mm']:g} at {r['at_deg']:g}"]
           for k, r in sorted((prod.get("springs") or {}).items()) if not k.startswith("_")]
    spr += [["FLAG", f, "", "", "", "", ""] for f in (prod.get("springs") or {}).get("_flags", [])]
    out: list[dict[str, Any]] = [
        {"title": "Servos per pair", "columns": ["pair", "servo", ""], "rows": hw_rows, "warn": []},
        {"title": "Belt drives (catalog ids; C derived)", "columns": ["drive", "pulleys", "belt", "ratio", "C mm",
                                                                      "system"],
         "rows": belts, "warn": [i for i, d in enumerate(s["drives"]) if d["what_if"]]},
        {"title": "Binding limit per joint (use = value / limit at margin; > 1 = over)",
         "columns": ["joint", *LIMITS, "binds", "stopped plays"], "rows": joints, "warn": warn},
        {"title": "Screen (every seed)", "columns": ["play", "held", "worst margin", "closest limit"], "rows": screen,
         "warn": [i for i, v in enumerate(s["screen"].values()) if not v["held"]]},
        {"title": f"Behaviours, {hw.performance_s:.0f} s" + ("" if s["performances_played"] else
                                                             " (not played: screened out)"),
         "columns": ["behaviour", "seeds held", "worst margin", "closest limit"], "rows": perf,
         "warn": [i for i, r in enumerate(s["performances"]) if r["held"] < r["of"]]},
        {"title": "Hardware costs (catalogs and library only)", "columns": ["", "", ""], "rows": costs, "warn": []},
    ]
    if loads:
        out.append({"title": "Belt tension per drive and spring force per site, simulated (largest over every play "
                             "and seed, N)", "columns": ["drive / spring", "peak N", "largest mean N"], "rows": loads,
                    "warn": []})
    if spr:
        out.append({"title": "Springs through the joint range (geometry, left leg)",
                    "columns": ["site", "k N/mm", "free mm", "standing mm", "max extension mm", "peak force N",
                                "closest line to axis mm (deg)"], "rows": spr, "warn": []})
    return out


# ====================================================================== cost estimate
#: R11 (ADR-102): plays in 7 parallel workers ran about 2x slower per simulated second than the single-process probe
#: rollout the lab times (the seed run: 3 bodies fully played in 8.5 min on 7 workers)
PARALLEL_SLOWDOWN = 2.0


def estimate(hw: HardwareSettings, n_seeds: int, per_sim_s: float, workers: int, generations: int, batch: int,
             pass_rate: float = 0.5, held_rate: float = 0.2) -> dict[str, Any]:
    """CPU and wall time of a run. A screen plays every play on the first seed and the other seeds only for what
    held there (``held_rate`` of them); a body that passes (``pass_rate``) plays every performance on every seed.
    ``per_sim_s`` = wall seconds per simulated second of the lab's single probe rollout, scaled by
    ``PARALLEL_SLOWDOWN``. An upper bound: plays that fall stop early, and cached plays cost nothing."""
    from calflab.behave.interpret import InterpretSettings

    per_sim_s = per_sim_s * PARALLEL_SLOWDOWN

    s = InterpretSettings()
    screen_s = 0.0
    for play in screen_plays(hw):
        try:
            prim = registry.get("motion_primitive", play["primitive"])(play["params"])  # type: ignore[call-arg]
        except KeyError:
            continue
        per = float(prim.period_s())  # type: ignore[attr-defined]
        length = per if prim.one_shot else s.cycles * per  # type: ignore[attr-defined]
        sim = float(prim.warmup_s()) + min(max(length, s.min_play_s), s.max_play_s) + 0.7  # type: ignore[attr-defined]
        screen_s += sim * (1 + held_rate * (n_seeds - 1))
    perf_s = len(hw.performances) * n_seeds * (hw.performance_s + 0.4)
    bodies = generations * batch
    cpu = bodies * (screen_s + pass_rate * perf_s) * per_sim_s
    return {"bodies": bodies, "screen_sim_s_per_body": round(screen_s, 1), "performance_sim_s_per_body": round(perf_s, 1),
            "pass_rate": pass_rate, "held_rate": held_rate, "cpu_s": round(cpu, 1),
            "wall_s": round(cpu / max(1, workers), 1), "workers": workers,
            "body_cpu_s_screen": round(screen_s * per_sim_s, 1), "body_cpu_s_full": round((screen_s + perf_s) * per_sim_s, 1)}


# ====================================================================== the optimizer
@register
class MapElitesHardware(Optimizer):
    """MAP-Elites over the body and its hardware, judged by the loads of a behaviour suite (ADR-102)."""

    key = "map_elites_hardware"
    label = "MAP-Elites: hardware by behaviour loads"
    description = ("Evolves geometry, the servo per joint pair and the belt drives (catalog ids; C derived, failing "
                   "choices rejected), judging each body by a screen and then 60 s behaviours at margin 0.2 on three "
                   "seeds. Needs a preset with evaluation.hardware (preset 'hardware').")
    version = "1"
    #: varies servo and belt genes (the lab skips the belt-bound range scan, which assumes fixed belts)
    varies_hardware = True
    #: the gene file's evolve defaults (other axes, a walk-length rollout) do not apply: the axes are its own
    body_defaults = False

    class Params(BaseModel):
        generations: int = P(3, ge=1, le=500, desc="Generations.", group="Budget")
        batch_size: int = P(7, ge=1, le=256, desc="Bodies per generation.", group="Budget")
        descriptor_x: str = P("behaviour_minutes_held", desc="Archive X axis.", group="Archive")
        descriptor_y: str = P("trot_speed_within", desc="Archive Y axis.", group="Archive")
        grid_x: int = P(12, ge=2, le=50, desc="Archive cells along X.", group="Archive")
        grid_y: int = P(10, ge=2, le=50, desc="Archive cells along Y.", group="Archive")
        genes: list[str] = P(default_factory=list, ui="json", desc="Geometry genes to evolve (empty = every evolvable "
                                                                   "one).", group="Variation")
        vary_geometry: bool = P(True, desc="Evolve the geometry genes.", group="Variation")
        vary_servos: bool = P(True, desc="Evolve the servo per joint pair.", group="Variation")
        vary_belts: bool = P(True, desc="Evolve the belt drives (catalog ids).", group="Variation")
        what_if_pulleys: bool = P(False, desc="Offer R8's 45T/45T and 30T/45T pairs (NOT in the catalog; flagged as "
                                              "what-ifs).", group="Variation")
        seed_bodies: bool = P(True, desc="Start from the preset's seed bodies as well as the working body.",
                              group="Variation")
        sigma_init: float = P(0.1, ge=0.0, le=0.5, desc="Spread of the first random bodies.", group="Variation")
        sigma_iso: float = P(0.05, ge=0.0, le=0.5, desc="Geometry mutation (fraction of range).", group="Variation")
        sigma_line: float = P(0.2, ge=0.0, le=1.0, desc="Mutation along the line between two elites.",
                              group="Variation")
        hardware_flip: float = P(0.2, ge=0.0, le=1.0, desc="Chance per hardware gene of a new catalog choice.",
                                 group="Variation")
        redraws: int = P(40, ge=0, le=500, desc="Rejected draws per slot before giving up (each is recorded, never "
                                                "simulated).", group="Variation")
        seed: int = P(0, ge=0, le=2**31 - 1, ui="number", desc="Random seed.", group="Budget")

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        schema = super().params_schema()
        choices = sorted(registry.all("behavior_descriptor"))
        for f in schema["fields"]:
            if f["name"] in ("descriptor_x", "descriptor_y"):
                f.update({"type": "enum", "ui": "enum", "choices": choices})
        return schema

    def run(self, problem: Any, backend: ComputeBackend, report: Callable[..., None]) -> Any:
        from ribs.archives import GridArchive

        from calflab.design import build_design, genome_definition
        from calflab.evolve.map_elites import Candidate, EvolveResult
        from calflab.fitness.preset import FitnessPreset
        from calflab.mech.belts import BeltCatalog
        from calflab.model.genome import Genome
        from calflab.model.overrides import Override

        p: Any = self.params
        preset = FitnessPreset.model_validate(problem.fitness)
        if preset.evaluation is None or preset.evaluation.hardware is None:
            raise ValueError("map_elites_hardware needs a fitness preset with evaluation.hardware (preset 'hardware')")
        ev = preset.evaluation
        hw = HardwareSettings.model_validate(ev.hardware)
        hw.what_if_pulleys = bool(p.what_if_pulleys)
        gen_params = dict(problem.generator_params)
        if not gen_params.get("belt_catalog"):
            raise ValueError("The design node's params carry no inlined belt catalog (Lab.job_generator_params)")
        gen_params["belt_catalog"] = catalog_with_what_ifs(gen_params["belt_catalog"], hw.what_if_pulleys)
        catalog = BeltCatalog.from_dict(gen_params["belt_catalog"], origin="inlined")
        gdef = genome_definition(problem.genome["definition"])
        base_values = gdef.complete(problem.genome["values"])
        if hw.mass_model:  # R14 (ADR-108): every body of the run, and the cost baseline, at this mass model
            if hw.mass_model not in (gdef.gene("mass_model").choices or []):
                raise ValueError(f"mass_model {hw.mass_model!r} is not a choice of the gene mass_model")
            base_values = {**base_values, "mass_model": hw.mass_model}
        overrides = [Override.model_validate(o) for o in problem.overrides]

        def build(values: dict[str, Any]) -> Any:
            return build_design(Genome(definition=gdef.name, version=gdef.version, values=values), overrides,
                                problem.generator, gen_params)

        start = build(base_values)
        if hw.baseline is None:
            hw.baseline = baseline_of(start.spec, base_values)
        only = list(p.genes) or None
        geo = gdef.evolvable(only) if p.vary_geometry else []
        if p.vary_geometry and only and gdef.not_evolvable(only):
            raise ValueError(f"These genes cannot be evolved: {', '.join(gdef.not_evolvable(only))}")
        prod: Any = None
        if hw.production is not None:
            # R11c (ADR-103): every gene in one bounded, discrete space; geometry moves are Gaussian, the rest redrawn
            from calflab.evolve.production import ProductionSettings, ProductionSpace

            pr = ProductionSettings.model_validate(hw.production)
            if not p.vary_geometry:
                pr.geometry = None
            if not p.vary_belts:
                raise ValueError("The production space always varies the belt drives (vary_belts must be on)")
            hw.production = pr.model_dump(mode="json")
            prod = ProductionSpace(gdef, hw, catalog, base_values, start.spec, build)
            geo = []
            if prod.excluded_systems:
                notes0 = [f"belt systems with no pulley listed for their width, not offered: "
                          f"{', '.join(prod.excluded_systems)}"]
            else:
                notes0 = []
        space = None if prod is not None else HardwareSpace(gdef, hw, catalog, base_values, servos=p.vary_servos,
                                                              belts=p.vary_belts)
        if prod is not None:
            n_geo, n_hw = prod.n_ordinal, len(prod) - prod.n_ordinal
        else:
            n_geo, n_hw = len(geo), len(space)  # type: ignore[arg-type]
            notes0 = []
        if n_geo + n_hw == 0:
            raise ValueError("Nothing to evolve: geometry, servos and belts are all off")
        geo_ids = [g.id for g in geo]

        def encode(values: dict[str, Any]) -> np.ndarray:
            if prod is not None:
                return prod.encode(values)
            g = gdef.encode(values, geo_ids) if n_geo else np.zeros(0)
            return np.concatenate([g, space.encode(values)])  # type: ignore[union-attr]

        def realise(x: np.ndarray) -> tuple[dict[str, Any], Any, list[str], dict[str, Any]]:
            """Gene values, the built design (None if rejected before building), reasons, extra report."""
            if prod is not None:
                values, d, why, extra = prod.realise(x, base_values)
                if d is None:
                    return values, None, why, extra
                return values, d, why + rejection(d, hw), extra
            v = gdef.decode(x[:n_geo], base_values, geo_ids) if n_geo else dict(base_values)
            values = space.decode(x[n_geo:], v)  # type: ignore[union-attr]
            d = build(values)
            return values, d, rejection(d, hw), {}

        payload_hw = hw.model_dump(mode="json")
        payload_ev = ev.model_dump(mode="json")
        n_seeds = len(ev.seeds) or 1
        dkeys = [p.descriptor_x, p.descriptor_y]
        ranges = [registry.get("behavior_descriptor", k).range for k in dkeys]  # type: ignore[attr-defined]
        archive = GridArchive(solution_dim=n_geo + n_hw, dims=[p.grid_x, p.grid_y], ranges=ranges,
                              qd_score_offset=-3.0)
        rng = np.random.default_rng(p.seed)
        result = EvolveResult()
        by_id: dict[str, Any] = {}
        vec: dict[str, np.ndarray] = {}
        summaries: dict[str, dict[str, Any]] = {}
        x_base = encode(base_values)
        seeds: list[tuple[str, np.ndarray]] = [("working body", x_base)]
        notes: list[str] = list(notes0)
        slot_values: dict[str, dict[str, Any]] = {}
        slot_extra: dict[str, dict[str, Any]] = {}
        if p.seed_bodies:
            for sb in hw.seeds_bodies:
                vals = {**base_values, **sb.values}
                if not hw.what_if_pulleys and any(str(v).endswith("-whatif") for v in sb.values.values()):
                    notes.append(f"seed body {sb.label!r} skipped: it uses a what-if pulley pair and what-ifs are off")
                    continue
                seeds.append((sb.label, encode(vals)))

        def cancelled() -> bool:
            return bool(problem.cancelled and problem.cancelled())

        def common(values: dict[str, Any]) -> dict[str, Any]:
            return {"genome": {"definition": gdef.name, "version": gdef.version, "values": values},
                    "overrides": problem.overrides, "generator": problem.generator, "generator_params": gen_params,
                    "compile": problem.compile, "evaluation": payload_ev, "hardware": payload_hw}

        seed_queue = list(seeds)
        labels: dict[str, str] = {}
        for gen in range(p.generations):
            if cancelled():
                break
            # ---- variation, with draws the hardware or a belt check rejects redrawn (each recorded, never simulated)
            elites = list(result.cells.values())
            slots: list[tuple[np.ndarray, list[str], list[float] | None, str]] = []
            rejected: list[Any] = []
            for i in range(p.batch_size):
                for attempt in range(p.redraws + 1):
                    label = ""
                    if seed_queue and attempt == 0:
                        label, x = seed_queue.pop(0)
                        parents: list[str] = []
                    elif not elites:
                        x = x_base.copy()
                        x[:n_geo] += rng.normal(0, p.sigma_init, n_geo)
                        flip = rng.random(n_hw) < max(p.hardware_flip, 0.5)
                        x[n_geo:] = np.where(flip, rng.random(n_hw), x[n_geo:])
                        parents = []
                    else:
                        a = by_id[elites[int(rng.integers(len(elites)))]]
                        b = by_id[elites[int(rng.integers(len(elites)))]]
                        x = vec[a.id].copy()
                        x[:n_geo] += (rng.normal(0, p.sigma_iso, n_geo)
                                      + rng.normal(0, p.sigma_line) * (vec[b.id][:n_geo] - vec[a.id][:n_geo]))
                        take_b = rng.random(n_hw) < 0.5  # uniform crossover of the hardware choices
                        x[n_geo:] = np.where(take_b, vec[b.id][n_geo:], x[n_geo:])
                        flip = rng.random(n_hw) < p.hardware_flip
                        x[n_geo:] = np.where(flip, rng.random(n_hw), x[n_geo:])
                        parents = [a.id] if a.id == b.id else [a.id, b.id]
                    x = np.clip(x, 0.0, 1.0)
                    values, d, why, extra = realise(x)
                    cid = f"{problem.run_id}-g{gen:03d}-{i:03d}" + (f"-r{attempt:02d}" if attempt else "")
                    if not why:
                        slots.append((x, parents, None, cid))
                        slot_values[cid], slot_extra[cid] = values, extra
                        if label:
                            labels[cid] = label
                        break
                    rejected.append(Candidate(id=cid + "-x", run_id=problem.run_id, generation=gen, parents=parents,
                                              genome={"definition": gdef.name, "version": gdef.version,
                                                      "values": values},
                                              controller=problem.controller, fitness=-1e9, status="infeasible",
                                              error="; ".join(why),
                                              mass_g=float(d.spec.total_mass_g()) if d is not None else 0.0))
                    if label:
                        notes.append(f"seed body {label!r} rejected: {'; '.join(why)}")
                        break
            # ---- R11c: stop when more than the set share of this generation's draws is rejected (ADR-103)
            if prod is not None:
                n_draws = len(rejected) + len(slots)
                frac = len(rejected) / max(1, n_draws)
                if frac > prod.pr.stop_rejected_fraction:
                    tally: dict[str, int] = {}
                    for c in rejected:
                        for r in str(c.error).split("; "):
                            key = r.split(" (")[0][:120]
                            tally[key] = tally.get(key, 0) + 1
                    st0 = archive.stats
                    entry = {"generation": gen, "stopped": True, "rejected": len(rejected), "draws": n_draws,
                             # the fields every generation entry has (the lab's report reads "best" and "elites")
                             "best": float(st0.obj_max) if st0.num_elites else None,  # type: ignore[arg-type]
                             "mean": float(st0.obj_mean) if st0.num_elites else None,  # type: ignore[arg-type]
                             "coverage": float(st0.coverage), "qd_score": float(st0.qd_score),
                             "elites": int(st0.num_elites),
                             "rejected_fraction": round(frac, 3),
                             "reasons": [[k, n] for k, n in sorted(tally.items(), key=lambda kv: -kv[1])[:20]],
                             "notes": list(notes), "bodies": 0, "infeasible": len(rejected), "failed": 0,
                             "unsafe": 0, "evals": result.evals}
                    result.candidates += rejected
                    result.history.append(entry)
                    result.archive = self.archive_view(result, by_id, summaries, dkeys, ranges)
                    report(kind="generation", generation=gen, entry=entry, candidates=rejected, result=result)
                    break
            # ---- stage 1: the screen of every accepted body
            tasks = [Task(fn="calflab.evolve.hardware:screen_task", payload=common(slot_values[cid]), id=cid)
                     for _x, _par, _w, cid in slots]
            n_all = len(tasks)
            done = [0]

            def on_result(_i: int, _r: Any, gen: int = gen, done: list[int] = done, n_all: int = n_all) -> None:
                done[0] += 1
                report(kind="progress", generation=gen,
                       fraction=(gen + 0.5 * done[0] / max(1, n_all)) / p.generations)

            outs = backend.map(tasks, on_result=on_result, cancelled=cancelled) if tasks else []
            # ---- stage 2: the performances of the bodies that pass
            perf_jobs: list[tuple[int, int]] = []
            for k, out in enumerate(outs):
                if isinstance(out, dict) and "plays" in out:
                    s0 = summarise(out, None, hw, n_seeds)
                    if s0["passed_screen"] and hw.performances:
                        perf_jobs += [(k, j) for j in range(len(hw.performances))]
            ptasks = [Task(fn="calflab.evolve.hardware:perform_task",
                           payload={**tasks[k].payload, "performance": j}, id=f"{tasks[k].id}-p{j:02d}")
                      for k, j in perf_jobs]
            done2 = [0]

            def on_result2(_i: int, _r: Any, gen: int = gen, done2: list[int] = done2, n: int = len(ptasks)) -> None:
                done2[0] += 1
                report(kind="progress", generation=gen, fraction=(gen + 0.5 + 0.5 * done2[0] / max(1, n)) / p.generations)

            pouts = backend.map(ptasks, on_result=on_result2, cancelled=cancelled) if ptasks else []
            perfs: dict[int, list[dict[str, Any]]] = {}
            perf_errors: dict[int, str] = {}
            for (k, _j), po in zip(perf_jobs, pouts, strict=True):
                if isinstance(po, dict) and "seeds" in po:
                    perfs.setdefault(k, []).append(po)
                else:
                    perf_errors[k] = str(po.get("error") if isinstance(po, dict) else po)
            # ---- insertion
            new_cands: list[Any] = list(rejected)
            for k, ((x, parents, _w, cid), out) in enumerate(zip(slots, outs, strict=True)):
                genome = tasks[k].payload["genome"]
                if isinstance(out, dict) and out.get("infeasible"):
                    new_cands.append(Candidate(id=cid, run_id=problem.run_id, generation=gen, parents=parents,
                                               genome=genome, controller=problem.controller, fitness=-1e9,
                                               status="infeasible", error="; ".join(out["infeasible"]),
                                               mass_g=float(out.get("mass_g", 0.0))))
                    continue
                if not isinstance(out, dict) or "plays" not in out or k in perf_errors:
                    new_cands.append(Candidate(id=cid, run_id=problem.run_id, generation=gen, parents=parents,
                                               genome=genome, controller=problem.controller, fitness=-1e9,
                                               status="failed",
                                               error=perf_errors.get(k) or str(out.get("error") if isinstance(out, dict)
                                                                               else out)))
                    continue
                s0 = summarise(out, None, hw, n_seeds)
                summary = summarise(out, perfs.get(k) if s0["passed_screen"] and hw.performances else None, hw,
                                    n_seeds)
                summary["servo_genes"] = {g: genome["values"].get(g) for g in (f"servo_{q}" for q in PAIRS)
                                          if g in genome["values"]}
                summary["label"] = labels.get(cid, "")
                summary["production"] = slot_extra.get(cid) or {}
                summary["tables"] = tables(summary, hw)
                result.evals += int(out.get("evals", 0)) + sum(int(po.get("evals", 0)) for po in perfs.get(k, []))
                desc = {key: float(registry.get("behavior_descriptor", key)().describe_candidate(  # type: ignore[attr-defined]
                    None, {"hardware": summary}, {})) for key in dkeys}
                measures = np.array([[desc[key] for key in dkeys]])
                fit = float(summary["fitness"])
                info = archive.add(x[None, :], np.array([fit]), measures)
                status = int(info["status"][0])
                gi = archive.int_to_grid_index(archive.index_of(measures))[0]
                fastest = next((pl for pl in out["plays"] if pl["key"] == summary["fastest_trot"]), None)
                walk = next((pl for pl in out["plays"] if pl["primitive"] == "walk"), None)
                ctrl_src = fastest or walk
                ctrl = (ctrl_src["seeds"][0].get("controller") if ctrl_src and ctrl_src["seeds"] else None) \
                    or problem.controller
                cand = Candidate(
                    id=cid, run_id=problem.run_id, generation=gen, parents=parents, genome=genome, controller=ctrl,
                    fitness=fit, fitness_terms={
                        "headroom": {"value": summary["headroom"], "weight": 1.0, "weighted": summary["headroom"]},
                        "hardware_cost": {"value": summary["costs"]["cost_index"], "weight": -hw.cost_weight,
                                          "weighted": round(-hw.cost_weight * summary["costs"]["cost_index"], 4)}},
                    descriptors=desc, metrics={"hardware": summary, "speed_mps": summary["trot_speed_mm_s"] / 1000.0,
                                               "safety_margin": summary["headroom"]},
                    cell=(int(gi[0]), int(gi[1])), status={0: "rejected", 1: "improved", 2: "new"}[status],
                    mass_g=float(out.get("mass_g", 0.0)))
                by_id[cid] = cand
                vec[cid] = x
                summaries[cid] = summary
                if status > 0:
                    result.cells[f"{gi[0]},{gi[1]}"] = cid
                new_cands.append(cand)
            result.candidates += new_cands
            ok = [c for c in new_cands if c.status not in ("failed", "infeasible", "unsafe")]
            stats = archive.stats
            entry = {
                "generation": gen,
                "best": float(stats.obj_max) if stats.num_elites else None,  # type: ignore[arg-type]
                "mean": float(stats.obj_mean) if stats.num_elites else None,  # type: ignore[arg-type]
                "gen_best": max((c.fitness for c in ok), default=None),
                "gen_mean": float(np.mean([c.fitness for c in ok])) if ok else None,
                "coverage": float(stats.coverage), "qd_score": float(stats.qd_score),
                "elites": int(stats.num_elites), "evals": result.evals,
                "failed": sum(1 for c in new_cands if c.status == "failed"),
                "infeasible": sum(1 for c in new_cands if c.status == "infeasible"),
                "unsafe": 0, "passed_screen": sum(1 for c in ok if summaries[c.id]["passed_screen"]),
                "bodies": len(slots), "notes": list(notes),
            }
            notes.clear()
            result.history.append(entry)
            result.archive = self.archive_view(result, by_id, summaries, dkeys, ranges)
            report(kind="generation", generation=gen, entry=entry, candidates=new_cands, result=result)
        if not result.archive:
            result.archive = self.archive_view(result, by_id, summaries, dkeys, ranges)
        return result

    def archive_view(self, result: Any, by_id: dict[str, Any], summaries: dict[str, dict[str, Any]],
                     dkeys: list[str], ranges: list[tuple[float, float]]) -> dict[str, Any]:
        """The heatmap, plus the Pareto front over every body judged (minutes held, fastest trot within, cost index)
        as a ready-to-show table."""
        p: Any = self.params
        axes = []
        for key, rng_, n in zip(dkeys, ranges, (p.grid_x, p.grid_y), strict=True):
            cls = registry.get("behavior_descriptor", key)
            axes.append({"key": key, "label": cls.label, "unit": cls.unit, "range": list(rng_), "cells": n})  # type: ignore[attr-defined]
        cells = []
        for key, cid in result.cells.items():
            i, j = (int(v) for v in key.split(","))
            c = by_id[cid]
            cells.append({"i": i, "j": j, "candidate": cid, "fitness": c.fitness, "generation": c.generation,
                          "descriptors": c.descriptors, "speed_mps": c.metrics.get("speed_mps")})
        front = pareto(summaries)
        rows = []
        for cid in front:
            s = summaries[cid]
            c = s["costs"]
            stop = ", ".join(f"{j} {LIMIT_LABELS.get(lim, lim)} ({n})" for j, lim, n in s["stoppers"][:2]) or "-"
            rows.append([cid.split("-", 3)[-1] + (f" ({s['label']})" if s.get("label") else ""),
                         f"{s['minutes_held']}/{s['minutes_of']}" if s["performances_played"] else "screened out",
                         f"{s['trot_speed_mm_s']:.0f}", f"{c['cost_index']:.2f}",
                         ", ".join(f"{n} x {m}" for m, n in c["new_servos"].items()) or "none",
                         " ".join(f"{d['drive']}:{d['pulleys']}" for d in s["drives"]), stop])
        return {"axes": axes, "cells": cells, "tables": [{
            "title": "Pareto front: behaviour minutes held x fastest trot within x hardware cost",
            "columns": ["candidate", "minutes", "trot mm/s", "cost", "new servos", "pulleys", "stopped most by"],
            "rows": rows, "warn": [], "candidates": front}]}


def pareto(summaries: dict[str, dict[str, Any]]) -> list[str]:
    """Candidates no other one beats on every objective (more minutes held, faster trot within, lower cost index),
    sorted by minutes then speed."""
    pts = {cid: (s["minutes_held"], s["trot_speed_mm_s"], -float(s["costs"]["cost_index"]))
           for cid, s in summaries.items()}
    front = []
    for a, pa in pts.items():
        if not any(all(qb >= qa for qa, qb in zip(pa, pb, strict=True)) and pb != pa for b, pb in pts.items() if b != a):
            front.append(a)
    return sorted(front, key=lambda c: (-pts[c][0], -pts[c][1], -pts[c][2]))


# ====================================================================== archive axes
@register
class BehaviourMinutesHeld(BehaviorDescriptor):
    key = "behaviour_minutes_held"
    label = "Behaviour minutes held"
    description = ("How many one-minute performances (behaviour x seed) of the hardware preset stay within every "
                   "limit at the margin; 0 for a body screened out.")
    range = (0.0, 33.0)
    unit = "min"

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return float(((metrics.get("hardware") or {}).get("minutes_held")) or 0.0)


@register
class TrotSpeedWithin(BehaviorDescriptor):
    key = "trot_speed_within"
    label = "Fastest trot within limits"
    description = ("Speed of the fastest trot setting of the quick grid that stays within every limit at the margin "
                   "on every seed (its slowest seed); 0 if none does.")
    range = (0.0, 500.0)
    unit = "mm/s"

    def describe_candidate(self, spec: Any, metrics: dict[str, Any], controller_params: dict[str, Any]) -> float:
        return float(((metrics.get("hardware") or {}).get("trot_speed_mm_s")) or 0.0)
