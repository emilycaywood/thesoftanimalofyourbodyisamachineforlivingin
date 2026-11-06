"""Genome validity and migrations: old genomes must always reload."""

import numpy as np
import pytest
from calflab.components import library
from calflab.config import gene_definition_files
from calflab.design import build_design, genome_definition
from calflab.model.genome import GeneDef, Genome, GenomeDefinition
from calflab.model.migrations import migrate


def test_calf_definition_is_valid():
    d = genome_definition("calf")
    assert d.version >= 2
    assert len(d.genes) > 20
    for g in d.genes:
        assert g.description, f"gene {g.id} needs a description"
        if g.type in ("float", "int"):
            assert g.min < g.max


def test_enum_actuator_genes_exist_in_library():
    lib = library()
    d = genome_definition("calf")
    for g in d.genes:
        if g.id.startswith("act_"):
            for choice in g.choices:
                assert lib.actuator(choice).kind == "actuator"


def test_defaults_roundtrip_and_clamp():
    d = genome_definition("calf")
    assert d.complete(d.defaults()) == d.defaults()
    v = d.complete({"trunk_length": 99999, "unknown_gene": 1})
    assert v["trunk_length"] == d.gene("trunk_length").max
    assert "unknown_gene" not in v


def test_invalid_gene_definitions_rejected():
    with pytest.raises(ValueError):
        GeneDef(id="x", default=5, min=10, max=20)
    with pytest.raises(ValueError):
        GeneDef(id="x", type="enum", default="a", choices=["b"])
    with pytest.raises(ValueError):
        GenomeDefinition(name="d", genes=[GeneDef(id="x", default=1, min=0, max=2)] * 2)


def test_encode_decode_roundtrip():
    d = genome_definition("calf")
    vals = d.defaults()
    x = d.encode(vals)
    assert np.all((x >= 0) & (x <= 1))
    assert d.decode(x, vals) == pytest.approx(vals)
    lo = d.decode(np.zeros_like(x), vals)
    assert lo["trunk_length"] == d.gene("trunk_length").min


def test_migration_v1_to_current():
    d = genome_definition("calf")
    old = Genome(definition="calf", version=1, values={"leg_length": 400, "neck_angle": 30, "trunk_length": 450})
    new = migrate(old, d)
    assert new.version == d.version
    assert new.values["thigh_length"] == 200 and new.values["shank_length"] == 200
    assert new.values["neck_angle"] == 60  # v1 measured from vertical
    assert new.values["trunk_length"] == 450
    assert "leg_length" not in new.values
    assert set(new.values) == set(d.defaults())
    build_design(old)  # an old genome still builds a robot


def test_migration_rejects_future_and_foreign_genomes():
    d = genome_definition("calf")
    with pytest.raises(ValueError, match="newer"):
        migrate(Genome(definition="calf", version=d.version + 1, values={}), d)
    with pytest.raises(ValueError, match="definition"):
        migrate(Genome(definition="other", version=1, values={}), d)


def test_every_yaml_definition_has_a_migration_chain():
    for name, d in gene_definition_files().items():
        migrate(Genome(definition=name, version=1, values={}), d)


SERVO_GENES = [f"servo_{p}" for p in ("hip_abd", "stifle", "hock", "shoulder", "carpus")]


def test_feral_v1_actuator_becomes_one_servo_gene_per_pair():
    """v1 -> v2 (ADR-101): ``actuator`` fills each pair gene with setdefault, then goes."""
    d = genome_definition("feral_calf")
    assert d.version == 2 and not d.has("actuator")
    for gid in SERVO_GENES:
        g = d.gene(gid)
        assert g.default == "sts3215_c018" and g.choices_from == "actuator" and not g.evolvable
        assert g.group == "Mechanism" and "sts3250_c002" in (g.choices or [])
    new = migrate(Genome(definition="feral_calf", version=1, values={"actuator": "sts3250_c002"}), d)
    assert new.version == 2 and "actuator" not in new.values
    assert {new.values[g] for g in SERVO_GENES} == {"sts3250_c002"}
    # a value already set is kept
    kept = migrate(Genome(definition="feral_calf", version=1,
                          values={"actuator": "sts3250_c002", "servo_carpus": "sts3215_c018"}), d)
    assert kept.values["servo_carpus"] == "sts3215_c018" and kept.values["servo_hock"] == "sts3250_c002"
    # a v1 genome that never mentioned it had the default
    assert {migrate(Genome(definition="feral_calf", version=1, values={}), d).values[g] for g in SERVO_GENES} == {
        "sts3215_c018"}


def test_unversioned_feral_params_are_upgraded_where_they_are_completed():
    """A document's genome node params carry no version (GenomeNode stamps the current one): an open v1 document
    must build with its own servo, not the pair genes' defaults (ADR-101)."""
    from calflab.graph import node_types
    from calflab.model.migrations import upgrade_unversioned

    d = genome_definition("feral_calf")
    v1 = {k: v for k, v in d.defaults().items() if k not in SERVO_GENES} | {"actuator": "sts3250_c002"}
    done = d.complete(v1)
    assert "actuator" not in done and {done[g] for g in SERVO_GENES} == {"sts3250_c002"}
    v2 = d.defaults() | {"servo_hock": "sts3250_c002"}
    assert upgrade_unversioned(d, v2) is v2  # current params come back untouched
    assert d.complete(v2) == v2
    nt = node_types()["genome:feral_calf"]
    assert {nt.clean_params(v1)[g] for g in SERVO_GENES} == {"sts3250_c002"}


def test_a_gene_added_later_says_what_its_absence_meant():
    """New projects get forward front knees; anything saved before the gene
    existed (documents, runs, candidates, designs) keeps backward ones."""
    d = genome_definition("calf")
    g = d.gene("front_knee_forward")
    assert g.default is True and g.absent is False
    assert d.default_genome().values["front_knee_forward"] is True
    old = {k: v for k, v in d.defaults().items() if k != "front_knee_forward"}
    assert d.complete(old)["front_knee_forward"] is False
    assert d.complete(old | {"front_knee_forward": True})["front_knee_forward"] is True
    assert migrate(Genome(definition="calf", version=d.version, values=old), d).values["front_knee_forward"] is False
    assert migrate(Genome(definition="calf", version=1, values={"leg_length": 340}), d).values["front_knee_forward"] is False
    with pytest.raises(ValueError, match="absent"):
        GeneDef(id="x", default=1, min=0, max=2, absent=5)

