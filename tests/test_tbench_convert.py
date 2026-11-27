"""Unit tests for bench/tbench/convert_tb2.py (no Docker, no network)."""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
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


def _tar_bytes(*entries: tuple[str, bytes | None, str]) -> bytes:
    """Build an in-memory tar. Each entry is (name, content, kind) with kind in file/dir/sym/lnk."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name=name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tf.addfile(info)
            elif kind == "sym":
                info.type = tarfile.SYMTYPE
                info.linkname = (content or b"").decode()
                tf.addfile(info)
            elif kind == "lnk":
                info.type = tarfile.LNKTYPE
                info.linkname = (content or b"").decode()
                tf.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tf.addfile(info)
            else:
                data = content or b""
                info.size = len(data)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_dest_for_app_member_accepts_safe_paths_and_rejects_escapes(tmp_path: Path) -> None:
    # Called directly so the manual checker runs on every Python version (no filter='data' branch).
    mod = _load()
    dest = tmp_path / "dest"
    dest.mkdir()
    assert mod._dest_for_app_member("app/foo.txt", dest) == dest.resolve() / "foo.txt"
    assert mod._dest_for_app_member("app/sub/dir/file", dest) == dest.resolve() / "sub/dir/file"
    assert mod._dest_for_app_member("app", dest) is None
    assert mod._dest_for_app_member("other/file", dest) is None
    with pytest.raises(mod.Skip, match="escape"):
        mod._dest_for_app_member("app/../evil.txt", dest)
    with pytest.raises(mod.Skip, match="escape"):
        mod._dest_for_app_member("app/foo/../../../evil.txt", dest)
    with pytest.raises(mod.Skip, match="escape"):
        mod._dest_for_app_member("other/../evil.txt", dest)
    with pytest.raises(mod.Skip, match="absolute"):
        mod._dest_for_app_member("/app/foo.txt", dest)
    with pytest.raises(mod.Skip, match="absolute"):
        mod._dest_for_app_member("/etc/passwd", dest)


def test_extract_app_writes_files_under_dest(tmp_path: Path) -> None:
    mod = _load()
    dest = tmp_path / "dest"
    payload = b"hello"
    data = _tar_bytes(
        ("app", None, "dir"),
        ("app/hello.txt", payload, "file"),
        ("app/sub", None, "dir"),
        ("app/sub/nested.txt", b"nested", "file"),
        ("not-app/ignored.txt", b"nope", "file"),
    )
    mod._extract_app(data, dest)
    assert (dest / "hello.txt").read_bytes() == payload
    assert (dest / "sub" / "nested.txt").read_bytes() == b"nested"
    assert not (dest / "not-app").exists()
    assert not (dest / "ignored.txt").exists()


def test_extract_app_rejects_malicious_tar_path_escape(tmp_path: Path) -> None:
    mod = _load()
    dest = tmp_path / "dest"
    outside = tmp_path / "evil.txt"
    payload = b"pwned"
    data = _tar_bytes(("app/../evil.txt", payload, "file"))
    with pytest.raises(mod.Skip, match="escape"):
        mod._extract_app(data, dest)
    assert not outside.exists()
    assert list(dest.rglob("*")) == [] if dest.exists() else True


def test_extract_app_rejects_links_and_special_files(tmp_path: Path) -> None:
    mod = _load()
    dest = tmp_path / "dest"
    with pytest.raises(mod.Skip, match="link"):
        mod._extract_app(_tar_bytes(("app/link", b"../outside", "sym")), dest)
    with pytest.raises(mod.Skip, match="link"):
        mod._extract_app(_tar_bytes(("app/hard", b"app/hello.txt", "lnk")), dest)
    with pytest.raises(mod.Skip, match="special file"):
        mod._extract_app(_tar_bytes(("app/fifo", None, "fifo")), dest)
    assert not (dest / "link").exists()
    assert not (dest / "hard").exists()
    assert not (dest / "fifo").exists()
