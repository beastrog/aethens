"""Docker runner: the default and the only mode that isolates task code from the host.

Every run uses: --network none, memory and memory-swap limits (no swap), --cpus, --pids-limit,
a read-only root filesystem with a size-limited tmpfs on /tmp, --cap-drop ALL,
--security-opt no-new-privileges, a non-root user, --pull never, and a bind mount of a disposable
copy of the task as /work. The container is always removed and the copy always deleted, including
on timeouts and exceptions. The docker CLI is called with argument lists only.

Timeout accounting (D-064): ``timeout_s`` limits the verifier's run time inside the container, not
the time ``docker run`` spends creating, starting and tearing the container down. Under heavy host
load that overhead alone reached 20+ seconds and turned fast, passing verifiers into timeouts. The
runner polls the daemon until the container is running, then waits ``timeout_s`` of host-monotonic
time from that observation (never longer than ``timeout_s + STARTUP_GRACE_S`` from launch). After a
normal exit, a container whose daemon-recorded run time (FinishedAt - StartedAt) exceeds
``timeout_s`` is still reported as timed out, but that daemon delta is capped by the host-monotonic
time during which the container was observed running. Create time, teardown time and a forward
clock jump therefore cannot invent a timeout (D-064).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from aethens.errors import ContainerStartError, DockerUnavailableError, RunnerError
from aethens.runner.base import RunResult, RunSpec, TailPump, run_quiet, validate_env
from aethens.runner.workdir import build_workdir

NOBODY = "65534:65534"
# Extra wall time allowed for container creation, start and teardown on a loaded host (D-064).
STARTUP_GRACE_S = 60.0
# How often to re-ask the daemon while the container has not started yet or is tearing down.
POLL_S = 0.5
_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$")


def parse_docker_time(value: str) -> float | None:
    """Parse a Docker RFC 3339 timestamp (nanosecond precision) to epoch seconds; None if unset."""
    m = _TS.match(value or "")
    if m is None or m.group(1).startswith("0001-"):
        return None
    frac = (m.group(2) or "0")[:6].ljust(6, "0")
    zone = "+00:00" if m.group(3) == "Z" else m.group(3)
    try:
        return datetime.fromisoformat(f"{m.group(1)}.{frac}{zone}").timestamp()
    except ValueError:
        return None


def in_container_seconds(state: Mapping[str, object] | None) -> float | None:
    """FinishedAt - StartedAt from a container State, both on the daemon's clock."""
    if not state:
        return None
    start = parse_docker_time(str(state.get("StartedAt", "")))
    end = parse_docker_time(str(state.get("FinishedAt", "")))
    if start is None or end is None or end < start:
        return None
    return end - start


def observed_run_upper_s(last_absent: float, stopped_at: float | None, now: float) -> float:
    """Host-monotonic upper bound on how long the container can have been running.

    ``last_absent`` is the last moment it was observed not running (launch, if the first look
    already saw it running). Once it is observed stopped, ``stopped_at`` freezes the bound so
    later teardown does not count.
    """
    end = now if stopped_at is None else stopped_at
    return max(0.0, end - last_absent)


def _container_phase(state: Mapping[str, object] | None) -> str:
    """``running``, ``stopped``, ``absent`` or ``unknown`` from a ``docker inspect`` State.

    ``running`` requires Status running and a real StartedAt. ``absent`` means the state object
    describes a container that has not started (``created`` and anything else that is not
    running or stopped). A missing state is not ``absent``: the caller has to tell "no such
    container" apart from an inspect that failed.
    """
    if not state:
        return "unknown"
    status = str(state.get("Status", ""))
    if status in ("exited", "dead", "removing"):
        return "stopped"
    started = parse_docker_time(str(state.get("StartedAt", "")))
    if status == "running" and started is not None:
        return "running"
    return "absent"


