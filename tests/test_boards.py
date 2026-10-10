"""The boards in the trunk are chosen per project in Mechanism (ADR-061).
The ESP-WROOM-32 values are read from the library, never repeated here."""

import json

import pytest
from calflab.app import Lab
from calflab.components import library
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.mass import mass_breakdown
from calflab.sim import compile_mjcf
from calflab.wiring import power_budget
from calflab.wiring.budget import boards_used

BOARD_GENES = ("board_control", "board_compute")
ONLY_ESP32 = {"board_control": "esp_wroom_32", "board_compute": "none"}
#: the simplified prototype: two joints per leg, no neck, head, tail or ear motors
TWO_JOINT = {
    "scale": 0.337, "front_hip_abd": False, "hind_hip_abd": False, "front_knee_forward": True, "hind_knee_forward": False,
    "has_neck_yaw": False, "has_neck_pitch": False, "has_head_pitch": False, "has_tail": False, "has_ears": False,
    "act_hip_flex": "scs0009", "act_knee": "scs0009", "battery": "lipo_2s_1100",
}


def design(**genes):
    gdef = genome_definition("calf")
    return build_design(Genome(definition="calf", version=gdef.version, values=gdef.defaults() | genes))


def board_geoms(spec):
    return [g.id for b in spec.bodies for g in b.geoms if g.id.startswith("elec.") and g.id != "elec.battery"]


def test_a_genome_saved_before_the_board_genes_carries_the_teensy_and_the_pi():
    gdef = genome_definition("calf")
    assert (gdef.gene("board_control").default, gdef.gene("board_compute").default) == ("teensy_41", "raspberry_pi_5")
    assert not gdef.gene("board_control").evolvable and not gdef.gene("board_compute").evolvable
    assert gdef.gene("board_control").group == gdef.gene("battery").group == "Mechanism"
    assert "esp_wroom_32" in gdef.gene("board_control").choices and "none" not in gdef.gene("board_control").choices
    assert {"none", "esp_wroom_32", "teensy_41"} <= set(gdef.gene("board_compute").choices)
    lib = library()
    for genes in ({}, TWO_JOINT):
        old = {k: v for k, v in (gdef.defaults() | genes).items() if k not in BOARD_GENES}
        a = build_design(Genome(definition="calf", version=gdef.version, values=old)).spec
        b = design(**genes).spec
        assert a.model_dump_json() == b.model_dump_json()
        assert board_geoms(a) == ["elec.teensy_41", "elec.raspberry_pi_5"]
        assert compile_mjcf(a, lib).xml == compile_mjcf(b, lib).xml
    link = next(r for r in a.harness_routes if r.id == "harness.link")
    assert (link.src, link.dst) == ("elec.raspberry_pi_5", "elec.teensy_41")


def test_only_the_esp32_weighs_and_draws_what_its_entry_says():
    lib = library()
    esp, teensy, pi = lib.get("esp_wroom_32"), lib.get("teensy_41"), lib.get("raspberry_pi_5")
    assert esp.kind == "board" and esp.name == "ESP-WROOM-32" and esp.guessed == []
    assert set(esp.defaulted) == {"dims_mm", "cost_usd"}, "what the researcher did not give is named, not filled in"
    full, small = design(**TWO_JOINT).spec, design(**TWO_JOINT, **ONLY_ESP32).spec
    assert board_geoms(small) == ["elec.esp_wroom_32"]
    assert small.total_mass_g() == pytest.approx(full.total_mass_g() - teensy.mass_g - pi.mass_g + esp.mass_g)

    breakdown = mass_breakdown(small, lib)
    assert breakdown["total_g"] == pytest.approx(small.total_mass_g(), abs=0.01)
    trunk = next(r for r in breakdown["bodies"] if r["body"] == "trunk")
    parts = {i["component"]: i for i in trunk["items"] if i["component"]}
    assert "teensy_41" not in parts and "raspberry_pi_5" not in parts
    assert parts["esp_wroom_32"]["mass_g"] == esp.mass_g and parts["esp_wroom_32"]["source"] == "component"
    assert parts["esp_wroom_32"]["label"] == "ESP-WROOM-32" and parts["esp_wroom_32"]["verified"] is False

    before, after = power_budget(full, lib, None), power_budget(small, lib, None)
    loads = {row["id"]: row for row in after["other_loads"]}
    assert loads["elec.esp_wroom_32"]["power_w"] == esp.power_w
    assert "elec.teensy_41" not in loads and "elec.raspberry_pi_5" not in loads
    assert after["bus_voltage_v"] == pytest.approx(7.4)
    saved_w = teensy.power_w + pi.power_w - esp.power_w
    assert after["mean_power_w"] == pytest.approx(before["mean_power_w"] - saved_w, abs=0.011)
    # a board's watts become battery current at the pack voltage, like every other board's
    assert after["mean_current_a"] == pytest.approx(before["mean_current_a"] - saved_w / 7.4, abs=0.011)

    routes = {r.id: r for r in small.harness_routes}
    assert "harness.link" not in routes, "one board: nothing to link"
    assert routes["harness.power"].dst == "elec.esp_wroom_32" and routes["harness.imu"].dst == "elec.esp_wroom_32"
    assert all(routes[f"harness.bus.{k}"].src == "elec.esp_wroom_32" for k in ("fl", "fr", "hl", "hr"))
    assert [row["component"] for row in boards_used(small, lib)] == ["esp_wroom_32"]


