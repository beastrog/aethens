"""The typed error hierarchy (B1)."""

from __future__ import annotations

from aethens import errors


def test_all_errors_derive_from_base() -> None:
    for name in (
        "TaskLoadError",
        "MissingFileError",
        "SchemaError",
        "DuplicateIdError",
        "UnsafePathError",
        "SymlinkEscapeError",
        "OversizedFileError",
        "RunnerError",
        "DockerUnavailableError",
        "ContainerStartError",
        "UnsafeLocalNotAllowedError",
        "CheckError",
        "AuditConfigError",
        "CacheError",
    ):
        cls = getattr(errors, name)
        assert issubclass(cls, errors.AethensError), name


def test_loader_errors_are_task_load_errors() -> None:
    for cls in (
        errors.MissingFileError,
        errors.SchemaError,
        errors.DuplicateIdError,
        errors.UnsafePathError,
        errors.SymlinkEscapeError,
        errors.OversizedFileError,
    ):
        assert issubclass(cls, errors.TaskLoadError)


def test_runner_errors() -> None:
    assert issubclass(errors.DockerUnavailableError, errors.RunnerError)
    assert issubclass(errors.ContainerStartError, errors.RunnerError)
