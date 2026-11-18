"""Runner data types and shared helpers."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Protocol

from aethens.errors import RunnerError

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Limits:
    """Resource limits for one verifier run (owner-tunable defaults, see docs/DECISIONS.md)."""

    memory_mb: int = 1024
    cpus: float = 1.0
    pids: int = 256
    max_output_bytes: int = 65536
    tmpfs_mb: int = 256


@dataclass(frozen=True)
class RunSpec:
    """One verifier run.

    ``layers`` are (source directory, destination relative to the work directory) pairs, copied in
    order; later layers overwrite earlier files.
    """

    image: str
    command: tuple[str, ...]
    layers: tuple[tuple[Path, Path], ...]
    timeout_s: float
    env: Mapping[str, str] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)


@dataclass(frozen=True)
class RunResult:
    exit_code: int | None
    timed_out: bool
    oom_killed: bool
    stdout_tail: str
    stderr_tail: str
    duration_s: float
    truncated: bool
    mode: str
    argv: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Runner(Protocol):
    mode: str

    def run(self, spec: RunSpec) -> RunResult: ...


def validate_env(env: Mapping[str, str]) -> None:
    for k, v in env.items():
        if not _ENV_NAME.match(k) or "\x00" in v:
            raise RunnerError(f"invalid environment variable for a run: {k!r}")


def tail_text(data: bytes, limit: int) -> tuple[str, bool]:
    """Return the last ``limit`` bytes as text and whether anything was cut."""
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace"), False
    cut = data[-limit:]
    return f"[... {len(data) - limit} bytes truncated ...]\n" + cut.decode(
        "utf-8", errors="replace"
    ), True


class TailPump:
    """Read a pipe to EOF in a thread, keeping only the last ``limit`` bytes in memory."""

    def __init__(self, stream: IO[bytes], limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._buf = bytearray()
        self.total = 0
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while True:
            chunk = self._stream.read(65536)
            if not chunk:
                break
            self.total += len(chunk)
            self._buf += chunk
            if len(self._buf) > 2 * self._limit:
                del self._buf[: len(self._buf) - self._limit]

    def join(self, timeout: float = 10.0) -> None:
        self._thread.join(timeout)

    def result(self) -> tuple[str, bool]:
        data = bytes(self._buf[-self._limit :])
        text = data.decode("utf-8", errors="replace")
        if self.total > len(data):
            return f"[... {self.total - len(data)} bytes truncated ...]\n" + text, True
        return text, False


def run_quiet(argv: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    """Run a short helper command (docker inspect/rm/kill) with an argument list."""
    return subprocess.run(  # noqa: S603 - argument list, never a shell
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )
