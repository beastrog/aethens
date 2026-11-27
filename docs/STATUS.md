# Status

Last updated: 2026-11-27 (Asia/Calcutta), after the pre-launch fixes and the hardening review.

## Mode

GitHub remote connected on 27 Nov 2026: origin = github.com/beastrog/aethens (private). Work goes
through PRs (`gh pr create`, `gh pr checks --watch`, squash-merge). Hosted CI (`ci` on Python 3.11
and 3.12, `action-selftest`) has run and is green on main; the first `bench-results` artifact (main
at 8af4d39) is identical to the committed bench/results.json. Before that (B1-D5) everything was
local-only.

The build box's shell `make` is a shim from another project at /home/box/bin/make; run
`sg docker -c "/usr/bin/make check"` (GNU make was installed with apt on 27 Nov).

Docker: not preinstalled on the build box. apt was unusable (mirror errors), so Docker Engine 29.10.0
static binaries from download.docker.com were installed and `dockerd` started manually with
`--iptables=false --ip6tables=false` (the box has no iptables; containers run with `--network none`
anyway, so this does not change task isolation). `docker run --rm hello-world` works.

## Done
- B1: skeleton, pyproject (hatchling, src layout, console script), Makefile (`check lint type test bench`),
  Apache-2.0 LICENSE, README stub, CHANGELOG, .gitignore (includes `audits/private/`), CI workflow,
  typed models with JSON round-trip, typed errors.

- B2: aethens-task/v1 loader and validator (`aethens.adapters.load_task/load_tasks`), typed error per
  class, docs/task-format.md, examples/add-two and examples/word-format.

- B3: runner (`aethens.runner`): DockerRunner (default) and LocalRunner (explicit opt-in). Verified
  against Docker Engine 29.10.0 on this box: hung verifier killed and cleaned up, memory blowup
  OOM-killed, network unreachable (only `lo`), output truncated, missing image -> ContainerStartError,
  cleanup after an injected exception, host env not leaked (both modes), uid != 0, CapEff/CapBnd = 0,
  NoNewPrivs = 1, read-only rootfs, pids limit, original task untouched.

- B4: Check interface; C001 gold sanity; C002 flakiness (PYTHONHASHSEED varied per run); minimal
  `aethens audit` with JSON output; bench/ with 8 tasks (6 planted: 2 no-assertions, 2 broken-gold,
  2 flaky; 2 controls) and manifest. Repro commands verified by running them in a subprocess.

- B5: C003 labeled candidates (label_source aware), C004 AST mutation probes (info only), bench grown
  to 15 tasks (11 defective, 4 controls). A full audit of the bench at seed 0 produced no error or
  warning on any control (ctrl-clamp has 2 C004 info survivors, which are equivalent mutants).
  C005 not built (reason in docs/IDEAS.md).

- B6: report JSON Schema (docs/report-schema.json), Markdown renderer, full CLI (exit codes 0/1/2/3,
  --fail-on, --format, --output), bench runner with precision/recall/false positives and baseline gate,
  bench grown to 22 tasks (8 controls, 14 defective, six classes, at least 2 each).
  Bench (locally generated, seed 0, standard): precision 1.0, recall 0.8571 (12/14), 0 false positives.
  See bench/results.json and docs/sessions/B6.md.

- B7: composite Action (action.yml) + action-selftest workflow, README (bench block generated from
  bench/results.json), SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue templates (bug,
  "I ran Aethens on X"), docs/DISCLOSURE.md, release.yml (Trusted Publishing). Verified locally:
  sdist and wheel build, `twine check --strict` passes, the README quickstart works exactly as
  written from a fresh clone and virtualenv, and the Action's shell steps (run with GitHub's
  `bash --noprofile --norc -eo pipefail`) give exit 0 on a clean sample repo, 1 with the report in the
  job summary on a defective one, and 2 on a bad path.

## Differentiators (owner-approved 18 Nov 2026; ROADMAP phase 1D)
- D1 DONE_LOCAL: C005 test order and isolation (driver inside the sandbox; default, reversed,
  seeded shuffles, each test alone; same PYTHONHASHSEED; changes must reproduce). Bench 26 tasks
  (10 controls, 16 defective): precision 1.0, recall 1.0 (16/16), 0 false positives, seed 0,
  standard. Before D1: precision 1.0, recall 0.8571 (12/14) on 22 tasks.
