# Status

Last updated: 2026-11-18 (Asia/Calcutta), after B4.

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

## Next
- B5: C003 labeled candidates, C004 mutation probes, bench to at least 12 tasks.

## Open risks
- C002 is probabilistic in the run count (about 1 seed in 16 misses a 50/50 flaky test at 5 runs).
- Hosted CI has never run; the workflow file is only checked by running its commands locally.

## Not verified
- Rootless Docker, Docker Desktop (macOS/Windows), Podman. Local mode's RLIMIT_AS is not enforced on macOS.
- The build box's dockerd runs with `--iptables=false`; on hosts with iptables the bridge network exists
  but runs still use `--network none`.
- Running the test suite needs access to the Docker socket; on this box that is the `docker` group
  (`sg docker -c "make check"`).
- Loader behaviour on case-insensitive filesystems (macOS, Windows); tested on Linux only.
- GitHub Actions behaviour (no remote).
