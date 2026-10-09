"""HTTP + websocket facade over the Lab."""

import json
import time

import pytest
from calflab.app import Lab
from calflab_server.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    lab = Lab.open(tmp_path / "proj")
    lab.execute("set_node_params", {"node": "sim", "params": {"duration_s": 1.0}})
    with TestClient(create_app(lab, watch_plugins=False)) as c:
        c.lab = lab
        yield c
    lab.close()


def wait_job(client, job_id, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise TimeoutError


def test_meta_plugins_and_schemas(client):
    assert client.get("/api/health").json()["ok"] is True
    meta = client.get("/api/meta").json()
    assert meta["units"] == {"length": "mm", "mass": "g", "angle": "deg"}
    assert [layer["name"] for layer in meta["layers"]][:2] == ["Structure", "Actuators"]
    plugins = client.get("/api/plugins").json()["plugins"]
    cpg = next(p for p in plugins["controller"] if p["key"] == "cpg")
    freq = next(f for f in cpg["schema"]["fields"] if f["name"] == "frequency")
    assert freq["ui"] == "slider" and freq["unit"] == "Hz" and freq["description"]
    assert any(p["stub"] for p in plugins["optimizer"])
    comps = client.get("/api/components").json()
    assert all(c["source"] for c in comps) and not all(c["verified"] for c in comps)
    types = {t["type"] for t in client.get("/api/graph/node-types").json()}
    assert {"genome:calf", "mjcf", "simulator:mujoco"} <= types


def test_commands_scene_undo_over_http(client):
    scene = client.get("/api/scene").json()
    assert scene["bodies"][0]["id"] == "trunk" and len(scene["support_polygon"]) == 4
    r = client.post("/api/commands/add_override", json={"target": "leg.fl.shank", "param": "length", "value": 195},
                    headers={"x-calflab-client": "web"})
    assert r.status_code == 200 and r.json()["changed"] == ["overrides"]
    assert client.get("/api/state").json()["overrides"][0]["source"] == "web"
    assert client.get("/api/history").json()["records"][-1]["client"] == "web"
    assert client.post("/api/undo").status_code == 200
    assert client.get("/api/state").json()["overrides"] == []

    bad = client.post("/api/commands/set_genes", json={"values": {"knee_drive": "magnets"}})
    assert bad.status_code == 400 and "error" in bad.json()
    assert client.post("/api/commands/nope", json={}).status_code == 400
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post("/api/analysis/system_id", json={}).status_code == 501


def test_websocket_broadcasts_edits_and_sim_frames(client):
    with client.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"
        client.post("/api/commands/set_genes", json={"values": {"trunk_length": 440}})
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "state.changed" and ev["changed"] == ["graph"]

        job_id = client.post("/api/commands/run_sim", json={}).json()["result"]["job"]
        seen = []
        while True:
            ev = json.loads(ws.receive_text())
            seen.append(ev["type"])
            if ev["type"] == "job.finished":
                break
        assert "sim.frames" in seen and "sim.done" in seen
    job = wait_job(client, job_id)
    run_id = job["result"]["run_id"]
    roll = client.get(f"/api/runs/{run_id}/rollout").json()
    assert len(roll["pos"]) == len(roll["t"]) and roll["scene"]["genome"]["values"]["trunk_length"] == 440
    assert client.get("/api/runs", params={"kind": "sim"}).json()[0]["id"] == run_id
    assert client.get("/api/graph").json()["status"]["metrics"]["status"] == "ok"
    out = client.get("/api/graph/nodes/metrics/output").json()
    assert out["outputs"]["metrics"]["speed_mps"] > 0

    tm = client.post("/api/analysis/torque_margin", json={}).json()
    assert tm["run_id"] == run_id and tm["rows"][0]["required_peak_nm"] is not None
    blender = client.get(f"/api/bridge/blender/rollout/{run_id}").json()
    assert blender["frames"] == len(roll["t"]) and "joint.fl.knee" in blender["joints"]


def test_export_job_and_file_download(client):
    job = wait_job(client, client.post("/api/commands/export", json={"exporter": "bom"}).json()["result"]["job"])
    assert job["status"] == "done", job
    rel = next(v for k, v in job["result"]["files"].items() if k.endswith(".csv"))
    assert "Dynamixel" in client.get(f"/api/files/{rel}").text
    assert client.get("/api/files/../../pyproject.toml").status_code in (403, 404)
    h = client.post("/api/analysis/harness", json={}).json()
    assert client.get(f"/api/files/{h['svg']}").status_code == 200


def test_journal_motions_and_bake_over_http(client):
    d = client.post("/api/commands/bake", json={"name": "http calf"}).json()["result"]["design"]
    assert client.get("/api/designs").json()[0]["id"] == d
    assert client.get(f"/api/designs/{d}").json()["spec"]["bodies"]
    e = client.post("/api/journal", json={"title": "Note", "body": f"calflab://design/{d}"}).json()
    got = client.get(f"/api/journal/{e['id']}").json()
    assert got["links"] == [{"kind": "design", "id": d}]
    cap = client.post("/api/captures", json={"data_url": "data:image/png;base64,iVBORw0KGgo=",
                                             "provenance": {"design": d}}).json()
    assert cap["provenance"]["design"] == d and "revision" in cap["provenance"]

    clip = {"name": "Head nod", "fps": 24, "joints": {"joint.head_pitch": [0, 5, 10, 5, 0]}}
    r = client.post("/api/motions", json=clip).json()
    assert r == {"id": "head-nod", "frames": 5, "duration_s": pytest.approx(5 / 24)}
    assert client.get("/api/motions").json()[0]["joints"] == ["joint.head_pitch"]
    bad = client.post("/api/motions", json={"name": "bad", "joints": {"a": [1, 2], "b": [1]}})
    assert bad.status_code == 400


def test_hops_endpoints(client):
    names = [e["name"] for e in client.get("/hops").json()]
    assert names == ["getdesign", "setgenomeparams", "runsim", "getmetrics", "baketorhino"]
    io = client.get("/hops/SetGenomeParams").json()
    assert [i["Name"] for i in io["Inputs"]] == ["names", "values"]

    def solve(pointer, **inputs):
        values = [
            {"ParamName": k, "InnerTree": {"{0}": [{"type": "x", "data": json.dumps(i)} for i in v]}}
            for k, v in inputs.items()
        ]
        out = client.post("/hops/solve", json={"pointer": pointer, "values": values}).json()["values"]
        return {v["ParamName"]: [json.loads(i["data"]) for i in v["InnerTree"]["{0}"]] for v in out}

    solve("setgenomeparams", names=["trunk_length", "neck_length"], values=[460, 180])
    d = solve("/hops/getdesign")
    assert json.loads(d["genome"][0])["trunk_length"] == 460 and d["mass_g"][0] > 3000
    assert client.lab.log.records[-1].client == "grasshopper"
    job = solve("runsim", run=[True])["job"][0]
    wait_job(client, job)
    m = solve("getmetrics", job=[job])
    assert m["status"] == ["done"] and json.loads(m["metrics"][0])["speed_mps"] > 0
    assert json.loads(solve("baketorhino")["build_list"][0])["objects"]
