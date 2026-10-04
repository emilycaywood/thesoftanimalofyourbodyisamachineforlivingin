"""Lab session: commands, overrides, undo/redo, bake, simulation jobs, registry."""

import json

import pytest
from calflab.app import Lab, LabError
from calflab.project import Project


@pytest.fixture()
def lab(tmp_path):
    lab = Lab.open(tmp_path / "proj", name="test")
    lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
    yield lab
    lab.close()


def events(lab):
    seen = []
    lab.bus.subscribe(seen.append)
    return seen


def test_project_layout_and_text_formats(lab):
    p = lab.project.path
    for name in ("project.calflab.json", "commands.jsonl", "index.sqlite", "runs", "designs", "journal", "assets", "exports"):
        assert (p / name).exists(), name
    doc = json.loads((p / "project.calflab.json").read_text(encoding="utf-8"))
    assert doc["state"]["graph"]["roles"]["design"] == "morphology"


def test_set_genes_updates_scene_and_is_undoable(lab):
    seen = events(lab)
    before = lab.scene()
    lab.execute("set_genes", {"values": {"trunk_length": 500}})
    after = lab.scene()
    assert after["mass"]["total_g"] > before["mass"]["total_g"]
    assert after["genome"]["values"]["trunk_length"] == 500
    assert seen[-1]["type"] == "state.changed" and seen[-1]["changed"] == ["graph"]
    lab.undo()
    assert lab.scene()["mass"]["total_g"] == before["mass"]["total_g"]
    lab.redo()
    assert lab.scene()["genome"]["values"]["trunk_length"] == 500
    with pytest.raises(LabError, match="Nothing to redo"):
        lab.redo()


def test_gene_values_are_validated(lab):
    lab.execute("set_genes", {"values": {"trunk_length": 99999}})
    assert lab.scene()["genome"]["values"]["trunk_length"] == 560  # clamped to the gene range
    with pytest.raises(LabError):
        lab.execute("set_genes", {"values": {"knee_drive": "magnets"}})
    with pytest.raises(LabError, match="No command"):
        lab.execute("no_such_command")


def test_slider_drag_coalesces_into_one_undo_step(lab):
    start = lab.log.cursor
    for v in (430, 440, 450, 460):
        lab.execute("set_genes", {"values": {"trunk_length": v}}, client="web")
    assert lab.log.cursor == start + 1
    lab.end_gesture()
    lab.execute("set_genes", {"values": {"trunk_length": 470}}, client="web")
    assert lab.log.cursor == start + 2
    lab.undo()
    assert lab.scene()["genome"]["values"]["trunk_length"] == 460
    lab.undo()
    assert lab.scene()["genome"]["values"]["trunk_length"] == 420


def test_override_lifecycle_gumball_edit(lab):
    """Gumball edit of one segment -> override -> toggle -> internalize / remove."""
    r = lab.execute("add_override", {"target": "leg.fl.shank", "param": "length", "value": 200})
    oid = r["result"]["override"]
    el = lab.scene()["elements"]["leg.fl.shank"]["params"]["length"]
    assert (el["value"], el["parametric"], el["override"], el["gene"]) == (200, 170, oid, "shank_length")
    assert lab.scene()["elements"]["leg.fr.shank"]["params"]["length"]["override"] is None
    assert lab.state_view()["overrides"][0]["id"] == oid

    lab.execute("toggle_override", {"id": oid})
    assert lab.scene()["elements"]["leg.fl.shank"]["params"]["length"]["value"] == 170
    lab.execute("toggle_override", {"id": oid, "enabled": True})

    lab.execute("internalize_override", {"id": oid})
    s = lab.scene()
    assert s["genome"]["values"]["shank_length"] == 200
    assert lab.state_view()["overrides"] == []
    assert s["elements"]["leg.fr.shank"]["params"]["length"]["value"] == 200, "the gene drives all four legs"

    lab.undo()  # internalize is one undoable step
    assert lab.state_view()["overrides"][0]["id"] == oid
    lab.execute("remove_override", {"id": oid})
    assert lab.scene()["elements"]["leg.fl.shank"]["params"]["length"]["value"] == 170


def test_bound_drag_drives_the_gene_instead(lab):
    lab.execute("add_override", {"target": "leg.fl.thigh", "param": "length", "value": 190, "bound": True})
    assert lab.state_view()["overrides"] == []
    assert lab.scene()["genome"]["values"]["thigh_length"] == 190
    with pytest.raises(LabError, match="not driven by a gene"):
        lab.execute("add_override", {"target": "leg.fl.thigh", "param": "offset_x", "value": 5, "bound": True})


