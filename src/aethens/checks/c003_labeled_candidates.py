"""C003 labeled candidates: false rejects of valid candidates, false accepts of invalid ones."""

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
from aethens.models import Finding, Label, LabelSource, Severity, Task, confidence_for

RELIES = (
    "Aethens cannot decide whether a solution is correct; this finding relies on the candidate's "
    "label ({label}, label_source: {source})."
)


class C003LabeledCandidates(Check):
    id = "C003"
    title = "Labeled candidates"
    tier = "core"
    cost_class = "low"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        findings: list[Finding] = []
        for cand in task.candidates:
            hs = str(hash_seed(ctx.seed, task.id, self.id, cand.name))
            r = ctx.runner.run(run_spec(task, cand.path, {"PYTHONHASHSEED": hs}))
            if cand.label is Label.VALID and r.passed:
                continue
            if cand.label is Label.INVALID and not r.passed:
                continue
            unreviewed = cand.label_source is LabelSource.LLM_UNREVIEWED
            relies = RELIES.format(label=cand.label.value, source=cand.label_source.value)
            if cand.label is Label.VALID:
                title = f"Verifier rejects a solution labelled valid ({cand.name})"
                detail = (
                    "False reject: a candidate labelled valid did not pass. The tests may be "
                    "over-strict (pinning one implementation's details) or the candidate may be "
                    f"wrong. {relies}"
                )
                observed = f"{describe(r)}: expected exit code 0"
            else:
                title = f"Verifier accepts a solution labelled invalid ({cand.name})"
                detail = (
                    "False accept: a candidate labelled invalid passed. The tests may be too weak "
                    f"to tell it apart from a correct solution, or the label may be wrong. {relies}"
                )
                observed = f"{describe(r)}: expected a failure"
            if unreviewed:
                detail += " The label has not been reviewed by a human, so this needs review."
            findings.append(
                make_finding(
                    check_id=self.id,
                    severity=Severity.WARNING if unreviewed else Severity.ERROR,
                    task=task,
                    title=title,
                    detail=detail,
                    ev=evidence(
                        f"candidate:{cand.name}",
                        task,
                        [r],
                        observed,
                        {
                            "candidate_path": cand.path.as_posix(),
                            "label": cand.label.value,
                            "label_source": cand.label_source.value,
                            "PYTHONHASHSEED": hs,
                        },
                    ),
                    ctx=ctx,
                    confidence=confidence_for(cand.label_source),
                    limits=(
                        "One run of this candidate. Correctness comes from the label, not from "
                        "Aethens; a wrong label produces a wrong finding."
                    ),
                )
            )
        return findings
