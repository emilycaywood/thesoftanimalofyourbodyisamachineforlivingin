"""Later-phase optimizers, scaffolded with real interfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from calflab.plugins import ComputeBackend, Optimizer, register
from calflab.schema import P


@register
class PPOTraining(Optimizer):
    """Phase 2: PPO policy training (MJX / MuJoCo Playground) on a remote GPU backend.

    Plan: export the compiled MJCF and reward definition (fitness preset +
    imitation term with a Blender reference clip) as a job bundle
    (:class:`calflab.compute.remote.CloudNotebook`), train remotely, import the
    ONNX policy and training curves into the registry as a ``train`` run, and
    expose the policy as a ``Controller`` plugin for rollouts and Deploy.
    """

    key = "ppo"
    label = "PPO policy training"
    description = "Reinforcement learning with imitation rewards on a remote GPU (Phase 2)."
    stub = True

    class Params(BaseModel):
        total_steps: int = P(50_000_000, ge=100_000, le=2_000_000_000, ui="number", desc="Environment steps.")
        num_envs: int = P(4096, ge=64, le=32768, ui="number", desc="Parallel environments on the GPU.")
        learning_rate: float = P(3e-4, ge=1e-6, le=1e-2, ui="number", desc="Adam learning rate.")
        imitation_clip: str = P("", desc="Motion-library clip used for the imitation reward.")
        randomize: bool = P(True, desc="Apply the domain randomization preset during training.")

    def run(self, problem: Any, backend: ComputeBackend, report: Callable[..., None]) -> Any:
        # TODO(phase2): bundle -> remote train -> import ONNX + curves.
        raise NotImplementedError("PPO training is scaffolded for Phase 2 (needs a remote GPU backend).")


@register
class InteractiveSelection(Optimizer):
    """Phase 2: the designer picks parents from a grid of animated candidates."""

    key = "interactive"
    label = "Interactive selection"
    description = "Human-in-the-loop evolution: choose parents from animated thumbnails (planned)."
    stub = True

    class Params(BaseModel):
        population: int = P(9, ge=4, le=25, desc="Candidates shown per generation.")
        sigma: float = P(0.1, ge=0.01, le=0.5, step=0.01, desc="Mutation strength.")

    def run(self, problem: Any, backend: ComputeBackend, report: Callable[..., None]) -> Any:
        # TODO(phase2): yield a population, wait for a `SelectParents` command, breed, repeat.
        raise NotImplementedError("Interactive selection is scaffolded; the selection UI is planned.")
