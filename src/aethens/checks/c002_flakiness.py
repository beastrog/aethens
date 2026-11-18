"""C002 flakiness: rerun the gold solution until a flake-rate bound is shown or flakiness is seen.

Each run gets a different PYTHONHASHSEED derived from the audit seed, so flakiness caused by hash
order (set and dict-of-str iteration, ``hash()``) shows up deterministically and every run can be
reproduced from the seed.

Adaptive (D4): C002 first makes ``MIN_RUNS[budget]`` runs. If they disagree, that is the finding.
If they all agree, it keeps running, one run at a time, until either a run disagrees (finding), or
the runs that agreed are enough to state "flake rate below p at 95% confidence" for the budget's
target p (``TARGET_P``), or the budget's time limit on summed run time is reached. Without a
finding it records a coverage statement with the bound it actually reached. The statistics are in
``aethens.stats`` and docs/DECISIONS.md (D-056).
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
from aethens.models import Budget, Confidence, Coverage, Finding, Severity, Task
from aethens.runner import RunResult
from aethens.stats import clopper_pearson, flake_upper_bound, runs_needed

MIN_RUNS = FLAKY_RUNS
TARGET_P = {Budget.SMOKE: 0.5, Budget.STANDARD: 0.25, Budget.DEEP: 0.05}
TIME_BUDGET_S = {Budget.SMOKE: 120.0, Budget.STANDARD: 300.0, Budget.DEEP: 1800.0}
CONFIDENCE = 0.95


def max_runs(budget: Budget) -> int:
    return max(MIN_RUNS[budget], runs_needed(TARGET_P[budget], CONFIDENCE))


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
        return self.run_with_coverage(task, ctx)[0]

    def run_with_coverage(
        self, task: Task, ctx: CheckContext
    ) -> tuple[list[Finding], list[Coverage]]:
        budget = ctx.budget
        lo, hi, limit = MIN_RUNS[budget], max_runs(budget), TIME_BUDGET_S[budget]
        seeds: list[str] = []
        results: list[RunResult] = []
        spent = 0.0
        stop = "target"
        while len(results) < hi:
            seed = str(hash_seed(ctx.seed, task.id, self.id, len(results)))
            r = ctx.runner.run(run_spec(task, task.gold, {"PYTHONHASHSEED": seed}))
            seeds.append(seed)
            results.append(r)
            spent += r.duration_s
            if len(results) < lo:
                continue
            if len({_outcome(x) for x in results}) > 1:
                stop = "disagreement"
                break
            if spent >= limit and len(results) < hi:
                stop = "time"
                break
        outcomes = [_outcome(r) for r in results]
        if len(set(outcomes)) <= 1:
            return [], [self._coverage(task, budget, outcomes, seeds, spent, stop)]
        return [self._finding(task, ctx, results, outcomes, seeds)], []

    def _coverage(
        self,
        task: Task,
        budget: Budget,
        outcomes: list[str],
        seeds: list[str],
        spent: float,
        stop: str,
    ) -> Coverage:
        n = len(outcomes)
        bound = flake_upper_bound(n, CONFIDENCE)
        target = TARGET_P[budget]
        verdict = outcomes[0] if outcomes else "none"
        reached = bound < target
        if reached:
            statement = (
                f"Gold verdict was '{verdict}' in all {n} runs: flake rate below {target:g} at "
                f"95% confidence (exact bound {bound:.3f})."
            )
        elif bound < 0.5:
            statement = (
                f"Gold verdict was '{verdict}' in all {n} runs: flake rate below {bound:.3f} at "
                f"95% confidence; the {target:g} target was not reached (time budget)."
            )
        else:
            statement = (
                f"Gold verdict was '{verdict}' in all {n} runs: too few runs to bound the flake "
                f"rate below 0.5 at 95% confidence (time budget)."
            )
        return Coverage(
            check_id=self.id,
            task_id=task.id,
            statement=statement,
            stats={
                "runs": str(n),
                "verdict": verdict,
                "confidence": f"{CONFIDENCE:g}",
                "flake_rate_upper_bound": f"{bound:.6f}",
                "target_p": f"{target:g}",
                "target_reached": "yes" if reached else "no",
                "stopped_by": stop,
                "run_seconds": f"{spent:.1f}",
                "method": "exact binomial (Clopper-Pearson test inversion), see DECISIONS D-056",
                "PYTHONHASHSEED_values": ",".join(seeds),
            },
        )

    def _finding(
        self,
        task: Task,
        ctx: CheckContext,
        results: list[RunResult],
        outcomes: list[str],
        seeds: list[str],
    ) -> Finding:
        n = len(results)
        kinds = set(outcomes)
        counts = {k: outcomes.count(k) for k in ("pass", "fail", "timeout")}
        minority = min(c for c in counts.values() if c > 0)
        ci_lo, ci_hi = clopper_pearson(minority, n, CONFIDENCE)
        extra = {
            "runs": str(n),
            "pass_count": str(counts["pass"]),
            "fail_count": str(counts["fail"]),
            "timeout_count": str(counts["timeout"]),
            "outcomes": ",".join(outcomes),
            "PYTHONHASHSEED_values": ",".join(seeds),
            "minority_count": str(minority),
            "flake_rate_estimate": f"{minority / n:.3f}",
            "flake_rate_ci95": f"{ci_lo:.3f}-{ci_hi:.3f}",
        }
        first_bad = next(r for r in results if not r.passed)
        observed = (
            f"{counts['pass']} pass, {counts['fail']} fail, {counts['timeout']} timeout "
            f"out of {n} identical gold runs (less common verdict {minority}/{n}; 95% "
            f"Clopper-Pearson interval {ci_lo:.3f}-{ci_hi:.3f})"
        )
        limits = (
            f"{n} runs, varying only PYTHONHASHSEED (adaptive: at least {MIN_RUNS[ctx.budget]}, "
            f"at most {max_runs(ctx.budget)}). Flakiness from wall-clock time, unseeded "
            "randomness, scheduling or the network is caught only by chance; the interval assumes "
            "independent runs."
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
        return make_finding(
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
