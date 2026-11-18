"""Docker runner: the default and the only mode that isolates task code from the host.

Every run uses: --network none, memory and memory-swap limits (no swap), --cpus, --pids-limit,
a read-only root filesystem with a size-limited tmpfs on /tmp, --cap-drop ALL,
--security-opt no-new-privileges, a non-root user, --pull never, and a bind mount of a disposable
copy of the task as /work. The container is always removed and the copy always deleted, including
on timeouts and exceptions. The docker CLI is called with argument lists only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from aethens.errors import ContainerStartError, DockerUnavailableError, RunnerError
from aethens.runner.base import RunResult, RunSpec, TailPump, run_quiet, validate_env
from aethens.runner.workdir import build_workdir

NOBODY = "65534:65534"


class DockerRunner:
    mode = "docker"

    def __init__(self, docker_bin: str = "docker", tmp_root: Path | None = None) -> None:
        self.docker_bin = docker_bin
        self.tmp_root = tmp_root
        self._checked = False

    # --- availability -------------------------------------------------------------------------

    def ensure_available(self) -> None:
        try:
            r = run_quiet([self.docker_bin, "version", "--format", "{{.Server.Version}}"], 30)
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            raise DockerUnavailableError(f"docker CLI not usable: {exc}") from exc
        if r.returncode != 0:
            raise DockerUnavailableError(f"docker daemon not reachable: {r.stderr.strip()[:300]}")
        self._checked = True

    # --- argv ---------------------------------------------------------------------------------

    @staticmethod
    def _user() -> str:
        uid, gid = os.getuid(), os.getgid()
        if uid == 0 or gid == 0:
            return NOBODY
        return f"{uid}:{gid}"

    def build_argv(self, spec: RunSpec, workdir: Path, name: str) -> list[str]:
        validate_env(spec.env)
        if "," in str(workdir) or "=" in str(workdir):
            raise RunnerError(f"work directory path not usable in --mount: {workdir}")
        lim = spec.limits
        env = {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}  # noqa: S108 - container tmpfs
        env.update(spec.env)
        argv = [
            self.docker_bin,
            "run",
            "--name",
            name,
            "--label",
            "aethens.run=1",
            "--pull",
            "never",
            "--network",
            "none",
            "--memory",
            f"{lim.memory_mb}m",
            "--memory-swap",
            f"{lim.memory_mb}m",
            "--cpus",
            f"{lim.cpus}",
            "--pids-limit",
            str(lim.pids),
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,size={lim.tmpfs_mb}m",  # noqa: S108 - container tmpfs
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            self._user(),
            "--mount",
            f"type=bind,src={workdir},dst=/work",
            "--workdir",
            "/work",
        ]
        for k in sorted(env):
            argv += ["-e", f"{k}={env[k]}"]
        argv.append(spec.image)
        argv += list(spec.command)
        return argv

    # --- helpers ------------------------------------------------------------------------------

    def _inspect(self, name: str) -> dict[str, object] | None:
        r = run_quiet([self.docker_bin, "inspect", "--format", "{{json .State}}", name], 60)
        if r.returncode != 0:
            return None
        state = json.loads(r.stdout)
        return state if isinstance(state, dict) else None

    def _remove(self, name: str) -> None:
        # Retry once: removal right after a kill can race the daemon.
        for _ in range(2):
            r = run_quiet([self.docker_bin, "rm", "-f", "-v", name], 60)
            if r.returncode == 0 or "No such container" in r.stderr:
                return
            time.sleep(0.5)

    # --- run ----------------------------------------------------------------------------------

    def run(self, spec: RunSpec) -> RunResult:
        if not self._checked:
            self.ensure_available()
        name = f"aethens-{uuid.uuid4().hex[:16]}"
        tmp = Path(tempfile.mkdtemp(prefix="aethens-run-", dir=self.tmp_root))
        try:
            work = tmp / "work"
            work.mkdir()
            build_workdir(spec.layers, work)
            if self._user() == NOBODY:
                _open_up(work)
            argv = self.build_argv(spec, work, name)
            return self._execute(spec, argv, name)
        finally:
            self._remove(name)
            shutil.rmtree(tmp, ignore_errors=True)

    def _execute(self, spec: RunSpec, argv: list[str], name: str) -> RunResult:
        limit = spec.limits.max_output_bytes
        start = time.monotonic()
        proc = subprocess.Popen(  # noqa: S603 - argument list, never a shell
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert proc.stdout is not None and proc.stderr is not None
        out, err = TailPump(proc.stdout, limit), TailPump(proc.stderr, limit)
        timed_out = False
        try:
            proc.wait(timeout=spec.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            run_quiet([self.docker_bin, "kill", name], 60)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        duration = time.monotonic() - start
        out.join()
        err.join()
        stdout, t1 = out.result()
        stderr, t2 = err.result()
        state = self._inspect(name)
        started = state is not None and str(state.get("StartedAt", "")) > "0001-01-01T00:00:00Z"
        if not started and not timed_out:
            raise ContainerStartError(
                f"container for image {spec.image!r} did not start "
                f"(docker exit {proc.returncode}): {stderr.strip()[-500:]}"
                + (f" -- try: docker pull {spec.image}" if "No such image" in stderr else "")
            )
        oom = bool(state and state.get("OOMKilled"))
        code = None if timed_out else proc.returncode
        return RunResult(
            exit_code=code,
            timed_out=timed_out,
            oom_killed=oom,
            stdout_tail=stdout,
            stderr_tail=stderr,
            duration_s=round(duration, 3),
            truncated=t1 or t2,
            mode=self.mode,
            argv=tuple(argv),
        )


def _open_up(path: Path) -> None:
    """Make the disposable copy writable for the 'nobody' user (only when the host user is root)."""
    for dirpath, _dirnames, filenames in os.walk(path):
        os.chmod(dirpath, 0o777)  # noqa: S103 - private disposable copy
        for f in filenames:
            os.chmod(Path(dirpath) / f, 0o666)  # noqa: S103
