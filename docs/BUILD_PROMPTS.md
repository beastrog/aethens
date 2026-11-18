# Aethens: build prompts for Cursor and Claude Code

Prompt 1 is START_PROMPT.md. The prompts below are for later sessions. Each is self-contained. Everything between the `~~~` lines is the prompt; the rest is for you.

## Before the first prompt (Day 0, you, about 2 hours)

1. Decide the spelling (Aethens or Athens). The prompts say Aethens; switching is a find-and-replace.
2. Create an empty GitHub repo, private until launch day. Clone it. Put these in it: `AGENTS.md`, `ROADMAP.yaml`, and `docs/AETHENS_PLAN.md` (this folder's `AETHENS_PLAN.md`). Add a one-line `CLAUDE.md`: "Read and follow AGENTS.md in full before any work." Commit and push.
3. Run `gh auth login` yourself. Never paste tokens into a prompt or a chat.
4. Confirm Docker runs on your machine (`docker run --rm hello-world`). The runner depends on it.
5. Reserve the PyPI project name and add a trusted publisher for the repo (PyPI supports a pending publisher for a name that does not exist yet; follow PyPI's current docs). The agent never gets a PyPI token.
6. Read your own employment, contractor and university terms for IP and side-project clauses. If anything restricts open-source work in this domain, stop here and sort it out first.
7. One milestone per session works best. Start a fresh session for each prompt that says "fresh session"; the STATUS file carries the memory.

## Prompt 1: master kickoff

This is `START_PROMPT.md` at the root of the kit (not part of the repo). Paste that file's prompt once; it runs B1 to B7. It replaces the older copy that was here, so there is only one version to maintain.

## Prompt 2: resume after a context reset (fresh session)

~~~
Read AGENTS.md, ROADMAP.yaml, docs/AETHENS_PLAN.md, docs/STATUS.md and docs/DECISIONS.md. Run git status, git log --oneline -10 and make check, and tell me in five lines where the project stands: last merged milestone, anything uncommitted or red, the next milestone, open risks. Then continue with the next milestone under the same rules and stop conditions as in AGENTS.md. If STATUS.md and the repo disagree, trust the repo and fix STATUS.md.
~~~

## Milestone details (if you run one milestone per session instead of the master prompt)

Paste the line "Read AGENTS.md, ROADMAP.yaml and docs/AETHENS_PLAN.md, then do milestone <id> only, following the protocol in AGENTS.md" and add the block below.

### B1: skeleton and models

~~~
Milestone B1. Create: pyproject.toml (src layout, package "aethens", Python 3.11+, build backend hatchling or equivalent, console script "aethens"), Makefile with targets check, lint, type, test, bench, LICENSE (Apache-2.0), README stub, CHANGELOG.md, .gitignore (include audits/private/), py.typed, .github/workflows/ci.yml (ubuntu, Python 3.11 and 3.12, runs make check; permissions contents: read; pin third-party actions to commit SHAs; trigger pull_request and push to main only).
Typed models in src/aethens/models.py: Task, Candidate (name, path, label in {valid, invalid}, label_source in {human, oracle, llm-unreviewed}), Finding (id, check_id, severity in {error, warning, info}, task_id, title, detail, evidence, repro, seed, confidence in {confirmed, needs-review}, limits), Report (schema "aethens-report/v1", tool_version, task_ids, checks_run, budget, seed, findings, started_at, duration_s). src/aethens/errors.py with a typed exception hierarchy. JSON round-trip tests. Check the current stable versions of the tools you pin; do not rely on memory.
Acceptance: make check green locally and in CI; mypy --strict clean.
~~~

### B2: task format and loader

~~~
Milestone B2. Define aethens-task/v1: a directory containing task.yaml (schema, id, language: python, image default python:3.12-slim, statement path, starter dir, tests dir, verifier command as an argument list, timeout_s, gold overlay dir, optional candidates/valid/* and candidates/invalid/* as overlay directories, each with a label_source in a small sidecar file). Candidates are directories whose files are overlaid onto the starter; do not implement patch files in v0.1.
Write the loader and validator in src/aethens/adapters/. Typed errors for: missing files, schema violations, duplicate ids, absolute paths, ".." traversal, symlinks that escape the task directory, oversized files. Provide docs/task-format.md and two valid examples under examples/.
Acceptance: each error class has a test; both examples load; nothing outside the task directory is ever read.
~~~

### B3: runner and sandbox

~~~
Milestone B3. Implement src/aethens/runner/. Default mode: Docker via the docker CLI called with an argument list (never shell=True). Per run: copy the task (starter, then candidate overlay, then tests) into a fresh temp directory; mount only that copy; run with --network none, memory and memory-swap limits, --cpus, --pids-limit, a read-only root filesystem with a tmpfs for /tmp where the verifier allows it, --cap-drop ALL, --security-opt no-new-privileges, a non-root user, a wall-clock timeout that kills the container, and output truncation. Always clean up containers and temp dirs, including on exceptions and timeouts.
Local mode only with the explicit flag --unsafe-local: scrubbed environment (pass only PATH and a temp HOME; nothing else is inherited), subprocess in its own process group killed on timeout, resource limits where the OS supports them, and a loud warning from the CLI layer. The core never prints.
Return a typed RunResult (exit code, timed_out, stdout and stderr tails, duration, truncated flag). Tests: hung verifier, verifier that allocates memory until killed, verifier that tries the network, huge output, container start failure, cleanup after exception. If Docker is not available in CI, say so in STATUS.md and mark Docker tests with a clear marker rather than skipping silently; GitHub's ubuntu runners normally have Docker, so verify.
Acceptance: all those tests pass; grep finds no shell=True; nothing from the host environment leaks into a run (test it).
~~~

### B4: C001 gold sanity and C002 flakiness

~~~
Milestone B4. Implement the Check interface (id, tier, cost class, run(task, ctx) -> list[Finding]) and two checks. C001: the starting state (no solution) must fail the verifier; the gold solution must pass; a failing gold is severity error, a passing no-op is severity error. C002: run the gold solution N times (smoke 3, standard 5, deep 10); mixed outcomes are a finding (error if gold itself flips, warning if only timing differs), with the pass and fail counts as evidence. Findings must be deterministic under a seed and carry full evidence and a repro command.
For each check write: a planted-defect fixture (original tiny Python tasks you author), a clean control, and a unit test. Put the fixtures under bench/ with a manifest listing the expected findings, so B6 can compute precision and recall from the same files.
Acceptance: each check finds its planted defect, stays silent on the control, and the finding's repro command actually reproduces the result when run by hand.
~~~

### B5: C003 labeled candidates and C004 mutation probes

~~~
Milestone B5. C003: run every labeled candidate through the verifier. A candidate labeled valid that is rejected is a false reject; one labeled invalid that is accepted is a false accept. Severity error when label_source is human or oracle; severity warning with confidence needs-review when it is llm-unreviewed. State plainly in the finding that the tool cannot decide validity itself and relies on the label.
C004: deterministic AST-based mutations of the gold solution using the standard library ast module (operator swaps, comparison boundary changes, constant off-by-one, negated conditions, return-value removal), seeded and capped by budget. Run each mutant through the verifier; surviving mutants are severity info with the text "may be semantically equivalent; review". Never report a surviving mutant above info.
Grow bench/ to at least 12 tasks, with at least 2 instances per defect class so far and tricky clean controls (for example tests that legitimately pin an exact output format, and valid alternative solutions that must be accepted). If time remains, add C005: a candidate that exits with status 0 before the tests run, to see whether the harness notices.
Acceptance: each check has fixture, control and unit test; no control task produces an error or warning.
~~~

### B6: reports, CLI, bench metrics

~~~
Milestone B6. Report JSON (aethens-report/v1) with a published JSON Schema in docs/; a Markdown renderer suitable for a PR comment; a CLI: aethens audit PATH [--budget smoke|standard|deep] [--fail-on error|warning] [--format json|markdown] [--seed N] [--unsafe-local]; exit codes 0 pass, 1 findings at or above fail-on, 2 tool error, 3 timeout. Only the cli package prints.
Bench runner (make bench): runs the tool over bench/, compares to each manifest, and prints precision (true findings over true findings plus false positives, where a false positive is any error or warning on a clean control), recall (planted defects found over planted), and per-check results. Write bench/results.json and bench/baseline.json; CI fails if precision or recall regress. Grow bench to 20-24 tasks: about 8 clean controls and 16+ defective across six classes (weak tests accepting a wrong solution, over-strict tests rejecting a valid one, flaky tests, tests with no real assertions, a broken gold solution, order or state dependence), at least two per class.
Acceptance: make bench is deterministic across two runs with the same seed; CI fails on a deliberately injected regression (show me that you tried it); every finding in a sample report can be reproduced with its repro command.
~~~

### B7: Action, docs, release workflow

~~~
Milestone B7. Composite GitHub Action (action.yml) that installs the package and runs aethens audit on a path, with read-only permissions, no secrets, documented for pull_request only; test it on a sample repository or a workflow in this repo. README: what it is and is not, 60-second quickstart, a table of checks with what each can and cannot catch, bench numbers pasted from the CI-generated report, a "known misses and limits" section, and a plain statement that the bench is self-authored so its numbers measure whether the tool catches planted defects, not real-world recall. Add SECURITY.md (threat model for running untrusted code, how to report), CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue templates (bug, "I ran Aethens on X" feedback), docs/DISCLOSURE.md (the owner's policy: private notice first, 2-4 weeks, offer a fix, never name before then), and .github/workflows/release.yml that builds and publishes to PyPI with Trusted Publishing when a GitHub release is published (permissions id-token: write only in that job). Do not create a release or tag.
Acceptance: every README claim traces to a file or the bench report; the Action works on the sample; release.yml has no secrets; twine check passes on the built distribution.
~~~

## Prompt 3: hardening review (fresh session, after B7, before launch)

~~~
You are a skeptical reviewer who did not write this code. Read AGENTS.md and docs/AETHENS_PLAN.md, then review the repo adversarially. Do not trust docs/STATUS.md.
1. Security: the runner and the task loader. Look for ways a malicious task or candidate could reach the host: path traversal, symlinks, mounts, environment leakage, container options that are missing or weaker than AGENTS.md rule 8, zombie containers, temp files left behind, shell injection through task.yaml fields.
2. Correctness: for each check, find inputs that make it produce a false positive or false negative, and add a failing test for each real one.
3. Honesty: list every claim in README.md and docs/ that is not backed by the bench report or a test.
4. Release: make a fresh virtualenv, install the built wheel, run the quickstart from the README exactly as written, and report every step that fails.
Write docs/review-<date>.md with findings ranked by severity, each with evidence. Fix only issues you can reproduce with a failing test, one PR per fix; list the rest as open issues in the review file. Do not change semantics, schema or isolation settings without asking me.
~~~

## Prompt 4: release prep (after the review, before you press the button)

~~~
Prepare release v0.1.0. Do not create a tag or a release. Update CHANGELOG.md, confirm the version in pyproject.toml, build sdist and wheel, run twine check, install the wheel into a clean virtualenv and run the README quickstart, run make check and make bench on main, and confirm .github/workflows/release.yml needs no secrets. Output a checklist of what you verified and what I must do myself: review the final README cold, create the GitHub release (which publishes to PyPI), make the repo public.
~~~

## Prompt 5: audit run on public benchmarks (after launch, or from day 5 to start the disclosure clock)

~~~
Goal: find real defects in two or three public code benchmarks using Aethens, without contacting anyone. Step 1: propose 3 candidate benchmarks with runnable tests and permissive licences; for each, read and quote the licence and say whether we may run and describe it. Wait for my choice. Step 2: write a small script under audits/<name>/ (committed) that converts tasks to aethens-task/v1; never commit third-party data unless the licence permits it and bench/LICENSES.md records it. Step 3: run the tool and write all findings, with evidence and repro commands, to audits/private/ (gitignored). For each finding say how it could be wrong (for example that a rejected solution might not actually be valid). Do not open issues, PRs or comments anywhere, and do not publish. I will verify each finding by hand and send the private notices myself.
~~~

## Prompt 6: weekly iteration loop (after launch)

~~~
Read docs/STATUS.md, open issues and docs/IDEAS.md. Triage: label each issue bug, false-positive, feature or question, and fix false positives first, each with a failing bench case added before the fix. Then pick at most one improvement that an outside user actually asked for and implement it under the normal protocol. Never let precision or recall on the bench regress. Do not start any deferred track from ROADMAP.yaml without my approval. Finish with a short report: what changed, bench numbers before and after, what users asked for that we did not do.
~~~

## What to paste back to me for review

After B3 (the sandbox), after B6 (bench numbers), after the hardening review, and any time an agent stops on a stop condition. Those are the places where mistakes are expensive and where an independent read helps most.
