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
    """IDs of containers with label aethens.run currently on the daemon."""
    out = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=aethens.run"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


def _owned_containers(tmp_root: Path) -> set[str]:
    """aethens.run containers that bind-mount a path under this test's tmp_root.

    Other processes on a shared daemon may create or remove aethens.run containers
    during a test; only this runner's mounts are this test's responsibility.
    """
    root = tmp_root.resolve()
    owned: set[str] = set()
    for cid in _containers():
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{range .Mounts}}{{.Source}}\n{{end}}", cid],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            continue  # already gone
        for src in r.stdout.splitlines():
            if not src:
                continue
            path = Path(src).resolve()
            if path == root or path.is_relative_to(root):
                owned.add(cid)
                break
    return owned


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


def _assert_clean(runner: DockerRunner, _before: set[str]) -> None:
    # `_before` is the pre-run global snapshot kept at call sites for readability.
    # We do not compare the global aethens.run set for equality: that flakes when
    # another process creates or removes a container. Instead, any aethens.run
    # container that still bind-mounts this runner's tmp_root is a leftover.
    assert runner.tmp_root is not None
    leftover = _owned_containers(runner.tmp_root)
    assert leftover == set(), leftover
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


# --- timeout accounting under load (fix for the ctrl-tags-sorted false positive) ---------------
# Under heavy host load `docker run` can spend many seconds creating, starting or tearing down a
# container. That overhead is not verifier run time and must not turn a fast, passing verifier into
# a timeout (it did: 38/300 passing runs of ctrl-tags-sorted timed out with 128 concurrent runs and
# 24 CPU burners). A wrapper around the real docker CLI injects the delay deterministically.


def _slow_docker(tmp_path: Path, before_run: float, after_run: float) -> str:
    real = subprocess.run(["which", "docker"], capture_output=True, text=True, check=True)
    script = tmp_path / "slow-docker"
    script.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = run ]; then\n'
        f"  sleep {before_run}\n"
        f'  {real.stdout.strip()} "$@"; rc=$?\n'
        f"  sleep {after_run}\n"
        "  exit $rc\n"
        "fi\n"
        f'exec {real.stdout.strip()} "$@"\n'
    )
    script.chmod(0o755)
    return str(script)


