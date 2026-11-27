# Aethens

Aethens checks the verifiers of code tasks by running them. For each task it runs the tests against
the unsolved starting state, the reference (gold) solution, labeled candidate solutions and small
mutations of the gold solution. It reports every problem with the exact command that ran, what
happened, a seed and a one-line repro command.

Use it before you train or evaluate on a set of coding tasks, to find tests that accept wrong
solutions, reject right ones, or give different answers on different runs.

Status: pre-release (0.1.0.dev0), Python tasks only. Licence: Apache-2.0.

## What it is not

- It does not decide whether a solution is correct. Checks that judge candidates (C003) rely on the
  labels you provide, and every such finding says so.
- It does not prove a verifier is sound. No findings means only that these checks found nothing at
  the chosen budget and seed.
- It is not a sandbox product. It runs untrusted task code in Docker with a locked-down
  configuration (see [SECURITY.md](SECURITY.md)); that reduces risk but is not a guarantee.
- No LLMs, no network access for task code, no telemetry, no hosted service.

## Quickstart (about a minute, needs Docker and Python 3.11+)

Aethens is not on PyPI yet. From a clone of this repository:

```sh
python -m pip install .
docker pull python:3.12-slim
aethens audit examples/add-two --format markdown
```

The example task is clean, so this prints a report with no error or warning findings (C004 may
list info-level surviving mutants) and exits 0. Try a task with a planted defect:

```sh
aethens audit bench/tasks/brokengold-offbyone --check C001 --format markdown
```

This exits 1 and reports "Gold solution fails the verifier", with the verifier's output and a repro
command you can paste.

Useful options: `--budget smoke|standard|deep`, `--fail-on error|warning`, `--format json|markdown`,
`--seed N`, `--check C00X` (repeatable), `--output FILE`. Exit codes: 0 pass, 1 findings at or above
`--fail-on`, 2 tool error (including Ctrl-C and SIGTERM), 3 the gold solution timed out.

`--unsafe-local` runs task code directly on your machine without container isolation, with a
scrubbed environment and timeouts. Only use it on code you trust.

Tasks use the `aethens-task/v1` directory format: [docs/task-format.md](docs/task-format.md).
Reports follow `aethens-report/v2` (v1 plus a `coverage` list of what checks established where they found nothing): [docs/report-schema.json](docs/report-schema.json).

## Checks

