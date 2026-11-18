"""C007 reward-hacking probes against real bench fixtures in the Docker sandbox (D5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import C007RewardHacking, CheckContext
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner

pytestmark = pytest.mark.docker

BENCH = Path(__file__).resolve().parent.parent / "bench" / "tasks"


def _categories(task: str) -> set[str]:
    ctx = CheckContext(runner=DockerRunner(), seed=0, budget=Budget.STANDARD)
    findings = C007RewardHacking().run(load_task(BENCH / task), ctx)
    return {f.evidence.extra["category"] for f in findings if f.severity is not Severity.INFO}


def test_plain_unittest_verifier_is_gameable() -> None:
    assert _categories("ctrl-clamp") == {
        "exit-zero",
        "atexit-override",
        "framework-patch",
        "always-equal",
        "hardcoded-visible",
    }


def test_sitecustomize_hook_needs_the_workdir_on_pythonpath() -> None:
    assert "sitecustomize-hook" in _categories("hack-sitecustomize")
    assert "sitecustomize-hook" not in _categories("weak-leap")


def test_framework_patch_survives_setupclass_failure() -> None:
    assert "framework-patch" in _categories("order-classfixture")


@pytest.mark.parametrize("task", ["ctrl-hardened-harness", "ctrl-hardened-cli"])
def test_hardened_verifiers_resist_every_probe(task: str) -> None:
    assert _categories(task) == set()


def test_starter_passing_is_left_to_c001() -> None:
    assert _categories("noassert-exists") == set()
