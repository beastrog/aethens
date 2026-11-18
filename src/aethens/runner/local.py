"""Local runner: NO isolation from the host. Only with an explicit opt-in (``--unsafe-local``).

What it does do: a disposable copy of the task, a scrubbed environment (PATH, a temporary HOME,
and the run's own variables; nothing else is inherited), a new process group that is killed with
SIGKILL on timeout, and rlimits on address space and file size where the OS supports them.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aethens.errors import UnsafeLocalNotAllowedError
from aethens.runner.base import RunResult, RunSpec, TailPump, validate_env
from aethens.runner.workdir import build_workdir

_FSIZE_BYTES = 256 * 1024 * 1024
_LIMITER = Path(__file__).resolve().with_name("_limiter.py")


class LocalRunner:
    mode = "local"

    def __init__(self, *, allow_unsafe_local: bool = False, tmp_root: Path | None = None) -> None:
        if allow_unsafe_local is not True:
            raise UnsafeLocalNotAllowedError(
                "local execution runs task code on the host without isolation; "
                "it needs the explicit --unsafe-local opt-in"
            )
        self.tmp_root = tmp_root

    def run(self, spec: RunSpec) -> RunResult:
        validate_env(spec.env)
        tmp = Path(tempfile.mkdtemp(prefix="aethens-local-", dir=self.tmp_root))
        try:
            work, home = tmp / "work", tmp / "home"
            work.mkdir()
            home.mkdir()
            build_workdir(spec.layers, work)
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(home),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }
            env.update(spec.env)
            mem = spec.limits.memory_mb * 1024 * 1024
            argv = [
                sys.executable,
                "-I",  # isolated: ignores PYTHON* variables and user site; stdlib only
                str(_LIMITER),
                str(mem),
                str(_FSIZE_BYTES),
                "--",
                *spec.command,
            ]
            return self._execute(spec, argv, work, env)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _execute(
        self, spec: RunSpec, argv: list[str], work: Path, env: dict[str, str]
    ) -> RunResult:
        limit = spec.limits.max_output_bytes
        start = time.monotonic()
        proc = subprocess.Popen(  # noqa: S603 - argument list, never a shell
            argv,
            cwd=work,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert proc.stdout is not None and proc.stderr is not None
        out, err = TailPump(proc.stdout, limit), TailPump(proc.stderr, limit)
        timed_out = False
        try:
            proc.wait(timeout=spec.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Kill the whole group: children must not outlive the run (also on success).
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        duration = time.monotonic() - start
        out.join()
        err.join()
        stdout, t1 = out.result()
        stderr, t2 = err.result()
        return RunResult(
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            oom_killed=False,
            stdout_tail=stdout,
            stderr_tail=stderr,
            duration_s=round(duration, 3),
            truncated=t1 or t2,
            mode=self.mode,
            argv=tuple(spec.command),
        )
