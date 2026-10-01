"""Shared fixtures."""

from __future__ import annotations

import pytest
from calflab.plugins import load_plugins


@pytest.fixture(scope="session", autouse=True)
def _plugins() -> None:
    load_plugins()


@pytest.fixture(scope="session")
def calf_design():
    from calflab.design import build_design, genome_definition

    return build_design(genome_definition("calf").default_genome())


@pytest.fixture(scope="session")
def calf_model(calf_design):
    from calflab.components import library
    from calflab.sim import compile_mjcf

    return compile_mjcf(calf_design.spec, library())