def test_state_and_undo_stack_survive_reopen(tmp_path):
    lab = Lab.open(tmp_path / "p")
    lab.execute("set_genes", {"values": {"neck_length": 200}})
    lab.end_gesture()
    lab.execute("add_override", {"target": "head", "param": "length", "value": 210})
    lab.close()
    lab2 = Lab.open(tmp_path / "p", create=False)
    assert lab2.scene()["genome"]["values"]["neck_length"] == 200
    assert len(lab2.state.overrides) == 1
    lab2.undo()
    lab2.undo()
    assert lab2.scene()["genome"]["values"]["neck_length"] == 160
    assert lab2.state.overrides == []
    lab2.close()


def test_bake_is_versioned_and_immutable(lab):
    a = lab.execute("bake", {"name": "First calf", "note": "baseline"})["result"]
    lab.execute("set_genes", {"values": {"trunk_length": 480}})
    b = lab.execute("bake", {"name": "First calf"})["result"]
    assert (a["design"], b["design"]) == ("first-calf-v001", "first-calf-v002")
    d1 = lab.registry.get_design("first-calf-v001")
    assert d1.genome["values"]["trunk_length"] == 420 and d1.note == "baseline"
    assert d1.spec["bodies"] and d1.graph["nodes"] and d1.code_version
    with pytest.raises(FileExistsError):
        lab.registry.save_design(d1)
    assert [d["id"] for d in lab.registry.list_designs()] == ["first-calf-v002", "first-calf-v001"]
    assert len(lab.registry.list_runs("bake")) == 2


def test_graph_commands(lab):
    r = lab.execute("add_node", {"type": "slider", "x": 10, "y": 20, "params": {"value": 3, "max": 5}})
    sid = r["result"]["node"]
    lab.execute("add_node", {"type": "gene_set", "id": "gs", "params": {"gene": "trunk_width"}})
    lab.execute("connect", {"source": sid, "source_socket": "value", "target": "gs", "target_socket": "value"})
    with pytest.raises(LabError, match="Cannot connect"):
        lab.execute("connect", {"source": sid, "source_socket": "value", "target": "gs", "target_socket": "genome"})
    lab.execute("connect", {"source": "genome", "source_socket": "genome", "target": "gs", "target_socket": "genome"})
    lab.execute("connect", {"source": "gs", "source_socket": "genome", "target": "morphology", "target_socket": "genome"})
    with pytest.raises(LabError, match="cycle"):
        lab.execute("connect", {"source": "gs", "source_socket": "genome", "target": "gs", "target_socket": "genome"})
    lab.execute("set_node_params", {"node": sid, "params": {"value": 180, "max": 300}})
    assert lab.scene()["genome"]["values"]["trunk_width"] == 180
    view = lab.graph_view()
    assert view["status"]["gs"]["status"] == "ok" and view["status"]["sim"]["status"] == "stale"
    assert lab.node_output("mass")["outputs"]["mass"] > 0

    r = lab.execute("cluster_nodes", {"ids": [sid, "gs"], "label": "Width driver"})
    assert lab.scene()["genome"]["values"]["trunk_width"] == 180, "a cluster behaves like its contents"
    with pytest.raises(LabError, match="cannot be clustered"):
        lab.execute("cluster_nodes", {"ids": ["genome"]})
    lab.execute("remove_nodes", {"ids": [r["result"]["cluster"]]})
    assert lab.graph_view()["status"]["morphology"]["status"] == "error"
    lab.execute("reset_graph")
    assert lab.graph_view()["status"]["morphology"]["status"] == "ok"


def test_layers(lab):
    lab.execute("set_layer", {"layer": "Skin", "visible": False})
    assert lab.scene()["layers"]["Skin"]["visible"] is False
    with pytest.raises(LabError):
        lab.execute("set_layer", {"layer": "Nope", "visible": False})


def test_sim_job_streams_poses_and_records_a_run(lab):
    seen = events(lab)
    job = lab.jobs.wait(lab.execute("run_sim")["result"]["job"])
    assert job.status == "done", job.error
    run_id = job.result["run_id"]
    types = [e["type"] for e in seen]
    assert "sim.started" in types and "sim.frames" in types and "sim.done" in types
    frames = [e for e in seen if e["type"] == "sim.frames"]
    started = next(e for e in seen if e["type"] == "sim.started")
    assert len(frames[0]["pos"][0]) == 3 * len(started["body_ids"])
    assert 300 < frames[0]["pos"][0][2] < 450, "poses are streamed in mm"

    rec = lab.registry.get_run(run_id)
    assert rec.kind == "sim" and rec.git_hash and rec.versions["mujoco"] and rec.seed == 0
    assert rec.genome["values"]["trunk_length"] == 420
    assert rec.fitness["preset"]["name"] == "walk" and "total" in rec.fitness["result"]
    assert rec.metrics["speed_mps"] > 0
    for rel in rec.artifacts.values():
        assert (lab.project.path / rel).is_file()

    payload = lab.rollout_payload(run_id)
    assert len(payload["t"]) == len(payload["pos"]) == len(payload["series"]["t"])
    assert payload["scene"]["bodies"][0]["id"] == "trunk"

    again = lab.jobs.wait(lab.run_sim().id)
    assert again.result == {"run_id": run_id, "cached": True, "metrics": rec.metrics}
    assert len(lab.registry.list_runs("sim")) == 1
    assert lab.graph_view()["status"]["fitness"]["status"] == "ok"


