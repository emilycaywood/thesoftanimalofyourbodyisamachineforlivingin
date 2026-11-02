"""Evolving the feral calf (ADR-070): belts are catalog ids held fixed, belt-bound geometry stays where every belt
passes, an infeasible body is rejected, never repaired."""

from __future__ import annotations

import pytest
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome


def genome(**values: object) -> Genome:
    d = genome_definition("feral_calf")
    return Genome(definition="feral_calf", version=d.version, values=d.complete({**d.defaults(), **values}))


@pytest.fixture()
def lab(tmp_path):
    from calflab.app import Lab
    from calflab.project.templates import create_project

    project = create_project(tmp_path / "feral", "feral_calf")
    lab = Lab.open(project.path, create=False)
    yield lab
    lab.close()


def test_belt_genes_cannot_be_evolved():
    from calflab.evolve.map_elites import EvolveProblem, MapElitesCMA

    d = genome_definition("feral_calf")
    belt = [g.id for g in d.genes if g.id.startswith("belt_")]
    assert d.not_evolvable(belt) == belt and not set(belt) & {g.id for g in d.evolvable()}
    assert "femur_length" in {g.id for g in d.evolvable()} and "spring_hock_k" in {g.id for g in d.evolvable()}
    opt = MapElitesCMA({"genes": ["femur_length", "belt_hock_length"]})
    problem = EvolveProblem(genome=genome().model_dump(), overrides=[], generator="feral_calf", generator_params={},
                            compile={}, sim={}, controller={"key": "feral_motion", "params": {}}, fitness={})
    with pytest.raises(ValueError, match="belt_hock_length"):
        opt.run(problem, None, lambda **_: None)  # type: ignore[arg-type]


def test_open_catalog_genes_take_any_id_and_the_build_checks_it():
    d = genome_definition("feral_calf")
    assert d.gene("belt_hock_length").coerce("GT2-2mm-394-C") == "GT2-2mm-394-C"
    with pytest.raises(ValueError, match="no-such-belt"):
        build_design(genome(belt_hock_length="no-such-belt"), [], "feral_calf", {})
    assert "belt_hock_length" not in {f["name"] for f in d.ui_schema()["fields"]}  # not in Form


def test_belt_bound_ranges_are_narrowed_where_a_belt_would_fail():
    from calflab.evolve.constraints import feasible_bounds

    d = genome_definition("feral_calf")
    genes = [d.gene(g) for g in ("femur_length", "tibia_length", "femur_angle", "rear_cannon_length")]
    b = feasible_bounds(genome(), [], "feral_calf", {}, None, genes, samples=17)
    assert set(b) == {"femur_length", "tibia_length", "femur_angle"}  # rear_cannon_length is not belt-bound
    assert b["tibia_length"]["min"] > 220 and b["tibia_length"]["narrowed"]  # the hock servo must fit on the tibia
    assert b["femur_length"]["min"] > 130
    assert b["femur_angle"]["max"] < 50  # the hock servo against the stifle belt
    for gene, r in b.items():
        lo = build_design(genome(**{gene: r["min"]}), [], "feral_calf", {}).spec.metadata["infeasible_by"]["belt"]
        hi = build_design(genome(**{gene: r["max"]}), [], "feral_calf", {}).spec.metadata["infeasible_by"]["belt"]
        assert lo == [] and hi == [], gene


def test_an_infeasible_candidate_is_rejected_before_it_is_simulated():
    from calflab.evolve.tasks import evaluate_candidate

    out = evaluate_candidate({"genome": genome(tibia_length=170).model_dump(), "generator": "feral_calf",
                              "generator_params": {}, "controller": {"key": "feral_motion", "params": {}},
                              "fitness": {"name": "x", "version": 1, "terms": []}})
    assert out["evals"] == 0 and any("hock" in r for r in out["infeasible"])


def test_jobs_get_the_project_catalog_inlined_and_documents_never_keep_it(lab):
    from calflab.mech.belts import catalog_files

    params = lab.job_generator_params(lab.state.graph)
    assert params["belt_catalog"] == catalog_files(lab.project.path)
    assert lab.state.graph.node("morphology").params.get("belt_catalog") is None
    inline = build_design(lab.design().genome, [], "feral_calf", params)
    assert inline.spec.metadata["feral"]["belt_catalog"]["digest"] == lab.design().spec.metadata["feral"]["belt_catalog"]["digest"]
    assert not any("repository's belt catalog" in w for w in inline.warnings)


def test_walk_parameters_are_a_bounded_vector():
    import numpy as np
    from calflab.plugins import load_plugins, registry

    load_plugins()
    cls = registry.get("controller", "feral_motion")
    dims = cls.vector_dims()  # type: ignore[attr-defined]
    assert "cycle_s" in [d.name for d in dims]
    x = cls.vector_from_params(cls.Params().model_dump())  # type: ignore[attr-defined]
    assert np.all((x >= 0) & (x <= 1))
    back = cls.params_from_vector(cls.Params().model_dump(), x)  # type: ignore[attr-defined]
    assert back["cycle_s"] == pytest.approx(4.0) and back["mode"] == "walk"


@pytest.mark.slow
def test_evolution_keeps_every_belt_as_it_is(lab):
    from calflab.mech.belts import BeltChoice

    start = {k: v for k, v in lab.state.graph.node("genome").params.items() if k.startswith("belt_")}
    params = {"generations": 2, "batch_size": 4, "inner_iterations": 0, "seed": 3,
              "genes": ["femur_length", "tibia_length", "femur_angle", "tibia_angle", "spring_stifle_k"]}
    job = lab.jobs.wait(lab.run_evolve(params=params, backend="inline", sim={"duration_s": 3.0}).id, timeout=900)
    assert job.status == "done", getattr(job, "error", None)
    rec = lab.registry.get_run(job.result["run_id"])
    assert rec.inputs["params"]["descriptor_x"] == "standing_height"  # the body's own evolve defaults
    assert rec.inputs["bounds"]["tibia_length"]["min"] > 220
    cands = lab.registry.list_candidates(rec.id)
    assert len(cands) == 8
    seen = set()
    for c in cands:
        values = c["genome"]["values"]
        assert {k: v for k, v in values.items() if k.startswith("belt_")} == start
        d = build_design(Genome.model_validate(c["genome"]), [], "feral_calf", {}, lab.project.path)
        for drive, r in d.spec.metadata["feral"]["belt_drives"].items():
            assert BeltChoice.model_validate(r["choice"]) == BeltChoice(
                system=start[f"belt_{drive}_system"], pulleys=start[f"belt_{drive}_pulleys"], length=start[f"belt_{drive}_length"])
            seen.add((drive, round(r["c_mm"], 9), round(r["servo_axis_from_driven_mm"], 9)))
        if c["status"] == "infeasible":
            assert c["error"]
    assert len(seen) == 2  # one C and one servo position per drive, the same in every candidate
