"""Evolving the body to perform a repertoire consistently and safely (ADR-079)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from calflab.design import build_design, genome_definition
from calflab.project.motions import AffectTags, MotionClip


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


def _sway(name, amp, fps=20, seconds=2.0):
    n = int(fps * seconds)
    v = [amp * 0.5 * (1 - np.cos(2 * np.pi * i / n)) for i in range(n)]
    return MotionClip(id=name, name=name, fps=fps, joints={"joint.fl.carpus": v, "joint.fr.carpus": v,
                                                           "joint.hl.stifle": [0.3 * x for x in v],
                                                           "joint.hr.stifle": [0.3 * x for x in v]},
                      affect=AffectTags(arousal=0.2, words=["calm"]))


def _payload(spec_genome, params, preset, compile_extra=None):
    from calflab.mech.belts import catalog_files

    return {"genome": spec_genome, "overrides": [], "generator": "feral_calf",
            "generator_params": {"belt_catalog": catalog_files(None)},
            "compile": {**(compile_extra or {})}, "sim": {"duration_s": 3.0, "record_hz": 25},
            "controller": {"key": "behaviors", "params": params}, "fitness": preset, "descriptors": [],
            "inner": {"iterations": 0}}


def _resolved(params, clips):
    from calflab.plugins import load_plugins, registry

    load_plugins()
    cls = registry.get("controller", "behaviors")
    base = {**cls.Params().model_dump(mode="json"), **params}
    base["clips"] = {c.id: {"fps": c.fps, "joints": c.joints, "affect": c.affect.model_dump(mode="json") if c.affect else None}
                     for c in clips}
    return base


def test_safety_constraints_reject_a_deliberately_overloading_clip(spec):
    from calflab.components import library
    from calflab.evolve.safety import SafetyPolicy, safety_report
    from calflab.plugins import registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, compute_metrics, run_rollout

    lib = library()
    # the carpus slammed through 100 deg in a tenth of a second, again and again: the servo saturates
    slam = MotionClip(id="slam", name="slam", fps=50, joints={"joint.fl.carpus": [0, 0, 100, 100, 100, 0, 0, 0] * 6})
    params = _resolved({"repertoire": [{"name": "slam", "kind": "clip", "clip": "slam", "speed": [1, 1],
                                        "amplitude": [1, 1]}], "blend_s": 0.0, "speed_fraction": 0.0}, [slam])
    cm = compile_mjcf(spec, lib, CompileOptions(torque_derating=1.0), 0)
    r = run_rollout(cm, registry.get("controller", "behaviors")(params), SimSettings(duration_s=3.0), lib)
    rep = safety_report(r, spec, lib, SafetyPolicy(), compute_metrics(r))
    by = {c["key"]: c for c in rep["constraints"]}
    assert set(by) == {"servo_sustained", "stall", "belt_sustained", "belt_breaking", "joint_speed", "joint_limit",
                       "envelope", "fall"}  # envelope and fall since ADR-084
    assert by["envelope"]["violated"] and by["fall"]["action"] == "report"
    assert by["stall"]["violated"] and by["stall"]["action"] == "reject" and rep["rejected"]
    assert any("stall" in x for x in rep["reject_reasons"]) and rep["margin"] < 0
    # the same rollout under a policy that only penalises: kept, but it costs fitness
    soft = safety_report(r, spec, lib, SafetyPolicy(actions={k: "penalise" for k in by}), compute_metrics(r))
    assert not soft["rejected"] and soft["penalty"] > 0
    # and a gentle sway of the same joints passes every constraint that rejects
    calm = _resolved({"repertoire": [{"name": "calm", "kind": "clip", "clip": "calm", "speed": [0.5, 0.5]}]},
                     [_sway("calm", 15.0)])
    r2 = run_rollout(cm, registry.get("controller", "behaviors")(calm), SimSettings(duration_s=3.0), lib)
    assert not safety_report(r2, spec, lib, SafetyPolicy())["rejected"]


def test_robust_evaluation_scores_over_seeds_and_rejects_unsafe_candidates(spec):
    from calflab.evolve.tasks import evaluate_candidate
    from calflab.fitness import presets

    preset = presets()["repertoire"].model_dump(mode="json")
    genome = genome_definition("feral_calf").default_genome().model_dump(mode="json")
    calm = _resolved({"repertoire": [{"name": "calm", "kind": "clip", "clip": "calm", "required": True,
                                      "speed": [0.5, 0.5]}, {"name": "idle", "kind": "idle"}]}, [_sway("calm", 15.0)])
    out = evaluate_candidate(_payload(genome, calm, preset))
    seeds = out["metrics"]["seeds"]
    assert [s["seed"] for s in seeds] == [0, 1, 2] and out["evals"] == 3
    assert len({s["scales"]["friction"] for s in seeds}) == 3  # each seed its own friction
    agg = out["metrics"]["aggregate"]
    assert agg["value"] == pytest.approx(agg["mean"] - agg["spread"], abs=1e-3) and out["fitness"] == pytest.approx(agg["value"], abs=1e-3)
    assert out["fitness_terms"]["imitation_required"]["value"] > 0  # the required clip played first
    assert out["metrics"]["required_clips"]["calm"]["tracking_rms_deg"] is not None
    assert "expressive_range_deg_s" in out["metrics"]["movement"] and out["metrics"]["safety_margin"] is not None
    # a clip that folds both carpi to their limit: the shoulder servos then hold the body above their rated torque
    # for most of a window (measured: about 70 %), which this stricter policy rejects. The inner loop can slow a clip
    # down (playback limits) and lower its amplitude a little, but not enough to keep the load down.
    lim = spec.joint("joint.fl.carpus").range_deg[1]
    press = MotionClip(id="press", name="press", fps=20, joints={j: [min(lim + 10, 5.0 * i) for i in range(80)]
                                                                for j in ("joint.fl.carpus", "joint.fr.carpus")})
    bad = _resolved({"repertoire": [{"name": "press", "kind": "clip", "clip": "press", "required": True}]}, [press])
    strict = {**preset, "evaluation": {**preset["evaluation"], "safety": {
        **preset["evaluation"]["safety"],
        "actions": {**preset["evaluation"]["safety"]["actions"], "servo_sustained": "reject"}}}}
    out = evaluate_candidate(_payload(genome, bad, strict))
    assert out.get("unsafe") and any("rated-torque" in x for x in out["unsafe"])
    assert [s["seed"] for s in out["metrics"]["seeds"]] == [0, 1, 2]  # every seed recorded, rejected or not


def test_playback_limits_are_the_inner_loop_and_stay_within_the_clip_report(spec):
    from calflab.behave.feasibility import clip_report
    from calflab.components import library
    from calflab.plugins import registry

    cls = registry.get("controller", "behaviors")
    fast = _sway("fast", 60.0, seconds=0.5)
    params = _resolved({"repertoire": [{"name": "fast", "kind": "clip", "clip": "fast"}, {"name": "idle", "kind": "idle"}]},
                       [fast])
    dims = cls.vector_dims_for(params, spec)
    assert [d.name for d in dims] == ["speed:fast", "amplitude:fast"]
    top = clip_report(fast, spec, library())["playable_speed"]
    assert top < 1.0 and dims[0].hi == pytest.approx(top)
    p = cls.params_from_vector_for(params, np.array([1.0, 0.5]), spec)
    e = p["repertoire"][0]
    assert e["speed"][1] == pytest.approx(top, abs=1e-3) and e["speed"][0] == pytest.approx(0.8 * top, abs=1e-3)
    assert e["amplitude"][1] == pytest.approx(0.65, abs=1e-3)
    assert np.allclose(cls.vector_from_params_for(p, spec), [1.0, 0.5], atol=1e-3)


@pytest.mark.slow
def test_a_tiny_repertoire_evolution_keeps_belts_fixed_and_records_seeds(tmp_path):
    from calflab.app import Lab
    from calflab.project.store import write_json
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    (project.path / "motions").mkdir(exist_ok=True)
    clip = _sway("calm", 15.0)
    write_json(project.path / "motions" / "calm.json", clip.model_dump(mode="json"))
    lab = Lab.open(project.path, create=False)
    try:
        lab.execute("set_controller", {"key": "behaviors", "params": {"repertoire": [
            {"name": "calm", "kind": "clip", "clip": "calm", "required": True, "speed": [0.5, 0.6]},
            {"name": "idle", "kind": "idle"}]}})
        fit = lab.state.graph.role("fitness")
        lab.execute("set_node_params", {"node": fit.id, "params": {"preset": "repertoire"}})
        est = lab.execute("estimate_evolve", {"params": {"generations": 1, "batch_size": 2, "inner_iterations": 0},
                                              "sim": {"duration_s": 2.0}})["result"]
        assert est["seeds"] == 3 and est["run"]["rollouts"] == 1 * 2 * 1 * 3 and est["run"]["cpu_s"] > 0
        assert est["small"]["generations"] == 2
        job = lab.run_evolve(params={"generations": 1, "batch_size": 2, "inner_iterations": 1, "inner_popsize": 2,
                                     "descriptor_x": "expressive_range", "descriptor_y": "safety_margin",
                                     "genes": ["femur_length", "tibia_length"], "seed": 1},
                             sim={"duration_s": 2.0, "record_hz": 25})
        done = lab.jobs.wait(job.id, 900)
        assert done.status == "done", done.error
        run_id = done.result["run_id"]
        cands = [json.loads(line) for line in (project.path / "runs" / run_id / "candidates.jsonl").read_text().splitlines()]
        start = lab.design().genome.values
        for c in cands:
            for k, v in c["genome"]["values"].items():
                if k.startswith("belt_"):
                    assert v == start[k]  # belts are fixed catalog genes
            if c["status"] not in ("infeasible", "failed"):
                assert [s["seed"] for s in c["metrics"]["seeds"]] == [0, 1, 2]
                assert "speed:calm" not in c["controller"]["params"]  # limits land in the entry's ranges
                calm = next(e for e in c["controller"]["params"]["repertoire"] if e["name"] == "calm")
                assert calm["speed"][1] <= 1.0
        archive = json.loads((project.path / "runs" / run_id / "archive.json").read_text())
        assert [a["key"] for a in archive["archive"]["axes"]] == ["expressive_range", "safety_margin"]
    finally:
        lab.close()
