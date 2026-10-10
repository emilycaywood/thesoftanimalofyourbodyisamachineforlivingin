"""Proportion study: many bodies, each tried in several gaits (ADR-059).

Evolve looks for one best body for one fitness. This asks a different
question: across the ranges the researcher sets for a few lengths, which
proportions walk, trot and bound, how fast, and what does each motor and the
battery see? Every body is built from the working design with only those
lengths changed, gets a gait tuned for it per footfall pattern (CMA-ES within
the motors' speed caps, as *Tune for this body* does), and is then judged on a
longer rollout. Nothing is chosen: the result is the whole table, with the
bodies no other body beats on both speed and torque margin marked.

Lengths are real millimetres on the body, as the Form sliders show them
(ADR-052). Bodies are plain tasks, so they run on any compute backend.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.model.genome import GenomeDefinition
from calflab.schema import P

#: fitness lost per 100 % over a speed cap, and the excess beyond which a gait is not simulated (as in tune_gait)
SPEED_PENALTY = 6.0
SKIP_ABOVE = 0.5
#: a body "works" in a gait only if it spends at most this fraction of the time at a joint limit
MAX_LIMIT_TIME = 0.02


class ProportionStudySettings(BaseModel):
    """What to vary and how hard to look. A range of 0 to 0 leaves that length as the design has it."""

    thigh_min: float = P(0.0, unit="mm", ui="number", ge=0, le=400, group="Thigh length", label="From", desc="Shortest thigh to try (real mm on the body).")
    thigh_max: float = P(0.0, unit="mm", ui="number", ge=0, le=400, group="Thigh length", label="To", desc="Longest thigh to try. 0 to 0 = keep the design's thighs.")
    shank_min: float = P(0.0, unit="mm", ui="number", ge=0, le=500, group="Shank length", label="From", desc="Shortest shank to try (knee axis to hoof centre, real mm).")
    shank_max: float = P(0.0, unit="mm", ui="number", ge=0, le=500, group="Shank length", label="To", desc="Longest shank to try. 0 to 0 = keep the design's shanks.")
    front_hind_differ: bool = P(
        False, group="Front and hind legs", label="Vary separately",
        desc="Off = one thigh and one shank length for all four legs. On = front and hind legs each get their own (twice as many unknowns: use more bodies).",
    )
    trunk_length_min: float = P(0.0, unit="mm", ui="number", ge=0, le=800, group="Trunk length", label="From", desc="Shortest trunk to try (real mm).")
    trunk_length_max: float = P(0.0, unit="mm", ui="number", ge=0, le=800, group="Trunk length", label="To", desc="Longest trunk to try. 0 to 0 = keep the design's trunk.")
    stance_width_min: float = P(0.0, unit="mm", ui="number", ge=0, le=400, group="Stance width", label="From", desc="Narrowest left-right hip distance to try (real mm).")
    stance_width_max: float = P(0.0, unit="mm", ui="number", ge=0, le=400, group="Stance width", label="To", desc="Widest. 0 to 0 = keep the design's stance.")
    hip_drop_min: float = P(0.0, unit="mm", ui="number", ge=0, le=120, group="Hip drop", label="From", desc="Smallest hip drop to try (real mm).")
    hip_drop_max: float = P(0.0, unit="mm", ui="number", ge=0, le=120, group="Hip drop", label="To", desc="Largest. 0 to 0 = keep the design's hip drop.")
    height_min: float = P(0.0, unit="mm", ui="number", ge=0, le=1000, group="Overall height", label="From", desc="Bodies standing lower than this are not tried (the height readout of the lab).")
    height_max: float = P(0.0, unit="mm", ui="number", ge=0, le=1000, group="Overall height", label="To", desc="Bodies standing taller than this are not tried. 0 to 0 = any height.")
    bodies: int = P(24, ge=1, le=200, group="Search", desc="Bodies to try, besides the design as it is.")
    gaits: list[str] = P(
        default_factory=lambda: ["walk", "trot", "bound"], ui="json", group="Search",
        desc="Footfall patterns each body is tried in.",
    )
    iterations: int = P(10, ge=0, le=100, group="Search", desc="CMA-ES iterations per body and gait (0 = only the document's gait numbers).")
    popsize: int = P(8, ge=4, le=64, group="Search", desc="Gaits tried per iteration.")
    duration_s: float = P(6.0, unit="s", ge=2, le=30, step=0.5, group="Search", desc="Simulated seconds per trial; the final check runs 2.5 times as long.")
    speed_fraction: float = P(
        0.67, ge=0.2, le=1.0, step=0.01, group="Search",
        desc="Commanded joint speed may reach this fraction of each motor's recorded no-load speed.",
    )
    min_speed_mps: float = P(0.02, unit="m/s", ge=0, le=2, step=0.01, group="Search", desc="Slower than this forward does not count as working.")
    sigma: float = P(0.25, ge=0.05, le=0.5, step=0.01, group="Search", desc="Initial CMA-ES step size.", advanced=True)
    seed: int = P(1, ge=1, le=2**31 - 1, ui="number", group="Search", desc="Random seed (bodies and gait search).")


#: leg quantity -> (label, (front gene, hind gene))
_LEG = {
    "thigh": ("Thigh length", ("front_thigh_length", "hind_thigh_length")),
    "shank": ("Shank length", ("front_shank_length", "hind_shank_length")),
}
#: other quantity -> (label, gene)
_OTHER = {
    "trunk_length": ("Trunk length", "trunk_length"),
    "stance_width": ("Stance width", "stance_width"),
    "hip_drop": ("Hip drop", "hip_drop"),
}


def study_dimensions(gdef: GenomeDefinition, genes: dict[str, Any], settings: ProportionStudySettings) -> list[dict[str, Any]]:
    """The quantities the study varies, each with the genes it drives and its
    range in real millimetres after fitting it into what those genes allow.

    Leg lengths go through the front/hind length genes (``own_leg_lengths`` is
    switched on in every variant), because their sliders reach further than
    the shared ones. A front leg without a thigh has no thigh to vary.
    """
    values = gdef.complete(genes)
    dims: list[dict[str, Any]] = []

    def add(key: str, label: str, gene_ids: tuple[str, ...], lo: float, hi: float) -> None:
        if hi <= 0 or hi < lo:
            return
        g_lo = max(float(gdef.gene(g).min or 0.0) * gdef.factor(g, values) for g in gene_ids)
        g_hi = min(float(gdef.gene(g).max or 0.0) * gdef.factor(g, values) for g in gene_ids)
        a, b = max(lo, g_lo), min(hi, g_hi)
        if b < a:
            a = b = min(max(lo, g_lo), g_hi)
        dim: dict[str, Any] = {
            "key": key, "label": label, "genes": list(gene_ids), "unit": "mm", "min": round(a, 2), "max": round(b, 2),
            "asked": [lo, hi], "clamped": (a, b) != (lo, hi),
        }
        if dim["clamped"]:
            dim["note"] = (
                f"{label}: asked {lo:g} to {hi:g} mm; the slider allows {g_lo:.1f} to {g_hi:.1f} mm at this "
                f"overall scale, so {a:.1f} to {b:.1f} mm is used."
            )
        dims.append(dim)

    has_front_thigh = bool(values.get("front_thigh", True))
    for key, (label, (front, hind)) in _LEG.items():
        lo, hi = getattr(settings, f"{key}_min"), getattr(settings, f"{key}_max")
        both = (front, hind) if (key != "thigh" or has_front_thigh) else (hind,)
        if settings.front_hind_differ and len(both) == 2:
            add(f"front_{key}", f"Front {label.lower()}", (front,), lo, hi)
            add(f"hind_{key}", f"Hind {label.lower()}", (hind,), lo, hi)
        else:
            add(key, label, both, lo, hi)
    for key, (label, gene) in _OTHER.items():
        add(key, label, (gene,), getattr(settings, f"{key}_min"), getattr(settings, f"{key}_max"))
    return dims


def _own_lengths(gdef: GenomeDefinition, genes: dict[str, Any], dims: list[dict[str, Any]]) -> dict[str, Any]:
    """The design's genes, with ``own_leg_lengths`` on if a leg length is varied.
    The four front/hind lengths then take what the legs measure now, so the
    switch by itself changes nothing."""
    out = dict(gdef.complete(genes))
    varies_legs = any(g in gs for d in dims for g in d["genes"] for _, gs in _LEG.values())
    if varies_legs and not out.get("own_leg_lengths"):
        for seg in ("thigh", "shank"):
            out[f"front_{seg}_length"] = out[f"hind_{seg}_length"] = out[f"{seg}_length"]
        out["own_leg_lengths"] = True
    return out


def variant_genes(gdef: GenomeDefinition, genes: dict[str, Any], dims: list[dict[str, Any]], real: dict[str, float]) -> dict[str, Any]:
    """The design's genes with the study quantities set to ``real`` (mm on the body)."""
    out = _own_lengths(gdef, genes, dims)
    for d in dims:
        for g in d["genes"]:
            out[g] = gdef.gene(g).coerce(real[d["key"]] / gdef.factor(g, out))
    return out


