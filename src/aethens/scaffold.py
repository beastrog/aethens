"""Write a minimal aethens-task/v1 directory. No printing; the CLI does that.

The generated verifier is a plain ``unittest`` harness. C001 can pass on it. C007's
reward-hacking probes usually get past a harness that trusts the solution process,
and the CLI says so. This module does not run the task.
"""

from __future__ import annotations

import re
from pathlib import Path

from aethens.errors import AethensError

# Same shape as the task-loader id check. A directory name that does not match
# cannot be a task id, so the scaffold uses a fixed id instead of inventing one.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_FALLBACK_ID = "example-task"

_RELATIVE_FILES = (
    "task.yaml",
    "statement.md",
    "starter/add.py",
    "gold/add.py",
    "tests/test_add.py",
)


class DestinationError(AethensError):
    """``aethens init`` refused to write, because the destination is not usable."""


def task_id_for(dest: Path) -> str:
    """A legal task id taken from the directory name, or a fixed fallback."""
    name = dest.name
    if _ID_RE.fullmatch(name):
        return name
    return _FALLBACK_ID


def example_files(task_id: str) -> dict[str, str]:
    """Relative path -> file text for one minimal task with this id."""
    if not _ID_RE.fullmatch(task_id):
        raise DestinationError(f"task id {task_id!r} is not a valid aethens-task/v1 id")
    return {
        "task.yaml": (
            "schema: aethens-task/v1\n"
            f"id: {task_id}\n"
            "language: python\n"
            "image: python:3.12-slim\n"
            "statement: statement.md\n"
            "starter: starter\n"
            "tests: tests\n"
            'verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]\n'
            "timeout_s: 30\n"
            "gold: gold\n"
        ),
        "statement.md": (
            "# Add two integers\n"
            "\n"
            "Implement `add(a, b)` so it returns the sum of the two integers.\n"
            "\n"
            "This directory was written by `aethens init`. It is a minimal "
            "aethens-task/v1 task: the starter raises, and the gold returns `a + b`. "
            "The tests are a plain `unittest` harness, which reward-hacking probes "
            "can usually get past.\n"
        ),
        "starter/add.py": ("def add(a: int, b: int) -> int:\n    raise NotImplementedError\n"),
        "gold/add.py": ("def add(a: int, b: int) -> int:\n    return a + b\n"),
        "tests/test_add.py": (
            "import unittest\n"
            "\n"
            "from add import add\n"
            "\n"
            "\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_small(self) -> None:\n"
            "        self.assertEqual(add(2, 3), 5)\n"
            "\n"
            "    def test_negative(self) -> None:\n"
            "        self.assertEqual(add(-4, 1), -3)\n"
            "\n"
            "    def test_zero(self) -> None:\n"
            "        self.assertEqual(add(0, 0), 0)\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        ),
    }


def write_example(dest: Path) -> tuple[Path, ...]:
    """Create a minimal task at ``dest``.

    ``dest`` may be missing or an empty directory. If it is a file, or if any file
    this function would write already exists, raise ``DestinationError`` and write
    nothing.
    """
    if dest.exists() and not dest.is_dir():
        raise DestinationError(f"{dest}: not a directory")
    files = example_files(task_id_for(dest))
    if tuple(files) != _RELATIVE_FILES:
        raise DestinationError("internal error: example file list drifted")
    existing = [dest / rel for rel in files if (dest / rel).exists()]
    if existing:
        listed = ", ".join(str(p) for p in existing)
        raise DestinationError(f"refusing to overwrite: {listed}")
    written: list[Path] = []
    for rel, text in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise DestinationError(f"refusing to overwrite: {path}")
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return tuple(written)