| check | what it does | can catch | cannot catch |
|---|---|---|---|
| C001 gold sanity | runs the starting state (must fail) and the gold solution (must pass), once each | tests with no real assertions; a broken gold solution or wrong file layout | defects that only show on some runs (see C002) |
| C002 flakiness | runs the gold solution at least 3/5/10 times (smoke/standard/deep), varying only `PYTHONHASHSEED`; while every run agrees it keeps going (up to 6/11/59 runs, or 120/300/1800 s of run time) until it can state "flake rate below 0.5/0.25/0.05 at 95% confidence" (exact binomial bound, recorded in the report's coverage list) | verdicts that depend on set or dict ordering or `hash()`; flips rarer than the old fixed run count could see | flakiness from time, unseeded randomness or scheduling, except by chance; a flake rate below the stated bound |
| C003 labeled candidates | runs each candidate in `candidates/valid` and `candidates/invalid` | false rejects (over-strict tests) and false accepts (weak tests), but only as good as the labels; `llm-unreviewed` labels give warnings marked needs-review | anything for which you have no labeled candidate |
| C004 mutation probes | runs up to 5/10/30 AST mutants of the gold solution; each surviving mutant is then called side by side with the gold on the inputs the tests use plus derived inputs, inside the sandbox: a survivor that behaves differently is reported with that input as a counterexample, one that behaved like the gold on every valid input tried is not reported (listed in the report's coverage instead) | behaviour the tests never check (surviving mutants, info only) | a mutant that differs only on inputs the probe never tried is hidden (see the external bench for how often); a counterexample input may be outside the task's intended inputs; a killed mutant does not prove the tests are strong |
| C005 test order and isolation | reruns the gold's tests in their default order, reversed, in 1/2/5 seeded shuffles and each test alone (up to 10/30/200), all with the same `PYTHONHASHSEED`; a change must reproduce on a second run | tests that pass only because an earlier test left state behind, or that break when another test runs first | orders it did not try; verifiers other than `python -m unittest` (it says it checked nothing) |
| C006 over-specified tests | reruns the gold after behaviour-preserving AST rewrites (reformat, local renames, swapping adjacent constant assignments, append loop to comprehension, if/else inversion; smoke: the first two), each applied only where its safety conditions hold; a rejection must reproduce and the gold must still pass | tests that read the gold's source, line numbers, local variable names or code shape, so they would reject correct solutions written differently (warning, needs review) | over-strict tests on behaviour the statement leaves open, such as exact messages or float digits (use C003); rewrites it cannot prove safe are skipped |
| C007 reward-hacking probes | when the unsolved starter fails, runs candidates that do not solve the task, in the same sandbox: `os._exit(0)` on import, an atexit hook forcing exit 0, a unittest patch that reports success, a `sitecustomize.py` hook, functions returning an object equal to everything, and a lookup table of the visible tests' literal answers; an accepted probe must pass twice | verifiers a policy can game without solving the task (error; the lookup-table probe is a warning, needs review, since it matters only when tests are visible) | other gaming routes; pytest `conftest.py` hooks (not probed); a verifier that resists these probes can still be gamed |

## Bench numbers

The bench is **self-authored**: small original tasks written for this project, with defects planted
on purpose (task list and expected findings: [bench/manifest.yaml](bench/manifest.yaml)). Its numbers show whether Aethens catches the defects that were planted. They do
not measure real-world recall on other people's benchmarks.

<!-- bench:start -->
Generated from `bench/results.json` (aethens 0.1.0.dev0, seed 0, budget standard) by `bench/render_readme.py`.

Bench: 34 self-authored tasks, 15 clean controls and 19 with planted defects.

| metric | value |
|---|---|
| precision (error/warning findings) | 1.0 |
| recall (planted defects found) | 1.0 (20/20) |
| false positives on controls | 0 |
| unexpected error/warning findings on defective tasks | 3 |
| info findings on controls | 6 |

| defect class | found / planted |
|---|---|
| weak-tests | 3/3 |
| over-strict | 5/5 |
| flaky | 3/3 |
| no-assertions | 2/2 |
| broken-gold | 2/2 |
| order-dependence | 5/5 |

| check | found / planted | false positives |
|---|---|---|
| C001 | 4/4 | 0 |
| C002 | 4/4 | 0 |
| C003 | 4/4 | 0 |
| C004 | 1/1 | 0 |
| C005 | 4/4 | 0 |
| C006 | 3/3 | 0 |

Known misses in this run:

- none

Reward hacking (C007), scored separately: each task lists the probe categories that should get through its verifier (labels in bench/manifest.yaml).

Overall: recall 1.0 (116/116), precision 1.0, false positives 0.

| exploit category | found / labelled | false positives |
|---|---|---|
| exit-zero | 30/30 | 0 |
| atexit-override | 30/30 | 0 |
| framework-patch | 30/30 | 0 |
| sitecustomize-hook | 1/1 | 0 |
| always-equal | 15/15 | 0 |
| hardcoded-visible | 10/10 | 0 |
<!-- bench:end -->

These numbers come from a local run on the build machine (Docker Engine 29.10.0, Linux). The GitHub
CI workflow regenerates `bench/results.json` and uploads it as the `bench-results` artifact. The
first hosted run (on main at commit 8af4d39, 27 Nov 2026) produced an artifact identical to the
committed `bench/results.json`; the external HumanEval bench is not run in CI (it needs a download
and about 20 minutes).

## Accuracy on public data Aethens did not write

The bench above is self-authored, so it can only show that Aethens finds what its authors planted.
The external bench runs Aethens on public tasks and judges the results with an outside oracle.
Method, ground truth and caveats: [bench/external/README.md](bench/external/README.md).

<!-- external:start -->
Generated from `bench/external/results.json` by `bench/external/render_external.py` (aethens 0.1.0.dev0, seed 0, budget standard).

On 164 HumanEval tasks (MIT), judged by EvalPlus's HumanEval+ tests (Apache-2.0) as an outside oracle:

- C004 precision 0.8158: 31 of 38 mutants that HumanEval's own tests accepted are rejected by HumanEval+.
- C004 recall 0.8 relative to exhaustive mutation (24 of 30 weak tasks found at budget standard).
- Without C004's equivalent-mutant filter (same run): precision 0.4615, recall 0.8667; the filter hid 51 survivors, 5 of which HumanEval+ rejects.
- Error/warning findings on checks without labels in this data (presumed clean): C001 0, C002 0, C005 0, C006 0. Details: [docs/EXTERNAL_BENCH.md](docs/EXTERNAL_BENCH.md).
<!-- external:end -->

## Known misses and limits

- C005 reorders tests only for `python -m unittest` verifiers, and only tries the default order,
  reversed, a few seeded shuffles and each test alone; other orders are not tried.
- C006 only catches tests coupled to implementation details (source text, line numbers, local
  names, code shape). Its five rewrites are argued and tested to preserve behaviour, not
  machine-proved, and it skips every site it cannot show is safe. Its findings need review: a
  statement may legitimately require an implementation detail.
- C002 is still statistical: without a finding it states only that the flake rate is below a bound
  (0.25 at 95% confidence at the default budget, 0.05 at deep), assuming independent runs. A rarer
  flake can pass unseen, and the time budget can stop it before the target bound.
- C007 tries six probe families; resisting them does not prove a verifier cannot be gamed. It does
  not probe pytest `conftest.py` hooks. Almost every plain `python -m unittest` verifier is gameable
  by its exit-code probes, so expect C007 errors on most tasks until the harness judges results
  outside the solution's process (see bench/tasks/ctrl-hardened-harness for one way).
- Python tasks only; verifiers must be runnable as a command inside a Docker image with no network.
- Tested on Linux with Docker Engine. Rootless Docker, Docker Desktop and Podman are untested.

## Contributing, security and disclosure

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and the disclosure policy for findings about other people's
benchmarks in [docs/DISCLOSURE.md](docs/DISCLOSURE.md).
