# Changelog

All notable changes are recorded here. The format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Added
- CI: a non-required `website build` job runs `npm ci` and `npm run build` in `website/` on pull requests and pushes to main that touch `website/**`, `bench/results.json`, `bench/external/results.json`, or the workflow file. It does not deploy, and it is not a required ruleset check.
- Docs section on the marketing site at `/docs/`: getting started, CLI, checks C001–C007, GitHub Action, report format, and FAQ. The site header links to it.

### Changed
- Launch copy: the site and package metadata say version 0.1.0 (not on PyPI yet). Bench provenance stays `0.1.0.dev0`, which is the `tool_version` recorded in `bench/results.json`. Public docs no longer list audit prices. The hosted-CI card is labelled "Not available".
- Site background: one fixed ground (fine dot grid, edge vignette, a warm spot that drifts a short way with the pointer) sits behind every page, including docs. The hero-only canvas field is removed. Touch and `prefers-reduced-motion` keep the ground still.

### Fixed
- Docker runner: the post-exit timeout cap now uses the host-monotonic time the container was observed running, not the full `docker run` wall time. The previous cap (total elapsed) still counted create and teardown, so a start or teardown longer than `timeout_s` combined with an inflated `FinishedAt - StartedAt` reported a fast verifier as timed out (`exit_code` `None`). That is the same symptom as `test_deterministic_under_seed` on hosted `check (3.12)` (run 45989844568, attempt 1): `[1, 1, None, 0, 1]` versus `[1, 1, 0, 0, 1]`. `timeout_s` still means in-container time; a genuinely slow run is still a timeout. Isolation settings are unchanged.

## [0.1.0] - 2026-11-27

### Added
- Community and repository metadata for a public open-source project: Contributor Covenant 2.1, contributing / support / governance guides, issue and pull-request templates, CODEOWNERS, Dependabot, a draft-only Release Drafter workflow, and a GitHub Sponsors button.
- `NOTICE` and `docs/LICENSING.md`, listing third-party notices and dependency licences. The sdist now ships both `LICENSE` and `NOTICE`.
- Documentation landing page at `docs/README.md`, and a redesigned root README with an in-repo wordmark, a real C005 report SVG, mermaid architecture, and generated bench tables.


### Changed
- CI: the `check` job matrix now includes Python 3.13. Docker-marked tests and the bench (`make check`) run only on 3.12; 3.11 and 3.13 run lint, mypy, and `pytest -m "not docker"`. Required-check names `check (3.11)` and `check (3.12)` are unchanged. Making `check (3.13)` a required ruleset check is an owner decision and is not done in this change.
- Marketing site published accuracy now cites hosted CI run 45969249199 (`4d75c86`): external C004 precision 0.8158 / recall 0.80 with the equivalent-mutant filter (0.4615 / 0.8667 without). `info_on_controls` is 6. The Pages workflow always builds the site so real build errors still fail, and skips deploy when Pages is not enabled. Contact is GitHub Discussions and the founder LinkedIn; no email.
- C004 filters equivalent mutants (D-065): each surviving mutant is run side by side with the gold, inside the sandbox, on the inputs the task's tests pass plus inputs derived from them. A survivor that behaves differently is reported with the counterexample input; one that behaves like the gold on at least 20 valid inputs is not reported and is listed in the report's coverage. Mutants with bytecode identical to the gold are never selected (TCE). On the external HumanEval bench: precision 0.4615 -> 0.8158, recall 0.8667 -> 0.80 (same run, filter off vs on). **Changes C004's output; owner approval requested.**

### Fixed
- Docker runner tests assert cleanup by this test's workdir bind mounts, not by requiring the global `label=aethens.run` container set to be unchanged, which flaked on a shared daemon. Leftover containers created by the test are still a failure; isolation settings are unchanged.
- Docker runner: the post-exit timeout check caps daemon `FinishedAt - StartedAt` by the host's elapsed wait, matching D-064. A forward clock jump (or a bogus timestamp pair) could previously mark a fast verifier as timed out (`exit_code` `None`), which made `test_deterministic_under_seed` fail on hosted `check (3.12)` with `[1, None, 0, 0, 1]` versus `[1, 1, 0, 0, 1]`. `timeout_s` still means in-container time; a genuinely slow run is still a timeout. Isolation settings are unchanged.
- CLI: an unexpected internal error, an unwritable `--output` path, SIGTERM and Ctrl-C now exit 2 (tool error) instead of 1 ("findings"), a traceback or a raw signal death. SIGTERM is turned into an exception so the Docker runner's normal cleanup (its `finally`, which removes the container) still runs; there is no separate sweep of `label=aethens.run=1`. The message states what cleanup confirmed: no container started, all removals confirmed, or the names of containers whose removal was not confirmed (hardening review F4-F6, post-merge review of #5).
- The example tasks (examples/add-two, examples/word-format) now use hardened tests: the solution runs in a separate `python -I` child, only its JSON answers are judged in the test process, type-strictly, with seeded hidden cases. C007 found their old verifiers gameable (exit-zero, atexit-override, framework-patch, always-equal; hardcoded-visible as a warning), which made the README quickstart and the action-selftest exit 1. C007 is unchanged; the old plain task is kept as the C007 unit-test fixture tests/fixtures/plain-add.
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
