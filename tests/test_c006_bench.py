"""C006 over-specification against real bench fixtures in Docker (D3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import C006OverSpecified, CheckContext
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner

pytestmark = pytest.mark.docker

BENCH = Path(__file__).resolve().parent.parent / "bench" / "tasks"


def _ctx() -> CheckContext:
    return CheckContext(runner=DockerRunner(), seed=0, budget=Budget.STANDARD)


@pytest.mark.parametrize(
    ("task", "family"),
    [
        ("overspec-source", "loop-to-comprehension"),
        ("overspec-lineno", "reformat"),
        ("overspec-varnames", "rename-locals"),
    ],
)
def test_c006_finds_planted_overspecification(task: str, family: str) -> None:
    findings = C006OverSpecified().run(load_task(BENCH / task), _ctx())
    assert findings and all(f.severity is Severity.WARNING for f in findings)
    assert f"rewrite:{family}" in {f.evidence.subject for f in findings}


@pytest.mark.parametrize(
    "task",
    ["ctrl-overspec-behaviour", "ctrl-signature-pinned", "ctrl-clamp", "ctrl-order-cache"],
)
def test_c006_silent_on_controls(task: str) -> None:
    findings = C006OverSpecified().run(load_task(BENCH / task), _ctx())
    assert [f for f in findings if f.severity is not Severity.INFO] == []
