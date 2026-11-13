"""Belted or direct carpus (ADR-123..): the compare set's body order, the direct layout, the clearance geometry."""
from __future__ import annotations

import importlib.util
import math
import sys

import numpy as np
import pytest
from calflab.design import build_design, genome_definition
from calflab.model.genome import Genome
from calflab.model.spec import Geom
from calflab.paths import repo_root


def _study():  # type: ignore[no-untyped-def]
    """``docs/studies/carpus_r18.py`` as a module (it imports ``mcmaster_r18`` beside it)."""
    folder = repo_root() / "docs" / "studies"
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("carpus_r18", folder / "carpus_r18.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _design(genes: dict | None = None):  # type: ignore[no-untyped-def]
    d = genome_definition("feral_calf")
    g = Genome(definition="feral_calf", version=d.version, values=d.complete({**d.defaults(), **(genes or {})}))
    return build_design(g, [], "feral_calf", {})


@pytest.fixture(scope="module")
def direct():  # type: ignore[no-untyped-def]
    return _design({"carpus_belt": False})


def test_the_compare_set_shows_the_studys_order_first() -> None:
    from calflab.app.body_compare import body_order

    data = {"replay": {"base": [], "swap": [], "r18-a": [], "direct": []}, "order": ["base", "swap", "direct", "gone"]}
    assert body_order(data) == ["base", "swap", "direct", "r18-a"]
    assert body_order({"replay": {"a": [], "b": []}}) == ["a", "b"]  # no order: as added


def test_the_direct_body_differs_only_in_carpus_belt() -> None:
    mod = _study()
    swap = {"belt_carpus_system": "MM-3MGT-9", "belt_carpus_pulleys": "MM-3MGT-45T+MM-3MGT-45T", "carpus_belt": True}
    d = mod.direct_genes(swap)
    assert {k for k in d if d[k] != swap[k]} == {"carpus_belt"} and d["carpus_belt"] is False


def test_a_direct_carpus_puts_the_servo_case_on_the_joint(direct) -> None:  # type: ignore[no-untyped-def]
    spec = direct.spec
    acts = {a.joint: a for a in spec.actuators}
    for k in ("fl", "fr"):
        assert acts[f"joint.{k}.carpus"].transmission is None
        upper = spec.body(f"leg.{k}.upper")
        length = next(g for g in upper.geoms if g.id == f"leg.{k}.upper.tube").size[1]
        case = next(g for g in upper.geoms if g.id == f"act.{k}.carpus.motor")
        assert case.pos[0] == 0.0 and case.pos[2] == pytest.approx(-length)  # centred on the carpus axis
        assert not any(g.id.startswith(f"belt.{k}.carpus") for b in spec.bodies for g in b.geoms)


def test_geom_low_for_a_box_a_cylinder_and_a_sphere() -> None:
    mod = _study()
    box = Geom(id="b", shape="box", size=(20.0, 10.0, 40.0), pos=(0.0, 0.0, -100.0))
    assert float(mod.geom_low(box, (0.0, 0.0, 500.0), (1.0, 0.0, 0.0, 0.0))) == pytest.approx(380.0)
    # turned 90 deg about y: the 20 mm side is now vertical
    q = (math.cos(math.pi / 4), 0.0, math.sin(math.pi / 4), 0.0)
    assert float(mod.geom_low(box, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))) == pytest.approx(-120.0)
    low = float(mod.geom_low(Geom(id="b2", shape="box", size=(20.0, 10.0, 40.0)), (0.0, 0.0, 0.0), q))
    assert low == pytest.approx(-10.0)
    cyl = Geom(id="c", shape="cylinder", size=(5.0, 100.0, 0.0))  # along z
    assert float(mod.geom_low(cyl, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))) == pytest.approx(-50.0)
    assert float(mod.geom_low(cyl, (0.0, 0.0, 0.0), q)) == pytest.approx(-5.0)  # lying: its radius
    sph = Geom(id="s", shape="sphere", size=(7.0, 0.0, 0.0), pos=(0.0, 0.0, 3.0))
    lows = mod.geom_low(sph, np.zeros((4, 3)), np.tile((1.0, 0.0, 0.0, 0.0), (4, 1)))
    assert lows.shape == (4,) and np.allclose(lows, -4.0)


def test_cylinder_to_box_gap_is_lateral_for_a_case_beside_the_tube() -> None:
    mod = _study()
    # a tube of radius 7.5 along -z from the origin; a box 9.5 mm beyond its axis in y
    gap = mod._cyl_box_gap((0, 0, 0), (0, 0, -1), 200.0, 7.5, (0.0, 27.0, 0.0), (12.35, 17.5, 22.6))
    assert gap == pytest.approx(2.0)


def test_the_direct_case_is_lowest_once_the_carpus_folds(direct) -> None:  # type: ignore[no-untyped-def]
    """Standing, the case is far above the hoof; folded to the end of its range, it is below the carpus tube, so a
    kneeling leg would rest on it (it is a visual geom: the simulator does not collide it)."""
    mod = _study()
    spec = direct.spec
    rest = spec.rest_angles()
    case = next(g for g in spec.body("leg.fl.upper").geoms if g.id == "act.fl.carpus.motor")
    leg = [(b.id, g) for b in spec.bodies if b.id in ("leg.fl.upper", "leg.fl.cannon") for g in b.geoms
           if g.role in ("collision", "both")]

    def clearance(q: float) -> float:
        poses = spec.world_poses({**rest, "joint.fl.carpus": q})
        low = min(float(mod.geom_low(g, *poses[b])) for b, g in leg)
        return float(mod.geom_low(case, *poses["leg.fl.upper"])) - low

    hi = spec.joint("joint.fl.carpus").range_deg[1]
    assert clearance(0.0) > 100.0
    assert clearance(hi) < 0.0


def test_the_carpus_set_shows_only_the_belted_and_the_direct_body() -> None:
    from calflab.app.body_compare import BODY_SETS, body_manifest

    s = BODY_SETS["carpus"]
    assert s.bodies == ["g020-008-r01-mc", "g020-008-r01-mc-direct"] and s.study == BODY_SETS["r18"].study
    from calflab.paths import repo_root

    if (repo_root() / s.study).is_file():  # the study's JSON is in git; both bodies are replayed there
        m = body_manifest(None, "carpus")
        assert [b["key"] for b in m["bodies"]] == s.bodies
        assert all(len(it["cells"]) == 2 for g in m["groups"] for it in g["items"])
