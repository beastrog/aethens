"""AGENTS.md rule 9: no shell=True and no os.system anywhere in the package."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def test_no_shell_true_or_os_system() -> None:
    offenders = []
    for py in SRC.rglob("*.py"):
        text = py.read_text()
        for needle in ("shell=True", "os.system(", "os.popen("):
            if needle in text:
                offenders.append(f"{py}: {needle}")
    assert offenders == []
