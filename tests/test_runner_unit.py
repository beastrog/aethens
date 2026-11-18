"""Runner pieces that do not need Docker (B3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aethens.errors import DockerUnavailableError, RunnerError, UnsafeLocalNotAllowedError
from aethens.runner import DockerRunner, Limits, LocalRunner, RunSpec, build_workdir
from aethens.runner.base import tail_text


def spec(tmp_path: Path, **kw: object) -> RunSpec:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    base: dict[str, object] = {
        "image": "python:3.12-slim",
        "command": ("python", "-c", "print(1)"),
        "layers": ((src, Path(".")),),
        "timeout_s": 5.0,
    }
    base.update(kw)
    return RunSpec(**base)  # type: ignore[arg-type]


def test_docker_argv_has_every_isolation_flag(tmp_path: Path) -> None:
    runner = DockerRunner()
    argv = runner.build_argv(spec(tmp_path, env={"PYTHONHASHSEED": "3"}), tmp_path, "aethens-x")
    joined = " ".join(argv)
    for flag in (
        "--network none",
        "--memory 1024m",
        "--memory-swap 1024m",
        "--cpus 1.0",
        "--pids-limit 256",
        "--read-only",
        "--tmpfs /tmp:rw,nosuid,nodev,size=256m",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--pull never",
        "--workdir /work",
        "-e PYTHONHASHSEED=3",
        "-e HOME=/tmp",
    ):
        assert flag in joined, flag
    assert f"type=bind,src={tmp_path},dst=/work" in joined
    user = argv[argv.index("--user") + 1]
    assert not user.startswith("0:")
    # image comes right before the command, after every option
    i = argv.index("python:3.12-slim")
    assert argv[i + 1 :] == ["python", "-c", "print(1)"]
    assert "--rm" not in argv  # removal is explicit, after inspection


def test_docker_user_never_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getuid", lambda: 0)
    monkeypatch.setattr(os, "getgid", lambda: 0)
    argv = DockerRunner().build_argv(spec(tmp_path), tmp_path, "aethens-x")
    assert argv[argv.index("--user") + 1] == "65534:65534"


def test_bad_env_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(RunnerError):
        DockerRunner().build_argv(spec(tmp_path, env={"A B": "1"}), tmp_path, "aethens-x")


def test_mount_path_with_comma_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "a,b"
    bad.mkdir()
    with pytest.raises(RunnerError):
        DockerRunner().build_argv(spec(tmp_path), bad, "aethens-x")


def test_docker_unavailable(tmp_path: Path) -> None:
    runner = DockerRunner(docker_bin="/nonexistent/docker-binary")
    with pytest.raises(DockerUnavailableError):
        runner.ensure_available()
    with pytest.raises(DockerUnavailableError):
        runner.run(spec(tmp_path))


def test_local_requires_explicit_flag() -> None:
    with pytest.raises(UnsafeLocalNotAllowedError):
        LocalRunner()
    with pytest.raises(UnsafeLocalNotAllowedError):
        LocalRunner(allow_unsafe_local=False)


def test_build_workdir_layers_in_order(tmp_path: Path) -> None:
    starter, gold, tests = tmp_path / "starter", tmp_path / "gold", tmp_path / "tests"
    for d in (starter, gold, tests):
        d.mkdir()
    (starter / "sol.py").write_text("starter")
    (starter / "keep.py").write_text("keep")
    (gold / "sol.py").write_text("gold")
    (tests / "test_x.py").write_text("t")
    os.symlink("sol.py", gold / "alias.py")
    dest = tmp_path / "work"
    dest.mkdir()
    build_workdir(((starter, Path(".")), (gold, Path(".")), (tests, Path("tests"))), dest)
    assert (dest / "sol.py").read_text() == "gold"
    assert (dest / "keep.py").read_text() == "keep"
    assert (dest / "tests" / "test_x.py").read_text() == "t"
    assert not (dest / "alias.py").is_symlink()  # dereferenced: containers never see symlinks
    assert (dest / "alias.py").read_text() == "gold"


def test_tail_text_truncates() -> None:
    text, truncated = tail_text(b"x" * 100 + b"END", 10)
    assert truncated and text.endswith("END") and len(text) <= 10 + 40
    text, truncated = tail_text(b"short", 10)
    assert text == "short" and not truncated


def test_limits_defaults() -> None:
    lim = Limits()
    assert (lim.memory_mb, lim.cpus, lim.pids, lim.max_output_bytes) == (1024, 1.0, 256, 65536)
