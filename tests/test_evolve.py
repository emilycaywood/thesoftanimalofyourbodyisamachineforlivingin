"""Evolution: CMA-ES inner loop, MAP-Elites outer loop, lineage, registry."""

import pytest
from calflab.app import Lab, LabError
from calflab.compute.bundle import read_results, write_bundle
from calflab.compute.remote import CloudNotebook, RemoteSSH
from calflab.design import genome_definition
from calflab.evolve.tasks import evaluate_candidate
from calflab.fitness import preset
from calflab.plugins import Task, registry

SMALL = {"generations": 2, "batch_size": 3, "inner_iterations": 1, "inner_popsize": 4, "seed": 1}
SIM = {"duration_s": 1.5, "record_hz": 25}


def payload(**kw):
    g = genome_definition("calf").default_genome()
    base = {
        "genome": g.model_dump(),
        "controller": {"key": "cpg", "params": {}},
        "sim": SIM,
        "fitness": preset("walk").model_dump(),
        "descriptors": ["leg_length", "gait_frequency"],
        "inner": {"iterations": 2, "popsize": 4},
        "seed": 5,
    }
    base.update(kw)
    return base


def test_inner_cma_never_does_worse_than_the_start_and_is_deterministic():
    base = evaluate_candidate(payload(inner={"iterations": 0}))
    tuned = evaluate_candidate(payload())
    assert tuned["fitness"] >= base["fitness"]
    assert tuned["evals"] == 1 + 2 * 4
    assert tuned == evaluate_candidate(payload())
    assert set(tuned["descriptors"]) == {"leg_length", "gait_frequency"}
    assert tuned["descriptors"]["leg_length"] == 340


def test_fitness_preset_is_explicit_and_weighted():
    p = preset("walk")
    assert p.ref == "walk@1"
    r = p.evaluate({"speed_mps": 0.5, "survival": 1.0, "stability": 1.0, "cost_of_transport": 0.0,
                    "lateral_drift_m": 0.0, "foot_impact_mps": 0.0, "joint_limit_violation": 0.0})
    assert r["total"] == pytest.approx(sum(t.weight for t in p.terms))
    assert r["terms"]["forward_speed"] == {"value": 1.0, "weight": 1.0, "weighted": 1.0}


@pytest.fixture()
def lab(tmp_path):
    lab = Lab.open(tmp_path / "proj")
    yield lab
    lab.close()


def test_map_elites_run_records_lineage_and_archive(lab):
    seen = []
    lab.bus.subscribe(seen.append)
    r = lab.execute("run_evolve", {"params": SMALL, "backend": "inline", "sim": SIM})["result"]
    job = lab.jobs.wait(r["job"], timeout=300)
    assert job.status == "done", job.error
    run_id = job.result["run_id"]
    assert r["run_id"] == run_id

    rec = lab.registry.get_run(run_id)
    assert rec.kind == "evolve" and rec.status == "done" and rec.backend == "inline"
    assert rec.inputs["params"]["generations"] == 2 and rec.fitness["preset"]["name"] == "walk"
    assert rec.metrics["candidates"] == 6 and rec.metrics["evals"] == 6 * 5

    cands = lab.registry.list_candidates(run_id)
    assert len(cands) == 6
    gen0 = [c for c in cands if c["generation"] == 0]
    gen1 = [c for c in cands if c["generation"] == 1]
    assert all(c["parents"] == [] for c in gen0)
    ids0 = {c["id"] for c in gen0}
    assert all(c["parents"] and set(c["parents"]) <= ids0 for c in gen1), "children know their parents"
    lineage = lab.registry.lineage(gen1[0]["id"])
    assert lineage[-1]["id"] == gen1[0]["id"] and lineage[0]["generation"] == 0

    view = lab.evolve_view(run_id)
    assert len(view["history"]) == 2 and view["history"][-1]["elites"] >= 1
    axes = view["archive"]["axes"]
    assert [a["key"] for a in axes] == ["leg_length", "gait_frequency"]
    cell = view["archive"]["cells"][0]
    assert lab.registry.get_candidate(cell["candidate"])["cell"] == [cell["i"], cell["j"]]
    assert sum(e["type"] == "evolve.update" for e in seen) == 2
    assert lab.registry.check() == []

    # clicking a heatmap cell: replay the candidate without touching the document
    before = lab.scene()["genome"]["values"]
    sim = lab.jobs.wait(lab.simulate_candidate(cell["candidate"]).id)
    assert sim.status == "done", sim.error
    assert lab.registry.get_run(sim.result["run_id"]).parent == cell["candidate"]
    assert lab.scene()["genome"]["values"] == before

    # adopting it is an undoable document edit
    cand = gen0[1]  # a mutated body (gen0[0] is the unchanged starting design)
    lab.execute("adopt_candidate", {"id": cand["id"]})
    assert lab.scene()["genome"]["values"] == cand["genome"]["values"]
    assert lab.state.graph.role("controller").params["frequency"] == pytest.approx(cand["controller"]["params"]["frequency"])
    lab.undo()
    assert lab.scene()["genome"]["values"] == before