- D2 DONE_LOCAL: external bench on 164 HumanEval tasks (MIT) with EvalPlus HumanEval+
  (Apache-2.0) as the outside oracle; full results in docs/EXTERNAL_BENCH.md (C004 confirmed-
  survivor precision 0.4615 = 36/78, recall 0.8387 against oracle-detected weak tests; C001 and
  C005 0 loud findings; C002 1 timing warning on he-063; 20 tasks have no usable oracle). The
  6-task vendored sample runs offline in `make check` with a regression gate. The full run is
  local only (needs a one-time pinned download; about 17 minutes with 4 workers).

- D3 DONE_LOCAL: C006 over-specified tests (behaviour-preserving AST rewrites of the gold; a
  rejection must reproduce). Bench 31 tasks (12 controls, 19 defective): precision 1.0, recall 1.0
  (19/19), 0 false positives.

- D4 DONE_LOCAL: adaptive C002 (at least 3/5/10 runs, up to 6/11/59 until "flake rate below
  0.5/0.25/0.05 at 95% confidence", time-capped at 120/300/1800 s); bound statements in the new
  report `coverage` list; report schema aethens-report/v2 (reads v1). It now also finds
  order-generated's hash-seed flakiness at seed 0 (new C002 label, D-059): bench 31 tasks,
  precision 1.0, recall 1.0 (20/20), 0 false positives.

- D5 DONE_LOCAL: C007 reward-hacking probes (six categories, same sandbox, isolation unchanged).
  Bench 34 tasks (15 controls, 19 defective): core precision 1.0, recall 1.0 (20/20), 0 false
  positives; reward hacking recall 1.0 (116/116 labelled task-category pairs), precision 1.0,
  both hardened controls silent. pytest conftest probes not built.

## Pre-launch fixes (27 Nov 2026)
- D-064: Docker runner timeouts count only in-container time (root cause of the intermittent C002
  false positive on ctrl-tags-sorted under load; 38/300 -> 0/300 in the stress repro). On main.
  Follow-up: the post-exit cap used total host elapsed, so create/teardown longer than `timeout_s`
  plus an inflated FinishedAt-StartedAt still timed out a fast verifier (the
  `test_deterministic_under_seed` flake on run 45989844568). The cap is now the observed running
  window. `timeout_s` and isolation flags are unchanged.
- D-065 (PR #1): C004 equivalent-mutant filter. External precision 0.4615 -> 0.8158, recall
  0.8667 -> 0.80 (same run, filter off vs on).
- PR #2: hardened example verifiers; README quickstart and action-selftest exit 0 again.
- PR #5: CLI exit 2 on internal errors, unwritable --output, SIGTERM (with container cleanup).
- Hardening review written to docs/review-2026-11-27.md (run by the build agent, so not truly
  independent; an outside read is still advised).

## Next (owner actions)
- D-064 (what timeout_s measures, 60 s grace) and D-065 (C004 equivalent-mutant filter) were
  approved by the owner on 27 Nov 2026; no semantics approvals are pending.
- Decide the open review items, above all O1 (no size limit on /work writes) and O2 (containers
  outlive a SIGKILLed Aethens); see docs/review-2026-11-27.md.
- Confirm exit code 3 semantics (D-032) and the agent-chosen limits (D-008, D-013).
- Terms check, README cold read, PyPI trusted publisher, release, flip public.

## Open risks
- Exit code 3 semantics are an agent decision (D-032); the owner should confirm.
- The external HumanEval bench is local only (not run in CI).
- /work writes are not size-limited (review O1); a SIGKILLed Aethens leaves running containers (O2).
- C002 is statistical: a clean result means "flake rate below 0.25 at 95% confidence" at the default
  budget (0.05 at deep), assuming independent runs; rarer flakes can be missed.

## Not verified
- release.yml and Trusted Publishing end to end (ci and action-selftest are verified on GitHub).
- Security contact: SECURITY.md points to GitHub private vulnerability reporting, which the owner must enable.
- Rootless Docker, Docker Desktop (macOS/Windows), Podman. Local mode's RLIMIT_AS is not enforced on macOS.
- The build box's dockerd runs with `--iptables=false`; on hosts with iptables the bridge network exists
  but runs still use `--network none`.
- Running the test suite needs access to the Docker socket; on this box that is the `docker` group
  (`sg docker -c "make check"`).
- Loader behaviour on case-insensitive filesystems (macOS, Windows); tested on Linux only.