def design_real(gdef: GenomeDefinition, genes: dict[str, Any], dims: list[dict[str, Any]]) -> dict[str, float]:
    """What the study quantities measure on the design as it is (mm). Where
    front and hind share a quantity but differ on the design, the front value."""
    own = _own_lengths(gdef, genes, dims)
    return {d["key"]: round(float(own[d["genes"][0]]) * gdef.factor(d["genes"][0], own), 2) for d in dims}


def study_notes(spec: Any, lib: Any, compile_params: dict[str, Any], dims: list[dict[str, Any]]) -> list[str]:
    """What the reader of a study must know before trusting it: ranges that
    were cut to fit, component values that are unverified, guessed or defaults,
    the voltage the motor figures are for, and the model settings in use."""
    from calflab.wiring.budget import power_budget

    notes = [d["note"] for d in dims if d.get("note")]
    keys = dict.fromkeys(a.component for a in spec.actuators)
    bat = next((g.component for b in spec.bodies for g in b.geoms if g.id == "elec.battery"), None)
    for key in [*keys, *([bat] if bat else [])]:
        if not key or not lib.has(key):
            continue
        c = lib.get(key)
        parts = []
        if not c.verified:
            parts.append("not verified")
        if c.guessed:
            parts.append("guessed: " + ", ".join(c.guessed))
        if c.defaulted:
            parts.append("not on its datasheet, default assumed: " + ", ".join(c.defaulted))
        if parts:
            notes.append(f"{c.name} ({c.key}): {'; '.join(parts)}.")
    note = power_budget(spec, lib, None).get("voltage_note")
    if note:
        notes.append(note)
    for name, label in (("joint_loss_scale", "Joint loss scale"), ("armature_scale", "Armature scale")):
        v = float(compile_params.get(name, 1.0))
        if v != 1.0:
            notes.append(f"Model setting {label} = {v:g} (1 = the values chosen for the 5 kg calf / the library).")
    if compile_params.get("include_skin", True):
        notes.append(
            "The skin model is on: skin mass and skin stiffness at the joints are simulated. "
            "Switch Include skin off in the Model settings for a body without skin."
        )
    return notes


