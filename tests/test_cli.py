"""CLI behaviour: formats, fail-on and exit codes 0/1/2/3 (B6)."""

from __future__ import annotations

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
