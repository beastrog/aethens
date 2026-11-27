"""CLI behaviour: formats, fail-on and exit codes 0/1/2/3 (B6)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def aethens(*args: str) -> subprocess.CompletedProcess[str]:
    # Default cache is on. These tests check a real execution, so they opt out unless the
    # caller already chose a cache directory or passed --no-cache (a cache hit would not re-run).
    argv = list(args)
    if (
        argv
        and argv[0] == "audit"
        and "--help" not in argv
        and "-h" not in argv
        and "--no-cache" not in argv
        and "--cache-dir" not in argv
    ):
        argv.append("--no-cache")
    return subprocess.run(
        [sys.executable, "-m", "aethens", *argv],
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


def test_audit_help_lists_jobs_and_cache() -> None:
    r = aethens("audit", "--help")
    assert r.returncode == 0
    for flag in ("--jobs", "--no-cache", "--cache-dir"):
        assert flag in r.stdout


def test_jobs_must_be_at_least_one() -> None:
    r = aethens(
        "audit",
        "examples/add-two",
        "--unsafe-local",
        "--check",
        "C001",
        "--budget",
        "smoke",
        "--jobs",
        "0",
    )
    assert r.returncode == 2
    assert "AuditConfigError" in r.stderr
    assert "from cache" not in r.stderr


def test_no_cache_and_cache_dir_are_mutually_exclusive(tmp_path: Path) -> None:
    r = aethens(
        "audit", "examples/add-two", "--no-cache", "--cache-dir", str(tmp_path), "--unsafe-local"
    )
    assert r.returncode == 2
    assert "not allowed with" in r.stderr


def test_jobs_keeps_task_order(tmp_path: Path) -> None:
    r = aethens(
        "audit",
        "examples",
        "--unsafe-local",
        "--check",
        "C001",
        "--budget",
        "smoke",
        "--jobs",
        "2",
        "--cache-dir",
        str(tmp_path / "cache"),
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["schema"] == "aethens-report/v2"
    assert data["task_ids"] == ["add-two", "word-format"]
    assert "2 tasks (0 from cache, 2 ran) jobs=2" in r.stderr


def test_interrupted_run_resumes_from_the_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    args = (
        "audit",
        "tests/fixtures/hung-gold",
        "--check",
        "C001",
        "--unsafe-local",
        "--cache-dir",
        str(cache),
    )
    started = time.perf_counter()
    first = aethens(*args)
    first_s = time.perf_counter() - started
    assert first.returncode == 3, first.stderr
    assert "1 task (0 from cache, 1 ran)" in first.stderr
    started = time.perf_counter()
    second = aethens(*args)
    second_s = time.perf_counter() - started
    assert second.returncode == 3, second.stderr
    assert "1 task (1 from cache, 0 ran)" in second.stderr
    # The fixture's verifier sleeps until timeout_s (2). A hit must not do that again.
    assert first_s > 1.5
    assert second_s < 1.0
    left, right = json.loads(first.stdout), json.loads(second.stdout)
    for key in ("started_at", "duration_s"):
        left.pop(key)
        right.pop(key)
    assert left == right
