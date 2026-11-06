"""The STS3250 C002 entry (ADR-100): only the researcher's values, nothing filled in, unverified."""

from __future__ import annotations

import pytest

from calflab.components import library


def test_sts3250_c002_holds_only_the_supplied_values() -> None:
    c = library().actuator("sts3250_c002")
    assert c.verified is False
    assert c.mass_g == 74.5 and tuple(c.dims_mm) == (45.22, 24.72, 35.0)
    assert c.stall_torque_nm == 4.9 and c.rated_torque_nm == 1.57 and c.stall_current_a == 4.2
    assert c.no_load_speed_rpm == pytest.approx(10.0 / 0.133, abs=1e-3)  # 0.133 s / 60 deg, the spec (not 0.129)
    assert c.voltage_v == 12.0 and c.gear_ratio == 345
    # not given: the model default is used and reported, never entered as a value
    assert set(c.defaulted) >= {"idle_current_a", "armature_kgm2", "winding_resistance_ohm", "r_thermal_k_per_w",
                                "c_thermal_j_per_k", "max_temp_c", "cost_usd"}
    assert c.unknown == ["encoder_steps_per_rev"] and c.guessed == []


def test_sts3250_c002_is_not_on_the_working_body() -> None:
    """The feral calf's default servo is unchanged: the swap of R9 is a what-if only."""
    from calflab.morphology.feral import feral_config

    assert feral_config()["servo"]["component"] == "sts3215_c018"
