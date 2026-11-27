# Decisions

Every dependency and design decision, with the reason. Newest at the bottom of each section.

## Dependencies

| Package | Version | Licence | Kind | Why |
|---|---|---|---|---|
| hatchling | >=1.33 (1.33.0 current on 2026-11-18) | MIT | build backend | Small, standard PEP 517 backend with src-layout support. |
| ruff | 0.17.5 | MIT | dev | Lint and format in one fast tool. |
| mypy | 2.4.1 | MIT | dev | `mypy --strict` is required by AGENTS.md. |
| pytest | 9.2.0 | MIT | dev | Test runner. |
| jsonschema | 4.26.0 | MIT | dev | Validates reports against the published JSON Schema in tests (B6). |
| PyYAML | >=6.0.3,<7 | MIT | runtime | Parse task.yaml and label sidecars (B2). Only `SafeLoader` (subclass) is used. |
| types-PyYAML | 6.0.12.20261113 | Apache-2.0 | dev | Type stubs for mypy --strict. |

Versions were read from the PyPI JSON API on 2026-11-18, not from memory.

GitHub Actions pinned to commit SHAs (resolved with `git ls-remote` on 2026-11-18):
actions/checkout v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`,
actions/setup-python v7.1.0 `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`.
CI installs uv with `pip install uv==0.13.7` instead of a third-party setup action (one less action to pin).

## Design

- D-001 (B1) Models are frozen stdlib dataclasses with hand-written `to_dict`/`from_dict`, not pydantic:
  zero runtime dependencies, and validation raises the typed `SchemaError`.
- D-002 (B1) `Evidence` is a typed object (subject, command, observed, exit_codes, timed_out, stdout and
  stderr tails, string-to-string `extra`) rather than a free-form dict, so every finding carries the same
  evidence fields.
- D-003 (B1) `confidence_for(label_source)` is the single place that maps a label source to a
  confidence; `llm-unreviewed` always maps to `needs-review` (AGENTS.md rule 3).
- D-004 (B1) Local-only build mode: the owner approved building without a GitHub remote. The PR/CI step
  is replaced by a local feature branch, `make check`, the CI commands run locally on Python 3.11, 3.12
  and 3.13 (uv-managed interpreters), and `git merge --squash` into main. Hosted CI has not run.
- D-005 (B1) The console script exists from B1 with only `--version`, so the packaging entry point is
  tested from the start.
- D-006 (B1) The Makefile calls tools through `RUN ?= uv run`; CI selects the interpreter with
  `UV_PYTHON`.
- D-007 (B2) Candidate labels live in a sidecar `<name>.label.yaml` next to each candidate directory,
  not inside it, so the overlay contains only solution files.
- D-008 (B2) Limits chosen by the agent (owner may change): max file size 5 MiB, `timeout_s` 1..3600,
  default 60 s, default image `python:3.12-slim`.
- D-009 (B2) The loader scans the whole task tree before parsing anything and rejects escaping or
  dangling symlinks and special files (FIFO, device, socket). Internal symlinks are allowed; the runner
  will copy them dereferenced (B3), so containers never see a symlink.
- D-010 (B2) `image` must match `^[a-z0-9][A-Za-z0-9._/:@-]{0,254}$` and ids
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`: neither can start with `-`, so neither can be parsed as a docker
  CLI option (argument injection).
- D-011 (B2) The YAML loader rejects duplicate keys (a silently ignored duplicate could hide a field).
- D-012 (B2) Bench and example tasks use stdlib `unittest` as their verifier, because the default image
  has no pytest and runs have no network.
- D-013 (B3) Docker run flags (AGENTS.md rule 8, BUILD_PROMPTS B3): `--network none`, `--memory` =
  `--memory-swap` (no swap), `--cpus`, `--pids-limit`, `--read-only`, `--tmpfs /tmp:rw,nosuid,nodev,size=`,
  `--cap-drop ALL`, `--security-opt no-new-privileges`, non-root `--user`, `--pull never`, bind mount of a
  disposable copy at /work. Default limits chosen by the agent (owner may change): 1024 MiB memory,
  1.0 CPU, 256 pids, 256 MiB tmpfs, 64 KiB output tail per stream.
