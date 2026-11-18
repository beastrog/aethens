"""Build the disposable work directory for one run."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from aethens.errors import RunnerError


def build_workdir(layers: tuple[tuple[Path, Path], ...], dest: Path) -> None:
    """Copy each (source, relative destination) layer into ``dest`` in order.

    Symlinks are dereferenced (the loader already proved they stay inside the task directory), so
    the container never sees a symlink. Destinations must be relative and free of '..'.
    """
    for src, rel in layers:
        pure = PurePosixPath(rel.as_posix())
        if pure.is_absolute() or ".." in pure.parts:
            raise RunnerError(f"unsafe layer destination {rel}")
        target = dest / pure
        shutil.copytree(src, target, symlinks=False, dirs_exist_ok=True)
