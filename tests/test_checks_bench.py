"""C001/C002 against real bench fixtures in Docker (B4)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.audit import run_audit
from aethens.checks import C001GoldSanity, C002Flakiness, CheckContext
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner

pytestmark = pytest.mark.docker

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "bench" / "tasks"


def _ctx(seed: int = 1) -> CheckContext:
    return CheckContext(runner=DockerRunner(), seed=seed, budget=Budget.STANDARD)


@pytest.mark.parametrize(
    ("task", "subject"),
    [
        ("noassert-exists", "starter"),
        ("noassert-swallow", "starter"),
        ("brokengold-offbyone", "gold"),
        ("brokengold-wrongfile", "gold"),
    ],
)
def test_c001_finds_planted_defect(task: str, subject: str) -> None:
    findings = C001GoldSanity().run(load_task(BENCH / task), _ctx())
    assert [f.evidence.subject for f in findings] == [subject]
    assert findings[0].severity is Severity.ERROR


@pytest.mark.parametrize("task", ["flaky-setorder", "flaky-hashshard"])
def test_c002_finds_planted_defect(task: str) -> None:
    findings = C002Flakiness().run(load_task(BENCH / task), _ctx())
    assert len(findings) == 1 and findings[0].severity is Severity.ERROR
    extra = findings[0].evidence.extra
    assert int(extra["pass_count"]) > 0 and int(extra["fail_count"]) > 0


@pytest.mark.parametrize("task", ["ctrl-clamp", "ctrl-tags-sorted"])
def test_controls_are_silent(task: str) -> None:
    t = load_task(BENCH / task)
    assert C001GoldSanity().run(t, _ctx()) == []
    assert C002Flakiness().run(t, _ctx()) == []


def test_deterministic_under_seed() -> None:
    t = load_task(BENCH / "flaky-setorder")
    a = C002Flakiness().run(t, _ctx(seed=5))
    b = C002Flakiness().run(t, _ctx(seed=5))
    assert [f.to_dict()["evidence"]["exit_codes"] for f in a] == [
        f.to_dict()["evidence"]["exit_codes"] for f in b
    ]
    assert [f.id for f in a] == [f.id for f in b]


@pytest.mark.parametrize("task", ["brokengold-offbyone", "flaky-setorder"])
def test_repro_command_reproduces(task: str) -> None:
    t = load_task(BENCH / task)
    report = run_audit([t], [C001GoldSanity(), C002Flakiness()], _ctx(seed=3))
    assert report.findings
    for f in report.findings:
        argv = shlex.split(f.repro)
        assert argv[0] == "aethens"
        # --no-cache: the repro string itself is unchanged, but the default cache would
        # otherwise return the stored finding without running the verifier again.
        cmd = [sys.executable, "-m", "aethens", *argv[1:], "--no-cache"]
        proc = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True, timeout=300, env=dict(os.environ)
        )
        assert proc.returncode in (0, 1), proc.stderr
        data = json.loads(proc.stdout)
        again = [g for g in data["findings"] if g["id"] == f.id]
        assert len(again) == 1, (f.repro, data["findings"])
        assert again[0]["evidence"]["exit_codes"] == list(f.evidence.exit_codes)
