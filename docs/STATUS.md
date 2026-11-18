# Status

Last updated: 2026-11-18 (Asia/Calcutta), after B7 (build week complete, local-only).

## Mode

Local-only build approved by the owner: no GitHub remote, `gh` not authenticated, so no pushes, no PRs,
and **the hosted CI has never run**. Each milestone is a local branch `feat/<id>-<slug>`, `make check`
green, CI commands run locally (Python 3.11, 3.12, 3.13), then `git merge --squash` into `main`.

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

## Next (owner actions; the agent stops after B7)
- Fresh-session hardening review (Prompt 3 in docs/BUILD_PROMPTS.md). NOT done: B7's acceptance
  criterion "fresh-session hardening review done" is therefore open, and B7 is marked PARTIAL.
- Create the GitHub repo (private), push, let CI and action-selftest run on a PR, confirm the
  bench-results artifact matches bench/results.json.
- Confirm exit code 3 semantics (D-032) and the agent-chosen limits (D-008, D-013).
- Terms check, README cold read, PyPI trusted publisher, release, flip public.

## Open risks
- Exit code 3 semantics are an agent decision (D-032); the owner should confirm.
- Bench numbers are from local runs; the hosted CI artifact does not exist yet.
- C002 is probabilistic in the run count (about 1 seed in 16 misses a 50/50 flaky test at 5 runs).
- Hosted CI has never run; the workflow file is only checked by running its commands locally.

## Not verified
- The Action and both workflows on GitHub-hosted runners; release.yml and Trusted Publishing end to end.
- Security contact: SECURITY.md points to GitHub private vulnerability reporting, which the owner must enable.
- Rootless Docker, Docker Desktop (macOS/Windows), Podman. Local mode's RLIMIT_AS is not enforced on macOS.
- The build box's dockerd runs with `--iptables=false`; on hosts with iptables the bridge network exists
  but runs still use `--network none`.
- Running the test suite needs access to the Docker socket; on this box that is the `docker` group
  (`sg docker -c "make check"`).
- Loader behaviour on case-insensitive filesystems (macOS, Windows); tested on Linux only.
- GitHub Actions behaviour (no remote).
