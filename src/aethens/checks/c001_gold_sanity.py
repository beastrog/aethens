"""C001 gold sanity: the unsolved starting state must fail; the gold solution must pass."""

from __future__ import annotations

from aethens.checks.base import (
    Check,
    CheckContext,
    describe,
    evidence,
    hash_seed,
    make_finding,
    run_spec,
)
from aethens.models import Confidence, Finding, Severity, Task

LIMITS = (
    "One run each of the starting state and the gold solution. A flaky verifier can cause or hide "
    "this (see C002). The tool cannot tell whether the tests or the gold solution are wrong."
)


class C001GoldSanity(Check):
    id = "C001"
    title = "Gold sanity"
    tier = "core"
    cost_class = "low"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        findings: list[Finding] = []
        starter_seed = str(hash_seed(ctx.seed, task.id, self.id, "starter"))
        starter = ctx.runner.run(run_spec(task, None, {"PYTHONHASHSEED": starter_seed}))
        if starter.passed:
            findings.append(
                make_finding(
                    check_id=self.id,
                    severity=Severity.ERROR,
                    task=task,
                    title="Verifier accepts the unsolved starting state",
                    detail=(
                        "The verifier passed on the starter files with no solution applied. "
                        "Any submission that changes nothing would be accepted, which usually "
                        "means the tests assert too little or nothing at all."
                    ),
                    ev=evidence(
                        "starter",
                        task,
                        [starter],
                        f"{describe(starter)}: expected a failure",
                        {"PYTHONHASHSEED": starter_seed},
                    ),
                    ctx=ctx,
                    confidence=Confidence.CONFIRMED,
                    limits=LIMITS,
                )
            )
        gold_seed = str(hash_seed(ctx.seed, task.id, self.id, "gold"))
        gold = ctx.runner.run(run_spec(task, task.gold, {"PYTHONHASHSEED": gold_seed}))
        if not gold.passed:
            findings.append(
                make_finding(
                    check_id=self.id,
                    severity=Severity.ERROR,
                    task=task,
                    title="Gold solution fails the verifier",
                    detail=(
                        "The reference solution, overlaid onto the starter, did not pass the "
                        "verifier. Either the gold solution or the tests are wrong; until this is "
                        "fixed, no result from this task can be trusted."
                    ),
                    ev=evidence(
                        "gold",
                        task,
                        [gold],
                        f"{describe(gold)}: expected exit code 0",
                        {"PYTHONHASHSEED": gold_seed},
                    ),
                    ctx=ctx,
                    confidence=Confidence.CONFIRMED,
                    limits=LIMITS,
                )
            )
        return findings
