"""Loader and validator for the aethens-task/v1 directory format (see docs/task-format.md).

Security properties (tested in tests/test_task_loader.py):
- The whole task directory is scanned before anything is parsed. Symlinks that resolve outside the
  task directory, dangling symlinks, special files (FIFOs, devices, sockets) and files larger than
  ``MAX_FILE_BYTES`` are rejected, so nothing outside the task directory is ever read, and copying
  the task later cannot hang on a FIFO.
- Every path field must be relative, without '..', and resolve inside the task directory.
- ``image`` and ``id`` are restricted to conservative character sets so they can never be parsed as
  command-line options by the docker CLI.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from aethens.errors import (
    DuplicateIdError,
    MissingFileError,
    OversizedFileError,
    SchemaError,
    SymlinkEscapeError,
    TaskLoadError,
    UnsafePathError,
)
from aethens.models import TASK_SCHEMA, Candidate, Label, LabelSource, Task

DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT_S = 60
MAX_TIMEOUT_S = 3600
MAX_FILE_BYTES = 5 * 1024 * 1024

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_IMAGE_RE = re.compile(r"^[a-z0-9][A-Za-z0-9._/:@-]{0,254}$")
_REQUIRED = ("schema", "id", "language", "statement", "starter", "tests", "verifier", "gold")
_OPTIONAL = ("image", "timeout_s")
_LABEL_SUFFIX = ".label.yaml"
_LABEL_KEYS_REQUIRED = ("label_source",)
_LABEL_KEYS_OPTIONAL = ("note",)


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently keeping the last one."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise SchemaError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _read_yaml(path: Path, where: str) -> Any:
    # builtins.open on a path already proven to be inside the task directory.
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    except SchemaError as exc:
        raise SchemaError(f"{where}: {exc}") from None
    except yaml.YAMLError as exc:
        raise SchemaError(f"{where}: invalid YAML: {exc}") from None


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _scan_tree(root: Path) -> None:
    """Reject escaping or dangling symlinks, special files and oversized files anywhere in root."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in sorted(dirnames + filenames):
            p = Path(dirpath) / name
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                target = p.resolve(strict=False)
                if not _inside(target, root):
                    raise SymlinkEscapeError(
                        f"{p.relative_to(root)} points outside the task directory"
                    )
                if not target.exists():
                    raise MissingFileError(f"{p.relative_to(root)} is a dangling symlink")
                st = target.stat()
            if stat.S_ISDIR(st.st_mode):
                continue
            if not stat.S_ISREG(st.st_mode):
                raise SchemaError(f"{p.relative_to(root)} is not a regular file or directory")
            if st.st_size > MAX_FILE_BYTES:
                raise OversizedFileError(
                    f"{p.relative_to(root)} is {st.st_size} bytes; the limit is {MAX_FILE_BYTES}"
                )


def _rel_path(value: Any, key: str, root: Path, *, want_dir: bool) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SchemaError(f"task.yaml: '{key}' must be a non-empty relative path string")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value.startswith("\\") or re.match(r"^[A-Za-z]:", value):
        raise UnsafePathError(f"task.yaml: '{key}' must be relative, got {value!r}")
    if ".." in pure.parts:
        raise UnsafePathError(f"task.yaml: '{key}' must not contain '..', got {value!r}")
    full = (root / pure).resolve(strict=False)
    if not _inside(full, root):
        raise SymlinkEscapeError(f"task.yaml: '{key}' resolves outside the task directory")
    if not full.exists():
        raise MissingFileError(f"task.yaml: '{key}' points to {value!r}, which does not exist")
    if want_dir and not full.is_dir():
        raise SchemaError(f"task.yaml: '{key}' must be a directory")
    if not want_dir and not full.is_file():
        raise SchemaError(f"task.yaml: '{key}' must be a file")
    return Path(pure)


def _load_label(path: Path, root: Path) -> LabelSource:
    where = str(path.relative_to(root))
    data = _read_yaml(path, where)
    if not isinstance(data, dict):
        raise SchemaError(f"{where}: expected a mapping")
    unknown = set(data) - set(_LABEL_KEYS_REQUIRED) - set(_LABEL_KEYS_OPTIONAL)
    if unknown:
        raise SchemaError(f"{where}: unknown keys {sorted(map(str, unknown))}")
    if "label_source" not in data:
        raise SchemaError(f"{where}: missing 'label_source'")
    if "note" in data and not isinstance(data["note"], str):
        raise SchemaError(f"{where}: 'note' must be a string")
    try:
        return LabelSource(data["label_source"])
    except ValueError:
        allowed = ", ".join(s.value for s in LabelSource)
        raise SchemaError(
            f"{where}: label_source {data['label_source']!r} is not one of: {allowed}"
        ) from None


