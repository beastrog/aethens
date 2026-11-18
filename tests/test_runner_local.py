"""Explicit unsafe-local runner (B3). Runs real subprocesses, no Docker."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from aethens.runner import Limits, LocalRunner, RunSpec


@pytest.fixture
def runner(tmp_path: Path) -> LocalRunner:
    (tmp_path / "runs").mkdir()
    return LocalRunner(allow_unsafe_local=True, tmp_root=tmp_path / "runs")


def _spec(tmp_path: Path, code: str, timeout: float = 20.0, **kw: object) -> RunSpec:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "probe.py").write_text(code)
    return RunSpec(
        image="python:3.12-slim",  # ignored in local mode
        command=(sys.executable, "probe.py"),
        layers=((src, Path(".")),),
        timeout_s=timeout,
        **kw,  # type: ignore[arg-type]
    )


def test_local_pass_and_cleanup(runner: LocalRunner, tmp_path: Path) -> None:
    r = runner.run(_spec(tmp_path, "print('hi')"))
    assert r.passed and "hi" in r.stdout_tail and r.mode == "local"
    assert runner.tmp_root is not None and list(runner.tmp_root.iterdir()) == []


def test_local_env_is_scrubbed(
    runner: LocalRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AETHENS_SECRET_PROBE", "must-not-leak")
    r = runner.run(_spec(tmp_path, "import os, json\nprint(json.dumps(dict(os.environ)))"))
    import json

    env = json.loads(r.stdout_tail)
    assert "AETHENS_SECRET_PROBE" not in env
    assert set(env) <= {"PATH", "HOME", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "LC_CTYPE"}
    assert env["HOME"] != os.environ.get("HOME")


def test_local_timeout_kills_process_group(runner: LocalRunner, tmp_path: Path) -> None:
    marker = tmp_path / "child-alive"
    code = (
        "import os, time, sys\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    time.sleep(3)\n"
        f"    open({str(marker)!r}, 'w').write('survived')\n"
        "    os._exit(0)\n"
        "time.sleep(600)\n"
    )
    t0 = time.monotonic()
    r = runner.run(_spec(tmp_path, code, timeout=1))
    assert r.timed_out and time.monotonic() - t0 < 10
    time.sleep(4)
    assert not marker.exists(), "child process outlived the timeout"


def test_local_huge_output_truncated(runner: LocalRunner, tmp_path: Path) -> None:
    code = "import sys\nsys.stdout.write('y' * 5_000_000)\nprint('LAST')\n"
    r = runner.run(_spec(tmp_path, code, limits=Limits(max_output_bytes=2048)))
    assert r.truncated and r.stdout_tail.rstrip().endswith("LAST")


def test_local_memory_limit(runner: LocalRunner, tmp_path: Path) -> None:
    code = "b = []\nwhile True:\n    b.append(bytearray(10**7))\n"
    r = runner.run(_spec(tmp_path, code, limits=Limits(memory_mb=256)))
    assert not r.passed
    assert "MemoryError" in r.stderr_tail or r.exit_code != 0
