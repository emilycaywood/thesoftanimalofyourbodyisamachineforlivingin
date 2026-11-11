"""Built-in plugins. Importing this package registers them.

Built-ins use exactly the same mechanism as third-party plugins: the package is
listed under the ``calflab.plugins`` entry-point group in ``pyproject.toml``.
"""

from calflab.app import (  # noqa: F401
    commands,
    footage_commands,
    interpret_commands,
    physics_commands,
)
from calflab.behave import trackers  # noqa: F401
from calflab.builtin import joint_types, outputs, primitives, simulators, stubs  # noqa: F401
from calflab.compute import local, remote  # noqa: F401
from calflab.control import (  # noqa: F401
    behaviors,
    cpg,
    feral_motion,
    interpreted,
    outcome,
    weight_shift,
)
from calflab.evolve import (
    diversity,  # noqa: F401
    hardware,  # noqa: F401
    map_elites,  # noqa: F401
    vigour,  # noqa: F401
)
from calflab.evolve import stubs as evolve_stubs  # noqa: F401
from calflab.export import cad, geometry  # noqa: F401
from calflab.fitness import outcomes, terms  # noqa: F401
from calflab.morphology import calf, feral  # noqa: F401
