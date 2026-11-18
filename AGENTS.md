# Aethens: agent rules (Cursor / Claude Code)

Aethens is an open-source (Apache-2.0) Python CLI that validates the verifiers of code tasks by running them: it checks that the tests accept correct solutions, reject wrong ones, and behave the same on every run. Read `ROADMAP.yaml` and `docs/AETHENS_PLAN.md` before any work. Work on one milestone at a time, in order, and only the current phase.

## Non-negotiable rules

### Product
1. Library first. Core code never calls `sys.exit`, never prints, never reads global state. Only `cli/` prints and maps results to exit codes (0 pass, 1 findings at or above `fail_on`, 2 tool error, 3 timeout).
2. Fail loudly. No placeholder fallbacks, no hardcoded tasks. A loader that cannot load raises a typed error.
3. Findings are evidence, not opinions. Every finding carries a check id, severity, task id, the exact thing that was run, the observed result, a seed, a one-line repro command, a confidence value and a limits note. A candidate label carries its `label_source`; an unreviewed label never produces a "confirmed" finding.
4. Never claim more than was checked. Reports state checks run, budget and tool version. A clean report never says "cannot be exploited".
5. A new check merges only with: a planted-defect fixture, a clean control, a unit test, and updated precision and recall from the bench.
6. README and docs numbers come from the CI-generated bench report, never typed by hand. Comparative claims about other tools go in only after you reproduced them on the same inputs, with versions and commands recorded.
7. When unsure about an external API, file format or tool behaviour, read its source or docs; if you could not verify something, say so in a code comment and in `docs/STATUS.md`. Do not guess.

### Safety
8. Never execute task or candidate code in the tool's own process. Use the runner: Docker by default (no network, memory, CPU and pids limits, non-root, all capabilities dropped, no-new-privileges, a disposable copy of the task, always cleaned up). Local mode requires an explicit flag, scrubs the environment, enforces timeouts and kills the process group.
9. No `shell=True`, no string-built shell commands. Argument lists only.
10. No network calls in tests. No telemetry. No secrets in code, tests, prompts, logs or commit messages. Never read, print or search for tokens or credentials; if a push or API call fails on auth, stop and report.
11. Never use confidential material from any employer or client. Public benchmarks, public environments and original work only. Do not commit third-party data until its licence is checked and recorded in `bench/LICENSES.md`; prefer download scripts.
12. Never contact third parties: no issues, PRs, comments, emails or messages on repositories you do not own. Findings about other people's benchmarks go to the gitignored `audits/private/` directory for the owner to review.
13. GitHub Actions: `pull_request` only, read-only permissions, no secrets, never `pull_request_target` with a checkout of PR code; pin third-party actions to commit SHAs.

### Scope
14. Do not build anything outside the current milestone. Write new ideas to `docs/IDEAS.md`. Not in v0.1: LLM candidate generation, other languages, Gymnasium or verifiers adapters, dashboards, hosted anything, badges, `aethens-shield`.
15. Keep dependencies minimal and permissively licensed. Record every new dependency and why in `docs/DECISIONS.md`.

## Git and iteration protocol

- One milestone per branch: `feat/<milestone-id>-<slug>`. Tests first, then code. `make check` (ruff, `mypy --strict`, pytest, bench regression) must pass before every push. Never weaken or delete a test to get green.
- Conventional commit messages. Open a PR with `gh pr create`; wait for CI with `gh pr checks --watch`; squash-merge only when green and the diff stays inside the milestone; pull main; delete the merged branch.
- Never force-push, rewrite history, change repository settings or branch protection, create tags or releases, or publish packages. The owner does those.
- After each milestone update `ROADMAP.yaml` status and `docs/STATUS.md` (done, next, decisions made, open risks, what you could not verify). A fresh session must be able to resume from these files alone.
- Stop and report instead of continuing when: the same failure persists after 3 attempts; CI stays red after 2 fixes; a change would alter check semantics, the report schema, severity rules or a threshold; something needs money, keys or a third party; a licence is unclear; Docker is unavailable; you are tempted to broaden scope.

## Definition of done for a milestone

1. Every acceptance criterion in `ROADMAP.yaml` passes, verified by running it.
2. `make check` is green on main after the merge.
3. Docs and `CHANGELOG.md` updated; `docs/STATUS.md` updated.
4. Summary to the owner: files changed, tests run, what is still missing.

Never mark a milestone or phase complete if any criterion failed or was skipped.

## Style

Python 3.11+, typed, `ruff` and `mypy --strict` on the core. Small modules, one check per class, deterministic by default (seed everything). Boring, explicit code over clever abstractions.

## What you may do without asking

Find technical debt and missing tests, add bench cases, improve performance. Anything that changes check semantics, report schema, thresholds, severities or the Docker isolation settings needs the owner's approval and a changelog note.
