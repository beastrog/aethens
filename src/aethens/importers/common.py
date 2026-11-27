"""Shared helpers for importers: a task draft and a writer that validates what it wrote."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from aethens.adapters import load_task
from aethens.errors import AethensError, ImporterError

_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
EMPTY_MARKER = ".aethens-empty"


def safe_id(raw: str, prefix: str = "") -> str:
    """Turn an upstream id (``Mbpp/2``, ``django__django-11099``) into a valid task id."""
    cleaned = _ID_SAFE.sub("-", raw).strip("-.")
    out = f"{prefix}{cleaned}"[:100]
    if not out or not out[0].isalnum():
        raise ImporterError(f"cannot make a task id from {raw!r}")
    return out


@dataclass(frozen=True)
class TaskDraft:
    """Everything needed to write one aethens-task/v1 directory. Paths are relative POSIX paths."""

    id: str
    statement: str
    starter: Mapping[str, str]
    gold: Mapping[str, str]
    tests: Mapping[str, str]
    verifier: tuple[str, ...]
    image: str
    timeout_s: int
    provenance: Mapping[str, object] = field(default_factory=dict)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL export (one JSON object per line). Raises ImporterError on bad input."""
    if not path.is_file():
        raise ImporterError(f"{path}: no such file")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ImporterError(f"{path}:{n}: not JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ImporterError(f"{path}:{n}: expected a JSON object")
            rows.append(obj)
    return rows


def _check_rel(rel: str) -> None:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts or rel != p.as_posix():
        raise ImporterError(f"unsafe relative path in draft: {rel!r}")


def _write_tree(root: Path, files: Mapping[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if not files:
        (root / EMPTY_MARKER).write_text("", encoding="utf-8")
        return
    for rel, text in files.items():
        _check_rel(rel)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")


def _yaml_list(items: tuple[str, ...]) -> str:
    return "[" + ", ".join(json.dumps(a) for a in items) + "]"


def write_task(draft: TaskDraft, out_root: Path, *, overwrite: bool = False) -> Path:
    """Write ``draft`` to ``out_root/<id>`` and validate it with the task loader.

    Refuses to replace an existing directory unless ``overwrite`` is set. Raises ImporterError if
    the result does not load.
    """
    if not draft.verifier:
        raise ImporterError(f"{draft.id}: empty verifier")
    dest = out_root / draft.id
    if dest.exists():
        if not overwrite:
            raise ImporterError(f"{dest} already exists (use overwrite)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "statement.md").write_text(draft.statement, encoding="utf-8")
    _write_tree(dest / "starter", draft.starter)
    _write_tree(dest / "gold", draft.gold)
    _write_tree(dest / "tests", draft.tests)
    (dest / "task.yaml").write_text(
        "schema: aethens-task/v1\n"
        f"id: {draft.id}\n"
        "language: python\n"
        f"image: {draft.image}\n"
        "statement: statement.md\n"
        "starter: starter\n"
        "tests: tests\n"
        f"verifier: {_yaml_list(draft.verifier)}\n"
        f"timeout_s: {draft.timeout_s}\n"
        "gold: gold\n",
        encoding="utf-8",
    )
    if draft.provenance:
        (dest / "PROVENANCE.json").write_text(
            json.dumps(dict(draft.provenance), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    try:
        load_task(dest)
    except AethensError as exc:
        raise ImporterError(f"{draft.id}: imported task does not load: {exc}") from exc
    return dest