def test_slow_container_start_is_not_a_timeout(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    runner = DockerRunner(docker_bin=_slow_docker(tmp_path, 4, 0), tmp_root=tmp_path / "runs")
    before = _containers()
    r = runner.run(_spec(tmp_path, "print('fast')", 2))
    assert r.passed and not r.timed_out and r.exit_code == 0
    assert "fast" in r.stdout_tail
    _assert_clean(runner, before)


def test_slow_container_teardown_is_not_a_timeout(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    runner = DockerRunner(docker_bin=_slow_docker(tmp_path, 0, 4), tmp_root=tmp_path / "runs")
    before = _containers()
    r = runner.run(_spec(tmp_path, "print('fast')", 2))
    assert r.passed and not r.timed_out and r.exit_code == 0
    _assert_clean(runner, before)


def test_hung_verifier_after_slow_start_still_times_out(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    runner = DockerRunner(docker_bin=_slow_docker(tmp_path, 3, 0), tmp_root=tmp_path / "runs")
    before = _containers()
    r = runner.run(_spec(tmp_path, "import time\ntime.sleep(600)", 2))
    assert r.timed_out and not r.passed and r.exit_code is None
    assert r.duration_s < 30
    _assert_clean(runner, before)


def test_verifier_slower_than_timeout_is_a_timeout(runner: DockerRunner, tmp_path: Path) -> None:
    # In-container run time over timeout_s is a timeout even if the process exits by itself.
    r = runner.run(_spec(tmp_path, "import time\ntime.sleep(4)\nprint('late')", 2))
    assert r.timed_out and not r.passed


_INFLATE_INSPECT = """\
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

REAL = __REAL__
EXTRA = __EXTRA__


def _bump(ts: str, extra: float) -> str:
    raw = ts.replace("Z", "+00:00")
    if "." in raw:
        head, rest = raw.split(".", 1)
        frac, off = rest, "+00:00"
        for i, ch in enumerate(rest):
            if ch in "+-":
                frac, off = rest[:i], rest[i:]
                break
        raw = f"{head}.{frac[:6].ljust(6, '0')}{off}"
    t = datetime.fromisoformat(raw)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t = t + timedelta(seconds=extra)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "000Z"


args = sys.argv[1:]
if args and args[0] == "inspect":
    r = subprocess.run([REAL, *args], capture_output=True)
    sys.stderr.buffer.write(r.stderr)
    if r.returncode != 0:
        sys.stdout.buffer.write(r.stdout)
        raise SystemExit(r.returncode)
    state = json.loads(r.stdout.decode())
    finished = str(state.get("FinishedAt") or "")
    if finished and not finished.startswith("0001-"):
        state["FinishedAt"] = _bump(finished, EXTRA)
    sys.stdout.write(json.dumps(state))
    raise SystemExit(0)
os.execvp(REAL, [REAL, *args])
"""


def _inflate_inspect_docker(tmp_path: Path, extra_s: float) -> str:
    """A docker CLI wrapper that adds extra_s to inspect's FinishedAt (a clock jump)."""
    real = subprocess.run(["which", "docker"], capture_output=True, text=True, check=True)
    wrapper = tmp_path / "inflate_inspect.py"
    wrapper.write_text(
        _INFLATE_INSPECT.replace("__REAL__", repr(real.stdout.strip())).replace(
            "__EXTRA__", repr(extra_s)
        )
    )
    wrapper.chmod(0o755)
    return str(wrapper)


def test_inflated_daemon_runtime_does_not_timeout_a_fast_verifier(tmp_path: Path) -> None:
    # Post-exit D-064 check must cap FinishedAt-StartedAt by host elapsed time, otherwise a
    # daemon clock jump turns a fast run into exit_code None (test_deterministic_under_seed).
    (tmp_path / "runs").mkdir()
    runner = DockerRunner(
        docker_bin=_inflate_inspect_docker(tmp_path, 30), tmp_root=tmp_path / "runs"
    )
    r = runner.run(_spec(tmp_path, "print('fast')", 2))
    assert r.passed and not r.timed_out and r.exit_code == 0, (
        r.timed_out,
        r.exit_code,
        r.duration_s,
        r.stderr_tail,
    )
    # Host wall time includes create/teardown; 30 s is comfortably below STARTUP_GRACE_S.
    assert r.duration_s < 30
    assert "fast" in r.stdout_tail
    # Assert only this runner's workdir; do not compare the global aethens.run
    # container set (shared-daemon flake; fixed separately).
    assert runner.tmp_root is not None
    assert list(runner.tmp_root.iterdir()) == []


def _delay_inflate_docker(tmp_path: Path, before: float, after: float, extra: float) -> str:
    """Sleep around ``docker run`` and add ``extra`` seconds to inspect's FinishedAt."""
    inflate = _inflate_inspect_docker(tmp_path, extra)
    script = tmp_path / "delay-inflate-docker"
    script.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = run ]; then\n'
        f"  sleep {before}\n"
        f'  {inflate} "$@"; rc=$?\n'
        f"  sleep {after}\n"
        "  exit $rc\n"
        "fi\n"
        f'exec {inflate} "$@"\n'
    )
    script.chmod(0o755)
    return str(script)


@pytest.mark.parametrize(("before", "after"), [(3.0, 0.0), (0.0, 3.0)])
def test_overhead_plus_clock_jump_is_not_a_timeout(
    tmp_path: Path, before: float, after: float
) -> None:
    # Create or teardown longer than timeout_s, plus a FinishedAt jump. Capping the daemon
    # delta by the full host wait still exceeds timeout_s and reports exit_code None.
    # That hole matches test_deterministic_under_seed on hosted check (3.12): one seeded
    # run of flaky-setorder came back [1, 1, None, 0, 1] and the repeat [1, 1, 0, 0, 1]
    # (actions/runs/45989844568, attempt 1), after the total-elapsed cap was already on main.
    # The job log has no per-run timestamps, so this test locks the code path that produces
    # that symptom; it does not replay that runner's daemon clock.
    (tmp_path / "runs").mkdir()
    runner = DockerRunner(
        docker_bin=_delay_inflate_docker(tmp_path, before, after, 30),
        tmp_root=tmp_path / "runs",
    )
    r = runner.run(_spec(tmp_path, "print('fast')", 2))
    assert r.passed and not r.timed_out and r.exit_code == 0, (
        r.timed_out,
        r.exit_code,
        r.duration_s,
        r.stderr_tail,
    )
    assert r.duration_s >= before + after
    assert "fast" in r.stdout_tail
    assert runner.tmp_root is not None
    assert list(runner.tmp_root.iterdir()) == []
