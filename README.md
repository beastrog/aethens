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
`--fail-on`, 2 tool error, 3 the gold solution timed out.

`--unsafe-local` runs task code directly on your machine without container isolation, with a
scrubbed environment and timeouts. Only use it on code you trust.

Tasks use the `aethens-task/v1` directory format: [docs/task-format.md](docs/task-format.md).
Reports follow `aethens-report/v1`: [docs/report-schema.json](docs/report-schema.json).

## Checks

| check | what it does | can catch | cannot catch |
|---|---|---|---|
| C001 gold sanity | runs the starting state (must fail) and the gold solution (must pass), once each | tests with no real assertions; a broken gold solution or wrong file layout | defects that only show on some runs (see C002) |
| C002 flakiness | runs the gold solution 3/5/10 times (smoke/standard/deep), varying only `PYTHONHASHSEED` | verdicts that depend on set or dict ordering or `hash()` | flakiness from time, unseeded randomness or scheduling, except by chance; a test that flips 50/50 is missed with probability 2 × 0.5^5 = 1/16 at 5 runs |
| C003 labeled candidates | runs each candidate in `candidates/valid` and `candidates/invalid` | false rejects (over-strict tests) and false accepts (weak tests), but only as good as the labels; `llm-unreviewed` labels give warnings marked needs-review | anything for which you have no labeled candidate |
| C004 mutation probes | runs up to 5/10/30 AST mutants of the gold solution | behaviour the tests never check (surviving mutants, info only) | equivalent mutants look like weaknesses; a killed mutant does not prove the tests are strong |

## Bench numbers

The bench is **self-authored**: small original tasks written for this project, with defects planted
on purpose (task list and expected findings: [bench/manifest.yaml](bench/manifest.yaml)). Its numbers show whether Aethens catches the defects that were planted. They do
not measure real-world recall on other people's benchmarks.

<!-- bench:start -->
Generated from `bench/results.json` (aethens 0.1.0.dev0, seed 0, budget standard) by `bench/render_readme.py`.

Bench: 22 self-authored tasks, 8 clean controls and 14 with planted defects.

| metric | value |
|---|---|
| precision (error/warning findings) | 1.0 |
| recall (planted defects found) | 0.8571 (12/14) |
| false positives on controls | 0 |
| unexpected error/warning findings on defective tasks | 3 |
| info findings on controls | 2 |

| defect class | found / planted |
|---|---|
| weak-tests | 3/3 |
| over-strict | 2/2 |
| flaky | 2/2 |
| no-assertions | 2/2 |
| broken-gold | 2/2 |
| order-dependence | 1/3 |

| check | found / planted | false positives |
|---|---|---|
| C001 | 4/4 | 0 |
| C002 | 3/5 | 0 |
| C003 | 4/4 | 0 |
| C004 | 1/1 | 0 |

Known misses in this run:

- `order-generated` (order-dependence, expected C002)
- `order-alphabetical` (order-dependence, expected C002)
<!-- bench:end -->

These numbers come from a local run on the build machine (Docker Engine 29.10.0, Linux). The GitHub
CI workflow regenerates `bench/results.json` and uploads it as the `bench-results` artifact; it has
not run yet.

## Known misses and limits

- Order dependence that follows unittest's fixed alphabetical order (`bench/tasks/order-alphabetical`)
  is not caught: no v0.1 check reorders tests.
- C002 is probabilistic in the number of runs. At the bench seed, `bench/tasks/order-generated` is
  missed because all five runs happened to execute the tests in the failing order.
- Harnesses that judge only the exit code accept a solution that calls `os._exit(0)` on import. v0.1
  has no check for this (see docs/IDEAS.md).
- Python tasks only; verifiers must be runnable as a command inside a Docker image with no network.
- Tested on Linux with Docker Engine. Rootless Docker, Docker Desktop and Podman are untested.

## Contributing, security and disclosure

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and the disclosure policy for findings about other people's
benchmarks in [docs/DISCLOSURE.md](docs/DISCLOSURE.md).
