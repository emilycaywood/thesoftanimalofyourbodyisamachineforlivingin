"""Built-in plugins. Importing this package registers them.

Built-ins use exactly the same mechanism as third-party plugins: the package is
listed under the ``calflab.plugins`` entry-point group in ``pyproject.toml``.
"""

from calflab.app import commands, footage_commands, physics_commands  # noqa: F401
from calflab.behave import trackers  # noqa: F401
from calflab.builtin import joint_types, outputs, primitives, simulators, stubs  # noqa: F401
from calflab.compute import local, remote  # noqa: F401
from calflab.control import behaviors, cpg, feral_motion, weight_shift  # noqa: F401
from calflab.evolve import map_elites  # noqa: F401
from calflab.evolve import stubs as evolve_stubs  # noqa: F401
from calflab.export import cad, geometry  # noqa: F401
from calflab.fitness import terms  # noqa: F401
from calflab.morphology import calf, feral  # noqa: F401
