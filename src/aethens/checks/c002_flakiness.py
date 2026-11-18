"""C002 flakiness: run the gold solution N times; mixed outcomes are a finding.

Each run gets a different PYTHONHASHSEED derived from the audit seed, so flakiness caused by hash
order (set and dict-of-str iteration, ``hash()``) shows up deterministically and every run can be
reproduced from the seed.
"""

from __future__ import annotations

from aethens.checks.base import (
    FLAKY_RUNS,
    Check,
    CheckContext,
    evidence,
    hash_seed,
    make_finding,
    run_spec,
)
from aethens.models import Confidence, Finding, Severity, Task
from aethens.runner import RunResult


def _outcome(r: RunResult) -> str:
    if r.timed_out:
        return "timeout"
    return "pass" if r.exit_code == 0 else "fail"


class C002Flakiness(Check):
    id = "C002"
    title = "Flakiness"
    tier = "core"
    cost_class = "medium"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        n = FLAKY_RUNS[ctx.budget]
        seeds = [str(hash_seed(ctx.seed, task.id, self.id, i)) for i in range(n)]
        results = [ctx.runner.run(run_spec(task, task.gold, {"PYTHONHASHSEED": s})) for s in seeds]
        outcomes = [_outcome(r) for r in results]
        kinds = set(outcomes)
        if len(kinds) <= 1:
            return []
        counts = {k: outcomes.count(k) for k in ("pass", "fail", "timeout")}
        extra = {
            "runs": str(n),
            "pass_count": str(counts["pass"]),
            "fail_count": str(counts["fail"]),
            "timeout_count": str(counts["timeout"]),
            "outcomes": ",".join(outcomes),
            "PYTHONHASHSEED_values": ",".join(seeds),
        }
        first_bad = next(r for r in results if not r.passed)
        observed = (
            f"{counts['pass']} pass, {counts['fail']} fail, {counts['timeout']} timeout "
            f"out of {n} identical gold runs"
        )
        limits = (
            f"{n} runs, varying only PYTHONHASHSEED. Flakiness from wall-clock time, unseeded "
            "randomness, scheduling or the network is caught only by chance; no finding does not "
            "prove the verifier is deterministic."
        )
        if "pass" in kinds and "fail" in kinds:
            severity = Severity.ERROR
            title = "Gold solution passes on some runs and fails on others"
            detail = (
                "The same gold solution gave different verdicts across runs. A flaky verifier "
                "rewards or punishes solutions at random. Output tails are from the first "
                "non-passing run; rerun with the listed PYTHONHASHSEED to reproduce one run."
            )
        else:
            severity = Severity.WARNING
            title = "Gold solution run time varies: some runs time out"
            detail = (
                "Verdicts differ only because some runs hit the timeout. The verifier may be too "
                "slow for its timeout_s, or timing-dependent."
            )
        return [
            make_finding(
                check_id=self.id,
                severity=severity,
                task=task,
                title=title,
                detail=detail,
                ev=evidence("gold", task, results, observed, extra, tail_from=first_bad),
                ctx=ctx,
                confidence=Confidence.CONFIRMED,
                limits=limits,
            )
        ]
