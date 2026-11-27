"""Check interface and the helpers every check shares (run specs, evidence, ids, repro)."""

from __future__ import annotations

import hashlib
import os
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from aethens.models import Budget, Confidence, Coverage, Evidence, Finding, Severity, Task
from aethens.runner import Runner, RunResult, RunSpec

FLAKY_RUNS = {Budget.SMOKE: 3, Budget.STANDARD: 5, Budget.DEEP: 10}


@dataclass(frozen=True)
class CheckContext:
    runner: Runner
    seed: int
    budget: Budget
    unsafe_local: bool = False


class Check(ABC):
    id: str
    title: str
    tier: str  # "core" or "probe"
    cost_class: str  # "low" (a few runs), "medium" (N runs), "high" (one run per mutant)

    @abstractmethod
    def run(self, task: Task, ctx: CheckContext) -> list[Finding]: ...

    def cache_config(self) -> dict[str, str]:
        """Settings that change this check's results, included in the result-cache key.

        The default is empty. A check that stores result-changing state on ``self`` must
        override this (C004's equivalent-mutant filter does). Values are strings so the key
        is canonical. ``run`` must not mutate ``self``: one instance is shared by worker threads.
        """
        return {}

    def run_with_coverage(
        self, task: Task, ctx: CheckContext
    ) -> tuple[list[Finding], list[Coverage]]:
        """Findings plus what the check established when it found nothing (default: nothing)."""
        return self.run(task, ctx), []


def hash_seed(seed: int, task_id: str, check_id: str, salt: int | str) -> int:
    """Deterministic PYTHONHASHSEED value (0..2**32-1) for one run."""
    digest = hashlib.sha256(f"{seed}|{task_id}|{check_id}|{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def run_spec(task: Task, overlay: Path | None, env: dict[str, str]) -> RunSpec:
    """starter, then the overlay (if any), then tests at their task-relative path."""
    layers: list[tuple[Path, Path]] = [(task.root / task.starter, Path("."))]
    if overlay is not None:
        layers.append((task.root / overlay, Path(".")))
    layers.append((task.root / task.tests, task.tests))
    return RunSpec(
        image=task.image,
        command=task.verifier,
        layers=tuple(layers),
        timeout_s=float(task.timeout_s),
        env=env,
    )


def describe(result: RunResult) -> str:
    if result.timed_out:
        return "timed out (killed)"
    text = f"exit code {result.exit_code}"
    if result.oom_killed:
        text += " (killed: out of memory)"
    return text


def evidence(
    subject: str,
    task: Task,
    results: list[RunResult],
    observed: str,
    extra: dict[str, str],
    tail_from: RunResult | None = None,
) -> Evidence:
    pick = tail_from if tail_from is not None else results[0]
    return Evidence(
        subject=subject,
        command=task.verifier,
        observed=observed,
        exit_codes=tuple(r.exit_code for r in results),
        timed_out=any(r.timed_out for r in results),
        stdout_tail=pick.stdout_tail,
        stderr_tail=pick.stderr_tail,
        extra=extra,
    )


def display_path(task: Task) -> str:
    """Task path for repro commands: relative to the working directory when inside it."""
    cwd = Path(os.getcwd()).resolve()
    try:
        return task.root.relative_to(cwd).as_posix() or "."
    except ValueError:
        return task.root.as_posix()


def repro(task: Task, check_id: str, ctx: CheckContext) -> str:
    parts = [
        "aethens",
        "audit",
        display_path(task),
        "--check",
        check_id,
        "--seed",
        str(ctx.seed),
        "--budget",
        ctx.budget.value,
    ]
    if ctx.unsafe_local:
        parts.append("--unsafe-local")
    return shlex.join(parts)


def make_finding(
    *,
    check_id: str,
    severity: Severity,
    task: Task,
    title: str,
    detail: str,
    ev: Evidence,
    ctx: CheckContext,
    confidence: Confidence,
    limits: str,
) -> Finding:
    key = f"{check_id}|{task.id}|{ev.subject}|{title}"
    fid = f"{check_id}-{task.id}-{hashlib.sha256(key.encode()).hexdigest()[:8]}"
    return Finding(
        id=fid,
        check_id=check_id,
        severity=severity,
        task_id=task.id,
        title=title,
        detail=detail,
        evidence=ev,
        repro=repro(task, check_id, ctx),
        seed=ctx.seed,
        confidence=confidence,
        limits=limits,
    )
