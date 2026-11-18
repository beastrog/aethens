# Status

Last updated: 2026-11-18 (Asia/Calcutta), after B1.

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

## Next
- B2: aethens-task/v1 loader and validator.

## Open risks
- Hosted CI has never run; the workflow file is only checked by running its commands locally.

## Not verified
- GitHub Actions behaviour (no remote).
