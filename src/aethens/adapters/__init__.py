"""Task adapters. v0.1 has one: the aethens-task/v1 directory format."""

from aethens.adapters.task_loader import (
    DEFAULT_IMAGE,
    DEFAULT_TIMEOUT_S,
    MAX_FILE_BYTES,
    MAX_TIMEOUT_S,
    load_task,
    load_tasks,
)

__all__ = [
    "DEFAULT_IMAGE",
    "DEFAULT_TIMEOUT_S",
    "MAX_FILE_BYTES",
    "MAX_TIMEOUT_S",
    "load_task",
    "load_tasks",
]