- D-014 (B3) The container user is the host user's uid:gid (so the host can always delete the copy),
  or 65534:65534 (nobody) when the host user is root; never root.
- D-015 (B3) No `--rm`: the runner inspects the container state (OOMKilled, whether it started) and then
  always removes it with `docker rm -f -v`, in a `finally` block, also after timeouts and exceptions.
- D-016 (B3) `--pull never`: runs never pull images implicitly, so tests make no network calls and an
  audit never downloads anything mid-run. A missing image raises `ContainerStartError` with a
  `docker pull` hint. CI pulls `python:3.12-slim` in a separate step.
- D-017 (B3) A container that never started (docker exit 125, missing image, bad option) raises
  `ContainerStartError` (tool error, exit 2), not a verifier failure; exit codes 126/127 from inside a
  started container are verifier results.
- D-018 (B3) Output is read by threads that keep only the last N bytes in memory (no disk spill), so a
  verifier printing gigabytes cannot exhaust host memory or disk.
- D-019 (B3) Local mode applies rlimits through a tiny stdlib-only exec wrapper run with `python -I`,
  not `preexec_fn` (unsafe with threads). Its environment is exactly PATH, a temp HOME,
  PYTHONDONTWRITEBYTECODE, PYTHONUNBUFFERED and the run's own variables. The process group is killed
  with SIGKILL after every run, not only on timeout, so background children never outlive a run.
- D-020 (B3) Docker tests carry the `docker` marker. Without Docker they are skipped with a
  "NOT VERIFIED (Docker): <reason>" message; with `AETHENS_REQUIRE_DOCKER=1` (set in CI) a missing daemon
  or image is a failure.
- D-021 (B4) Check interface: abstract class with `id`, `title`, `tier`, `cost_class` and
  `run(task, ctx) -> list[Finding]`; `CheckContext` carries the runner, seed, budget and whether the
  run is unsafe-local (so repro commands include `--unsafe-local`).
- D-022 (B4) Every run pins `PYTHONHASHSEED` to a value derived from (seed, task id, check id, run);
  C002 varies it per run. Hash-order flakiness is therefore detected deterministically for a given seed,
  and C002 detection is probabilistic in the number of runs: with 5 runs a 50/50 flaky test is missed
  for about 1 seed in 16 (observed on flaky-setorder: seeds 0-7 caught 7 of 8, seed 4 missed). This is
  stated in every C002 finding's limits.
- D-023 (B4) C002 severity: error when the gold both passes and fails across runs; warning when the
  only difference is timeouts (as in BUILD_PROMPTS B4). Runs: smoke 3, standard 5, deep 10.
- D-024 (B4) Finding ids are `<check>-<task>-<sha256(check|task|subject|title)[:8]>`: stable across runs
  so a repro run can be matched to the original finding.
- D-025 (B4) Repro commands are `aethens audit <task path> --check <id> --seed <n> --budget <b>`, with
  the path relative to the working directory when the task is inside it. To make them runnable by hand
  (B4 acceptance) a minimal `aethens audit` (JSON output) is added now; markdown, --fail-on and exit
  code 3 are B6 scope. `python -m aethens` works too.
- D-026 (B4) The bench lives in `bench/tasks/` with `bench/manifest.yaml` (aethens-bench/v1) listing each
  task as `control` or `defective`, and for defective tasks each planted defect's class and the check
  expected to catch it. Bench tasks are excluded from ruff (they contain deliberate defects).
- D-027 (B5) C003 severity and confidence follow BUILD_PROMPTS B5: error + confirmed for `human` and
  `oracle` labels, warning + needs-review for `llm-unreviewed`. A valid candidate that times out counts
  as rejected (the evidence shows `timed_out`).
