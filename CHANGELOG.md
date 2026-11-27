# Changelog

All notable changes are recorded here. The format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Fixed
- The example tasks (examples/add-two, examples/word-format) now use hardened tests: the solution runs in a separate `python -I` child, only its JSON answers are judged in the test process, type-strictly, with seeded hidden cases. C007 found their old verifiers gameable (exit-zero, atexit-override, framework-patch, always-equal; hardcoded-visible as a warning), which made the README quickstart and the action-selftest exit 1. C007 is unchanged; the old plain task is kept as the C007 unit-test fixture tests/fixtures/plain-add.

### Fixed
- Docker runner: `timeout_s` now limits the verifier's run time inside the container, not the time `docker run` spends creating, starting and removing it. On a heavily loaded host that overhead alone exceeded 20 s and turned passing runs into timeouts (the intermittent C002 false positive on bench control ctrl-tags-sorted). Total wall time per run is capped at `timeout_s + 60 s`. A kill sent before the container existed could also leave a hung verifier running for 30 s; container removal now retries with backoff (D-064). **Changes how timeouts are measured; owner approval requested.**

### Added
- D5: check C007 (reward-hacking probes): runs six families of non-solutions (early exit, atexit override, unittest patch, sitecustomize hook, always-equal objects, hardcoded visible answers) through the same sandbox and reports those the verifier accepts. Bench grows to 34 tasks with per-task exploit labels and per-category recall, scored separately from the core metrics; two hardened-harness controls stay silent.
- D4: C002 is adaptive: it keeps rerunning while the gold agrees until it can state "flake rate below p at 95% confidence" (p = 0.5/0.25/0.05 by budget, time-capped), and reports a 95% Clopper-Pearson interval when it finds flakiness. Report schema bumped to `aethens-report/v2`, which adds a `coverage` list; v1 reports still load.
- D3: check C006 (over-specified tests): reruns the gold after behaviour-preserving AST rewrites and warns (needs review) when the tests reject one. Bench grows to 31 tasks (3 planted over-specification defects, 2 controls).
- D2: external bench on public data Aethens did not write: HumanEval tasks (MIT) judged with EvalPlus HumanEval+ (Apache-2.0) as an outside oracle; per-check results generated into docs/EXTERNAL_BENCH.md and the README; a 6-task vendored sample runs offline in `make check` with a regression gate.
- D1: check C005 (test order and isolation): reruns the tests reversed, in seeded shuffles and one at a time, and reports every test whose verdict changes and reproduces. Bench grows to 26 tasks; order-alphabetical and order-generated are now caught (expected check moved to C005).
- B1: project skeleton, typed models (Task, Candidate, Finding, Report), typed errors, `make check`, CI workflow.
- B2: aethens-task/v1 loader and validator with typed errors; two example tasks; docs/task-format.md.
- B3: runner with Docker default (no network, memory/CPU/pids limits, read-only rootfs, all capabilities dropped, no-new-privileges, non-root, disposable copy, guaranteed cleanup) and explicit unsafe-local mode.
- B4: checks C001 (gold sanity) and C002 (flakiness), minimal `aethens audit` (JSON), first bench fixtures with manifest.
- B5: checks C003 (labeled candidates, label_source aware) and C004 (AST mutation probes, info only); bench grows to 15 tasks.
- B6: aethens-report/v1 JSON Schema, Markdown reports, full `aethens audit` CLI with exit codes 0/1/2/3, bench runner with precision/recall and a baseline regression gate; bench grows to 22 tasks.
- B7: composite GitHub Action, README with generated bench numbers and limits, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, issue templates, disclosure policy, release workflow with Trusted Publishing.
