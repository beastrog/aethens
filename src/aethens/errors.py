"""Typed exception hierarchy. Core code raises these; only the CLI maps them to exit codes."""

from __future__ import annotations


class AethensError(Exception):
    """Base class for every error Aethens raises on purpose."""


# --- task loading -----------------------------------------------------------------------------


class TaskLoadError(AethensError):
    """A task directory could not be loaded or validated."""


class MissingFileError(TaskLoadError):
    """A file or directory the task format requires does not exist."""


class SchemaError(TaskLoadError):
    """Data does not match its schema (task.yaml, label sidecar, or a serialized model)."""


class DuplicateIdError(TaskLoadError):
    """Two tasks, or two candidates in one task, share an id."""


class UnsafePathError(TaskLoadError):
    """A path is absolute or uses '..' to leave the task directory."""


class SymlinkEscapeError(TaskLoadError):
    """A symlink inside the task directory points outside it."""


class OversizedFileError(TaskLoadError):
    """A file in the task directory is larger than the allowed limit."""


# --- running ----------------------------------------------------------------------------------


class RunnerError(AethensError):
    """The runner could not execute a verifier (as opposed to the verifier failing)."""


class DockerUnavailableError(RunnerError):
    """The docker CLI or daemon is not available."""


class ContainerStartError(RunnerError):
    """Docker could not create or start the container (for example a missing image)."""


class UnsafeLocalNotAllowedError(RunnerError):
    """Local (non-container) execution was requested without the explicit opt-in."""


# --- checks -----------------------------------------------------------------------------------


class CheckError(AethensError):
    """A check could not run (for example the gold solution has no Python files to mutate)."""
