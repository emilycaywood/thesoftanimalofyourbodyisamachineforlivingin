"""The R15 compare manifest (calflab.app.outcome_compare, ADR-111): bodies x behaviours -> stored replays, badges."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from calflab.app import outcome_compare as oc


def _best(holds: bool, within: bool, outcome: dict[str, Any], rank: float = 0.0) -> dict[str, Any]:
    return {"holds": holds, "within": within,
            "seeds": [{"seed": 0, "rank": rank + 1, "margin": 0.5, "within": within, "outcome": {"gates": {}}},
                      {"seed": 1, "rank": rank, "margin": 0.4, "within": within,
                       "binding": {"joint": "fl.carpus", "limit": "speed", "use": 1.25}, "outcome": outcome}]}


def test_manifest_cells_badges_and_missing(tmp_path: Path, monkeypatch: Any) -> None:
    trot = {"speed_min_mm_s": 312.0, "drift_mm_s": 4.5, "footfall": {"label": "trot"}, "gates": {"useful_speed": True}}
    suckle = {"push_p20_n": 0.88, "push_mean_n": 1.02, "slip_max_mm": 24.0, "effort_max": 0.15,
              "gates": {"pressing": True, "no_slip": False}}
    data = {"pilot": {"a": {"trot": {"best": _best(True, True, trot)}, "suckle": {"best": _best(False, True, suckle)}},
                      "b": {"trot": {"best": _best(False, False, trot)}}},
            "stored": {"a": {"trot": "run-a-trot", "suckle": "run-a-suckle"}, "b": {"trot": "run-b-trot"}},
            "mass_g": {"a": 2040.0}}
    f = tmp_path / "study.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setitem(oc.OUTCOME_SETS, "t", oc.OutcomeCompareSet(key="t", title="T", study=str(f), bodies=["a", "b"],
                                                                     behaviours=["trot", "suckle"]))
    m = oc.outcome_manifest(None, "t")
    assert m["per_cell"] and m["seeds"] == [0]
    assert m["bodies"][0]["line"] == "2040 g · holds 1/2 (trot)"
    trot_item, suckle_item = m["groups"][0]["items"]
    a, b = trot_item["cells"]
    assert a["seeds"][0]["run"] == "run-a-trot" and a["seeds"][0]["badge"] == "within"
    assert "312 mm/s" in a["playing"] and "footfall trot" in a["playing"]  # the worst seed (lowest rank) is described
    assert b["seeds"][0]["badge"] == "over" and b["seeds"][0]["limit"] == "fl.carpus speed (1.25)"
    sa, sb = suckle_item["cells"]
    assert sa["seeds"][0]["badge"] == "near" and sa["seeds"][0]["text"] == "fails no_slip"
    assert sb["empty"] and sb["message"] == "not searched yet" and m["missing"] == 1


def test_r15_set_is_served_by_the_compare_manifest() -> None:
    from calflab.app.compare import manifest

    m = manifest(None, "r15")
    assert [b["key"] for b in m["bodies"]] == oc.OUTCOME_SETS["r15"].bodies
    assert [it["key"] for it in m["groups"][0]["items"]] == ["stand", "suckle", "trot", "lie"]