def test_evolution_starts_from_the_document_and_says_so(lab):
    lab.execute("add_override", {"target": "leg.fl.shank", "param": "length", "value": 200.0})
    job = lab.jobs.wait(lab.run_evolve(params=SMALL, backend="inline", sim=SIM).id, timeout=300)
    rec = lab.registry.get_run(job.result["run_id"])
    assert rec.inputs["start"] == {"source": "document", "revision": lab.revision} and rec.parent is None
    assert [(o["target"], o["param"], o["value"]) for o in rec.overrides] == [("leg.fl.shank", "length", 200.0)]
    cands = lab.registry.list_candidates(rec.id)
    assert cands[0]["genome"]["values"] == rec.genome["values"], "the first candidate is the starting design itself"
    # the override is not a gene: every candidate keeps the long front-left shank, whatever shank_length evolves to
    for c in cands:
        params = lab.candidate_scene(c["id"])["elements"]
        assert params["leg.fl.shank"]["params"]["length"]["value"] == 200.0
        assert params["leg.fr.shank"]["params"]["length"]["value"] == pytest.approx(c["genome"]["values"]["shank_length"])


def test_load_a_baked_design_and_evolve_from_it(lab):
    gdef = genome_definition("calf")
    lab.execute("set_genes", {"values": {"trunk_length": 460, "front_knee_forward": True}})
    lab.execute("add_override", {"target": "leg.fl.shank", "param": "length", "value": 200.0})
    lab.execute("set_node_params", {"node": lab.state.graph.role("controller").id, "params": {"frequency": 2.1}})
    baked = lab.bake("long fl shank")
    assert baked.id == "long-fl-shank-v001"
    lab.execute("clear_overrides")
    lab.execute("reset_genes")
    lab.execute("set_node_params", {"node": lab.state.graph.role("controller").id, "params": {"frequency": 1.2}})
    doc_genes = dict(lab.state.graph.role("genome").params)

    # ---- evolve from the design without touching the document
    r = lab.execute("run_evolve", {"params": SMALL, "backend": "inline", "sim": SIM, "design": baked.id})["result"]
    job = lab.jobs.wait(r["job"], timeout=300)
    assert job.status == "done", job.error
    rec = lab.registry.get_run(job.result["run_id"])
    assert rec.parent == baked.id and rec.inputs["start"] == {"source": "design", "design": baked.id}
    assert rec.genome["values"]["trunk_length"] == 460 and rec.genome["values"]["front_knee_forward"] is True
    assert rec.controller["params"]["frequency"] == pytest.approx(2.1), "the gait comes from the design too"
    assert [o["target"] for o in rec.overrides] == ["leg.fl.shank"]
    assert lab.state.graph.role("genome").params == doc_genes and lab.state.overrides == []
    assert {r["id"]: r["parent"] for r in lab.registry.list_runs("evolve")}[rec.id] == baked.id
    cands = lab.registry.list_candidates(rec.id)
    assert cands[0]["genome"]["values"] == gdef.complete(baked.genome["values"])
    assert all(c["genome"]["values"]["front_knee_forward"] is True for c in cands), "genes that do not evolve stay"

    # ---- a candidate is shown and replayed as it was evaluated, not with the document's overrides
    child = next(c for c in cands if c["generation"] == 1)
    assert lab.candidate_scene(child["id"])["elements"]["leg.fl.shank"]["params"]["length"]["override"]
    sim = lab.jobs.wait(lab.simulate_candidate(child["id"]).id)
    assert sim.status == "done", sim.error
    assert [o["target"] for o in lab.registry.get_run(sim.result["run_id"]).overrides] == ["leg.fl.shank"]

    # ---- its genes, as differences from the working design, its parent and another candidate
    view = lab.candidate_genes(child["id"], compare=cands[1]["id"])
    assert view["parent"] == child["parents"][0] and view["compare"] == cands[1]["id"]
    rows = {g["gene"]: g for g in view["genes"]}
    assert set(rows) == {g.id for g in gdef.genes}
    trunk = rows["trunk_length"]
    assert trunk["value"] == child["genome"]["values"]["trunk_length"] and trunk["current"] == doc_genes["trunk_length"]
    assert trunk["current_delta"] == pytest.approx(trunk["value"] - doc_genes["trunk_length"]) and trunk["evolved"]
    parent = lab.registry.get_candidate(child["parents"][0])["genome"]["values"]
    assert trunk["parent_delta"] == pytest.approx(trunk["value"] - parent["trunk_length"])
    assert trunk["compare"] == cands[1]["genome"]["values"]["trunk_length"]
    knee = rows["front_knee_forward"]
    assert knee["current_differs"] and knee["current_delta"] is None and not knee["parent_differs"] and not knee["evolved"]
    assert not rows["act_knee"]["differs"]
    assert view["overrides"][0]["target"] == "leg.fl.shank", "fixed parameters are listed beside the genes"
    start = lab.candidate_genes(cands[1]["id"])
    assert start["parent"] == "start" and start["compare"] is None
    assert {g["gene"]: g for g in start["genes"]}["trunk_length"]["parent"] == 460

    # ---- adopting brings the overrides it was evaluated with (the document had none)
    out = lab.execute("adopt_candidate", {"id": child["id"]})["result"]
    assert out["overrides_replaced"] is True
    assert [(o.target, o.value) for o in lab.state.overrides] == [("leg.fl.shank", 200.0)]
    assert lab.scene()["genome"]["values"] == child["genome"]["values"]
    assert lab.execute("adopt_candidate", {"id": cands[2]["id"]})["result"]["overrides_replaced"] is False
    lab.undo()
    lab.undo()
    assert lab.state.overrides == [] and lab.state.graph.role("genome").params == doc_genes

    # ---- load the design into the working document; one undo brings the document back
    out = lab.execute("load_design", {"id": baked.id})["result"]
    assert out == {"design": baked.id, "overrides": 1}
    scene = lab.scene()
    assert scene["genome"]["values"]["trunk_length"] == 460 and scene["genome"]["values"]["front_knee_forward"] is True
    assert scene["elements"]["leg.fl.shank"]["params"]["length"]["value"] == 200.0
    assert lab.state.graph.role("controller").params["frequency"] == pytest.approx(2.1)
    assert lab.design().spec.total_mass_g() == pytest.approx(baked.mass_g)
    lab.undo()
    assert lab.state.overrides == [] and lab.state.graph.role("genome").params == doc_genes
    with pytest.raises(LabError, match="No design"):
        lab.execute("load_design", {"id": "no-such-v001"})
    with pytest.raises(LabError, match="No design"):
        lab.run_evolve(params=SMALL, backend="inline", design="no-such-v001")


