"""aethens-task/v1 loader and validator (B2). One test per error class, plus the examples."""

from __future__ import annotations

import builtins
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from aethens.adapters import MAX_FILE_BYTES, load_task, load_tasks
from aethens.errors import (
    DuplicateIdError,
    MissingFileError,
    OversizedFileError,
    SchemaError,
    SymlinkEscapeError,
    TaskLoadError,
    UnsafePathError,
)
from aethens.models import Label, LabelSource

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"

TASK_YAML = """\
schema: aethens-task/v1
id: {id}
language: python
image: python:3.12-slim
statement: statement.md
starter: starter
tests: tests
verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]
timeout_s: 30
gold: gold
"""


def make_task(root: Path, task_id: str = "t1", yaml_text: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "task.yaml").write_text(
        yaml_text if yaml_text is not None else TASK_YAML.format(id=task_id)
    )
    (root / "statement.md").write_text("Do it.\n")
    for d in ("starter", "tests", "gold"):
        (root / d).mkdir(exist_ok=True)
    (root / "starter" / "sol.py").write_text("def f():\n    raise NotImplementedError\n")
    (root / "gold" / "sol.py").write_text("def f():\n    return 1\n")
    (root / "tests" / "test_sol.py").write_text("import sol\n")
    return root


def add_candidate(root: Path, label: str, name: str, source: str | None = "human") -> None:
    d = root / "candidates" / label / name
    d.mkdir(parents=True)
    (d / "sol.py").write_text("def f():\n    return 2\n")
    if source is not None:
        (root / "candidates" / label / f"{name}.label.yaml").write_text(f"label_source: {source}\n")


# --- happy paths ------------------------------------------------------------------------------


def test_examples_load() -> None:
    tasks = load_tasks(EXAMPLES)
    ids = sorted(t.id for t in tasks)
    assert ids == ["add-two", "word-format"]
    add = next(t for t in tasks if t.id == "add-two")
    assert add.root == (EXAMPLES / "add-two").resolve()
    assert add.verifier == ("python", "-m", "unittest", "discover", "-s", "tests")
    assert add.image == "python:3.12-slim"
    labels = {(c.name, c.label, c.label_source) for c in add.candidates}
    assert labels == {
        ("reversed-operands", Label.VALID, LabelSource.HUMAN),
        ("always-five", Label.INVALID, LabelSource.HUMAN),
    }


