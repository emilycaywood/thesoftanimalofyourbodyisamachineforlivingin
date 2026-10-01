"""Plugin system: base classes, registry, discovery.

    from calflab.plugins import register, FitnessTerm
    from calflab.schema import P

    @register
    class QuietFeet(FitnessTerm):
        key = "quiet_feet"
        ...
"""

from calflab.plugins.base import Plugin, Registry, register, registry
from calflab.plugins.discovery import PluginWatcher, load_plugins
from calflab.plugins.types import (
    BASES,
    PLUGIN_TYPES,
    Analysis,
    Behavior,
    BehaviorDescriptor,
    BuildContext,
    Command,
    ComponentProvider,
    ComputeBackend,
    ControlInfo,
    Controller,
    ExportContext,
    Exporter,
    FitnessTerm,
    GeneDefinition,
    JointType,
    Observation,
    Optimizer,
    Panel,
    PartGenerator,
    Simulator,
    Task,
    VectorDim,
)

__all__ = [
    "BASES",
    "PLUGIN_TYPES",
    "Analysis",
    "Behavior",
    "BehaviorDescriptor",
    "BuildContext",
    "Command",
    "ComponentProvider",
    "ComputeBackend",
    "ControlInfo",
    "Controller",
    "ExportContext",
    "Exporter",
    "FitnessTerm",
    "GeneDefinition",
    "JointType",
    "Observation",
    "Optimizer",
    "Panel",
    "PartGenerator",
    "Plugin",
    "PluginWatcher",
    "Registry",
    "Simulator",
    "Task",
    "VectorDim",
    "load_plugins",
    "register",
    "registry",
]
