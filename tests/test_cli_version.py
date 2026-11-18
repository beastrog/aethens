"""The console script exists and reports its version (B1)."""

from __future__ import annotations

import pytest

from aethens import __version__
from aethens.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
