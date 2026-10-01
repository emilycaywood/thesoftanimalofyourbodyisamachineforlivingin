"""MJCF compile, deterministic rollouts, metrics, skin model."""

import numpy as np
import pytest
from calflab.components import library
from calflab.plugins import registry
from calflab.sim import (
    CompileOptions,
    DomainRandomization,
    Push,
    Rollout,
    SimSettings,
    compile_mjcf,
    compute_metrics,
    run_rollout,
    timeseries,
)
from calflab.sim.metrics import METRIC_DEFS


def cpg(**params):
    return registry.get("controller", "cpg")(params)


def test_mjcf_compiles_in_mujoco(calf_design, calf_model):
    import mujoco

    model = mujoco.MjModel.from_xml_string(calf_model.xml)
    assert model.nu == len(calf_design.spec.actuators) == 18
    assert model.njnt == 1 + 18
    assert model.body(calf_model.body_ids[0]).name == "trunk"
    mass = float(np.sum(model.body_mass))
    assert mass == pytest.approx(calf_design.spec.total_mass_g() / 1000.0, rel=1e-3)
    assert len(calf_model.foot_geoms) == 4


def test_fk_matches_mujoco(calf_design, calf_model):
    """The pure-Python forward kinematics used for the viewport agrees with MuJoCo."""
    import mujoco

    model = mujoco.MjModel.from_xml_string(calf_model.xml)
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    poses = calf_design.spec.world_poses()
    for bid in calf_model.body_ids:
        mj = data.xpos[model.body(bid).id] * 1000.0
        mine = np.array(poses[bid][0]) + np.array([0, 0, 2.0])  # compiler lifts the root 2 mm
        assert np.allclose(mj, mine, atol=1e-3), bid


def test_rollout_is_deterministic(calf_model):
    s = SimSettings(duration_s=2.0, seed=3)
    a = run_rollout(calf_model, cpg(), s, library())
    b = run_rollout(calf_model, cpg(), s, library())
    assert np.array_equal(a.body_pos, b.body_pos)
    assert np.array_equal(a.torque, b.torque)
    assert compute_metrics(a) == compute_metrics(b)


def test_default_gait_walks_forward(calf_model):
    r = run_rollout(calf_model, cpg(), SimSettings(duration_s=4.0), library())
    m = compute_metrics(r)
    assert not m["fell"]
    assert m["speed_mps"] > 0.1
    assert 0 < m["cost_of_transport"] < 10
    assert set(METRIC_DEFS) <= set(m)
    assert len(m["by_actuator"]) == 18
    ts = timeseries(r)
    assert len(ts["t"]) == r.n_frames == len(ts["channels"]["speed"]["values"])


def test_streaming_chunks_cover_all_frames(calf_model):
    seen = []
    r = run_rollout(calf_model, cpg(), SimSettings(duration_s=1.0), on_frames=seen.append, chunk_frames=10)
    assert sum(len(c["t"]) for c in seen) == r.n_frames
    assert seen[0]["start"] == 0 and seen[0]["pos"].shape[1:] == (len(r.body_ids), 3)


def test_rollout_save_load(tmp_path, calf_model):
    r = run_rollout(calf_model, cpg(), SimSettings(duration_s=1.0), library())
    r.save(tmp_path / "r.npz")
    back = Rollout.load(tmp_path / "r.npz")
    assert np.array_equal(back.body_pos, r.body_pos)
    assert compute_metrics(back) == compute_metrics(r)


def test_push_disturbs_the_robot(calf_model):
    calm = run_rollout(calf_model, cpg(), SimSettings(duration_s=2.0), library())
    push = Push(t_s=0.8, duration_s=0.2, force_n=(0.0, 40.0, 0.0))
    hit = run_rollout(calf_model, cpg(), SimSettings(duration_s=2.0, pushes=[push]), library())
    assert not np.array_equal(calm.body_pos, hit.body_pos)
    assert compute_metrics(hit)["lateral_drift_m"] > compute_metrics(calm)["lateral_drift_m"]


def test_skin_adds_joint_stiffness_and_mass(calf_design):
    with_skin = compile_mjcf(calf_design.spec, library(), CompileOptions(include_skin=True))
    without = compile_mjcf(calf_design.spec, library(), CompileOptions(include_skin=False))
    assert "stiffness" in with_skin.xml and "stiffness" not in without.xml
    assert with_skin.total_mass_kg > without.total_mass_kg + 0.3


def test_domain_randomization_is_seeded(calf_design):
    opt = CompileOptions(randomization=DomainRandomization(enabled=True))
    a = compile_mjcf(calf_design.spec, library(), opt, seed=1)
    b = compile_mjcf(calf_design.spec, library(), opt, seed=1)
    c = compile_mjcf(calf_design.spec, library(), opt, seed=2)
    assert a.xml == b.xml and a.xml != c.xml


def test_stand_up_from_lying_reports_a_time(calf_model):
    r = run_rollout(
        calf_model, cpg(hip_amplitude=0, knee_amplitude=0), SimSettings(duration_s=5.0, start_pose="lying"), library()
    )
    t = compute_metrics(r)["time_to_stand_s"]
    assert t is None or t > 0
