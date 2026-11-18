"""C003/C004 against real bench fixtures in Docker (B5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import (
    C001GoldSanity,
    C002Flakiness,
    C003LabeledCandidates,
    C004MutationProbes,
    CheckContext,
)
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner

pytestmark = pytest.mark.docker

BENCH = Path(__file__).resolve().parent.parent / "bench" / "tasks"


def _ctx(budget: Budget = Budget.STANDARD) -> CheckContext:
    return CheckContext(runner=DockerRunner(), seed=0, budget=budget)


@pytest.mark.parametrize(
    ("task", "subject", "severity"),
    [
        ("weak-sign", "candidate:no-zero", Severity.ERROR),
        ("weak-llm", "candidate:naive-slice", Severity.WARNING),
        ("strict-float", "candidate:fsum", Severity.ERROR),
        ("strict-message", "candidate:other-message", Severity.ERROR),
    ],
)
def test_c003_finds_planted_defect(task: str, subject: str, severity: Severity) -> None:
    findings = C003LabeledCandidates().run(load_task(BENCH / task), _ctx())
    assert [(f.evidence.subject, f.severity) for f in findings] == [(subject, severity)]


def test_c004_finds_survivors_on_weak_tests() -> None:
    findings = C004MutationProbes().run(load_task(BENCH / "weak-leap"), _ctx())
    assert findings and all(f.severity is Severity.INFO for f in findings)


@pytest.mark.parametrize("task", ["ctrl-wordfmt", "ctrl-llm-labels", "ctrl-clamp"])
def test_controls_have_no_error_or_warning(task: str) -> None:
    t = load_task(BENCH / task)
    checks = [C001GoldSanity(), C002Flakiness(), C003LabeledCandidates(), C004MutationProbes()]
    for check in checks:
        for f in check.run(t, _ctx(Budget.SMOKE)):
            assert f.severity is Severity.INFO, (check.id, f.title)