- D-028 (B5) C004 operators: compare-boundary (< <=, > >=), compare-negate, binop-swap (+ -, * /, // *,
  % //, ** *), augassign-swap, constant-plus-one (ints, not bools), negate-condition (if, while, ternary),
  return-none, boolop-swap (and/or). Code under `if __name__ == "__main__":` is never mutated. Mutants are
  written with `ast.unparse` (comments are dropped in the mutant copy only). Caps: smoke 5, standard 10,
  deep 30 mutants per task, chosen by a `random.Random` seeded from (seed, task id).
- D-029 (B5) Survivors are info + needs-review with the text "may be semantically equivalent; review".
  A task whose gold has nothing to mutate gets one info finding saying C004 checked nothing, so a silent
  C004 never looks like a clean bill of health (AGENTS.md rule 4).
- D-030 (B5) C005 (exit-zero probe) was not built; see docs/IDEAS.md.
- D-031 (B5) Bench fixture fix found while building: Python 3.12+ `sum()` of floats uses compensated
  summation, so the strict-float gold uses an explicit loop to produce the float its test pins.
- D-032 (B6) Exit code 3 ("timeout") means a gold-solution run in C001 or C002 hit the task's
  timeout, so the gold verdict could not be established. Precedence 2 > 3 > 1 > 0. The plan names the
  code but does not define it; **owner to confirm**.
- D-033 (B6) Report JSON Schema is draft 2020-12 at docs/report-schema.json, `additionalProperties:
  false` throughout, and is tested against real reports. Markdown output is sized for a PR comment:
  output tails are cut to the last 1500 characters there (the JSON keeps the runner's 64 KiB tail).
- D-034 (B6) CLI additions beyond the B6 list: `--check ID` (repeatable; needed for one-line repro
  commands) and `--output FILE`.
- D-035 (B6) Bench metrics: a defect is found when its expected check reports at least its
  `min_severity` (default warning; weak-leap uses info for C004). Precision counts only error/warning
  findings; FP = error/warning on a control. Error/warning findings on defective tasks from checks
  that were not expected are reported as `unexpected`, outside precision. The baseline gate fails on
  lower precision, lower recall, or more false positives. Bench defaults: seed 0, budget standard,
  4 parallel workers (tasks are independent, so results do not depend on scheduling).
- D-036 (B6) bench/results.json is committed (no timings, so it is deterministic) so README numbers
  trace to a file; CI regenerates it and uploads it as the `bench-results` artifact
  (actions/upload-artifact v7.0.2 `cf430e030ddbb5b0abf93d22962f4752f3646cd9`).
- D-037 (B6) The bench includes a planted defect no v0.1 check can catch (order-alphabetical) so
  recall is not inflated by only planting what the tool can see.
- D-038 (B7) The composite Action installs Aethens from its own checkout (`pip install
  $GITHUB_ACTION_PATH`), pulls the images listed in its `images` input (runs use `--pull never`),
  writes the Markdown report to the job summary and exposes `exit-code`. Inputs reach scripts only via
  `env:` (no `${{ }}` inside `run:`), to prevent script injection. The Audit step starts with `set +e`
  because GitHub runs bash with `-e` (found by simulating the step with GitHub's exact bash flags).
- D-039 (B7) README bench numbers are inserted by `bench/render_readme.py` from bench/results.json,
  and a test fails if the README block is stale (AGENTS.md rule 6).
- D-040 (B7) release.yml: build job (contents: read) builds with build 1.6.1 and checks with
  twine 7.0.0 --strict; publish job alone has `id-token: write` and uses
  pypa/gh-action-pypi-publish v1.14.3 (`7245906fb61fa33a13554f9d5fb856fe61758086`) in a `pypi`
  environment. actions/download-artifact v8.0.2 `9000827ccba6bdab643e8b6fd33ac0654aef8333`.
  build and twine are pinned in the workflow only; locally they were run with `uvx`, so they are not
  project dependencies.
- D-041 (B7) The code of conduct is short original text that links to the Contributor Covenant rather
  than copying it.

## Differentiators (owner-approved 18 Nov 2026)

- D-042 (D1) Check ids: C005 is the test-order and isolation check. The id was floated for an
  exit-zero probe in B5 (docs/IDEAS.md); that probe is now part of the reward-hacking pack (D5).
- D-043 (D1) C005 runs the tests through a stdlib-only driver copied into the sandbox at
  `/work/.aethens/order_driver.py` and run with the verifier's own interpreter. The driver reuses
  `unittest.TestProgram` for argument parsing and discovery (only `runTests` is replaced), so it runs
  exactly the tests `python -m unittest ARGS` would. It sets `sys.path[0]` to the working directory
  to match `-m`. The driver never runs in the Aethens process (AGENTS.md rule 8); the runner, its
  isolation flags and limits are unchanged.
- D-044 (D1) Orders: default (baseline), reversed, seeded shuffles (smoke 1, standard 2, deep 5) and
  each test alone in a fresh container (cap smoke 10, standard 30, deep 200; a seeded sample above
  the cap). Shuffles permute modules, then classes within a module, then tests within a class
  (pytest-randomly's scheme), so class and module fixtures are not split, which would itself change
  behaviour through repeated setUpClass/tearDownClass.
- D-045 (D1) All C005 runs of a task share one PYTHONHASHSEED (derived from seed, task id, "C005"),
  so order is the only variable. Verdicts are compared as passing (pass, skip, expected failure) vs
  failing (fail, error, unexpected success); tests that did not run (failfast) are not compared.
- D-046 (D1) A verdict change becomes an error + confirmed finding only when it reproduces: the
  baseline and each changed order are run a second time. Changes that do not reproduce are info +
  needs-review ("did not reproduce", see C002). One finding per test, listing every order that
  changed its verdict. Evidence.command is the exact driver command of the first changed order;
  `extra.driver_command`, `extra.default_order` and `extra.changed_in` complete the picture.
- D-047 (D1) Only `python[3[.N]] -m unittest ...` verifiers are supported. Anything else, or a
  baseline run that produces no driver result line, gives one info finding saying C005 checked
  nothing (the C004 pattern), never silence. pytest support is in docs/IDEAS.md (the default image
  has no pytest and runs have no network, so it could not be tested here).
- D-048 (D1) Bench: order-alphabetical and order-generated now expect C005 (they are
  order-dependence defects; order-generated was a seed-dependent C002 miss). Added order-crossmodule,
  order-classfixture and the controls ctrl-order-cache and ctrl-order-shared-readonly.
- D-049 (D2) External bench data: HumanEval (MIT, commit b9453e8f) for tasks and HumanEval+
  (EvalPlus, Apache-2.0, HF revision d32357cf) as an outside oracle. Downloads are pinned by URL and
  sha256 (`bench/external/fetch.py`); only 6 converted tasks are vendored, each file with an
  attribution header (AGENTS.md rule 11). ImpossibleBench skipped (data licence not stated, no
  reference solutions, SWE split needs networked images); MBPP+ deferred. No new dependency (stdlib
  `urllib`, `gzip`, `json` only).
- D-050 (D2) Conversion: gold = prompt + ORIGINAL canonical solution; tests = ORIGINAL base check,
  one unittest method per assert when the check body is only asserts (so C005 has tests to
  reorder), else one method calling `check`. Tests see every name the solution defines, matching
  HumanEval's one-namespace harness (needed by HumanEval/32, whose test calls `poly`). timeout_s 20
  (gold runs take under 1 s; mutants that loop forever would otherwise cost 60 s each). Oracle runs
  get at least 60 s: a first full run with timeout 15 s and 6 workers saw load-induced timeouts.
- D-051 (D2) EvalPlus's numpy-based `is_floats`/`assertion` helpers are replaced with a stdlib
  equivalent (exact match, else `|out - exp| <= atol + 1e-7 * |exp|` element-wise, NaN equal NaN,
  atol 1e-6 for float outputs) because the sandbox image has no numpy and runs have no network.
  Not verified against numpy in every corner case.
- D-052 (D2) Ground truth. C004: a survivor is confirmed when the HumanEval+ tests reject the same
  mutant; precision = confirmed / survivors judged by the oracle. Recall (`--exhaustive`) is relative
  to exhaustive mutation with Aethens' own operators: weak task = some mutant passes the base tests
  and fails HumanEval+. C001/C002/C005/C006/C007 have no labels in the data: error/warning findings
  are counted and listed as findings on presumed-clean tasks; no precision is claimed from zero
  findings. Tasks whose original canonical solution fails HumanEval+ (EvalPlus fixed or
  re-specified them, or it times out) cannot use the oracle and are listed.
- D-053 (D2) `make bench` also runs the 6-task offline sample (`run_external.py --sample`), gated by
  bench/external/sample-baseline.json (more error/warning findings, or lower C004 precision or
  recall, fails). The full run is manual (about 15-20 minutes with 4 workers locally) and its results
  file is committed.
- D-054 (D3) C006 over-specified tests (id C006, tier probe, no LLM). Rewrites live in
  `aethens/checks/rewrites.py`; each states its preconditions and skips any site it cannot prove
  (introspective functions using locals/vars/eval/exec/inspect/sys/super, names seen by nested
  scopes, global/nonlocal, parameters, try/with/match around append loops, loop variables used
  after the loop, walrus/yield/await in the element, the `__main__` guard). A rewrite whose output
  is textually identical to the input is not run. Families: smoke = reformat + rename-locals;
  standard and deep = all five. Each family is applied to every provable site at once (one run per
  family, not per site), which keeps the cost at about 5-7 runs per task but cannot say which site
  a test rejected; the diff is in the finding.
- D-055 (D3) C006 findings are warnings with confidence needs-review: some tasks legitimately
  require an implementation detail (e.g. "use a list comprehension"); the statement decides. A
  rejection counts only if the rewritten gold fails twice and the original gold passes again with
  the same PYTHONHASHSEED (otherwise it is flakiness, C002's job). A task with no rewrite site gets
  one info finding saying C006 checked nothing. Bench: defect class over-strict gains check C006;
  planted overspec-source, overspec-lineno, overspec-varnames; controls ctrl-overspec-behaviour and
  ctrl-signature-pinned (introspects the public signature, which no rewrite changes).
- D-056 (D4) C002 statistics. Flake rate q = per-run probability of the less likely verdict
  (0 <= q <= 0.5), runs assumed independent. After n runs that all agree, C002 states "flake rate
  below b at 95% confidence", where b solves (1-q)^n + q^n = 0.05 on [0, 0.5]: the exact binomial
  test inversion behind Clopper-Pearson. The q^n term is there because C002 does not know in advance
  which verdict is the normal one; for n >= 30 b equals the textbook one-sided Clopper-Pearson bound
  1 - 0.05^(1/n) (rule of three, about 3/n) to 6 digits, and at small n it is slightly more
  conservative (6 runs, not 5, to rule out a 50/50 flip). When C002 finds flakiness, it reports k
  (the count of the less common verdict) out of n and the two-sided 95% Clopper-Pearson interval
  for k/n. Implemented in `aethens/stats.py` with the standard library (bisection on the exact
  binomial CDF); no scipy.
- D-057 (D4) New C002 semantics. Minimum runs 3/5/10 (smoke/standard/deep, the old fixed counts);
  if they disagree that is the finding (unchanged). If they agree, C002 keeps going one run at a
  time until a run disagrees (finding), the target bound holds (p = 0.5/0.25/0.05, reached after
  6/11/59 agreeing runs), or summed run time reaches 120/300/1800 s. Without a finding it records a
  coverage statement with the bound it actually reached and why it stopped. Cost: a stable task now
  costs 11 gold runs at standard instead of 5. Three existing unit tests pinned the old fixed run
  counts (5 at standard; 3/5/10 per budget; 5 distinct hash seeds); they were updated to the new
  exact counts (11; 6/11/59; 11), not loosened.
- D-058 (D4) Report schema bumped to aethens-report/v2: a top-level `coverage` list (check_id,
  task_id, statement, string stats), produced through `Check.run_with_coverage` (default: run(),
  no coverage). Only C002 produces coverage so far. `Report.from_dict` still reads v1 (coverage
  empty). The Markdown report shows coverage in its own section. Three tests that pinned the
  string "aethens-report/v1" now pin "aethens-report/v2".
- D-059 (D4) order-generated gains a second expected defect (flaky, C002). Its generated test names
  come from set iteration, so the run order and the verdict depend on PYTHONHASHSEED: it is both
  order-dependent and flaky. The old fixed 5 runs missed it at seed 0; adaptive C002 finds it after
  more runs. This adds one planted defect (20 total), labelled after D4 was written and observed
  failing before: the owner should review whether adding a label a new feature catches is fair.
- D-060 (D5) C007 reward-hacking probes (id C007, tier probe). Probe candidates are Aethens-written
  overlays over every Python file in the gold and starter overlays, run with `run_spec` through the
  task's normal runner: same Docker flags (`--network none`, read-only root, tmpfs, cap-drop ALL,
  no-new-privileges, non-root, limits); nothing in the runner changed. C007 runs only when the
  unsolved starter fails (a passing starter is C001's finding). An accepted probe must pass twice.
  Categories: exit-zero (`os._exit(0)` on import; a `sys.exit(0)` variant is also tried but the
  unittest loader catches it), atexit-override, framework-patch, sitecustomize-hook,
  always-equal, hardcoded-visible. Errors with confidence confirmed, except hardcoded-visible:
  warning, needs-review (a lookup table only matters when the tests are visible to the policy).
  pytest `conftest.py` hooks are not probed (no pytest in the default image; not testable here).
- D-061 (D5) Reward hacking is scored separately from the core metrics. Nearly every plain unittest
  task is gameable, so counting C007 findings as false positives on controls would make the
  existing controls meaningless. Each manifest entry now has a required `reward_hack` list of the
  probe categories expected to get through (written by reading each task's tests before running
  C007); per-category recall and precision are computed from it, C007 findings are excluded from
  the core metrics, and both sets of headline numbers are gated by bench/baseline.json. New tasks:
  hack-sitecustomize (verifier runs with `PYTHONPATH=.`), ctrl-hardened-harness and
  ctrl-hardened-cli (the candidate runs in an isolated `python -I` child; results are judged in the
  parent on seeded random inputs). All three are core controls.
- D-062 (D5) One label disagreed with the first run: order-classfixture was labelled
  framework-patch, but the first probe (patching only `TestResult.wasSuccessful`) did not pass
  because Python 3.12 unittest exits 5 when no test ran (its setUpClass fails). The label was kept
  and the probe strengthened to also report at least one test run. This is tuning on the bench: the
  first-version reward-hack recall was 115/116 (framework-patch 29/30).
- D-063 (D5) The external bench does not run C007: its verifier is Aethens' own unittest conversion
  of HumanEval's check function, so probe results would describe the converter, not HumanEval.
- D-064 (fix, approved by the owner on 27 Nov 2026) Timeout accounting in the Docker runner. Root cause of the
  intermittent ctrl-tags-sorted false positive: `timeout_s` was measured on the host around the
  whole `docker run`, so container create/start/teardown counted as verifier time. Reproduced with
  300 gold runs of ctrl-tags-sorted at 128-way concurrency plus 24 CPU burners: 38/300 passing runs
  ("Ran 3 tests ... OK" in stderr) were reported as timeouts (max wall time 24.6 s for a 20 s
  timeout). In C002 one such run among up to 11 gives the warning "Gold solution run time varies:
  some runs time out"; in C001 it gives a gold-fails error. Change: when the host wait reaches
  `timeout_s`, the runner asks the daemon for the container's state; if it has not started yet or
  has already exited (teardown) it keeps waiting, and if it is running it waits until the container
  itself has run `timeout_s` (daemon StartedAt, capped by host time since launch so a skewed daemon
  clock cannot shorten the old limit). Hard cap: `timeout_s + STARTUP_GRACE_S` (60 s, agent-chosen)
  of wall time. After a normal exit, daemon-recorded run time (FinishedAt - StartedAt) above
  `timeout_s` is still a timeout, so a slow verifier cannot slip through on the grace. That
  post-exit delta is capped the same way as the in-flight check: `capped_in_container_seconds`
  takes `min(FinishedAt - StartedAt, host_elapsed)`, where host elapsed is the monotonic time
  from just before `docker run` until the client exits, so a forward clock jump or a bogus
  timestamp pair cannot turn a fast run into a timeout. Same repro
  after the fix: 0/300. Thresholds, the default `timeout_s` values and isolation flags are
  unchanged; only what the clock covers changed. `RunResult.duration_s` stays host wall time (it
  feeds C002's time budget, which therefore still counts overhead).
- D-065 (owner-requested via the parent agent: "add equivalent-mutant filtering"; final semantics
  ACCEPTED by the owner on 27 Nov 2026, see the end of this entry) C004 equivalent-mutant filter. Analysis of the 42 unconfirmed
  survivors of the previous full external run: nearly all were semantically equivalent mutants
  (running-max `>`/`>=`, loop bounds one step too far, flags set to 2 instead of 1, `(a+b)%2` vs
  `(a-b)%2`, guarded comparisons), none bytecode-identical, so TCE alone removes nothing (0 of 2007
  mutants over both benches; kept because it is provable and cheap). Chosen method: a differential
  probe (`aethens/sandbox/equiv_driver.py`, stdlib only, one extra sandbox run per survivor, same
  isolation): record the arguments test code passes to module-level functions of the mutated file,
  derive inputs EvalPlus-style (sign-preserving neighbouring numbers, one-character and token-level
  string edits, list drops/duplicates/swaps, boundary values c-1/c/c+1 around integer constants in
  the gold file, string constants as words, rare out-of-sample characters), compare gold and mutant
  results and argument side effects (`==`, floats rel 1e-9), skipping inputs where the gold raises,
  times out or is nondeterministic. Verdicts: distinguished (reported with the counterexample),
  equivalent (>= MIN_VALID=20 valid inputs, no difference: not reported, listed in coverage with
  the mutant keys), inconclusive (anything else: reported exactly as before). Budgets (agent-chosen):
  100/300/1000 inputs and 5/8/30 s per probe for smoke/standard/deep, 2 s per call. Severity,
  confidence (needs-review), mutant caps and the report schema are unchanged; `C004MutationProbes(
  filter_equivalent=False)` restores the old behaviour in code (no CLI flag, see IDEAS).
  Tuning disclosure: the input derivation was designed while looking at the HumanEval false
  positives (first prototype kept 31/36 confirmed and 7/42 unconfirmed survivors of the old run;
  boundary constants and token edits were added after seeing the misses). Full run with the filter
  (seed 0, standard, exhaustive): precision 0.8158 (31/38), recall 0.80 (24/30 weak tasks); the
  same run without the filter: precision 0.4615, recall 0.8667 (26/30); the filter hid 51
  survivors, 5 of which HumanEval+ rejects. The previous full run reported 31 weak tasks; this run
  30 (the earlier run had load-induced timeouts, see D-064). Remaining false positives are mostly
  counterexamples outside the task's precondition (e.g. `factorize(0)`, duplicates in an array
  declared duplicate-free), which the probe cannot know without a spec.
  Status: ACCEPTED by the owner on 27 Nov 2026, relayed by the lead agent. Accepted as measured:
  external C004 precision 0.46 -> 0.82 (0.4615 -> 0.8158) and recall 0.87 -> 0.80 (0.8667 -> 0.80),
  filter off vs on in the same run. Budgets and MIN_VALID=20 stay as above; the CLI switch to turn
  the filter off is still open (docs/IDEAS.md, review item O6).