def test_registry_integrity_and_rebuild(lab):
    job = lab.jobs.wait(lab.run_sim().id)
    lab.execute("bake", {"name": "x"})
    assert lab.registry.check() == []
    counts = lab.registry.rebuild()
    assert counts["runs"] == 2 and counts["designs"] == 1
    assert lab.registry.check() == []
    rec = lab.registry.get_run(job.result["run_id"])
    (lab.project.path / rec.artifacts["rollout"]).unlink()
    assert any("rollout" in p for p in lab.registry.check())


def test_job_failure_is_reported_not_raised(lab):
    lab.execute("remove_nodes", {"ids": ["controller"]})
    with pytest.raises(LabError):
        lab.run_sim()
    lab.undo()

    def boom(ctx):
        raise RuntimeError("kaput")

    job = lab.jobs.wait(lab.jobs.submit("test", "boom", boom).id)
    assert job.status == "failed" and "kaput" in job.error
    retry = lab.jobs.wait(lab.jobs.retry(job.id).id)
    assert retry.status == "failed" and retry.retry_of == job.id


def test_journal_entries_link_to_runs_and_designs(lab):
    d = lab.execute("bake", {"name": "j"})["result"]["design"]
    e = lab.journal.save("First walk", f"It walks. See calflab://design/{d}.", tags=["gait"])
    assert lab.journal.get(e.id).links() == [{"kind": "design", "id": d}]
    assert lab.journal.list()[0]["title"] == "First walk"
    png = "data:image/png;base64,iVBORw0KGgo="
    cap = lab.journal.add_capture(png, {"revision": lab.revision, "design": d})
    assert (lab.project.path / cap["path"]).is_file() and cap["provenance"]["design"] == d
    assert lab.journal.captures()[0]["id"] == cap["id"]


def test_project_refuses_newer_schema(tmp_path):
    lab = Lab.open(tmp_path / "p")
    lab.close()
    f = tmp_path / "p" / "project.calflab.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["schema_version"] = 999
    f.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="newer"):
        Project.open(tmp_path / "p")


def test_documents_saved_before_the_front_knee_gene_keep_backward_knees(tmp_path):
    """Forward front knees are the default for new projects only: a document
    whose genome does not mention the gene was made with backward ones."""
    from calflab.project.store import PROJECT_FILE, read_json, write_json

    lab = Lab.open(tmp_path / "p")
    assert lab.scene()["genome"]["values"]["front_knee_forward"] is True
    lab.close()
    f = tmp_path / "p" / PROJECT_FILE
    data = read_json(f)
    genome = next(n for n in data["state"]["graph"]["nodes"] if n["type"] == "genome:calf")
    del genome["params"]["front_knee_forward"]
    write_json(f, data)
    lab = Lab.open(tmp_path / "p")
    try:
        scene = lab.scene()
        assert scene["genome"]["values"]["front_knee_forward"] is False
        assert next(j["rest_deg"] for j in scene["joints"] if j["id"] == "joint.fl.knee") < 0
        lab.execute("set_genes", {"values": {"trunk_length": 430}})  # editing another gene does not flip it
        assert lab.scene()["genome"]["values"]["front_knee_forward"] is False
        lab.execute("reset_genes")  # asking for the defaults does
        assert lab.scene()["genome"]["values"]["front_knee_forward"] is True
    finally:
        lab.close()


def test_reset_node_params_restores_the_default_gait(lab):
    cid = lab.state.graph.role("controller").id
    defaults = dict(lab.state.graph.role("controller").params)
    lab.execute("set_node_params", {"node": cid, "params": {"frequency": 3.1, "gait": "walk"}})
    out = lab.execute("reset_node_params", {"node": "controller"})["result"]  # by pipeline role
    assert out["node"] == cid and lab.state.graph.role("controller").params == defaults
    lab.undo()
    assert lab.state.graph.role("controller").params["frequency"] == 3.1
    with pytest.raises(LabError, match="No node"):
        lab.execute("reset_node_params", {"node": "nope"})