def test_single_task_dir(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    add_candidate(root, "valid", "alt", "oracle")
    add_candidate(root, "invalid", "bad", "llm-unreviewed")
    task = load_task(root)
    assert task.id == "t1"
    assert [c.name for c in task.candidates] == ["alt", "bad"]
    assert task.candidates[1].label_source is LabelSource.LLM_UNREVIEWED


def test_defaults_image_and_timeout(tmp_path: Path) -> None:
    text = (
        TASK_YAML.format(id="t1")
        .replace("image: python:3.12-slim\n", "")
        .replace("timeout_s: 30\n", "")
    )
    task = load_task(make_task(tmp_path / "t1", yaml_text=text))
    assert task.image == "python:3.12-slim"
    assert task.timeout_s == 60


# --- MissingFileError -------------------------------------------------------------------------


def test_missing_task_yaml(tmp_path: Path) -> None:
    (tmp_path / "t1").mkdir()
    with pytest.raises(MissingFileError):
        load_task(tmp_path / "t1")


def test_missing_gold_dir(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    shutil.rmtree(root / "gold")
    with pytest.raises(MissingFileError, match="gold"):
        load_task(root)


def test_missing_statement(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    (root / "statement.md").unlink()
    with pytest.raises(MissingFileError, match="statement"):
        load_task(root)


def test_missing_label_sidecar(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    add_candidate(root, "valid", "alt", source=None)
    with pytest.raises(MissingFileError, match="label"):
        load_task(root)


def test_no_tasks_found(tmp_path: Path) -> None:
    with pytest.raises(MissingFileError):
        load_tasks(tmp_path)


# --- SchemaError ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("schema: aethens-task/v1", "schema: aethens-task/v2"),
        ("language: python", "language: rust"),
        ("timeout_s: 30", "timeout_s: -1"),
        ("timeout_s: 30", "timeout_s: true"),
        ("timeout_s: 30", "timeout_s: 100000"),
        ('verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]', "verifier: []"),
        (
            'verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]',
            "verifier: python -m x",
        ),
        ("image: python:3.12-slim", "image: --privileged"),
        ("image: python:3.12-slim", "image: 'python:3.12 -v /:/host'"),
        ("id: t1", "id: ../evil"),
        ("id: t1", "id: -rf"),
    ],
)
def test_schema_violations(tmp_path: Path, old: str, new: str) -> None:
    text = TASK_YAML.format(id="t1")
    assert old in text
    with pytest.raises(SchemaError):
        load_task(make_task(tmp_path / "t1", yaml_text=text.replace(old, new)))


def test_unknown_key(tmp_path: Path) -> None:
    text = TASK_YAML.format(id="t1") + "privileged: true\n"
    with pytest.raises(SchemaError, match="privileged"):
        load_task(make_task(tmp_path / "t1", yaml_text=text))


def test_duplicate_yaml_key(tmp_path: Path) -> None:
    text = TASK_YAML.format(id="t1") + "id: t2\n"
    with pytest.raises(SchemaError, match="duplicate"):
        load_task(make_task(tmp_path / "t1", yaml_text=text))


def test_not_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(SchemaError):
        load_task(make_task(tmp_path / "t1", yaml_text="- a\n- b\n"))


def test_invalid_yaml(tmp_path: Path) -> None:
    with pytest.raises(SchemaError):
        load_task(make_task(tmp_path / "t1", yaml_text="id: [unclosed\n"))


def test_bad_label_source(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    add_candidate(root, "valid", "alt", source="vibes")
    with pytest.raises(SchemaError):
        load_task(root)


def test_unexpected_entry_in_candidates(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    (root / "candidates" / "maybe").mkdir(parents=True)
    with pytest.raises(SchemaError):
        load_task(root)


def test_gold_must_be_a_directory(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    shutil.rmtree(root / "gold")
    (root / "gold").write_text("not a dir")
    with pytest.raises(SchemaError):
        load_task(root)


# --- DuplicateIdError -------------------------------------------------------------------------


def test_duplicate_task_ids(tmp_path: Path) -> None:
    make_task(tmp_path / "a", task_id="same")
    make_task(tmp_path / "b", task_id="same")
    with pytest.raises(DuplicateIdError):
        load_tasks(tmp_path)


def test_duplicate_candidate_names(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    add_candidate(root, "valid", "x")
    add_candidate(root, "invalid", "x")
    with pytest.raises(DuplicateIdError):
        load_task(root)


# --- UnsafePathError --------------------------------------------------------------------------


def test_absolute_path(tmp_path: Path) -> None:
    text = TASK_YAML.format(id="t1").replace("gold: gold", "gold: /etc")
    with pytest.raises(UnsafePathError):
        load_task(make_task(tmp_path / "t1", yaml_text=text))


def test_dotdot_traversal(tmp_path: Path) -> None:
    (tmp_path / "outside").mkdir()
    text = TASK_YAML.format(id="t1").replace("gold: gold", "gold: ../outside")
    with pytest.raises(UnsafePathError):
        load_task(make_task(tmp_path / "t1", yaml_text=text))


def test_hidden_dotdot_traversal(tmp_path: Path) -> None:
    text = TASK_YAML.format(id="t1").replace("gold: gold", "gold: gold/../../t1/gold")
    with pytest.raises(UnsafePathError):
        load_task(make_task(tmp_path / "t1", yaml_text=text))


# --- SymlinkEscapeError -----------------------------------------------------------------------


def test_symlink_file_escaping(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read")
    root = make_task(tmp_path / "t1")
    os.symlink(secret, root / "gold" / "leak.txt")
    with pytest.raises(SymlinkEscapeError):
        load_task(root)


def test_symlink_dir_escaping(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    root = make_task(tmp_path / "t1")
    shutil.rmtree(root / "gold")
    os.symlink(tmp_path / "elsewhere", root / "gold")
    with pytest.raises(SymlinkEscapeError):
        load_task(root)


def test_relative_symlink_escaping(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("x")
    root = make_task(tmp_path / "t1")
    os.symlink("../../x.py", root / "tests" / "x.py")
    with pytest.raises(SymlinkEscapeError):
        load_task(root)


def test_task_yaml_symlink_escaping(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text(TASK_YAML.format(id="t1"))
    root = make_task(tmp_path / "t1")
    (root / "task.yaml").unlink()
    os.symlink(real, root / "task.yaml")
    with pytest.raises(SymlinkEscapeError):
        load_task(root)


def test_internal_symlink_is_allowed(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    os.symlink("sol.py", root / "gold" / "alias.py")
    assert load_task(root).id == "t1"


def test_dangling_symlink_is_rejected(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    os.symlink("missing.py", root / "gold" / "dangling.py")
    with pytest.raises(TaskLoadError):
        load_task(root)


# --- OversizedFileError -----------------------------------------------------------------------


def test_oversized_file(tmp_path: Path) -> None:
    root = make_task(tmp_path / "t1")
    with open(root / "tests" / "big.bin", "wb") as fh:
        fh.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(OversizedFileError):
        load_task(root)


# --- nothing outside the task directory is read -----------------------------------------------


def test_nothing_outside_task_dir_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_task(tmp_path / "t1")
    add_candidate(root, "valid", "alt")
    (tmp_path / "decoy.yaml").write_text("x: 1\n")
    real_open = builtins.open
    opened: list[Path] = []

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, (str, os.PathLike)):
            opened.append(Path(os.fspath(file)).resolve())
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    load_task(root)
    assert opened, "loader should have opened task.yaml"
    for p in opened:
        assert p.is_relative_to(root.resolve()), p
