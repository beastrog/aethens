"""A fake runner for check unit tests (no Docker, no subprocess)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from aethens.runner import RunResult, RunSpec


def result(
    code: int | None = 0,
    timed_out: bool = False,
    out: str = "",
    err: str = "",
    duration_s: float = 0.01,
) -> RunResult:
    return RunResult(
        exit_code=None if timed_out else code,
        timed_out=timed_out,
        oom_killed=False,
        stdout_tail=out,
        stderr_tail=err,
        duration_s=duration_s,
        truncated=False,
        mode="fake",
        argv=("fake",),
    )


def overlay_name(spec: RunSpec) -> str:
    """'starter' for a starting-state run, else the overlay directory name (e.g. 'gold')."""
    layers = spec.layers
    if len(layers) == 2:
        return "starter"
    return Path(layers[1][0]).name


class FakeRunner:
    mode = "fake"

    def __init__(self, decide: Callable[[RunSpec, int], RunResult]) -> None:
        self.decide = decide
        self.specs: list[RunSpec] = []

    def run(self, spec: RunSpec) -> RunResult:
        self.specs.append(spec)
        return self.decide(spec, len(self.specs) - 1)