def _load_candidates(root: Path) -> tuple[Candidate, ...]:
    cdir = root / "candidates"
    if not cdir.exists():
        return ()
    if not cdir.is_dir():
        raise SchemaError("candidates must be a directory")
    for entry in sorted(cdir.iterdir()):
        if entry.name not in ("valid", "invalid") or not entry.is_dir():
            raise SchemaError(
                f"candidates/{entry.name}: only 'valid/' and 'invalid/' directories are allowed"
            )
    found: list[Candidate] = []
    names: set[str] = set()
    for label in (Label.VALID, Label.INVALID):
        ldir = cdir / label.value
        if not ldir.is_dir():
            continue
        entries = sorted(ldir.iterdir())
        dirs = [e for e in entries if e.is_dir()]
        sidecars = {e.name for e in entries if e.is_file() and e.name.endswith(_LABEL_SUFFIX)}
        others = [e for e in entries if not e.is_dir() and e.name not in sidecars]
        if others:
            raise SchemaError(f"candidates/{label.value}/{others[0].name}: unexpected file")
        for d in dirs:
            if not _ID_RE.match(d.name):
                raise SchemaError(f"candidates/{label.value}/{d.name}: invalid candidate name")
            if d.name in names:
                raise DuplicateIdError(f"candidate name {d.name!r} is used more than once")
            names.add(d.name)
            sidecar = ldir / f"{d.name}{_LABEL_SUFFIX}"
            if sidecar.name not in sidecars:
                raise MissingFileError(
                    f"candidates/{label.value}/{d.name}: missing label sidecar {sidecar.name}"
                )
            found.append(
                Candidate(
                    name=d.name,
                    path=Path("candidates") / label.value / d.name,
                    label=label,
                    label_source=_load_label(sidecar, root),
                )
            )
        orphans = sidecars - {f"{d.name}{_LABEL_SUFFIX}" for d in dirs}
        if orphans:
            raise SchemaError(
                f"candidates/{label.value}/{sorted(orphans)[0]}: no matching directory"
            )
    return tuple(found)


def load_task(path: str | os.PathLike[str]) -> Task:
    """Load and validate one aethens-task/v1 directory. Raises a TaskLoadError subclass."""
    given = Path(path)
    if not given.is_dir():
        raise MissingFileError(f"{given}: task directory does not exist")
    root = given.resolve(strict=True)
    yaml_path = root / "task.yaml"
    if not os.path.lexists(yaml_path):
        raise MissingFileError(f"{root}: no task.yaml")
    _scan_tree(root)  # rejects an escaping task.yaml symlink before it is read
    data = _read_yaml(yaml_path, "task.yaml")
    if not isinstance(data, dict):
        raise SchemaError("task.yaml: expected a mapping at the top level")
    unknown = set(data) - set(_REQUIRED) - set(_OPTIONAL)
    if unknown:
        raise SchemaError(f"task.yaml: unknown keys {sorted(map(str, unknown))}")
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        raise SchemaError(f"task.yaml: missing required keys {missing}")
    if data["schema"] != TASK_SCHEMA:
        raise SchemaError(f"task.yaml: schema must be {TASK_SCHEMA!r}, got {data['schema']!r}")
    task_id = data["id"]
    if not isinstance(task_id, str) or not _ID_RE.match(task_id):
        raise SchemaError(f"task.yaml: id {task_id!r} must match {_ID_RE.pattern}")
    if data["language"] != "python":
        raise SchemaError(f"task.yaml: language must be 'python' in v0.1, got {data['language']!r}")
    image = data.get("image", DEFAULT_IMAGE)
    if not isinstance(image, str) or not _IMAGE_RE.match(image):
        raise SchemaError(f"task.yaml: image {image!r} is not a valid image reference")
    timeout = data.get("timeout_s", DEFAULT_TIMEOUT_S)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= MAX_TIMEOUT_S
    ):
        raise SchemaError(f"task.yaml: timeout_s must be an integer from 1 to {MAX_TIMEOUT_S}")
    verifier = data["verifier"]
    if (
        not isinstance(verifier, list)
        or not verifier
        or not all(isinstance(a, str) and a and "\x00" not in a for a in verifier)
    ):
        raise SchemaError("task.yaml: verifier must be a non-empty list of non-empty strings")
    return Task(
        id=task_id,
        root=root,
        language="python",
        image=image,
        statement=_rel_path(data["statement"], "statement", root, want_dir=False),
        starter=_rel_path(data["starter"], "starter", root, want_dir=True),
        tests=_rel_path(data["tests"], "tests", root, want_dir=True),
        verifier=tuple(verifier),
        timeout_s=timeout,
        gold=_rel_path(data["gold"], "gold", root, want_dir=True),
        candidates=_load_candidates(root),
    )


def load_tasks(path: str | os.PathLike[str]) -> tuple[Task, ...]:
    """Load one task directory, or every task directory found under ``path`` (sorted by path).

    Discovery does not follow symlinks, skips hidden directories, and does not descend into a
    directory once it holds a task.yaml.
    """
    base = Path(path)
    if not base.is_dir():
        raise MissingFileError(f"{base}: not a directory")
    if os.path.lexists(base / "task.yaml"):
        return (load_task(base),)
    roots: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if "task.yaml" in filenames:
            roots.append(Path(dirpath))
            dirnames[:] = []
    if not roots:
        raise MissingFileError(f"{base}: no task.yaml found")
    tasks: list[Task] = []
    seen: dict[str, Path] = {}
    for r in sorted(roots):
        try:
            task = load_task(r)
        except TaskLoadError as exc:
            raise type(exc)(f"{r}: {exc}") from exc
        if task.id in seen:
            raise DuplicateIdError(f"task id {task.id!r} is used by {seen[task.id]} and {r}")
        seen[task.id] = r
        tasks.append(task)
    return tuple(tasks)
