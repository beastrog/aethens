"""Task parallelism, the result cache and resume. No Docker: a fake runner or the local runner.

These tests pin behaviour that must not drift: report order, per-task run sequences, cache
invalidation, and that a failed task is not stored. They do not change check expectations.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import signal
import stat
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.audit import default_jobs, run_audit
from aethens.cache import (
    DockerImageDigest,
    ResultCache,
    default_cache_dir,
    format_fingerprint,
    hash_task_files,
    inspect_image_fingerprint,
)
from aethens.checks import C001GoldSanity, C002Flakiness, C004MutationProbes
from aethens.checks.base import CheckContext
from aethens.errors import (
    AuditConfigError,
    CacheError,
    ContainerStartError,
    MissingFileError,
    RunnerError,
    SymlinkEscapeError,
)
from aethens.models import REPORT_SCHEMA, Budget, Finding
from aethens.runner import LocalRunner, RunResult, RunSpec
from fakes import result

REPO = Path(__file__).resolve().parent.parent
ADD = load_task(REPO / "examples" / "add-two")
WORD = load_task(REPO / "examples" / "word-format")
PLAIN = load_task(REPO / "tests" / "fixtures" / "plain-add")
ID_A = "sha256:" + "ab" * 32
ID_B = "sha256:" + "cd" * 32
FP = format_fingerprint(ID_A, [ID_B])
FP_OTHER = format_fingerprint(ID_B, [ID_A])


def fp(_image: str) -> str:
    return FP


Decide = Callable[[RunSpec, int], RunResult]
Delay = Callable[[RunSpec], float]


class RecordingRunner:
    """Thread-safe runner. The decision must depend on the spec, not on a global call index."""

    mode: str = "docker"

    def __init__(self, decide: Decide | None = None, sleep_for: Delay | None = None) -> None:
        self.decide: Decide = _starter_fails if decide is None else decide
        self.sleep_for = sleep_for
        self.specs: list[RunSpec] = []
        self.peak = 0
        self._current = 0
        self._lock = threading.Lock()

    def run(self, spec: RunSpec) -> RunResult:
        delay = 0.0 if self.sleep_for is None else self.sleep_for(spec)
        with self._lock:
            self._current += 1
            self.peak = max(self.peak, self._current)
            n = len(self.specs)
            self.specs.append(spec)
        if delay:
            time.sleep(delay)
        try:
            return self.decide(spec, n)
        finally:
            with self._lock:
                self._current -= 1


def _starter_fails(spec: RunSpec, _i: int) -> RunResult:
    if len(spec.layers) == 2:
        return result(1)
    return result(0)


def _always_pass(_spec: RunSpec, _i: int) -> RunResult:
    return result(0)


def _ctx(runner: RecordingRunner, *, seed: int = 0, budget: Budget = Budget.SMOKE) -> CheckContext:
    return CheckContext(runner=runner, seed=seed, budget=budget)


def _names(specs: list[RunSpec]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for spec in specs:
        root = spec.layers[0][0].parent.name
        kind = "starter" if len(spec.layers) == 2 else Path(spec.layers[1][0]).name
        groups.setdefault(root, []).append(kind)
    return groups


def _stable(findings: Sequence[Finding]) -> list[dict[str, object]]:
    """Finding dicts without output tails (those embed the disposable work directory)."""
    out: list[dict[str, object]] = []
    for finding in findings:
        data: dict[str, object] = dict(finding.to_dict())
        evidence = dict(finding.evidence.to_dict())
        evidence.pop("stdout_tail")
        evidence.pop("stderr_tail")
        data["evidence"] = evidence
        out.append(data)
    return out


def _without_clock(report_dict: dict[str, object]) -> dict[str, object]:
    data = dict(report_dict)
    data.pop("started_at")
    data.pop("duration_s")
    return data


def test_library_default_is_one_job_and_no_cache() -> None:
    params = inspect.signature(run_audit).parameters
    assert params["jobs"].default == 1
    assert params["cache"].default is None
    assert 1 <= default_jobs() == max(1, min(os.cpu_count() or 1, 4)) <= 4


def test_jobs_below_one_is_an_error() -> None:
    runner = RecordingRunner()
    with pytest.raises(AuditConfigError):
        run_audit([PLAIN], [C001GoldSanity()], _ctx(runner), jobs=0)


def test_parallel_report_matches_sequential_order_and_per_task_calls() -> None:
    checks = [C001GoldSanity(), C002Flakiness()]
    sequential = RecordingRunner()
    parallel = RecordingRunner()
    tasks = [ADD, WORD]
    report_a = run_audit(tasks, checks, _ctx(sequential), jobs=1, cache=None)
    report_b = run_audit(tasks, checks, _ctx(parallel), jobs=4, cache=None)
    assert _without_clock(report_a.to_dict()) == _without_clock(report_b.to_dict())
    assert report_b.schema == REPORT_SCHEMA
    assert set(report_b.to_dict()) == {
        "schema",
        "tool_version",
        "task_ids",
        "checks_run",
        "budget",
        "seed",
        "findings",
        "coverage",
        "started_at",
        "duration_s",
    }
    assert _names(sequential.specs) == _names(parallel.specs)
    for spec in parallel.specs:
        root = spec.layers[0][0].parent.resolve()
        for src, _dest in spec.layers:
            assert src.resolve().is_relative_to(root)


def test_slower_task_does_not_jump_the_report_queue() -> None:
    def delay(spec: RunSpec) -> float:
        return 0.15 if spec.layers[0][0].parent.name == "add-two" else 0.0

    finished: list[str] = []
    lock = threading.Lock()

    def decide(spec: RunSpec, _i: int) -> RunResult:
        with lock:
            finished.append(spec.layers[0][0].parent.name)
        return _always_pass(spec, _i)

    runner = RecordingRunner(decide=decide, sleep_for=delay)
    report = run_audit([ADD, WORD], [C001GoldSanity()], _ctx(runner), jobs=2)
    assert [f.task_id for f in report.findings] == ["add-two", "word-format"]
    assert finished[0] == "word-format"
    assert runner.peak >= 2


def test_failed_task_is_not_cached_and_a_finished_sibling_is(tmp_path: Path) -> None:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        if spec.layers[0][0].parent.name == "add-two":
            raise RunnerError("boom")
        time.sleep(0.05)
        return _starter_fails(spec, _i)

    runner = RecordingRunner(decide=decide)
    cache = ResultCache(tmp_path / "cache")
    with pytest.raises(RunnerError):
        run_audit(
            [ADD, WORD],
            [C001GoldSanity()],
            _ctx(runner),
            jobs=2,
            cache=cache,
            image_fingerprint=fp,
        )
    again = RecordingRunner()
    run_audit(
        [ADD, WORD],
        [C001GoldSanity()],
        _ctx(again),
        jobs=2,
        cache=cache,
        image_fingerprint=fp,
    )
    seen = {spec.layers[0][0].parent.name for spec in again.specs}
    assert "word-format" not in seen
    assert "add-two" in seen


def test_resume_skips_tasks_already_in_the_cache(tmp_path: Path) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    run_audit([ADD], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    runner.specs.clear()
    report = run_audit(
        [ADD, WORD],
        [C001GoldSanity()],
        _ctx(runner),
        jobs=2,
        cache=cache,
        image_fingerprint=fp,
    )
    seen = [spec.layers[0][0].parent.name for spec in runner.specs]
    assert seen
    assert "add-two" not in seen
    assert "word-format" in seen
    assert cache.hits == 1
    assert report.task_ids == ("add-two", "word-format")
    assert report.schema == REPORT_SCHEMA


def test_second_identical_run_does_not_call_the_runner(tmp_path: Path) -> None:
    runner = RecordingRunner(decide=_always_pass)
    cache = ResultCache(tmp_path / "cache")
    ctx = _ctx(runner)
    first = run_audit([PLAIN], [C001GoldSanity()], ctx, cache=cache, image_fingerprint=fp)
    calls = len(runner.specs)
    assert calls > 0
    runner.specs.clear()
    second = run_audit([PLAIN], [C001GoldSanity()], ctx, cache=cache, image_fingerprint=fp)
    assert runner.specs == []
    assert _without_clock(first.to_dict()) == _without_clock(second.to_dict())
    assert cache.hits == 1 and cache.misses == 1


def test_cache_miss_on_seed_budget_checks_digest_version_and_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    checks = [C001GoldSanity()]
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 2

    run_audit([PLAIN], checks, _ctx(runner, seed=1), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 4
    run_audit([PLAIN], checks, _ctx(runner, budget=Budget.DEEP), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 6
    run_audit(
        [PLAIN],
        [C001GoldSanity(), C002Flakiness()],
        _ctx(runner),
        cache=cache,
        image_fingerprint=fp,
    )
    assert len(runner.specs) > 6
    before = len(runner.specs)
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=lambda _image: FP_OTHER)
    assert len(runner.specs) > before

    monkeypatch.setattr("aethens.cache.__version__", "9.9.9-test")
    before = len(runner.specs)
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) > before

    monkeypatch.setattr("aethens.cache.package_code_digest", lambda: "different-sources")
    before = len(runner.specs)
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) > before


def test_local_mode_ignores_image_fingerprint_and_does_not_reuse_docker(
    tmp_path: Path,
) -> None:
    docker_runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    run_audit(
        [PLAIN],
        [C001GoldSanity()],
        _ctx(docker_runner),
        cache=cache,
        image_fingerprint=fp,
    )
    local = RecordingRunner()
    local.mode = "local"
    run_audit([PLAIN], [C001GoldSanity()], _ctx(local), cache=cache, image_fingerprint=fp)
    assert len(local.specs) == 2
    # Same local fingerprint is a hit even if the docker digest callable would differ.
    local.specs.clear()
    run_audit(
        [PLAIN],
        [C001GoldSanity()],
        _ctx(local),
        cache=cache,
        image_fingerprint=lambda _image: FP_OTHER,
    )
    assert local.specs == []


def test_docker_cache_without_fingerprint_is_rejected(tmp_path: Path) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    with pytest.raises(AuditConfigError):
        run_audit([PLAIN], [C001GoldSanity()], _ctx(runner), cache=cache)


def test_bad_fingerprint_is_rejected(tmp_path: Path) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    with pytest.raises(CacheError):
        run_audit(
            [PLAIN],
            [C001GoldSanity()],
            _ctx(runner),
            cache=cache,
            image_fingerprint=lambda _image: "latest",
        )


def test_unsafe_local_and_filter_flag_are_part_of_the_key(tmp_path: Path) -> None:
    runner = RecordingRunner(decide=_always_pass)
    cache = ResultCache(tmp_path / "cache")
    ctx = _ctx(runner)
    run_audit([PLAIN], [C001GoldSanity()], ctx, cache=cache, image_fingerprint=fp)
    other = CheckContext(runner=runner, seed=0, budget=Budget.SMOKE, unsafe_local=True)
    before = len(runner.specs)
    run_audit([PLAIN], [C001GoldSanity()], other, cache=cache, image_fingerprint=fp)
    assert len(runner.specs) > before

    c004 = RecordingRunner(decide=_always_pass)
    c004_cache = ResultCache(tmp_path / "c004")
    run_audit(
        [PLAIN],
        [C004MutationProbes(filter_equivalent=True)],
        _ctx(c004),
        cache=c004_cache,
        image_fingerprint=fp,
    )
    stored = len(c004.specs)
    assert stored > 0
    c004.specs.clear()
    run_audit(
        [PLAIN],
        [C004MutationProbes(filter_equivalent=True)],
        _ctx(c004),
        cache=c004_cache,
        image_fingerprint=fp,
    )
    assert c004.specs == []
    run_audit(
        [PLAIN],
        [C004MutationProbes(filter_equivalent=False)],
        _ctx(c004),
        cache=c004_cache,
        image_fingerprint=fp,
    )
    assert c004.specs


def test_file_bytes_and_mode_bust_the_cache_mtime_does_not(tmp_path: Path) -> None:
    root = tmp_path / "task"
    shutil.copytree(REPO / "tests" / "fixtures" / "plain-add", root)
    task = load_task(root)
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    run_audit([task], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 2

    gold = root / "gold" / "solution.py"
    os.utime(gold, (1_700_000_000, 1_700_000_000))
    task = load_task(root)
    run_audit([task], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 2

    os.chmod(gold, 0o600)
    task = load_task(root)
    run_audit([task], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 4

    gold.write_text(gold.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    task = load_task(root)
    run_audit([task], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 6


def test_corrupt_entry_is_recomputed(tmp_path: Path) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    run_audit([PLAIN], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    files = list(cache.root.rglob("*.json"))
    assert len(files) == 1
    files[0].write_text("{not json", encoding="utf-8")
    runner.specs.clear()
    run_audit([PLAIN], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 2
    json.loads(files[0].read_text(encoding="utf-8"))


def test_cache_hit_recomputes_repro_for_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(decide=_always_pass)
    cache = ResultCache(tmp_path / "cache")
    ctx = _ctx(runner)
    run_audit([PLAIN], [C001GoldSanity()], ctx, cache=cache, image_fingerprint=fp)
    monkeypatch.chdir(PLAIN.root)
    quiet = RecordingRunner(decide=_always_pass)
    cached = run_audit([PLAIN], [C001GoldSanity()], _ctx(quiet), cache=cache, image_fingerprint=fp)
    assert quiet.specs == []
    fresh = run_audit([PLAIN], [C001GoldSanity()], _ctx(RecordingRunner(decide=_always_pass)))
    assert cached.findings[0].repro == fresh.findings[0].repro
    assert cached.findings[0].repro.startswith("aethens audit . ")


def test_exception_during_a_task_writes_no_entry(tmp_path: Path) -> None:
    def boom(_spec: RunSpec, _i: int) -> RunResult:
        raise RunnerError("nope")

    runner = RecordingRunner(decide=boom)
    cache = ResultCache(tmp_path / "cache")
    with pytest.raises(RunnerError):
        run_audit([PLAIN], [C001GoldSanity()], _ctx(runner), cache=cache, image_fingerprint=fp)
    assert list(cache.root.rglob("*.json")) == []


def test_hash_ignores_mtime_and_rejects_bad_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "task"
    shutil.copytree(REPO / "tests" / "fixtures" / "plain-add", root)
    first = hash_task_files(root)
    gold = root / "gold" / "solution.py"
    os.utime(gold, (1_600_000_000, 1_600_000_000))
    assert hash_task_files(root) == first
    mode = stat.S_IMODE(gold.stat().st_mode)
    os.chmod(gold, 0o700 if mode != 0o700 else 0o640)
    assert hash_task_files(root) != first

    alias = root / "alias.py"
    alias.symlink_to("gold/solution.py")
    linked = hash_task_files(root)
    alias.unlink()
    alias.symlink_to("starter/solution.py")
    assert hash_task_files(root) != linked
    (root / "loop").symlink_to(".")
    hash_task_files(root)  # directory symlink to "." must not hang
    (root / "loop").unlink()
    (root / "evil").symlink_to("/etc/passwd")
    with pytest.raises(SymlinkEscapeError):
        hash_task_files(root)
    (root / "evil").unlink()
    (root / "dangling").symlink_to("missing-file")
    with pytest.raises(MissingFileError):
        hash_task_files(root)


def test_identical_trees_hash_equal(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    shutil.copytree(REPO / "tests" / "fixtures" / "plain-add", a)
    shutil.copytree(REPO / "tests" / "fixtures" / "plain-add", b)
    assert hash_task_files(a) == hash_task_files(b)


def test_default_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert default_cache_dir() == tmp_path / "xdg" / "aethens"
    monkeypatch.setenv("XDG_CACHE_HOME", "  ")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_cache_dir() == tmp_path / ".cache" / "aethens"


def test_fake_docker_inspect_parses_id_and_repo_digest(tmp_path: Path) -> None:
    seen = tmp_path / "argv.txt"
    image_id = "sha256:" + "11" * 32
    repo = "sha256:" + "22" * 32
    script = tmp_path / "docker"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(seen)!r}).write_text('\\n'.join(sys.argv))\n"
        "if sys.argv[1:3] != ['image', 'inspect']:\n"
        "    raise SystemExit(1)\n"
        f"print({image_id!r} + '|[\"python@' + {repo!r} + '\"]')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    got = inspect_image_fingerprint(str(script), "python:3.12-slim")
    assert got == format_fingerprint(image_id, [repo])
    argv = seen.read_text(encoding="utf-8").splitlines()
    assert argv[1:4] == ["image", "inspect", "--format"]
    assert argv[-1] == "python:3.12-slim"
    again = DockerImageDigest(str(script))
    assert again("python:3.12-slim") == got
    # Memo: a second call must not need the binary to succeed.
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    assert again("python:3.12-slim") == got


def test_fake_docker_missing_image_and_bad_id(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    missing.write_text(
        "#!/bin/sh\necho 'Error: No such image: python:missing' >&2\nexit 1\n",
        encoding="utf-8",
    )
    missing.chmod(0o755)
    with pytest.raises(ContainerStartError):
        inspect_image_fingerprint(str(missing), "python:missing")
    bad = tmp_path / "bad"
    bad.write_text("#!/bin/sh\necho 'nope|[]'\n", encoding="utf-8")
    bad.chmod(0o755)
    with pytest.raises(CacheError):
        inspect_image_fingerprint(str(bad), "python:3.12-slim")


@pytest.mark.docker
@pytest.mark.docker
def test_pulled_image_fingerprint_format() -> None:
    # Format only. Docker 28.5.2's classic store reports Id != RepoDigest; the containerd image
    # store can report them equal. Both are valid fingerprints.
    fingerprint = DockerImageDigest()("python:3.12-slim")
    image_id, sep, repos = fingerprint.partition(";repo=")
    assert sep == ";repo="
    body = image_id.removeprefix("id=")
    assert body.startswith("sha256:") and len(body) == len("sha256:") + 64
    if repos:
        for piece in repos.split(","):
            assert piece.startswith("sha256:") and len(piece) == len("sha256:") + 64
    assert DockerImageDigest()("python:3.12-slim") == fingerprint


def test_local_runner_jobs_match_and_cache(tmp_path: Path) -> None:
    tasks = [
        load_task(REPO / "examples" / "add-two"),
        load_task(REPO / "bench" / "tasks" / "brokengold-offbyone"),
    ]
    runner = LocalRunner(allow_unsafe_local=True)
    checks = [C001GoldSanity()]
    ctx = CheckContext(runner=runner, seed=0, budget=Budget.SMOKE, unsafe_local=True)
    sequential = run_audit(tasks, checks, ctx, jobs=1)
    parallel = run_audit(tasks, checks, ctx, jobs=4)
    # Tracebacks name the disposable copy, so the tails differ; the verdicts must not.
    assert _stable(sequential.findings) == _stable(parallel.findings)
    tails = [f.evidence.stderr_tail for f in (sequential.findings[0], parallel.findings[0])]
    assert all("/aethens-local-" in tail and "work/tests/test_seq.py" in tail for tail in tails)
    assert tails[0] != tails[1]
    cache = ResultCache(tmp_path / "cache")
    cached = run_audit(tasks, checks, ctx, jobs=2, cache=cache)
    assert cache.misses == 2 and cache.hits == 0
    again = run_audit(tasks, checks, ctx, jobs=2, cache=cache)
    assert cache.hits == 2
    assert [f.to_dict() for f in cached.findings] == [f.to_dict() for f in again.findings]


def test_interrupt_does_not_cache_the_task_in_flight(tmp_path: Path) -> None:
    sent = False

    def decide(spec: RunSpec, _i: int) -> RunResult:
        nonlocal sent
        if spec.layers[0][0].parent.name == "word-format":
            if not sent:
                sent = True
                os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.5)
        return result(1)

    runner = RecordingRunner(decide=decide)
    cache = ResultCache(tmp_path / "cache")
    with pytest.raises(KeyboardInterrupt):
        run_audit(
            [ADD, WORD],
            [C001GoldSanity()],
            _ctx(runner),
            jobs=2,
            cache=cache,
            image_fingerprint=fp,
        )
    stored = [
        json.loads(path.read_text(encoding="utf-8"))["task_id"]
        for path in cache.root.rglob("*.json")
    ]
    assert "word-format" not in stored


def test_host_python_and_pyyaml_bust_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner()
    cache = ResultCache(tmp_path / "cache")
    checks = [C001GoldSanity()]
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 2
    monkeypatch.setattr("aethens.cache._host_python", lambda: "python-under-test")
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 4
    monkeypatch.setattr("aethens.cache._pyyaml_version", lambda: "0.0.test")
    run_audit([PLAIN], checks, _ctx(runner), cache=cache, image_fingerprint=fp)
    assert len(runner.specs) == 6


def test_cache_dir_must_be_private(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    cache = ResultCache(root)
    assert stat.S_IMODE(root.stat().st_mode) & 0o077 == 0
    run_audit(
        [PLAIN], [C001GoldSanity()], _ctx(RecordingRunner()), cache=cache, image_fingerprint=fp
    )
    files = list(root.rglob("*.json"))
    assert files
    assert stat.S_IMODE(files[0].stat().st_mode) & 0o077 == 0
    opened = tmp_path / "opened"
    opened.mkdir()
    opened.chmod(0o777)
    with pytest.raises(CacheError):
        ResultCache(opened)


def test_format_fingerprint_sorts_and_rejects_garbage() -> None:
    assert format_fingerprint(ID_B, [ID_A, ID_B, ID_A]) == f"id={ID_B};repo={ID_A},{ID_B}"
    with pytest.raises(CacheError):
        format_fingerprint("latest", [])
