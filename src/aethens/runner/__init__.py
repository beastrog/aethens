"""Run a verifier against a disposable copy of a task. Docker by default; local only on request."""

from aethens.runner.base import Limits, Runner, RunResult, RunSpec
from aethens.runner.docker import DockerRunner
from aethens.runner.local import LocalRunner
from aethens.runner.workdir import build_workdir

__all__ = [
    "DockerRunner",
    "Limits",
    "LocalRunner",
    "RunResult",
    "RunSpec",
    "Runner",
    "build_workdir",
]