def capped_in_container_seconds(
    state: Mapping[str, object] | None, running_upper_s: float
) -> float | None:
    """Daemon in-container time, never larger than ``running_upper_s`` (D-064).

    ``running_upper_s`` must be the host-monotonic time the container could have been running,
    not the full ``docker run`` wall time. Capping by total wall time still counts create and
    teardown: a slow start or teardown longer than ``timeout_s``, plus a forward clock jump or a
    bogus FinishedAt/StartedAt pair, marks a fast verifier as timed out (exit code ``None``).
    """
    ran = in_container_seconds(state)
    if ran is None:
        return None
    return min(ran, max(running_upper_s, 0.0))


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

    def _read_state(self, name: str) -> tuple[dict[str, object] | None, bool]:
        """Return ``(state, absent)``. ``absent`` is True only for "no such container"."""
        try:
            r = run_quiet([self.docker_bin, "inspect", "--format", "{{json .State}}", name], 60)
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"docker inspect {name} did not answer within 60 s") from exc
        if r.returncode != 0:
            # Docker 29 says "no such object"; older engines say "no such container".
            err = r.stderr.lower()
            return None, "no such container" in err or "no such object" in err
        state = json.loads(r.stdout)
        return (state, False) if isinstance(state, dict) else (None, False)

    def _inspect(self, name: str) -> dict[str, object] | None:
        state, _absent = self._read_state(name)
        return state

    def _phase(self, name: str) -> str:
        """``running``, ``stopped``, ``absent`` or ``unknown`` for the named container.

        ``absent`` is only a positive "not running" answer (no such container, or a state that
        has not started). A daemon error is ``unknown`` and must not move the pre-start mark:
        doing so would hide a verifier that ran through the inspect failures.
        """
        state, absent = self._read_state(name)
        if absent:
            return "absent"
        if state is None:
            return "unknown"
        return _container_phase(state)

    def _remove(self, name: str) -> None:
        # Retry with backoff: removal right after a kill, or on a loaded daemon, can race
        # ("removal ... is already in progress"); a container left behind is a cleanup bug.
        for attempt in range(6):
            try:
                r = run_quiet([self.docker_bin, "rm", "-f", "-v", name], 60)
            except subprocess.TimeoutExpired:
                continue
            if r.returncode == 0 or "No such container" in r.stderr:
                return
            time.sleep(0.5 * (attempt + 1))

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
        running_upper = 0.0
        try:
            exited, running_upper = self._wait(proc, name, spec.timeout_s, start)
            if not exited:
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
        ran = capped_in_container_seconds(state, running_upper)
        if not timed_out and ran is not None and ran > spec.timeout_s:
            # It exited by itself, but only after running longer than its timeout (D-064).
            timed_out = True
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

    def _wait(
        self, proc: subprocess.Popen[bytes], name: str, timeout: float, t0: float
    ) -> tuple[bool, float]:
        """Wait for ``docker run`` to exit.

        Returns ``(exited_on_its_own, running_upper_s)``. ``running_upper_s`` is a host-monotonic
        upper bound on verifier run time: time before the container was observed running and time
        after it was observed stopped do not count (D-064). The kill clock starts when the
        container is first observed running and uses the monotonic clock only, so a daemon clock
        step cannot shorten ``timeout``. The hard cap remains ``timeout + STARTUP_GRACE_S`` from
        launch. The first observation can be up to ``POLL_S`` late, so a verifier may run that
        much past ``timeout`` before it is killed; the post-exit check still flags a daemon run
        time over ``timeout`` when the observed window agrees.
        """
        hard = t0 + timeout + STARTUP_GRACE_S
        # The container cannot be running before launch. The first poll may already see it
        # running, in which case this stays at ``t0`` and the bound includes that short gap.
        last_absent = t0
        running_mark: float | None = None
        stopped_at: float | None = None

        def upper(now: float) -> float:
            return observed_run_upper_s(last_absent, stopped_at, now)

        while True:
            now = time.monotonic()
            if now >= hard:
                return False, upper(now)
            if running_mark is not None and now - running_mark >= timeout:
                return False, upper(now)
            if stopped_at is not None:
                # Verifier already stopped. Wait out teardown until the client exits or the
                # hard cap, without letting that wait grow the in-container bound.
                try:
                    proc.wait(timeout=max(hard - now, 0.05))
                except subprocess.TimeoutExpired:
                    return False, upper(time.monotonic())
                return True, upper(time.monotonic())
            wait_for = (
                min(timeout - (now - running_mark), hard - now)
                if running_mark is not None
                else min(POLL_S, hard - now)
            )
            try:
                proc.wait(timeout=max(wait_for, 0.05))
            except subprocess.TimeoutExpired:
                now = time.monotonic()
            else:
                return True, upper(time.monotonic())
            if now >= hard or (running_mark is not None and now - running_mark >= timeout):
                return False, upper(now)
            if running_mark is not None:
                continue
            try:
                kind = self._phase(name)
            except RunnerError:
                kind = "unknown"  # the daemon is too busy to answer; ask again shortly
            if kind == "running":
                running_mark = now
            elif kind == "stopped":
                stopped_at = now
            elif kind == "absent":
                # Positively not started yet. An unknown inspect must not move this mark.
                last_absent = now


def _open_up(path: Path) -> None:
    """Make the disposable copy writable for the 'nobody' user (only when the host user is root)."""
    for dirpath, _dirnames, filenames in os.walk(path):
        os.chmod(dirpath, 0o777)  # noqa: S103 - private disposable copy
        for f in filenames:
            os.chmod(Path(dirpath) / f, 0o666)  # noqa: S103
