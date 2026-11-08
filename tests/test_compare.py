"""Group replays for compare.html (ADR-106): matching own behaviours across bodies, badges and the manifest."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from calflab.app import compare as cmp

B, R7 = "B-evolve", "R7-evolve"


# ---------------------------------------------------------------------------------------------- pure helpers
def _cand(cid: str, parents: list[str] | None = None, cell: list[int] | None = None, **kw: Any) -> dict[str, Any]:
    return {"id": cid, "parents": parents or [], "cell": cell or [0, 0], **kw}


def test_origin_follows_the_first_parent_back_to_a_start_vector():
    cands = {c["id"]: c for c in [
        _cand("run-g000-000"), _cand("run-g000-001"), _cand("run-g000-004"),  # 4 % 3 -> generator 1
        _cand("run-g001-000", ["run-g000-004", "run-g000-000"]),  # the first parent is the one mutated
        _cand("run-g002-007", ["run-g001-000"]),
    ]}
    assert cmp.origin_index("run-g000-001", cands, 3) == 1
    assert cmp.origin_index("run-g000-004", cands, 3) == 1
    assert cmp.origin_index("run-g002-007", cands, 3) == 1
    assert cmp.origin_index("run-g002-007", cands, 0) is None  # no start vectors: nothing to name
    orphan = {"run-g003-001": _cand("run-g003-001")}
    assert cmp.origin_index("run-g003-001", orphan, 3) is None


def test_matching_prefers_the_same_generator_then_the_same_or_nearest_cell():
    cells = [{"candidate": "a", "cell": [5, 5], "origin": 2}, {"candidate": "b", "cell": [1, 1], "origin": 0},
             {"candidate": "c", "cell": [2, 3], "origin": 0}]
    got, how = cmp.match_cell(2, [1, 1], cells, 2)  # same generator wins over a cell further away
    assert got["candidate"] == "a" and how == "same generator, other cell"
    got, how = cmp.match_cell(0, [2, 4], cells, 2)  # several of that generator: the nearest cell
    assert got["candidate"] == "c" and how == "same generator, other cell"
    got, how = cmp.match_cell(0, [1, 1], cells, 2)
    assert got["candidate"] == "b" and how == "same generator"
    got, how = cmp.match_cell(7, [1, 1], cells, 2)
    assert got["candidate"] == "b" and how == "same cell"
    got, how = cmp.match_cell(7, [3, 4], cells, 2)
    assert got["candidate"] == "c" and how == "nearest cell (1 away)"
    got, how = cmp.match_cell(7, [9, 0], cells, 2)
    assert got is None and how == "no matching behaviour"
    assert cmp.match_cell(None, [1, 1], [], 2) == (None, "no matching behaviour")


def test_badges_and_the_limit_that_stopped_a_play():
    assert cmp.badge(True, 0.32, 0.1) == "within"
    assert cmp.badge(True, 0.05, 0.1) == "near"
    assert cmp.badge(False, -0.2, 0.1) == "over"
    assert cmp.badge(None, None, 0.1) is None
    joints = {"fl.carpus": {"speed": 0.9, "belt": 1.4}, "hl.hip_abd": {"torque": 1.2}}
    assert cmp.stopped_by({"within": False}, joints) == "fl.carpus sustained belt tension"
    assert cmp.stopped_by({"within": True}, joints) is None
    assert cmp.stopped_by({"within": False, "violations": ["fell"]}, {}) == "fell"


def test_screen_names_and_the_body_line():
    assert cmp.slowest_trot([0.4, 0.45, 0.5, 0.6, 0.8], [0.5, 1.0, 1.5, 2.0]) == "trot 0.8/0.5"
    assert cmp.trot_label("trot 0.4/2") == "trot 0.4 s / stride 2.0"
    line = cmp.body_line({"held": 23, "trot_mm_s": 0.0, "lie_rise": -1.44, "cost": 1.58})
    assert line == "23 held · trot - mm/s · lie_rise -1.44 · cost 1.58"
    assert cmp.play_key("r12", "g", "run", "screen:walk", 0) == cmp.play_key("r12", "g", "run", "screen:walk", 0)
    assert cmp.play_key("r12", "g", "run", "screen:walk", 0) != cmp.play_key("r12", "g", "run", "screen:walk", 1)


# ---------------------------------------------------------------------------------------------- the manifest
class FakeRegistry:
    """Just what ``calflab.app.compare`` reads: two Stage C runs seeded with three R7 generators."""

    def __init__(self, root: Path):
        self.root = root
        hw = {"trot_cycles_s": [0.4, 0.8], "trot_strides": [0.5, 2.0], "screen_extra": ["walk", "turn", "lie_rise"],
              "performances": [{"label": "R7-calm", "ref": f"{R7}:g000-000"}, {"label": "R6c-x", "ref": "R6:g001-001"}]}
        self.runs = {
            B: SimpleNamespace(id=B, fitness={"preset": {"evaluation": {"hardware": hw}}}, inputs={}),
            R7: SimpleNamespace(id=R7, inputs={}),
        }
        self.cands: dict[str, list[dict[str, Any]]] = {R7: [
            {"id": f"{R7}-g000-000", "metrics": {"within_limits": True}},
            {"id": f"{R7}-g000-001", "metrics": {"within_limits": False}},
            {"id": f"{R7}-g000-002", "metrics": {"within_limits": True}},
            {"id": f"{R7}-g003-004", "metrics": {"within_limits": True}},
        ]}
        self.titles = {}
        # body A: descendants of generators 0 and 1; body B: only generator 2, far away in the archive
        for rid, body, safe in (("CA", "A", [("g000-000", [], [1, 5]), ("g001-002", ["CA-g000-004"], [6, 7])]),
                                ("CB", "B", [("g000-002", [], [9, 0])])):
            cs = [{"id": f"{rid}-{s}", "parents": p, "cell": c, "controller": {"key": "interpreted", "params": {}},
                   "descriptors": {"quantity_of_motion": 1.5 * c[0] + 0.7, "tempo_regularity": 0.1 * c[1] + 0.05}}
                  for s, p, c in safe]
            cs.append({"id": f"{rid}-g000-004", "parents": [], "cell": [0, 0], "controller": {}, "descriptors": {}})
            self.cands[rid] = cs
            self.runs[rid] = SimpleNamespace(id=rid, inputs={"params": {"start_vectors": [[0.0]] * 3}})
            self.titles[rid] = f"R12 Stage C {body}"
            d = root / rid
            d.mkdir(parents=True)
            (d / "archive.json").write_text(json.dumps({"archive": {"cells": [
                {"candidate": c["id"], "within_limits": True} for c in cs[:-1]]}}), encoding="utf-8")
        self.stored: dict[str, Any] = {}

    def list_runs(self, kind=None, limit=200):
        return [{"id": r, "title": t, "status": "done"} for r, t in self.titles.items()]

    def get_run(self, rid):
        return self.runs[rid]

    def list_candidates(self, rid):
        return self.cands[rid]

    def run_dir(self, rid):
        return self.root / rid

    def find_run_by_key(self, key, kind="sim"):
        return self.stored.get(key)


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    spec = cmp.CompareSet(key="t", title="test", stage_b_run=B, r7_run=R7, bodies=["A", "B"], labels={"A": "body A"})
    monkeypatch.setitem(cmp.SETS, "t", spec)
    cmp._PLAN_CACHE.pop("t", None)
    return SimpleNamespace(registry=FakeRegistry(tmp_path))


def test_manifest_groups_matches_and_badges(fake):
    m = cmp.manifest(fake, "t")
    assert [b["label"] for b in m["bodies"]] == ["body A", "B"]
    groups = {g["key"]: g for g in m["groups"]}
    assert [i["label"] for i in groups["screen"]["items"]] == [
        "lie_rise", "walk", "turn", "trot 0.4 s / stride 2.0", "slowest trot (0.8 s / stride 0.5)"]
    assert [i["label"] for i in groups["shared"]["items"]] == ["R7-calm", "R6c-x"]
    own = {i["key"]: i for i in groups["own"]["items"]}
    # three distinct (generator, cell) items; generator names come from the shared labels where R7 has one
    assert set(own) == {"own:0:1-5", "own:1:6-7", "own:2:9-0"}
    assert own["own:0:1-5"]["label"] == "from R7-calm · cell 1,5"
    assert own["own:2:9-0"]["label"].startswith("from R7 g003-004")
    a, b = own["own:0:1-5"]["cells"]
    assert a["match"] == "same generator" and "g000-000" in a["playing"]
    assert b["empty"] and b["message"] == "no matching behaviour" and b["seeds"] == []
    # body A has no descendant of generator 2 and nothing within two cells of (9, 0)
    assert own["own:2:9-0"]["cells"][0]["empty"]
    assert own["own:2:9-0"]["cells"][1]["match"] == "same generator"
    # nothing stored: every playable cell lists its three seeds as missing
    assert m["stored"] == 0 and m["missing"] == (5 + 2) * 2 * 3 + 3 * 3
    # store one play: the manifest finds it by its key and gives its badge and limit
    key = cmp.play_key("t", "A", "CA", "screen:walk", 1)
    fake.registry.stored[key] = SimpleNamespace(id="sim-1", metrics={"within_limits": False, "safety_margin": -0.12,
                                                                      "stopped_by": "hl.hip_abd sustained servo torque"})
    m = cmp.manifest(fake, "t")
    walk = next(i for g in m["groups"] for i in g["items"] if i["key"] == "screen:walk")
    s1 = walk["cells"][0]["seeds"][1]
    assert s1 == {"seed": 1, "run": "sim-1", "badge": "over", "margin": -0.12,
                  "limit": "hl.hip_abd sustained servo torque", "text": "over -0.12", "href": "/?replay=sim-1"}
    assert m["stored"] == 1


def test_route_answers_404_for_an_unknown_set_or_missing_runs(tmp_path):
    from calflab.app import Lab
    from calflab_server.app import create_app
    from fastapi.testclient import TestClient

    lab = Lab.open(tmp_path / "proj")
    try:
        with TestClient(create_app(lab, watch_plugins=False)) as c:
            assert c.get("/api/compare/nope").status_code == 404
            r = c.get("/api/compare/r12")  # a fresh project has none of R12's runs
            assert r.status_code == 404 and "No run" in r.json()["detail"]
    finally:
        lab.close()


PROJECT = Path(__file__).resolve().parents[1] / "projects" / "robot-calf-final"


@pytest.mark.skipif(not (PROJECT / "project.calflab.json").is_file(),
                    reason="projects/robot-calf-final (not in git) is only on the researcher's machine")
def test_r12_manifest_on_the_project():
    """The six R12 bodies; own behaviours matched by generator first; the origin rule names the start vectors."""
    import numpy as np
    from calflab.app import Lab

    lab = Lab.open(PROJECT, create=False)
    try:
        m = cmp.manifest(lab, "r12")
        assert [b["key"] for b in m["bodies"]] == cmp.SETS["r12"].bodies
        assert all(b["stage_c_run"] for b in m["bodies"])
        groups = {g["key"]: g for g in m["groups"]}
        assert len(groups["screen"]["items"]) == 5 and len(groups["shared"]["items"]) == 11
        assert groups["own"]["items"]
        p = cmp.plan(lab, cmp.SETS["r12"])
        for it in groups["own"]["items"]:
            for c in it["cells"]:
                assert c["empty"] or c["playing"]
                if c["match"] and c["match"].startswith("same generator"):
                    cell = next(x for x in p["_cells"][c["body"]] if f"own:{x['candidate']}" == c["play"])
                    assert cell["origin_name"] == it["origin"]
        # generation 0's first tasks are the start vectors themselves (what origin_index assumes)
        rid = m["bodies"][1]["stage_c_run"]
        sv = lab.registry.get_run(rid).inputs["params"]["start_vectors"]
        for c in lab.registry.list_candidates(rid):
            gen, i = c["id"].rsplit("-", 2)[-2:]
            if gen == "g000" and int(i) < len(sv):
                assert np.allclose(np.asarray(c["controller_x"])[:len(sv[int(i)])], sv[int(i)])
    finally:
        lab.close()
