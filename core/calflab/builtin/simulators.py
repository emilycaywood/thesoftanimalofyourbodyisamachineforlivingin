"""Built-in simulators."""

from __future__ import annotations

from typing import Any

from calflab.components import library
from calflab.model.spec import RobotSpec
from calflab.plugins import Controller, Simulator, register
from calflab.sim.mjcf import CompiledModel, CompileOptions, compile_mjcf
from calflab.sim.rollout import Rollout, SimSettings, run_rollout


@register
class MuJoCoSimulator(Simulator):
    """MuJoCo on CPU."""

    key = "mujoco"
    label = "MuJoCo (CPU)"
    description = "Rigid-body simulation with MuJoCo on the CPU; streams body poses."
    Params = SimSettings

    def compile(self, spec: RobotSpec, options: CompileOptions | None = None) -> CompiledModel:
        return compile_mjcf(spec, library(), options, seed=self.params.seed)  # type: ignore[attr-defined]

    def rollout(
        self,
        spec: RobotSpec | CompiledModel,
        controller: Controller,
        settings: SimSettings | None = None,
        **kwargs: Any,
    ) -> Rollout:
        settings = settings or self.params  # type: ignore[assignment]
        cm = spec if isinstance(spec, CompiledModel) else compile_mjcf(spec, library(), seed=settings.seed)  # type: ignore[union-attr]
        return run_rollout(cm, controller, settings, library(), **kwargs)  # type: ignore[arg-type]


@register
class MJXSimulator(Simulator):
    """Phase 2: MuJoCo MJX on a remote NVIDIA GPU (batched rollouts for RL)."""

    key = "mjx"
    label = "MuJoCo MJX (remote GPU)"
    description = "Batched GPU simulation for training; runs through a remote compute backend (Phase 2)."
    stub = True

    def rollout(self, spec: Any, controller: Any, settings: Any = None, **kwargs: Any) -> Any:
        # TODO(phase2): ship the compiled MJCF in a job bundle and run MJX remotely.
        raise NotImplementedError("MJX needs CUDA; use the CloudNotebook or RemoteSSH backend (Phase 2).")
