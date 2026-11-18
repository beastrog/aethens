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
