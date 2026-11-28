"""The first failures a new user hits name a next step, and still exit 2."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aethens.cli import main

REPO = Path(__file__).resolve().parent.parent


def test_missing_task_hint_points_at_init(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "does/not/exist"]) == 2
    err = capsys.readouterr().err
    assert "MissingFileError" in err
    assert "aethens: hint:" in err
    assert "aethens init demo" in err
    assert "task.yaml" in err


def test_schema_hint_names_the_task_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "task.yaml").write_text("schema: nope\n", encoding="utf-8")
    assert main(["audit", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "SchemaError" in err
    assert "aethens: hint:" in err
    assert "aethens-task/v1" in err
    assert "aethens init" not in err


def test_docker_unavailable_hint_offers_unsafe_local(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aethens", "audit", "examples/add-two"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": str(tmp_path)},
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "DockerUnavailableError" in result.stderr
    assert "aethens: hint:" in result.stderr
    assert "--unsafe-local" in result.stderr
    assert "no container isolation" in result.stderr


def test_init_errors_do_not_grow_an_audit_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "demo"
    dest.write_text("x", encoding="utf-8")
    assert main(["init", str(dest)]) == 2
    err = capsys.readouterr().err
    assert "DestinationError" in err
    assert "aethens: hint:" not in err
