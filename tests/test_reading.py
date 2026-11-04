"""Reading footage into behaviours (ADR-085): a known sequence is read back, the model counts it, the record
validates, and the two fixes found on the researcher's videos hold (a seen face; turns only across reliable
frames)."""

from __future__ import annotations

import numpy as np
import pytest
from calflab.behave import reading as rd
from calflab.behave.signals import synthetic_signals
from calflab.design import build_design, genome_definition

SEQ = [("stand", 2.0), ("weight_shift", 2.0), ("walk", 3.6), ("stand", 1.5), ("step", 1.2), ("stand", 1.0),
       ("turn", 3.0), ("other", 2.0), ("stand", 1.5)]


@pytest.fixture(scope="module")
def spec():
    return build_design(genome_definition("feral_calf").default_genome(), [], "feral_calf", {}).spec


@pytest.fixture(scope="module")
def read(spec):
    sig, truth = synthetic_signals(spec, SEQ, seed=1)
    s = rd.ReadingSettings()
    up, how = rd.lifted(sig, s)
    return sig, truth, rd.label(sig, up, s, video="synthetic"), s


def test_a_known_sequence_is_read_back(read):
    _sig, truth, sts, _s = read
    order = [st.behaviour for st in sts]
    expect = [b for b, _d in SEQ]
    # the step is read as its lift (the stand around it stays stand), so the sequences match exactly
    assert order == expect, order
    for st, (beh, t0, t1) in zip(sts, truth, strict=True):
        assert st.behaviour == beh
        if beh == "step":
            assert t0 <= st.t0 < st.t1 <= t1
        elif beh == "stand":  # around the step, standing goes on until the hoof lifts
            assert min(st.t1, t1) - max(st.t0, t0) >= 0.7 * (t1 - t0), (st.t0, st.t1, t0, t1)
        else:
            assert abs(st.t0 - t0) <= 0.5 and abs(st.t1 - t1) <= 0.5, (st.behaviour, st.t0, st.t1, t0, t1)
        assert 0.0 < st.confidence <= 1.0
        assert st.evidence.rule


def test_features_say_what_was_scripted(read):
    _sig, _truth, sts, _s = read
    by = {st.behaviour: st for st in sts if st.behaviour != "stand"}
    walk, turn, fast = by["walk"].features, by["turn"].features, by["other"].features
    assert walk["footfall"]["pattern"] == "lateral"
    assert walk["tempo_s"] == pytest.approx(1.2, abs=0.15)  # the stride period
    assert turn["turn_deg"] > 90 and turn["turn_direction"] == "left"
    assert fast["two_up_fraction"] > 0.4 and fast["footfall"]["pattern"] == "diagonal pairs"
    assert by["weight_shift"].features["roll_range_deg"] > 5
    assert by["weight_shift"].features["lifts"] == 0


def test_model_counts_transitions_and_durations(read):
    _sig, _truth, sts, s = read
    m = rd.fit_model(sts, s)
    assert m.counts["stand"]["weight_shift"] == 1 and m.counts["weight_shift"]["walk"] == 1
    assert sum(sum(r.values()) for r in m.counts.values()) == len(sts) - 1
    for a, row in m.probabilities.items():
        assert row[a] == 0.0  # semi-Markov: no self-transition
        assert sum(row.values()) == pytest.approx(1.0, abs=1e-3)
    assert m.durations["stand"].n == 4 and m.durations["stand"].censored == 2  # first and last are cut by the ends
    assert m.durations["walk"].note.startswith("one stretch")
    assert m.per_video["synthetic"]["stand"]["weight_shift"] == 1


def test_reading_record_validates_and_round_trips(read, spec):
    from calflab.app.reading_jobs import expressive_gaps

    _sig, _truth, sts, s = read
    m = rd.fit_model(sts, s)
    beh = rd.behaviour_summary(sts)
    v = rd.VideoReading(file="synthetic", usable=True, seconds=18.8, seconds_read=18.8, stretches=len(sts))
    r = rd.Reading(id="x", created="x", settings=s, provenance={}, videos=[v], stretches=sts, behaviours=beh, model=m,
                   support=rd.support_statement([v], sts, m), gaps=expressive_gaps(spec, beh, True))
    again = rd.Reading.model_validate_json(r.model_dump_json())
    assert again.schema_version == rd.SCHEMA_VERSION and len(again.stretches) == len(sts)
    assert any(g["what"] == "head and neck" for g in r.gaps)  # the feral calf has no neck joint
    assert "transitions" in r.support["lines"][2]


def test_turn_is_summed_only_across_reliable_frames(spec):
    """213625: a heading unwrapped through frames the lift could not read 'turned' 364 deg in 0.9 s."""
    sig, _truth = synthetic_signals(spec, [("stand", 2.0)])
    sig.heading_deg = np.linspace(0, 360, sig.frames)
    sig.reliable = np.zeros(sig.frames, dtype=bool)
    sig.reliable[:5] = True
    assert abs(rd._clean_turn(sig, 0, sig.frames)) < 360 * 6 / sig.frames


def test_paw_speed_contact_has_hysteresis(spec):
    sig, _truth = synthetic_signals(spec, [("stand", 1.0)])
    v = np.zeros(sig.frames)
    v[5:15] = 0.4  # under the swing threshold: never starts
    v[15:25] = 0.8  # over it: swing
    v[25:28] = 0.35  # between the two thresholds: still swing
    sig.hoof_speed_bl_s = {"hl": v}
    up = rd.lifted_from_speed(sig, rd.ReadingSettings())["hl"]
    assert not up[5:15].any() and up[15:28].all() and not up[28:].any()


def test_a_seen_face_counts_toward_the_camera():
    """214239: both eyes confidently tracked = the head faces the camera (ADR-085)."""
    from calflab.behave.keypoints import KeypointTracks
    from calflab.behave.lift import LiftMap, LiftSettings, _face_seen

    n = 30
    lk = np.full((n, 2), 1.2)
    lk[20:, 1] = 0.2  # one eye lost from frame 20
    tr = KeypointTracks(fps=30.0, names=["L_Eye", "R_Eye"], xy=np.zeros((n, 2, 2)), likelihood=lk)
    m = LiftMap(name="t", landmarks={}, face=["L_Eye", "R_Eye"])
    face = _face_seen(tr, m, LiftSettings(), 3)
    assert face is not None and face[:15].min() == 1.0 and face[25:].max() == 0.0
    assert _face_seen(tr, LiftMap(name="t", landmarks={}), LiftSettings(), 3) is None  # no face named: as before
