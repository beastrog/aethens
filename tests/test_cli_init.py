"""`aethens init` writes a minimal task and refuses to overwrite one."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.cli import main
from aethens.scaffold import DestinationError, task_id_for, write_example


def test_write_example_loads_as_a_task(tmp_path: Path) -> None:
    dest = tmp_path / "demo"
    written = write_example(dest)
    assert len(written) == 5
    task = load_task(dest)
    assert task.id == "demo"
    assert task.language == "python"
    assert task.verifier == ("python", "-m", "unittest", "discover", "-s", "tests")
    assert (dest / "gold" / "add.py").read_text(encoding="utf-8").endswith("return a + b\n")


def test_odd_directory_name_uses_the_fallback_id(tmp_path: Path) -> None:
    dest = tmp_path / "My Task!"
    assert task_id_for(dest) == "example-task"
    write_example(dest)
    assert load_task(dest).id == "example-task"


def test_write_example_refuses_to_overwrite_and_leaves_files(tmp_path: Path) -> None:
    dest = tmp_path / "demo"
    write_example(dest)
    original = (dest / "task.yaml").read_text(encoding="utf-8")
    with pytest.raises(DestinationError, match="refusing to overwrite"):
        write_example(dest)
    assert (dest / "task.yaml").read_text(encoding="utf-8") == original


def test_write_example_writes_nothing_when_one_file_exists(tmp_path: Path) -> None:
    dest = tmp_path / "demo"
    dest.mkdir()
    (dest / "statement.md").write_text("keep\n", encoding="utf-8")
    with pytest.raises(DestinationError, match="refusing to overwrite"):
        write_example(dest)
    assert (dest / "statement.md").read_text(encoding="utf-8") == "keep\n"
    assert not (dest / "task.yaml").exists()
    assert not (dest / "starter").exists()


def test_write_example_rejects_a_file_destination(tmp_path: Path) -> None:
    dest = tmp_path / "demo"
    dest.write_text("x", encoding="utf-8")
    with pytest.raises(DestinationError, match="not a directory"):
        write_example(dest)
    assert dest.read_text(encoding="utf-8") == "x"


def test_cli_init_then_c001_passes_without_docker(tmp_path: Path) -> None:
    created = subprocess.run(
        [sys.executable, "-m", "aethens", "init", "demo"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    assert "aethens audit demo --budget smoke --check C001" in created.stdout
    assert "C007" in created.stdout
    audited = subprocess.run(
        [
            sys.executable,
            "-m",
            "aethens",
            "audit",
            "demo",
            "--unsafe-local",
            "--check",
            "C001",
            "--budget",
            "smoke",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert audited.returncode == 0, audited.stderr
    assert "without container isolation" in audited.stderr
    assert json.loads(audited.stdout)["findings"] == []


def test_cli_init_on_a_file_is_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = tmp_path / "demo"
    dest.write_text("x", encoding="utf-8")
    assert main(["init", str(dest)]) == 2
    err = capsys.readouterr().err
    assert "DestinationError" in err
    assert dest.read_text(encoding="utf-8") == "x"
