"""Run checks over tasks and assemble a Report. Library code: no printing, no exit codes."""

from __future__ import annotations

import contextlib
import os
import signal
import threading
import time
import types
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

from aethens import __version__
from aethens.cache import ResultCache, cache_key, task_environment
from aethens.checks.base import Check, CheckContext, repro
from aethens.errors import AuditConfigError
from aethens.models import Coverage, Finding, Report, Task

# One task's checks share a check instance with the other workers. run() must not mutate self.
_TaskPart = tuple[tuple[Finding, ...], tuple[Coverage, ...]]


def default_jobs() -> int:
    """How many tasks ``--jobs`` runs at once when the flag is omitted.

    Capped at 4, the worker count the bench already uses (D-035). Each task may start a
    container limited to 1 GiB, so the default stays small; pass ``--jobs`` to raise it.
    """
    return max(1, min(os.cpu_count() or 1, 4))


def run_audit(
    tasks: Sequence[Task],
    checks: Sequence[Check],
    ctx: CheckContext,
    *,
    jobs: int = 1,
    cache: ResultCache | None = None,
    image_fingerprint: Callable[[str], str] | None = None,
) -> Report:
    """Audit every task with every check.

    ``jobs`` is how many tasks run at once. The default is 1, so existing callers stay
    sequential (the bench has its own pool and must not gain a second one). Findings and
    coverage are concatenated in input task order, then check order. That order does not
    depend on which task finishes first. Each task still calls the same runner: its own
    disposable copy and its own container or process group. Nothing here changes Docker flags.

    ``cache`` stores one entry per task after that task's checks all finish. Pass
    ``image_fingerprint`` when the runner mode is ``docker`` (see
    :class:`aethens.cache.DockerImageDigest`). ``started_at`` and ``duration_s`` describe this
    call, including cache hits, not the wall time of the original cached executions.
    """
    if isinstance(jobs, bool) or not isinstance(jobs, int) or jobs < 1:
        raise AuditConfigError(f"jobs must be an integer >= 1, got {jobs!r}")
    started = datetime.now(UTC).replace(microsecond=0).isoformat()
    t0 = time.monotonic()
    parts = _run_tasks(tasks, checks, ctx, jobs, cache, image_fingerprint)
    findings = tuple(finding for found, _covered in parts for finding in found)
    coverage = tuple(item for _found, covered in parts for item in covered)
    return Report(
        tool_version=__version__,
        task_ids=tuple(task.id for task in tasks),
        checks_run=tuple(check.id for check in checks),
        budget=ctx.budget,
        seed=ctx.seed,
        findings=findings,
        coverage=coverage,
        started_at=started,
        duration_s=round(time.monotonic() - t0, 3),
    )


def _run_tasks(
    tasks: Sequence[Task],
    checks: Sequence[Check],
    ctx: CheckContext,
    jobs: int,
    cache: ResultCache | None,
    image_fingerprint: Callable[[str], str] | None,
) -> list[_TaskPart]:
    # Set on SIGINT and on any exception out of the pool. A task still inside _execute when this
    # is set must not be cached: a terminal SIGINT is delivered to the whole process group, so a
    # verifier can die with KeyboardInterrupt and look like an ordinary failure (false C002).
    cancel = threading.Event()
    with _note_interrupts(cancel):
        if jobs == 1 or len(tasks) <= 1:
            try:
                return [
                    _audit_one(task, checks, ctx, cache, image_fingerprint, cancel)
                    for task in tasks
                ]
            except BaseException as exc:
                # KeyboardInterrupt and SIGTERM's Terminated are not Exception. A check or
                # runner error is: the sibling that already finished may still be cached.
                if not isinstance(exc, Exception):
                    cancel.set()
                raise
        # Threads: a task spends its time waiting on the runner. Each run already has its own
        # work directory and container name (DockerRunner) or process group (LocalRunner).
        pool = ThreadPoolExecutor(max_workers=min(jobs, len(tasks)), thread_name_prefix="aethens")
        futures: list[Future[_TaskPart]] = []
        try:
            futures = [
                pool.submit(_audit_one, task, checks, ctx, cache, image_fingerprint, cancel)
                for task in tasks
            ]
            # result() in submission order, so completion order cannot change the report.
            return [fut.result() for fut in futures]
        except BaseException as exc:
            # Same rule as the sequential path: only an interrupt drops in-flight results.
            if not isinstance(exc, Exception):
                cancel.set()
            for fut in futures:
                fut.cancel()
            raise
        finally:
            # Wait for tasks already in the pool so each runner's finally still removes its
            # container. That wait is the rest of those tasks, not only the current verifier run.
            # Not-yet-started tasks were cancelled. Their results are not cached (D-068).
            pool.shutdown(wait=True, cancel_futures=True)


@contextlib.contextmanager
def _note_interrupts(cancel: threading.Event) -> Iterator[None]:
    """Set ``cancel`` as soon as the main thread sees SIGINT, then keep the previous handler."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGINT)

    def handler(signum: int, frame: types.FrameType | None) -> None:
        cancel.set()
        if callable(previous):
            previous(signum, frame)
            return
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def _audit_one(
    task: Task,
    checks: Sequence[Check],
    ctx: CheckContext,
    cache: ResultCache | None,
    image_fingerprint: Callable[[str], str] | None,
    cancel: threading.Event,
) -> _TaskPart:
    if cache is None:
        return _execute(task, checks, ctx)
    environment = task_environment(task, ctx, image_fingerprint)
    key = cache_key(task, checks, ctx, environment=environment)
    hit = cache.get(key, task.id)
    if hit is not None:
        found, covered = hit
        return _refresh_repro(found, task, ctx), covered
    found, covered = _execute(task, checks, ctx)
    # Checked after the runs return: an interrupt during them must not be stored.
    if cancel.is_set():
        return found, covered
    cache.put(key, task.id, found, covered)
    return found, covered


def _execute(task: Task, checks: Sequence[Check], ctx: CheckContext) -> _TaskPart:
    findings: list[Finding] = []
    coverage: list[Coverage] = []
    for check in checks:
        found, covered = check.run_with_coverage(task, ctx)
        findings.extend(found)
        coverage.extend(covered)
    return tuple(findings), tuple(coverage)


def _refresh_repro(
    findings: tuple[Finding, ...], task: Task, ctx: CheckContext
) -> tuple[Finding, ...]:
    """Repro paths depend on the working directory. Recompute them on a cache hit."""
    return tuple(replace(finding, repro=repro(task, finding.check_id, ctx)) for finding in findings)
