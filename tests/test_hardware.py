"""Hardware chosen by the loads of behaviour (session R11, ADR-102): calflab.evolve.hardware."""

from __future__ import annotations

import hashlib
import importlib
from typing import Any

import pytest
from calflab.design import build_design, genome_definition
from calflab.evolve.hardware import (
    HardwareSettings,
    HardwareSpace,
    budget_reasons,
    catalog_with_what_ifs,
    pareto,
    rejection,
    screen_task,
)
from calflab.fitness import presets
from calflab.mech.belts import BeltCatalog, catalog_files
from calflab.model.genome import Genome
from calflab.plugins import load_plugins, registry
from calflab.plugins.contracts import check_plugin

NEW = "sts3250_c002"


def _genome(**values: Any) -> Genome:
    gdef = genome_definition("feral_calf")
    return Genome(definition=gdef.name, version=gdef.version, values={**gdef.defaults(), **values})


def _hw(**kw: Any) -> HardwareSettings:
    load_plugins()
    hw = HardwareSettings.model_validate(presets()["hardware"].evaluation.hardware)  # type: ignore[union-attr]
    return hw.model_copy(update={"baseline": {"servos": {p: "sts3215_c018" for p in
                                                         ("hip_abd", "stifle", "hock", "shoulder", "carpus")},
                                              "pulley_sizes": ["2 mm 30T", "2 mm 60T"], "belt_lengths": [],
                                              "mass_g": 0.0}, **kw})


def _payload(genome: Genome, hw: HardwareSettings, seeds: list[int] | None = None) -> dict[str, Any]:
    ev = presets()["hardware"].evaluation
    assert ev is not None
    return {"genome": genome.model_dump(mode="json"), "overrides": [], "generator": "feral_calf",
            "generator_params": {"belt_catalog": catalog_files(None)}, "compile": {},
            "evaluation": ev.model_copy(update={"seeds": seeds or [0, 1, 2]}).model_dump(mode="json"),
            "hardware": hw.model_dump(mode="json")}


# ---------------------------------------------------------------------- contract
def test_contract_preset_optimizer_and_axes() -> None:
    load_plugins()
    for kind, key in (("optimizer", "map_elites_hardware"), ("behavior_descriptor", "behaviour_minutes_held"),
                      ("behavior_descriptor", "trot_speed_within")):
        assert check_plugin(registry.get(kind, key)) == [], key
    pre = presets()["hardware"]
    assert pre.evaluation is not None and pre.evaluation.hardware is not None
    hw = HardwareSettings.model_validate(pre.evaluation.hardware)
    assert hw.margin == 0.2 and pre.evaluation.seeds == [0, 1, 2] and pre.evaluation.randomize
    assert hw.servo_budget == {NEW: 4} and not hw.what_if_pulleys
    assert len(hw.performances) == 11 and {s.label for s in hw.seeds_bodies} == {"R9 best", "R10 1:1 45T",
                                                                                   "R10 40T/80T"}


def test_hardware_genes_are_catalog_ids_only() -> None:
    hw = _hw()
    gdef = genome_definition("feral_calf")
    cat = BeltCatalog.from_dict(catalog_files(None))
    space = HardwareSpace(gdef, hw, cat, gdef.defaults())
    assert "belt_carpus_length" in space.names and "servo_hock" in space.names
    assert not any("c_mm" in n or "center" in n for n in space.names)  # C is never a gene (ADR-063)
    ids = {p.id for p in cat.pairs} | {e.id for e in cat.lengths} | {s.id for s in cat.systems} | set(hw.servo_choices)
    import numpy as np

    rng = np.random.default_rng(1)
    for _ in range(50):
        vals = space.decode(rng.random(len(space)), gdef.defaults())
        assert all(vals[n] in ids for n in space.names)
    start = gdef.defaults()
    assert space.decode(space.encode(start), start) == start  # the starting body round-trips
    # what-ifs only when switched on, and never in the project's catalog files
    assert not any(p.id.endswith("-whatif") for p in cat.pairs)
    cat2 = BeltCatalog.from_dict(catalog_with_what_ifs(catalog_files(None), True))
    assert {"45T-45T-whatif", "30T-45T-whatif"} <= {p.id for p in cat2.pairs}
    assert budget_reasons({"belt_carpus_pulleys": "45T-45T-whatif"}, hw)  # off: rejected


# ---------------------------------------------------------------------- the servo budget
def test_servo_budget_is_respected() -> None:
    hw = _hw()
    four = {"servo_hock": NEW, "servo_carpus": NEW}
    six = {"servo_hock": NEW, "servo_carpus": NEW, "servo_hip_abd": NEW}
    assert budget_reasons(four, hw) == []
    assert any("servo budget: 6 new sts3250_c002 > 4" in r for r in budget_reasons(six, hw))
    d = build_design(_genome(**six), [], "feral_calf")
    assert any("servo budget" in r for r in rejection(d, hw))
    out = screen_task(_payload(_genome(**six), hw))
    assert out["infeasible"] and out["evals"] == 0