def sample_unit(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """A Latin hypercube: ``n`` points in [0, 1]^d, one per stratum of every axis."""
    if n <= 0 or d <= 0:
        return np.zeros((max(n, 0), max(d, 0)))
    cols = [(rng.permutation(n) + rng.uniform(0.0, 1.0, n)) / n for _ in range(d)]
    return np.stack(cols, axis=1)


def study_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Try one body in every gait asked for.

    Payload: a :func:`calflab.evolve.tasks.simulate_once` payload plus ``gaits``,
    ``inner`` {iterations, popsize, sigma}, ``speed_fraction``, ``check_s``,
    ``min_speed_mps`` and ``seed``. Returns mass (g), height (mm) and one entry
    per gait with the tuned gait, whether it works and why not, the per-joint
    torque (N*m) and speed (deg/s) table and the battery load (A).
    """
    import cma

    from calflab.components import library
    from calflab.design import build_design
    from calflab.evolve.gait import speed_caps, speed_excess
    from calflab.fitness.preset import FitnessPreset
    from calflab.model.genome import Genome
    from calflab.model.overrides import Override
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout
    from calflab.wiring.budget import power_budget

    load_plugins()
    lib = library()
    design = build_design(
        Genome.model_validate(payload["genome"]),
        [Override.model_validate(o) for o in payload.get("overrides", [])],
        payload.get("generator", "calf"),
        payload.get("generator_params"),
    )
    spec = design.spec
    sim = {**payload.get("sim", {}), "start_pose": "stand", "pushes": []}
    settings = SimSettings.model_validate(sim)
    check = SimSettings.model_validate({**sim, "duration_s": float(payload.get("check_s", 15.0))})
    cm = compile_mjcf(spec, lib, CompileOptions.model_validate(payload.get("compile", {})), settings.seed)
    preset = FitnessPreset.model_validate(payload["fitness"])
    cls = registry.get("controller", payload["controller"]["key"])
    start: dict[str, Any] = dict(payload["controller"].get("params", {}))
    joint_ids = [a.joint for a in spec.actuators]
    dims = cls.vector_dims()  # type: ignore[attr-defined]
    relevant = set(cls.relevant_dims(joint_ids))  # type: ignore[attr-defined]
    free = [i for i, d in enumerate(dims) if d.name in relevant]
    caps = speed_caps(spec, lib, float(payload.get("speed_fraction", 0.67)))
    inner = payload.get("inner", {})
    iterations, popsize = int(inner.get("iterations", 0)), int(inner.get("popsize", 8))
    seed = int(payload.get("seed", 1))
    min_speed = float(payload.get("min_speed_mps", 0.0))
    comp = {a.id: a.component for a in spec.actuators}
    evals = 0

    def excess_of(params: dict[str, Any]) -> float:
        return max(0.0, speed_excess(cls.peak_joint_speeds(params, joint_ids), caps))  # type: ignore[attr-defined]

    def score(params: dict[str, Any], s: Any) -> tuple[float, dict[str, Any]]:
        nonlocal evals
        evals += 1
        m = compute_metrics(run_rollout(cm, cls(params), s, lib))  # type: ignore[arg-type]
        return float(preset.evaluate(m)["total"]), m

    gaits: dict[str, Any] = {}
    for n, gait in enumerate(payload.get("gaits") or [start.get("gait", "trot")]):
        base = {**start, "gait": gait}
        best: tuple[float, dict[str, Any]] | None = None
        if excess_of(base) == 0.0:
            f, m = score(base, settings)
            if not m.get("fell"):
                best = (f, base)
        if dims and free and iterations > 0:
            x_full = np.array(cls.vector_from_params(base), dtype=np.float64)  # type: ignore[attr-defined]
            es = cma.CMAEvolutionStrategy(
                list(x_full[free]), float(inner.get("sigma", 0.25)),
                {"bounds": [0.0, 1.0], "popsize": popsize, "seed": seed + n, "verbose": -9},
            )
            for _ in range(iterations):
                xs = es.ask()
                losses = []
                for x in xs:
                    full = x_full.copy()
                    full[free] = np.asarray(x, dtype=float)
                    params = cls.params_from_vector(base, full)  # type: ignore[attr-defined]
                    excess = excess_of(params)
                    if excess > SKIP_ABOVE:
                        losses.append(SPEED_PENALTY * excess)
                        continue
                    f, m = score(params, settings)
                    losses.append(-(f - SPEED_PENALTY * excess))
                    if excess == 0.0 and not m.get("fell") and (best is None or f > best[0]):
                        best = (f, params)
                es.tell(xs, losses)
        params = best[1] if best else base
        fit, m = score(params, check)
        budget = power_budget(spec, lib, m)
        joints = [
            {
                "joint": row["joint"],
                "actuator": aid,
                "component": comp.get(aid),
                "torque_peak_nm": round(row["torque_peak_nm"], 4),
                "torque_rms_nm": round(row["torque_rms_nm"], 4),
                "torque_limit_nm": round(row["torque_limit_nm"], 4),
                "torque_margin": round(row["torque_margin"], 3),
                "torque_saturated": round(row.get("torque_saturated", 0.0), 3),
                "speed_peak_deg_s": round(row["speed_peak_deg_s"], 1),
                "speed_limit_deg_s": round(row["speed_limit_deg_s"], 1) if "speed_limit_deg_s" in row else None,
                "speed_margin": round(row["speed_margin"], 3) if "speed_margin" in row else None,
            }
            for aid, row in m["by_actuator"].items()
        ]
        bat = budget.get("battery") or {}
        flags: list[str] = []
        if best is None:
            flags.append("no gait stayed upright within the motors' speed caps; the starting gait is shown")
        if m.get("fell"):
            flags.append(f"fell after {m.get('survival', 0) * check.duration_s:.1f} s")
        if m.get("speed_mps", 0.0) < min_speed:
            flags.append("does not move forward")
        if m.get("joint_limit_violation", 0.0) > MAX_LIMIT_TIME:
            flags.append(f"at a joint limit {m['joint_limit_violation'] * 100:.0f} % of the time")
        if m.get("speed_margin_min") is not None and m["speed_margin_min"] < 0:
            flags.append("a joint moved faster than its motor's no-load speed")
        works = not flags
        # reported, but a gait that needs all of a motor's usable torque still counts as working
        if m.get("torque_margin_min", 1.0) <= 0.005:
            flags.append("a motor is at its torque limit")
        if bat.get("peak_ok") is False:
            flags.append("battery peak current over its limit")
        gaits[gait] = {
            "works": works,
            "flags": flags,
            "fitness": round(fit, 4),
            "controller": {"key": cls.key, "params": params},
            "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items() if k != "by_actuator"},
            "joints": joints,
            "battery": {
                "mean_current_a": budget["mean_current_a"],
                "peak_current_a": bat.get("peak_current_a", budget["peak_current_a"]),
                "max_current_a": bat.get("max_current_a"),
                "peak_ok": bat.get("peak_ok"),
                "runtime_min": bat.get("runtime_min"),
                "bus_voltage_v": budget["bus_voltage_v"],
            },
        }
    return {
        "mass_g": round(cm.total_mass_kg * 1000.0, 1),  # as simulated (without the skin if the model leaves it out)
        "height_mm": round(spec.standing_height_mm(), 1),
        "gaits": gaits,
        "evals": evals,
        "warnings": list(design.warnings),
    }


def _rank(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    ranks = np.empty(len(v))
    ranks[order] = np.arange(len(v), dtype=float)
    for val in np.unique(v):  # ties share their mean rank
        same = v == val
        ranks[same] = ranks[same].mean()
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation of two lists (None if there are too few or either does not vary)."""
    if len(a) < MIN_FOR_TREND:
        return None
    x, y = _rank(np.asarray(a, dtype=float)), _rank(np.asarray(b, dtype=float))
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


#: the outcomes trends are reported for: key in a gait's metrics -> word used in the sentence
OUTCOMES = {"speed_mps": "speed", "torque_margin_min": "torque margin", "stability": "stability"}
TREND_THRESHOLD = 0.4
MIN_FOR_TREND = 10  # with fewer bodies a rank correlation is mostly chance


def summarize(bodies: list[dict[str, Any]], dims: list[dict[str, Any]], gaits: list[str]) -> dict[str, Any]:
    """What the table shows beyond its rows: per gait, how many bodies work,
    which of them no other beats on both speed and worst torque margin (the
    trade-off front), and how each varied length goes with the outcomes."""
    ok = [b for b in bodies if not b.get("error")]
    out: dict[str, Any] = {
        "gaits": {},
        "works_in_all": [b["id"] for b in ok if gaits and all(b["gaits"].get(g, {}).get("works") for g in gaits)],
    }
    for g in gaits:
        rows = [(b["id"], b["gaits"][g]) for b in ok if g in b["gaits"]]
        working = [(i, r) for i, r in rows if r["works"]]
        front = []
        for i, r in working:
            s, t = r["metrics"]["speed_mps"], r["metrics"]["torque_margin_min"]
            beaten = any(
                o["metrics"]["speed_mps"] >= s
                and o["metrics"]["torque_margin_min"] >= t
                and (o["metrics"]["speed_mps"] > s or o["metrics"]["torque_margin_min"] > t)
                for j, o in working
                if j != i
            )
            if not beaten:
                front.append(i)
        trends = []
        varied = [b for b in ok if g in b["gaits"] and not b.get("baseline")]
        for d in dims:
            xs = [float(b["real"][d["key"]]) for b in varied]
            for key, word in OUTCOMES.items():
                rho = spearman(xs, [float(b["gaits"][g]["metrics"].get(key) or 0.0) for b in varied])
                if rho is not None and abs(rho) >= TREND_THRESHOLD:
                    trends.append({
                        "dimension": d["key"], "label": d["label"], "outcome": key, "rho": round(rho, 2),
                        "text": f"More {d['label'].lower()}: {'more' if rho > 0 else 'less'} {word} (rank correlation {rho:+.2f}).",
                    })
        best = max(working, key=lambda ir: ir[1]["metrics"]["speed_mps"], default=None)
        out["gaits"][g] = {
            "tried": len(rows),
            "working": len(working),
            "front": front,
            "fastest": best[0] if best else None,
            "trends": sorted(trends, key=lambda t: -abs(t["rho"])),
        }
    return out
