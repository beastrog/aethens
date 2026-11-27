# Status

Last updated: 2026-11-27, after task parallelism and the result cache (D-066 to D-068), on top of
the pre-launch fixes and the hardening review.

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
- D-065 (PR #1): C004 equivalent-mutant filter. External precision 0.4615 -> 0.8158, recall
  0.8667 -> 0.80 (same run, filter off vs on).
- PR #2: hardened example verifiers; README quickstart and action-selftest exit 0 again.
- PR #5: CLI exit 2 on internal errors, unwritable --output, SIGTERM (with container cleanup).
- Hardening review written to docs/review-2026-11-27.md (run by the build agent, so not truly
  independent; an outside read is still advised).

## Parallelism, cache, resume (owner-requested 2026-11-27; not a ROADMAP milestone)
- D-066 to D-068. `aethens audit --jobs` (default min(CPU count, 4); library default remains 1 so
  the bench pool is unchanged). Content-addressed per-task cache (`--cache-dir`, `--no-cache`).
  The key includes task bytes, check config, package sources, host Python, PyYAML, and the image
  fingerprint. A task that had already finished is reused; a task still running at Ctrl-C or
  SIGTERM is not stored. Report schema stays aethens-report/v2. Docker flags, severities and
  thresholds were not changed. Design: docs/cache.md.
- Timings on this machine (4 CPUs, Docker Engine 28.5.2), 34 bench tasks, budget smoke, all
  checks. `jobs=1` is the old sequential loop.
  - `--unsafe-local --jobs 1 --no-cache`: wall 80.0 s; `--jobs 4`: wall 21.1 s; cache hit: 0.17 s
  - Docker `--jobs 1 --no-cache`: wall 319.2 s; `--jobs 4`: wall 89.6 s; cache hit: 0.17 s
  Finding ids, severities and exit codes matched. C002 coverage differed only in `run_seconds`.

## Next (owner actions)
- Approve or revert the semantics changes D-064 (what timeout_s measures, 60 s grace) and D-065
  (C004 hides likely-equivalent survivors; budgets and MIN_VALID=20 are agent-chosen).
- Decide the open review items, above all O1 (no size limit on /work writes) and O2 (containers
  outlive a SIGKILLed Aethens); see docs/review-2026-11-27.md.
- Decide whether the CLI default of `--jobs` (min(CPU count, 4), previously 1) should stay.
  Under load, C002's host-wall-time budget can stop sooner. That default was not changed in the
  review follow-up; it is flagged for the owner.
- Confirm exit code 3 semantics (D-032) and the agent-chosen limits (D-008, D-013).
- Terms check, README cold read, PyPI trusted publisher, release, flip public.

## Open risks
- The result cache does not record hits inside the report (schema v2). A short `duration_s` on a
  resumed run is the wall time of this command, not of the original verifier runs. The CLI stderr
  line is the only place that says how many tasks were skipped.
- `__version__` is still `0.1.0.dev0`. The cache also hashes installed `.py` files so a source
  edit misses. A wheel built without those sources, or a check whose behaviour depends on
  something outside the package tree, would not invalidate. `--no-cache` is the escape hatch.
- `--jobs` above 4 is unlimited on purpose. It can bring back the load-induced timeout problem
  D-064 fixed the measurement of; the grace and the isolation flags were not retuned.
- Ctrl-C and SIGTERM cancel tasks that have not started. Tasks already in the pool finish their
  remaining checks (so containers are still removed) and are not cached. That wait is the rest of
  the task, not only the verifier run in progress. SIGKILL can still leak a container.
- Exit code 3 semantics are an agent decision (D-032); the owner should confirm.
- The external HumanEval bench is local only (not run in CI).
- /work writes are not size-limited (review O1); a SIGKILLed Aethens leaves running containers (O2).
- C002 is statistical: a clean result means "flake rate below 0.25 at 95% confidence" at the default
  budget (0.05 at deep), assuming independent runs; rarer flakes can be missed.

## Not verified
- Image fingerprint on Podman and Docker Desktop. On Docker Engine 28.5.2, `Id` and `RepoDigests`
  differed for a pulled `python:3.12-slim`; the containerd image store can report them equal.
  Both are in the cache key either way. A `docker load` image with an empty `RepoDigests` is
  keyed by `Id` only.
- Cache hit/miss behaviour when two `aethens` processes write the same key at once (last replace
  wins; the runs are deterministic for a seed, so the bytes should match).
- Whether `os.replace` plus file `fsync` without a directory `fsync` survives a power loss.
- release.yml and Trusted Publishing end to end (ci and action-selftest are verified on GitHub).
- Security contact: SECURITY.md points to GitHub private vulnerability reporting, which the owner must enable.
- Rootless Docker, Docker Desktop (macOS/Windows), Podman. Local mode's RLIMIT_AS is not enforced on macOS.
- The build box's dockerd runs with `--iptables=false`; on hosts with iptables the bridge network exists
  but runs still use `--network none`. This session's daemon was started the same way (Docker 28.5.2
  static binaries) because the image had no dockerd.
- Running the test suite needs access to the Docker socket; on this box that is the `docker` group
  (`sg docker -c "make check"`).
- Loader behaviour on case-insensitive filesystems (macOS, Windows); tested on Linux only.
