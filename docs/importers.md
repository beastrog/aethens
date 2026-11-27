# Importers: public benchmarks into aethens-task/v1

`aethens import FORMAT SOURCE.jsonl OUT_DIR [--only id,id] [--overwrite]` converts a benchmark
export into task directories that `aethens audit` can run. Importers never run task code and never
use the network. `bench/real/fetch_real.py` downloads the pinned exports (licences:
[bench/LICENSES.md](../bench/LICENSES.md)).

| format | source | gold | verifier | image | status |
|---|---|---|---|---|---|
| `mbppplus` | evalplus/mbppplus | reference `code` | EvalPlus `test` code, verbatim, run in one namespace with the solution | `aethens-evalplus:py3.12` (build: `docker build -t aethens-evalplus:py3.12 bench/real/images/evalplus`) | audited, all 378 tasks |
| `humanevalplus` | evalplus/humanevalplus | prompt + canonical solution | EvalPlus `check(candidate)`, verbatim | same | importer only |
| `bigcodebench` | bigcode/bigcodebench v0.1.4 | complete prompt + canonical solution | the `TestCases` unittest code, verbatim, in a `__test__` module as BigCodeBench's harness does | official evaluation image, pinned by digest | importer done; audit next |
| `swebench` | SWE-bench/SWE-bench_Verified (the export with `image`, `eval_script`, `log_parser`) | `solution.patch` = gold patch | the official eval script and swebench 5.0.2's own log parser and grading rules, inside the sandbox (see below) | the official per-instance image | importer done, verified on django__django-11099 (gold resolved, starter not); audit next |
| Harbor / Terminal-Bench 2 | task directories | - | - | - | compatibility scan only: 0 of 89 tasks can run in the current sandbox (below) |
| Prime Intellect `verifiers` environments | - | - | - | - | not built (below) |

## SWE-bench under the Aethens sandbox

The sandbox is read-only, non-root and offline, while the official harness runs as root in a
writable container. `aethens.sandbox.swe_harness` bridges that without loosening isolation:

1. it copies the image's `/testbed` (with `.git`) into the disposable work directory;
2. applies `solution.patch` with the official fallbacks (git apply, `--3way`, `--reject`,
   `patch --fuzz=5`); no patch (the starter) means the unsolved repository;
3. runs the official eval script with three mechanical changes, all printed in the log:
   `/testbed` -> the copy (heredoc bodies untouched), `pip install -e .` lines skipped (the copy
   goes first on `PYTHONPATH`, mapped from the env's editable-install paths), and the
   `locale-gen` line skipped (needs root; the images already contain en_US.UTF-8);
4. grades the log with swebench 5.0.2's parsers and rules (vendored verbatim): every
   FAIL_TO_PASS test passes (XFAIL counts), every PASS_TO_PASS test passes or is skipped, the test
   command's exit code must not contradict a clean log.

Limits: a gold patch that changes compiled extensions or packaging metadata would need the
skipped reinstall (none observed yet); per-run limits are Aethens' defaults (1 GiB, 1 CPU,
256 pids), stricter than SWE-bench's, so a memory-hungry suite can fail C001 for that reason and
every such finding is checked against the official harness before it is counted.

## Terminal-Bench 2 / Harbor

`aethens.importers.harbor.scan_harbor_task` reads `task.toml`, `tests/test.sh` and
`solution/solve.sh`. On terminal-bench-2 @ 2fd12b88: 89 tasks; 89 verifiers install their test
dependencies from the network at test time (82 use `uvx`, most `apt-get install curl` and the uv
installer); 34 reference solutions also need the network; all 89 read or write absolute paths
such as `/app`, `/tests`, `/logs/verifier`. None can run under `--network none`, non-root, with a
read-only root filesystem. Running them needs a separate runner profile (dependencies baked into
the image at build time, a writable container layer, root inside the container, still no
network). That changes the Docker isolation settings, so it waits for the owner's decision
(docs/DECISIONS.md D-084).

## Prime Intellect `verifiers` environments

Environments are Python packages whose `load_environment()` builds a dataset (downloaded from
Hugging Face at load time) and a rubric of reward functions. The code environments read so far
(`mbpp`, `humaneval` in prime-environments) score a completion by `exec`-ing it with the dataset's
asserts in the reward process itself and return a pass fraction. A generic importer would have to
run the environment's own Python (and its dependencies) inside the sandbox; that is feasible per
environment but not built yet. Their tests are the original MBPP and HumanEval asserts, which the
MBPP+ and HumanEval audits already cover as data.
