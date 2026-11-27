"""CLI behaviour: formats, fail-on and exit codes 0/1/2/3 (B6)."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def aethens(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aethens", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_tool_error_exit_2() -> None:
    r = aethens("audit", "does/not/exist")
    assert r.returncode == 2
    assert "MissingFileError" in r.stderr
    assert r.stdout == ""


def test_bad_task_exit_2(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text("schema: nope\n")
    r = aethens("audit", str(tmp_path))
    assert r.returncode == 2 and "SchemaError" in r.stderr


def test_docker_unavailable_exit_2(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "aethens", "audit", "examples/add-two"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": str(tmp_path)},  # no docker binary on PATH
    )
    assert r.returncode == 2 and "DockerUnavailableError" in r.stderr


def test_unsafe_local_warns_loudly() -> None:
    r = aethens(
        "audit", "examples/add-two", "--unsafe-local", "--check", "C001", "--budget", "smoke"
    )
    assert "WARNING" in r.stderr and "without container isolation" in r.stderr
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["findings"] == []
    assert all("--unsafe-local" in f["repro"] for f in data["findings"])


@pytest.mark.docker
def test_clean_task_exit_0_json() -> None:
    r = aethens(
        "audit", "examples/add-two", "--budget", "smoke", "--check", "C001", "--check", "C003"
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["schema"] == "aethens-report/v2" and data["checks_run"] == ["C001", "C003"]


@pytest.mark.docker
def test_findings_exit_1_and_markdown() -> None:
    r = aethens(
        "audit", "bench/tasks/brokengold-offbyone", "--check", "C001", "--format", "markdown"
    )
    assert r.returncode == 1
    assert r.stdout.startswith("## Aethens report")
    assert "Gold solution fails the verifier" in r.stdout


@pytest.mark.docker
def test_fail_on_threshold() -> None:
    # weak-llm only has a warning (llm-unreviewed label) from C003.
    r = aethens("audit", "bench/tasks/weak-llm", "--check", "C003")
    assert r.returncode == 0
    r = aethens("audit", "bench/tasks/weak-llm", "--check", "C003", "--fail-on", "warning")
    assert r.returncode == 1


@pytest.mark.docker
def test_output_file(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    r = aethens(
        "audit", "examples/add-two", "--check", "C001", "--format", "markdown", "--output", str(out)
    )
    assert r.returncode == 0 and r.stdout == ""
    assert out.read_text().startswith("## Aethens report")


@pytest.mark.docker
def test_gold_timeout_exit_3() -> None:
    r = aethens("audit", "tests/fixtures/hung-gold", "--check", "C001")
    assert r.returncode == 3, r.stderr
    data = json.loads(r.stdout)
    assert data["findings"][0]["evidence"]["timed_out"] is True


@pytest.mark.docker
def test_every_finding_in_a_sample_report_reproduces() -> None:
    import shlex

    r = aethens("audit", "bench/tasks/weak-sign", "--budget", "smoke", "--seed", "4")
    assert r.returncode == 1, r.stderr
    findings = json.loads(r.stdout)["findings"]
    assert {f["check_id"] for f in findings} >= {"C003", "C004"}
    for f in findings:
        argv = shlex.split(f["repro"])
        assert argv[:2] == ["aethens", "audit"]
        again = aethens(*argv[1:])
        match = [g for g in json.loads(again.stdout)["findings"] if g["id"] == f["id"]]
        assert len(match) == 1, f["repro"]
        assert match[0]["evidence"]["exit_codes"] == f["evidence"]["exit_codes"]


# --- hardening review 2026-11-27 -----------------------------------------------------------------


def test_unexpected_internal_error_is_exit_2_not_1(monkeypatch: pytest.MonkeyPatch) -> None:
    # An uncaught exception made Python exit 1, which CI reads as "findings": a crash must be a
    # tool error (2).
    cli = importlib.import_module("aethens.cli.main")

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("injected internal failure")

    monkeypatch.setattr(cli, "run_audit", boom)
    monkeypatch.setattr(cli.DockerRunner, "ensure_available", lambda self: None)
    assert cli.main(["audit", "examples/add-two", "--check", "C001"]) == 2


def test_unwritable_output_is_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = importlib.import_module("aethens.cli.main")
    from aethens.models import Budget, Report

    empty = Report(
        tool_version="x",
        task_ids=("t",),
        checks_run=("C001",),
        budget=Budget.SMOKE,
        seed=0,
        findings=(),
        coverage=(),
        started_at="2026-01-01T00:00:00+00:00",
        duration_s=0.0,
    )
    monkeypatch.setattr(cli, "run_audit", lambda *_a, **_k: empty)
    monkeypatch.setattr(cli.DockerRunner, "ensure_available", lambda self: None)
    out = tmp_path / "missing-dir" / "report.json"
    assert cli.main(["audit", "examples/add-two", "--output", str(out)]) == 2


@pytest.mark.docker
def test_sigterm_removes_running_containers(tmp_path: Path) -> None:
    import os
    import shutil
    import signal
    import time

    def ours() -> set[str]:
        out = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "label=aethens.run"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return set(out.split())

    task = tmp_path / "hung"
    shutil.copytree(REPO / "tests" / "fixtures" / "hung-gold", task)
    before = ours()
    proc = subprocess.Popen(
        [sys.executable, "-m", "aethens", "audit", str(task), "--check", "C001"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not (ours() - before) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert ours() - before, "the audit never started a container"
        os.kill(proc.pid, signal.SIGTERM)
        _out, err = proc.communicate(timeout=90)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 2, err
    assert "terminated" in err.lower()
    assert ours() == before