def test_evolution_is_reproducible(lab):
    ids = []
    for _ in range(2):
        job = lab.jobs.wait(lab.run_evolve(params=SMALL, backend="inline", sim=SIM).id, timeout=300)
        ids.append(job.result["run_id"])
    a, b = (lab.registry.list_candidates(i) for i in ids)
    assert [c["fitness"] for c in a] == [c["fitness"] for c in b]


@pytest.mark.slow
def test_local_process_pool_gives_the_same_result_as_inline(lab):
    try:
        out = {}
        for backend in ("inline", "local"):
            job = lab.jobs.wait(lab.run_evolve(params=SMALL, backend=backend, sim=SIM).id, timeout=600)
            assert job.status == "done", job.error
            out[backend] = [c["fitness"] for c in lab.registry.list_candidates(job.result["run_id"])]
        assert out["inline"] == out["local"]
    finally:
        registry.get("compute_backend", "local").shutdown_all()


def test_stub_backends_refuse_clearly(lab):
    with pytest.raises(LabError, match="not available"):
        lab.run_evolve(params=SMALL, backend="remote_ssh")
    with pytest.raises(LabError, match="not implemented"):
        lab.run_evolve(optimizer="ppo")


def test_job_bundle_roundtrip_and_remote_plan(tmp_path):
    tasks = [Task(fn="calflab.plugins.contracts:contract_echo", payload={"x": i}) for i in range(3)]
    bundle = write_bundle(tasks, tmp_path / "job.zip", {"note": "t"})
    import zipfile

    names = zipfile.ZipFile(bundle).namelist()
    assert {"job.json", "run_job.py", "requirements.txt"} <= set(names)
    assert "src/calflab/compute/worker.py" in names and "config/genes/calf.yaml" in names

    (tmp_path / "results.jsonl").write_text('{"id": "1", "result": {"echo": 1}}\n{"id": "0", "result": {"echo": 0}}\n')
    res = read_results(tmp_path / "results.jsonl", 3)
    assert res[0] == {"echo": 0} and res[1] == {"echo": 1} and "error" in res[2]

    ssh = RemoteSSH({"host": "gpu.school.edu", "user": "me"})
    plan = ssh.commands("job1", bundle)
    assert plan["upload"][:1] == ["scp"] and plan["upload"][-1] == "me@gpu.school.edu:~/calflab_jobs/job1/job.zip"
    assert "run_job.py" in plan["run"][-1]

    z, nb = CloudNotebook().export_bundle(tasks, tmp_path / "cloud", "train")
    assert z.is_file() and '"nbformat": 4' in nb.read_text(encoding="utf-8")
