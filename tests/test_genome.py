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
    assert d.complete({}) == d.defaults()
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
