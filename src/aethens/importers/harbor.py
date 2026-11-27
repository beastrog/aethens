"""Harbor / Terminal-Bench 2 task directories: a compatibility scan, not yet a converter.

A Harbor task (format checked on 2026-11-27 against github.com/harbor-framework/terminal-bench-2 at
2fd12b88) is a directory with ``task.toml``, ``instruction.md``, ``environment/Dockerfile`` (or a
prebuilt ``[environment].docker_image``), ``solution/solve.sh`` and ``tests/test.sh``. The agent and
then ``tests/test.sh`` run as root inside the task container; ``test.sh`` writes the reward to
``/logs/verifier/reward.txt``.

Aethens' sandbox runs every verifier offline (``--network none``), as a non-root user, on a
read-only root filesystem with only the work directory writable. A Harbor verifier can run there
only if neither the solution nor the tests need the network, root, or writes outside the work
directory. This module reports, per task, which of those requirements are visible statically, so
the gap is measured instead of guessed. Converting the compatible subset, and any runner profile
for the rest (for example dependencies baked into the image at build time), needs the owner's
decision because it touches the Docker isolation settings (AGENTS.md rule 8).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from aethens.errors import ImporterError

_NETWORK = re.compile(
    r"\b(apt-get|apt|apk|curl|wget|git clone|pip3? install|uv pip|uv add|uvx|npm (i|install)|"
    r"cargo install|go install|conda install)\b"
)
_ROOT_PATHS = re.compile(r"(?<![\w.])/(app|logs|tests|root|etc|usr|opt|var)\b")


@dataclass(frozen=True)
class HarborTaskInfo:
    name: str
    docker_image: str
    allow_internet: bool
    tests_need_network: bool
    solution_needs_network: bool
    writes_outside_workdir: bool
    gpus: int

    @property
    def runs_in_aethens_sandbox(self) -> bool:
        return not (
            self.tests_need_network
            or self.solution_needs_network
            or self.writes_outside_workdir
            or self.gpus
        )


def scan_harbor_task(task_dir: Path) -> HarborTaskInfo:
    """Read one Harbor task directory. Raises ImporterError if it is not one."""
    toml_path = task_dir / "task.toml"
    if not toml_path.is_file():
        raise ImporterError(f"{task_dir}: no task.toml (not a Harbor task)")
    try:
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ImporterError(f"{toml_path}: {exc}") from exc
    env = meta.get("environment", {})
    test_sh = task_dir / "tests" / "test.sh"
    if not test_sh.is_file():
        raise ImporterError(f"{task_dir}: no tests/test.sh")
    tests = test_sh.read_text(encoding="utf-8", errors="replace")
    solve_path = task_dir / "solution" / "solve.sh"
    solve = solve_path.read_text(encoding="utf-8", errors="replace") if solve_path.is_file() else ""
    return HarborTaskInfo(
        name=str(meta.get("task", {}).get("name", task_dir.name)),
        docker_image=str(env.get("docker_image", "")),
        allow_internet=bool(env.get("allow_internet", True)),
        tests_need_network=bool(_NETWORK.search(tests)),
        solution_needs_network=bool(_NETWORK.search(solve)),
        writes_outside_workdir=bool(_ROOT_PATHS.search(tests) or _ROOT_PATHS.search(solve)),
        gpus=int(env.get("gpus", 0) or 0),
    )
