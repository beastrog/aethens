"""What `aethens --help` and `aethens audit --help` tell a first-time user."""

from __future__ import annotations

import pytest

from aethens.cli import main


def _flat(text: str) -> str:
    """Help text with argparse's column wrapping removed."""
    return " ".join(text.split())


def test_no_command_prints_help_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = _flat(capsys.readouterr().out)
    assert "exit codes:" in out
    assert "0 no finding at or above --fail-on" in out
    assert "1 findings at or above --fail-on" in out
    assert "2 tool error" in out
    assert "3 a gold-solution run in C001 or C002 timed out" in out
    assert "aethens audit path/to/task" in out
    assert "does not mean the verifier is sound" in out


def test_top_level_help_matches_the_no_command_text(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = _flat(capsys.readouterr().out)
    assert "Docker sandbox" in out
    assert "one-line repro" in out
    assert "does not mean the verifier is sound" in out


def test_audit_help_explains_budget_severity_and_format(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["audit", "--help"])
    assert exc.value.code == 0
    out = _flat(capsys.readouterr().out)
    assert "C002 starts at 3 / 5 / 10" in out
    assert "C004 tries up to 5 / 10 / 30 mutants" in out
    assert "minimum severity that exits 1" in out
    assert "default: json" in out
    assert "no container isolation" in out
    assert "does not mean the verifier is sound" in out