# ---------------------------------------------------------------------- a rejected belt never reaches a rollout
def test_rejected_belt_never_reaches_a_rollout(monkeypatch: pytest.MonkeyPatch) -> None:
    import calflab.sim as sim

    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a rejected body reached the simulator")

    monkeypatch.setattr(sim, "run_rollout", boom)
    monkeypatch.setattr(sim, "compile_mjcf", boom)
    bad = _genome(belt_hock_length="GT2-2mm-640-C")  # C ~ 275 mm on a 245 mm tibia: the servo is off its segment
    d = build_design(bad, [], "feral_calf")
    assert d.spec.metadata["infeasible"], "this belt was expected to fail a check"
    out = screen_task(_payload(bad, _hw()))
    assert out["infeasible"] and out["evals"] == 0 and "plays" not in out


# ---------------------------------------------------------------------- R13: lie_rise as a constraint (ADR-107)
def test_lie_rise_gate_screens_out_a_body_that_does_not_lie_and_rise(monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Any) -> None:
    """With a gate, a body whose best lie_rise does not hold plays nothing else and does not pass; one that holds
    plays the screen and passes on its other plays as before. The gate's search runs once per body (cached)."""
    import calflab.evolve.hardware as hwmod
    import calflab.evolve.lie_rise as lr
    from calflab.evolve.hardware import summarise

    calls: list[int] = []
    held = {"v": False}

    def fake_optimise(payload: Any, seeds: Any, margin: Any, s: Any, map_fn: Any = None, cache: Any = None,
                      report: Any = None) -> dict[str, Any]:
        calls.append(1)
        best = {"held": held["v"], "worst": 0.1 if held["v"] else -0.5, "params": {"kneel_carpus": 95.0},
                "seeds": [{"closest": "servo_sustained", "moves": []}]}
        return {"best": best, "start": {"worst": -3.0}, "plays": 30, "new_plays": 30}

    monkeypatch.setattr(lr, "optimise", fake_optimise)
    hw = _hw(lie_rise_gate={"popsize": 4, "generations": 1}, cache_dir=str(tmp_path / "hardware"),
             screen_extra=["walk"], trot_cycles_s=[0.8], trot_strides=[0.5])
    out = screen_task(_payload(_genome(), hw, [0]))
    assert out["plays"] == [] and out["lie_rise"]["held"] is False and out["evals"] == 30
    s = summarise(out, None, hw, 1)
    assert not s["passed_screen"] and s["screen"]["lie_rise (evolved)"]["worst_margin"] == -0.5
    again = screen_task(_payload(_genome(), hw, [0]))  # cached per body: no second search
    assert len(calls) == 1 and again["lie_rise"]["cached"]
    monkeypatch.setattr(hwmod, "play_primitive_seed", lambda *a, **k: {
        "within": True, "fell": False, "margin": 0.3, "violations": [], "closest": None, "speed_mm_s": 50.0,
        "joints": {}, "current": {}, "springs": {}, "controller": {"key": "feral_motion", "params": {}}})
    held["v"] = True
    hw2 = hw.model_copy(update={"lie_rise_gate": {"popsize": 4, "generations": 2}})  # other settings: new search
    out2 = screen_task(_payload(_genome(), hw2, [0]))
    assert len(calls) == 2 and out2["lie_rise"]["held"] and [p["key"] for p in out2["plays"]] == ["trot 0.8/0.5",
                                                                                                    "walk"]
    assert summarise(out2, None, hw2, 1)["passed_screen"]


# ---------------------------------------------------------------------- the optimizer, with plays faked
class _InProcess:
    """A compute backend that runs tasks in this process, in order (records what it was given)."""

    def __init__(self) -> None:
        self.given: list[Any] = []

    def map(self, tasks: list[Any], on_result: Any = None, cancelled: Any = None) -> list[Any]:
        out = []
        for i, t in enumerate(tasks):
            self.given.append(t)
            mod, fn = t.fn.split(":")
            out.append(getattr(importlib.import_module(mod), fn)(t.payload))
            if on_result:
                on_result(i, out[-1])
        return out


def _fake(spec: Any, key: str, seed: int) -> dict[str, Any]:
    h = int(hashlib.sha1(f"{spec.total_mass_g():.3f}|{spec.model_dump_json()[:4000]}|{key}|{seed}".encode())
            .hexdigest()[:8], 16)
    m = ((h % 1000) / 1000.0) * 0.8 - 0.4
    return {"within": m >= 0, "fell": False, "margin": round(m, 4), "violations": [] if m >= 0 else ["joint_speed"],
            "closest": "joint_speed", "speed_mm_s": float(h % 400),
            "joints": {"fl.carpus": {"speed": round(1 - m, 3), "torque": 0.1, "belt": None, "envelope": 0.5,
                                     "stall": 0.1, "binds": "speed", "belt_peak_n": None}},
            "current": {"known_servos": 0, "unknown_servos": 10, "known_peak_a": None, "known_mean_a": None},
            "controller": {"key": "feral_motion", "params": {}}}


