"""Unit tests for bench/tbench/convert_tb2.py's test.sh parser (no Docker, no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = REPO / "bench" / "tbench" / "convert_tb2.py"
    spec = importlib.util.spec_from_file_location("convert_tb2", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["convert_tb2"] = mod
    spec.loader.exec_module(mod)
    return mod


TEMPLATE = """#!/bin/bash

# Install curl
apt-get update
apt-get install -y curl

# Install uv
curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh

source $HOME/.local/bin/env

# Check if we're in a valid working directory
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

uvx \\
  -p 3.13 \\
  -w pytest==8.4.1 \\
  -w numpy==2.3.0 \\
  -w pytest-json-ctrf==0.3.5 \\
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -v -rA


if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""


def test_parses_standard_template() -> None:
    mod = _load()
    deps, args = mod.parse_test_sh(TEMPLATE)
    assert deps == ["pytest==8.4.1", "numpy==2.3.0", "pytest-json-ctrf==0.3.5"]
    assert args == ["/tests/test_outputs.py", "-v", "-rA"]  # --ctrf and its path dropped


def test_rejects_extra_commands() -> None:
    mod = _load()
    text = TEMPLATE.replace("uvx \\", "cp /tests/test.py /app/test.py\nuvx \\")
    with pytest.raises(mod.Skip, match="non-template"):
        mod.parse_test_sh(text)


def test_rejects_other_python_and_missing_pytest() -> None:
    mod = _load()
    with pytest.raises(mod.Skip, match=r"3\.13"):
        mod.parse_test_sh(TEMPLATE.replace("-p 3.13", "-p 3.12"))
    with pytest.raises(mod.Skip, match="no uvx pytest"):
        mod.parse_test_sh("#!/bin/bash\napt-get update\n")


def test_dockerfile_keeps_isolation_out_of_scope() -> None:
    # The derived image only adds test deps and path symlinks; it must not set USER or volumes
    # that would change how the unchanged Aethens runner starts the container.
    mod = _load()
    df = mod.DOCKERFILE
    assert "ln -s /work /app" in df
    assert "VOLUME" not in df
    assert df.count("USER") == 1  # only `USER root` for the build steps; runner sets --user