def test_a_board_named_twice_is_one_board_and_any_two_can_be_paired():
    assert board_geoms(design(board_control="esp_wroom_32", board_compute="esp_wroom_32").spec) == ["elec.esp_wroom_32"]
    spec = design(board_control="esp_wroom_32", board_compute="raspberry_pi_5").spec
    assert board_geoms(spec) == ["elec.esp_wroom_32", "elec.raspberry_pi_5"]
    link = next(r for r in spec.harness_routes if r.id == "harness.link")
    assert (link.src, link.dst) == ("elec.raspberry_pi_5", "elec.esp_wroom_32")
    with pytest.raises(ValueError, match="not in"):
        genome_definition("calf").gene("board_control").coerce("none")


def test_the_board_choice_is_undoable_and_recorded_with_runs_and_studies(tmp_path):
    lab = Lab.open(tmp_path / "p")
    try:
        lab.backend_key = "inline"
        lab.execute("set_genes", {"values": TWO_JOINT})
        lab.end_gesture()
        for role, params in (("model", {"include_skin": False}), ("simulation", {"duration_s": 2.0})):
            lab.execute("set_node_params", {"node": lab.state.graph.role(role).id, "params": params})
        lab.end_gesture()
        with_both = lab.scene()["mass"]["total_g"]
        lab.execute("set_genes", {"values": ONLY_ESP32})
        lab.end_gesture()
        lib = library()
        lighter = lib.get("teensy_41").mass_g + lib.get("raspberry_pi_5").mass_g - lib.get("esp_wroom_32").mass_g
        assert lab.scene()["mass"]["total_g"] == pytest.approx(with_both - lighter, abs=0.02)
        lab.undo()
        genes = lab.state.graph.role("genome").params
        assert (genes["board_control"], genes["board_compute"]) == ("teensy_41", "raspberry_pi_5")
        assert genes["battery"] == "lipo_2s_1100", "only the board choice was undone"
        assert lab.scene()["mass"]["total_g"] == pytest.approx(with_both, abs=0.02)
        lab.redo()
        assert board_geoms(lab.design().spec) == ["elec.esp_wroom_32"]

        job = lab.jobs.wait(lab.run_sim().id, timeout=300)
        assert job.status == "done", job.error
        run = lab.registry.get_run(job.result["run_id"])
        assert run.genome["values"]["board_control"] == "esp_wroom_32" and run.genome["values"]["board_compute"] == "none"
        (board,) = run.inputs["boards"]
        assert (board["id"], board["component"], board["verified"]) == ("elec.esp_wroom_32", "esp_wroom_32", False)
        assert board["mass_g"] == lib.get("esp_wroom_32").mass_g and board["power_w"] == lib.get("esp_wroom_32").power_w
        assert set(board["defaulted"]) == {"dims_mm", "cost_usd"}
        on_disk = json.loads((lab.registry.run_dir(run.id) / "run.json").read_text(encoding="utf-8"))
        assert [b["component"] for b in on_disk["inputs"]["boards"]] == ["esp_wroom_32"]

        out = lab.execute("run_study", {"shank_min": 40, "shank_max": 70, "bodies": 1, "gaits": ["trot"], "iterations": 0,
                                        "duration_s": 2.0})["result"]
        job = lab.jobs.wait(out["job"], timeout=600)
        assert job.status == "done", job.error
        study = json.loads((lab.registry.run_dir(out["run_id"]) / "study.json").read_text(encoding="utf-8"))
        assert [b["component"] for b in study["boards"]] == ["esp_wroom_32"]
        assert all(b["genome"]["values"]["board_control"] == "esp_wroom_32" for b in study["bodies"])
        record = lab.registry.get_run(out["run_id"])
        assert [b["component"] for b in record.inputs["boards"]] == ["esp_wroom_32"]
        assert any("esp_wroom_32" in n and "not verified" in n for n in record.inputs["notes"])
    finally:
        lab.close()
