"""Exporters, BOM, power budget, harness."""

import json
import xml.etree.ElementTree as ET

import pytest
import yaml
from calflab.components import library
from calflab.plugins import ExportContext, registry
from calflab.sim import SimSettings, compute_metrics, run_rollout
from calflab.wiring import (
    bill_of_materials,
    power_budget,
    render_harness,
    torque_margins,
    wireviz_document,
)


@pytest.fixture()
def ctx(calf_design):
    d = calf_design
    return ExportContext(spec=d.spec, genes=d.genome.values, element_params=d.element_params, library=library(), design_name="calf")


def export(key, ctx, tmp_path, **params):
    return registry.get("exporter", key)(params).export(ctx, tmp_path)


def test_gltf_nodes_are_named_by_stable_id(ctx, tmp_path):
    import trimesh

    (path,) = export("gltf", ctx, tmp_path)
    scene = trimesh.load(path)
    assert {"trunk.shell", "leg.fl.shank.tube", "leg.fl.hoof"} <= set(scene.geometry)


def test_stl_and_3mf_per_part(ctx, tmp_path):
    stl = export("stl", ctx, tmp_path / "a")
    assert any(p.name == "calf_leg.fl.shank.stl" for p in stl)
    one = export("threemf", ctx, tmp_path / "b", per_part=False)
    assert len(one) == 1 and one[0].suffix == ".3mf" and one[0].stat().st_size > 1000
    ctx.selection = ["leg.fl.thigh"]
    assert [p.name for p in export("stl", ctx, tmp_path / "c")] == ["calf_leg.fl.thigh.stl"]


def test_3dm_has_calflab_layers_and_user_text(ctx, tmp_path):
    import rhino3dm as r3

    (path,) = export("rhino_3dm", ctx, tmp_path)
    model = r3.File3dm.Read(str(path))
    names = [layer.FullPath for layer in model.Layers]
    assert "CALFLAB" in names and "CALFLAB::Structure" in names and "CALFLAB::Skin" in names
    objs = {o.Attributes.Name: o for o in model.Objects}
    shank = objs["leg.fl.shank.tube"]
    assert shank.Attributes.GetUserString("calflab.id") == "leg.fl.shank.tube"
    assert shank.Attributes.GetUserString("calflab.body") == "leg.fl.shank"
    assert model.Layers[shank.Attributes.LayerIndex].Name == "Structure"
    assert objs["act.fl.knee.motor"].Attributes.GetUserString("calflab.component") == "xh540_w270"


def test_urdf_and_mjcf_exports_parse(ctx, tmp_path):
    (urdf,) = export("urdf", ctx, tmp_path)
    root = ET.parse(urdf).getroot()
    assert len(root.findall("link")) == len(ctx.spec.bodies)
    assert len([j for j in root.findall("joint") if j.get("type") == "revolute"]) == 18
    (mjcf,) = export("mjcf", ctx, tmp_path)
    import mujoco

    assert mujoco.MjModel.from_xml_path(str(mjcf)).nu == 18


@pytest.mark.cad
def test_leg_segment_cad_with_actuator_mount_and_label(ctx, tmp_path):
    pytest.importorskip("build123d")
    import rhino3dm as r3

    paths = {p.suffix: p for p in export("leg_segment_cad", ctx, tmp_path / "a")}
    assert set(paths) == {".step", ".stl", ".3mf", ".3dm", ".json"}
    assert all(p.stat().st_size > 500 for p in paths.values())
    info = json.loads(paths[".json"].read_text())
    assert info["part_id"] == "leg.fl.shank" and info["actuator"]["component"] == "xh540_w270"
    assert info["actuator"]["verified"] is False and info["unverified"]
    assert info["bounding_box_mm"][2] == pytest.approx(170 + 8 / 2 + info["wall_mm"], abs=1.0)
    obj = next(iter(r3.File3dm.Read(str(paths[".3dm"])).Objects))
    assert obj.Attributes.GetUserString("calflab.id") == "leg.fl.shank"

    plain = json.loads(
        {p.suffix: p for p in export("leg_segment_cad", ctx, tmp_path / "b", label_mode="none")}[".json"].read_text()
    )
    assert info["volume_cm3"] > plain["volume_cm3"], "the embossed label adds material"
    with pytest.raises(ValueError, match="not a leg segment"):
        export("leg_segment_cad", ctx, tmp_path / "c", part="trunk")


