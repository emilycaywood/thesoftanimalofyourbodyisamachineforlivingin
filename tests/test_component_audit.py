"""Component verification worksheet and audit."""

from __future__ import annotations

import csv
import io

import pytest
from calflab.components import library
from calflab.components.library import _MODELS, META_FIELDS
from calflab.plugins import registry
from calflab.sim import SimSettings, compute_metrics, run_rollout
from calflab.wiring import component_audit, component_worksheet, component_worksheet_csv
from calflab.wiring.audit import FIELD_USES, RESULTS, WORKSHEET_COLUMNS

NOT_SPECS = set(META_FIELDS)
# common fields that mean nothing for a material (it is bought by the kg)
NOT_FOR_MATERIAL = {"mass_g", "dims_mm", "cost_usd"}


def test_every_spec_field_is_classified():
    """Adding a field to a component model must also say what it is used for."""
    for kind, model in _MODELS.items():
        fields = set(model.model_fields) - NOT_SPECS
        if kind == "material":
            fields -= NOT_FOR_MATERIAL
        assert fields == set(FIELD_USES[kind]), kind
        for _unit, uses in FIELD_USES[kind].values():
            assert set(uses) <= set(RESULTS)


def test_worksheet_has_one_row_per_value_and_blank_researcher_columns():
    lib = library()
    rows = component_worksheet(lib)
    assert len(rows) == sum(len(FIELD_USES[c.kind]) for c in lib.all())
    row = next(r for r in rows if r["component"] == "xh540_w270" and r["field"] == "stall_torque_nm")
    assert row["recorded_value"] == "10.6" and row["unit"] == "N*m" and "Torque margins" in row["used_for"]
    assert all(r["datasheet_value"] == r["ok"] == "" for r in rows)
    parsed = list(csv.DictReader(io.StringIO(component_worksheet_csv(lib))))
    assert tuple(parsed[0]) == WORKSHEET_COLUMNS and len(parsed) == len(rows)


def test_audit_reports_dependencies_and_saturated_actuators(calf_design, calf_model):
    lib = library()
    idle = component_audit(calf_design.spec, lib, None)
    assert idle["from_run"] is False and idle["at_limit"] == []
    assert idle["unverified"] == idle["total"] == len(lib.all())
    by_key = {c["key"]: c for c in idle["components"]}
    assert by_key["xh540_w270"]["in_design"] and by_key["xh540_w270"]["qty"] == 8
    assert not by_key["qdd_bldc_generic"]["in_design"]
    assert "gear_ratio" in by_key["sts3215"]["unused_fields"]
    assert "no_load_speed_rpm" not in by_key["sts3215"]["unused_fields"], "it caps the speed of tuned gaits"
    results = {r["key"]: r for r in idle["results"]}
    assert "lipo_3s_5000" in results["runtime"]["depends_on_unverified"]
    assert "lipo_3s_5000" not in results["torque_margin"]["depends_on_unverified"]
    assert "qdd_bldc_generic" not in results["bom_cost"]["depends_on_unverified"]
    assert results["bom_cost"]["unverified_share"] == pytest.approx(1.0)

    r = run_rollout(calf_model, registry.get("controller", "cpg")(), SimSettings(duration_s=2.0), lib)
    rep = component_audit(calf_design.spec, lib, compute_metrics(r))
    assert rep["from_run"] and len(rep["torque"]) == 18
    assert rep["at_limit"] == [t["actuator"] for t in rep["torque"] if t["margin"] <= rep["limit_margin"]]
    # a generous threshold flags everything, a negative one nothing
    assert len(component_audit(calf_design.spec, lib, compute_metrics(r), limit_margin=1.0)["at_limit"]) == 18
    assert component_audit(calf_design.spec, lib, compute_metrics(r), limit_margin=-1.0)["at_limit"] == []
