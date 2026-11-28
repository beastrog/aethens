# Terminal-Bench 2 in the unchanged Aethens sandbox

Status: experimental bench tooling (2026-11-27). Not part of `make check`; needs Docker, network for
`docker pull`/`docker build`, and the task images.

## Why this exists

PR #3's static Harbor scan (D-084) found that 0 of 89 Terminal-Bench 2 tasks can run as Harbor runs
them under Aethens' isolation (no network, non-root, read-only root filesystem). D-084 proposes a
"harbor" runner profile (writable layer, root), which loosens isolation and needs the owner's
approval. **This tooling does not do that.** The runner, CLI flags and isolation settings are
untouched. Instead `convert_tb2.py` moves Harbor's test-time network and root steps to image-build
and data-preparation time:

- **image**: a derived image `FROM` the task's own image (pinned by digest) that adds uv 0.9.5, a
  Python 3.13 venv with exactly the `-w` pins from the task's `tests/test.sh`, that venv's `bin/`
  first on `PATH` (as under `uvx`), and `/app -> /work`, `/tests -> /work/tests` symlinks so the
  task's absolute paths land in Aethens' disposable work directory.
- **starter**: `/app` of the original image. **gold**: the files under `/app` that the task's own
  `solution/solve.sh` created or changed, from a throwaway root container with network (Harbor's
  "oracle agent"). The task's ORIGINAL `tests/test.sh` then runs in that container and its reward is
  recorded as `oracle_reward`, so adaptation problems can be told apart from verifier problems.
- **tests**: verbatim. **verifier**: `python -m pytest -p no:cacheprovider` + the task's pytest
  arguments (minus `--ctrf`), in the image's WORKDIR.

It is an option (c) next to D-084's (a) and (b): it can run only tasks whose verifier is a pytest
file over state under `/app`, and every gold failure must be checked against `oracle_reward` and a
run in the unmodified image before it counts.

## Usage

```sh
bench/tbench/fetch_tb2.sh /path/to/terminal-bench-2          # pinned 2fd12b88
docker pull alexgshaw/<task>:20251031                        # per task, see task.toml
python bench/tbench/convert_tb2.py --tb2 /path/to/terminal-bench-2 --out /tmp/tb2 \
  --only example-task-a,example-task-b --docker "sg docker -c"   # --docker only if needed
python bench/tbench/run_tb2.py /tmp/tb2/tasks /tmp/tb2/out --budget standard
```

`conversion.json` records per task: base image digest, test pins, gold files, files solve.sh
deleted (not expressible as an overlay), WORKDIR, the task's own CPU/memory limits, and
`oracle_reward`. Converted tasks and anything derived from them stay out of git: Terminal-Bench
task files carry a "never in training corpora" canary.

## Licence

Terminal-Bench 2 (github.com/harbor-framework/terminal-bench-2 @ 2fd12b88aafdd04a52c298e3940bcb189f9766d6):
**Apache-2.0** (repository `LICENSE`, checked 2026-11-27). Task images `alexgshaw/*:20251031` on
Docker Hub are built from that repository; pulled at audit time, never redistributed. uv
(ghcr.io/astral-sh/uv:0.9.5): MIT OR Apache-2.0, copied into a local image only. Nothing from the
benchmark is committed. This entry belongs in `bench/LICENSES.md`, which PR #3 is editing; it moves
there after #3 merges.

## What Aethens can and cannot check on these tasks (first sample, seed 0)

- **C001, C002** apply fully (starter must fail, gold must pass, gold verdict stable over runs).
- **C003** applies when someone writes labelled candidate outputs by hand (the useful route here).
- **C004/C006** mutate or rewrite Python files in the gold overlay. Most TB2 golds are output files
  (no Python), so these report "checked nothing". Where the gold overlay contains the script that
  produced the output (e.g. a solver plus its `.npy` result), the verifier only reads the output, so
  every mutant of the script "survives": these are **false positives** of C004 on this task shape
  (the mutated file is never executed by the verifier). See "Proposed Aethens changes".
- **C005** supports only `python -m unittest`; it checks nothing on pytest verifiers.
- **C007** probes Python modules and unittest; pytest `conftest.py` hooks are not probed (IDEAS).

Findings about Terminal-Bench tasks are kept in the gitignored `audits/private/tb2/` for the owner
to review (AGENTS.md rule 12). The one finding the maintainer has published is
`constraints-scheduling` (tests 2 and 3 read the first `DTSTART`). It was confirmed with that
task's own `tests/test.sh`, and it is written up in `docs/reproduce-findings.md` and in
harbor-framework/terminal-bench-2 issue 107. Nothing else from the private directory is published here.

## Proposed Aethens changes (not made; need the owner's approval)

1. C004: before mutating a gold file, run the verifier with that file replaced by a stub that raises
   on import or execution; if the verdict does not change, report one info "gold file not exercised
   by the verifier" instead of N surviving mutants. Changes check output: owner decision.
2. C005 and C007 for pytest verifiers (both already in docs/IDEAS.md); TB2 tasks all use pytest.
3. Allow larger task files (the 5 MiB per-file limit skips TB2 tasks that ship git packs or data);
   changes the task-format contract: owner decision.