def _run(monkeypatch: pytest.MonkeyPatch, **params: Any) -> tuple[Any, _InProcess]:
    import calflab.evolve.hardware as hwmod
    from calflab.evolve import EvolveProblem

    monkeypatch.setattr(hwmod, "play_primitive_seed", lambda play, spec, lib, c, seed, m: _fake(spec, play["key"], seed))
    monkeypatch.setattr(hwmod, "play_performance_seed",
                        lambda perf, spec, lib, c, seed, m, s: _fake(spec, perf["label"], seed))
    pre = presets()["hardware"].model_dump(mode="json")
    hw = pre["evaluation"]["hardware"]
    hw.update({"trot_cycles_s": [0.5], "trot_strides": [1.0], "screen_extra": ["walk"], "cache_dir": "",
               "performances": [{**p, "controller": {"key": "feral_motion", "params": {}}}
                                for p in hw["performances"][:2]]})
    g = genome_definition("feral_calf").default_genome()
    problem = EvolveProblem(genome=g.model_dump(mode="json"), overrides=[], generator="feral_calf",
                            generator_params={"belt_catalog": catalog_files(None)}, compile={}, sim={},
                            controller={"key": "feral_motion", "params": {}}, fitness=pre, run_id="t")
    opt = registry.get("optimizer", "map_elites_hardware")({"generations": 2, "batch_size": 4, "seed": 3, **params})
    be = _InProcess()
    res = opt.run(problem, be, lambda **_k: None)  # type: ignore[attr-defined]
    return res, be


def test_optimizer_is_deterministic_and_respects_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    load_plugins()
    a, be = _run(monkeypatch, hardware_flip=1.0)
    b, _ = _run(monkeypatch, hardware_flip=1.0)
    sig = [(c.id, c.status, c.fitness, sorted(c.genome["values"].items())) for c in a.candidates]
    assert sig == [(c.id, c.status, c.fitness, sorted(c.genome["values"].items())) for c in b.candidates]
    assert a.history[0]["notes"] and "what-if" in " ".join(a.history[0]["notes"])  # R9's / R10's 45T seeds skipped
    hw = _hw()
    for t in be.given:  # nothing over the budget and no failing belt was ever submitted for a play
        d = build_design(Genome.model_validate(t.payload["genome"]), [], "feral_calf",
                         t.payload["generator_params"])
        assert rejection(d, hw) == [], t.id
    judged = [c for c in a.candidates if c.status not in ("infeasible", "failed")]
    assert judged and all(c.metrics["hardware"]["tables"] for c in judged)
    assert a.archive["tables"][0]["candidates"]  # the Pareto front
    labels = {c.metrics["hardware"].get("label") for c in judged}
    assert "R10 40T/80T" in labels


def test_pareto_front() -> None:
    s = {"a": {"minutes_held": 30, "trot_speed_mm_s": 0.0, "costs": {"cost_index": 0.0}},
         "b": {"minutes_held": 20, "trot_speed_mm_s": 400.0, "costs": {"cost_index": 1.0}},
         "c": {"minutes_held": 20, "trot_speed_mm_s": 300.0, "costs": {"cost_index": 1.5}}}
    assert pareto(s) == ["a", "b"]


# ---------------------------------------------------------------------- real plays are deterministic
def test_screen_plays_are_deterministic() -> None:
    hw = _hw(trot_cycles_s=[0.8], trot_strides=[1.0], screen_extra=[], cache_dir="")
    p = _payload(_genome(), hw, seeds=[0])
    a, b = screen_task(p), screen_task(p)
    strip = [{k: v for k, v in s.items() if k != "controller"} for pl in a["plays"] for s in pl["seeds"]]
    assert strip == [{k: v for k, v in s.items() if k != "controller"} for pl in b["plays"] for s in pl["seeds"]]
    assert a["plays"][0]["seeds"][0]["joints"]  # per-joint uses


def test_unknown_costs_are_reported_not_guessed() -> None:
    from calflab.components import library
    from calflab.evolve.hardware import hardware_costs

    d = build_design(_genome(servo_hock=NEW, servo_carpus=NEW), [], "feral_calf")
    c = hardware_costs(d.spec, dict(d.genome.values), _hw(), library())
    assert c["new_servo_cost_usd"] is None and NEW in c["cost_unknown_for"]  # no price entered for the C002
    assert any("sts3215_c018 stall current" in u for u in c["unknown"])
    assert c["masses_not_entered"] > 0
