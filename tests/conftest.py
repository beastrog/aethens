"""Shared fixtures. Docker tests are marked `docker`; without Docker they are skipped with a
reason, unless AETHENS_REQUIRE_DOCKER=1 (CI), where a missing daemon or image is a failure."""

from __future__ import annotations

import os
import subprocess
from functools import cache

import pytest

IMAGE = "python:3.12-slim"


@cache
def docker_problem() -> str | None:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"docker CLI unavailable: {exc}"
    if r.returncode != 0:
        return f"docker daemon or image {IMAGE} unavailable: {r.stderr.strip()[:200]}"
    return None


@pytest.fixture(autouse=True)
def _isolate_aethens_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Point the default result cache at a throwaway directory, not the real home."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("xdg-cache")))


@pytest.fixture(autouse=True)
def _require_docker(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("docker") is None:
        return
    problem = docker_problem()
    if problem is None:
        return
    if os.environ.get("AETHENS_REQUIRE_DOCKER") == "1":
        pytest.fail(f"AETHENS_REQUIRE_DOCKER=1 but {problem}")
    pytest.skip(f"NOT VERIFIED (Docker): {problem}")