def test_firmware_skeleton_carries_the_joint_map(ctx, tmp_path):
    paths = export("firmware", ctx, tmp_path)
    header = next(p for p in paths if p.name == "robot_config.h").read_text()
    assert "#define CALFLAB_NUM_JOINTS 18" in header and '"joint.fl.knee"' in header
    cfg = json.loads(next(p for p in paths if p.name == "robot_config.json").read_text())
    assert cfg["joints"][0]["min_rad"] < cfg["joints"][0]["max_rad"]


def test_bom_lists_everything_as_unverified(calf_design):
    bom = bill_of_materials(calf_design.spec, library())
    by_key = {r["key"]: r for r in bom["lines"]}
    assert by_key["xh540_w270"]["qty"] == 8 and by_key["xm430_w350"]["qty"] == 4 and by_key["sts3215"]["qty"] == 6
    assert by_key["fsr_foot"]["qty"] == 4 and by_key["lipo_3s_5000"]["qty"] == 1
    assert by_key["petg"]["qty_unit"] == "g" and by_key["knit_silicone_laminate"]["mass_g"] > 0
    assert bom["unverified"] == len(bom["lines"]) and all(r["source"] for r in bom["lines"])
    assert bom["total_cost_usd"] == pytest.approx(sum(r["cost_usd"] for r in bom["lines"]))


def test_power_budget_and_torque_margins_from_a_run(calf_design, calf_model):
    lib = library()
    idle = power_budget(calf_design.spec, lib, None)
    assert idle["from_run"] is False and idle["mean_power_w"] > 0
    r = run_rollout(calf_model, registry.get("controller", "cpg")(), SimSettings(duration_s=2.0), lib)
    m = compute_metrics(r)
    pb = power_budget(calf_design.spec, lib, m)
    assert pb["from_run"] and pb["mean_power_w"] > idle["mean_power_w"]
    assert pb["battery"]["runtime_min"] > 0 and len(pb["actuators"]) == 18
    rows = torque_margins(calf_design.spec, lib, m)
    knee = next(x for x in rows if x["joint"] == "joint.fl.knee")
    assert knee["required_peak_nm"] > 0 and knee["available_nm"] == pytest.approx(10.6 * 0.6)
    assert knee["margin"] == pytest.approx(1 - knee["required_peak_nm"] / knee["available_nm"], abs=1e-3)
    assert torque_margins(calf_design.spec, lib, None)[0]["margin"] is None


def test_harness_has_real_lengths_and_valid_wireviz(calf_design, tmp_path):
    spec = calf_design.spec
    routes = {r.id: r for r in spec.harness_routes}
    assert {"harness.power", "harness.bus.fl", "harness.imu"} <= set(routes)
    assert routes["harness.bus.fl"].length_mm > routes["harness.imu"].length_mm > 0
    doc = wireviz_document(spec)
    assert len(doc["cables"]) == len(doc["connections"]) == len(routes)
    assert doc["cables"]["harness_bus_fl"]["length"] == pytest.approx(routes["harness.bus.fl"].length_mm / 1000, abs=1e-3)
    res = render_harness(spec, tmp_path)
    assert yaml.safe_load(res["yaml"].read_text())["connectors"]
    assert res["svg"].read_text(encoding="utf-8").lstrip().startswith(("<svg", "<?xml"))
    assert res["renderer"] in ("wireviz", "fallback")
