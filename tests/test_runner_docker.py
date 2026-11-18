"""Docker runner behaviour against a real daemon (B3). Marked `docker`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from aethens.errors import ContainerStartError
from aethens.runner import DockerRunner, Limits, RunSpec

pytestmark = pytest.mark.docker


def _containers() -> set[str]:
    out = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=aethens.run"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


@pytest.fixture
def runner(tmp_path: Path) -> DockerRunner:
    (tmp_path / "runs").mkdir()
    return DockerRunner(tmp_root=tmp_path / "runs")


def _spec(tmp_path: Path, code: str, timeout: float = 20.0, **kw: object) -> RunSpec:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "probe.py").write_text(code)
    return RunSpec(
        image="python:3.12-slim",
        command=("python", "probe.py"),
        layers=((src, Path(".")),),
        timeout_s=timeout,
        **kw,  # type: ignore[arg-type]
    )


def _assert_clean(runner: DockerRunner, before: set[str]) -> None:
    assert _containers() == before
    assert runner.tmp_root is not None
    assert list(runner.tmp_root.iterdir()) == []


def test_passing_run(runner: DockerRunner, tmp_path: Path) -> None:
    before = _containers()
    r = runner.run(_spec(tmp_path, "print('hello')"))
    assert r.exit_code == 0 and r.passed and not r.timed_out
    assert "hello" in r.stdout_tail
    assert r.mode == "docker"
    _assert_clean(runner, before)


def test_failing_exit_code(runner: DockerRunner, tmp_path: Path) -> None:
    r = runner.run(_spec(tmp_path, "import sys; sys.exit(3)"))
    assert r.exit_code == 3 and not r.passed


def test_hung_verifier_times_out_and_is_cleaned_up(runner: DockerRunner, tmp_path: Path) -> None:
    before = _containers()
    r = runner.run(_spec(tmp_path, "import time\nprint('start', flush=True)\ntime.sleep(600)", 2))
    assert r.timed_out and not r.passed
    assert r.duration_s < 30
    assert "start" in r.stdout_tail
    _assert_clean(runner, before)


def test_memory_blowup_is_killed(runner: DockerRunner, tmp_path: Path) -> None:
    code = "b = []\nwhile True:\n    b.append(bytearray(10**7))\n"
    r = runner.run(_spec(tmp_path, code, limits=Limits(memory_mb=128)))
    assert not r.passed
    assert r.oom_killed or r.exit_code == 137


def test_network_attempt_blocked(runner: DockerRunner, tmp_path: Path) -> None:
    code = (
        "import socket\n"
        "s = socket.socket()\n"
        "s.settimeout(3)\n"
        "try:\n"
        "    s.connect(('1.1.1.1', 80))\n"
        "    print('CONNECTED')\n"
        "except OSError as e:\n"
        "    print('BLOCKED', e)\n"
        "import os\n"
        "print('IFACES', sorted(os.listdir('/sys/class/net')))\n"
    )
    r = runner.run(_spec(tmp_path, code))
    assert "BLOCKED" in r.stdout_tail and "CONNECTED" not in r.stdout_tail
    assert "IFACES ['lo']" in r.stdout_tail


def test_huge_output_is_truncated(runner: DockerRunner, tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "for i in range(200000):\n"
        "    sys.stdout.write('x' * 99 + '\\n')\n"
        "print('LAST')\n"
    )
    r = runner.run(_spec(tmp_path, code, limits=Limits(max_output_bytes=4096)))
    assert r.truncated
    assert len(r.stdout_tail) < 4096 + 100
    assert r.stdout_tail.rstrip().endswith("LAST")


def test_container_start_failure(runner: DockerRunner, tmp_path: Path) -> None:
    before = _containers()
    src = tmp_path / "src"
    src.mkdir()
    spec = RunSpec(
        image="aethens-test-image-that-does-not-exist:never",
        command=("python", "-c", "1"),
        layers=((src, Path(".")),),
        timeout_s=10,
    )
    with pytest.raises(ContainerStartError):
        runner.run(spec)
    _assert_clean(runner, before)


def test_cleanup_after_exception(
    runner: DockerRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _containers()

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("injected failure after the container started")

    monkeypatch.setattr(runner, "_inspect", boom)
    with pytest.raises(RuntimeError, match="injected"):
        runner.run(_spec(tmp_path, "print('x')"))
    _assert_clean(runner, before)


def test_host_environment_does_not_leak(
    runner: DockerRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AETHENS_SECRET_PROBE", "must-not-leak")
    r = runner.run(_spec(tmp_path, "import os\nprint(sorted(os.environ.items()))"))
    assert "must-not-leak" not in r.stdout_tail
    assert "AETHENS_SECRET_PROBE" not in r.stdout_tail


def test_isolation_properties(runner: DockerRunner, tmp_path: Path) -> None:
    code = (
        "import os\n"
        "print('UID', os.getuid())\n"
        "status = open('/proc/self/status').read()\n"
        "keys = ('CapEff', 'CapBnd', 'NoNewPrivs')\n"
        "caps = [l for l in status.splitlines() if l.startswith(keys)]\n"
        "print(caps)\n"
        "try:\n"
        "    open('/usr/aethens-probe', 'w')\n"
        "    print('ROOTFS WRITABLE')\n"
        "except OSError:\n"
        "    print('ROOTFS READONLY')\n"
        "open('/tmp/ok', 'w').write('tmp ok')\n"
        "open('scratch.txt', 'w').write('work ok')\n"
        "print('WRITES OK')\n"
    )
    r = runner.run(_spec(tmp_path, code))
    out = r.stdout_tail
    assert "UID 0" not in out
    assert "CapEff:\\t0000000000000000" in out
    assert "CapBnd:\\t0000000000000000" in out
    assert "NoNewPrivs:\\t1" in out
    assert "ROOTFS READONLY" in out
    assert "WRITES OK" in out


def test_original_task_is_untouched(runner: DockerRunner, tmp_path: Path) -> None:
    r = runner.run(_spec(tmp_path, "open('probe.py', 'w').write('overwritten')\nopen('new', 'w')"))
    assert r.passed
    assert (tmp_path / "src" / "probe.py").read_text().startswith("open(")
    assert not (tmp_path / "src" / "new").exists()


def test_pids_limit(runner: DockerRunner, tmp_path: Path) -> None:
    code = (
        "import os, sys\n"
        "n = 0\n"
        "try:\n"
        "    for _ in range(200):\n"
        "        if os.fork() == 0:\n"
        "            import time; time.sleep(30); os._exit(0)\n"
        "        n += 1\n"
        "except OSError:\n"
        "    print('FORK LIMITED at', n)\n"
        "    sys.exit(0)\n"
        "print('FORKED', n)\n"
    )
    r = runner.run(_spec(tmp_path, code, timeout=20, limits=Limits(pids=32)))
    assert "FORK LIMITED" in r.stdout_tail


def test_extra_env_is_passed(runner: DockerRunner, tmp_path: Path) -> None:
    r = runner.run(
        _spec(
            tmp_path, "import os\nprint(os.environ['PYTHONHASHSEED'])", env={"PYTHONHASHSEED": "42"}
        )
    )
    assert r.stdout_tail.strip() == "42"


def test_runs_as_non_root_even_when_files_are_read_only(
    runner: DockerRunner, tmp_path: Path
) -> None:
    r = runner.run(_spec(tmp_path, "import os\nprint(os.getuid(), os.getgid())"))
    uid, gid = (int(x) for x in r.stdout_tail.split())
    assert uid != 0
    if os.getuid() != 0:
        assert uid == os.getuid() and gid == os.getgid()
