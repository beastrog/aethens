# Contributing

Thanks for helping. Aethens is small on purpose: Python tasks, Docker isolation, honest numbers.

Please read the [code of conduct](CODE_OF_CONDUCT.md) before opening an issue or pull request. By contributing you agree that your work is licensed under the [Apache License 2.0](LICENSE), the same licence as the rest of the project. There is no CLA. We do not require a Developer Certificate of Origin or `Signed-off-by` lines.

## Setup

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker (for the default sandbox and for tests marked `docker`).

```sh
uv sync                 # or: python -m pip install -e . && pip install ruff mypy pytest jsonschema types-PyYAML
docker pull python:3.12-slim
make check              # ruff, mypy --strict, pytest, bench regression gate
```

Docker tests are marked `docker`. Without Docker they are skipped with a "NOT VERIFIED" reason; `AETHENS_REQUIRE_DOCKER=1` turns a missing daemon into a failure (CI sets it).

`make check` is the bar every change has to clear. You can run the pieces separately with `make lint`, `make type`, `make test`, and `make bench`.

## Tests first

Write or extend the failing test before the code that makes it pass. Never weaken or delete a test to get green. If a test is wrong, replace it with a stronger one and say why in the pull request.

## Adding a check

A new check is not just a class in `src/aethens`. It needs all of the following in the same change:

1. A planted-defect bench task that the check is supposed to catch.
2. A clean control task that must stay silent.
3. A unit test for the check's behaviour.
4. Updated bench numbers. README figures are generated with `python bench/render_readme.py` and must not be typed by hand.

Name the check consistently (for example C008) and document what it reports, its severity, and its limits. Changes to check semantics, the report schema, severities, thresholds, or Docker isolation settings need maintainer approval and a `CHANGELOG.md` entry.

## Rules that matter most

- Library first: only `src/aethens/cli/` prints or sets exit codes.
- No `shell=True`, no string-built commands, no network calls in tests, no telemetry, no secrets.
- Never run task code in the Aethens process; use the runner.
- Keep dependencies minimal and permissively licensed; record new ones in `docs/DECISIONS.md`.

## Pull requests

1. Branch from `main`. Use a focused name such as `fix/…`, `feat/…`, or `docs/…`.
2. Keep the diff to one change. Mention related issues in the description.
3. Update `CHANGELOG.md` under `[Unreleased]` for user-facing changes.
4. Open a pull request. CI must be green (`check (3.11)`, `check (3.12)`, and `selftest`).
5. Maintainers squash-merge. Do not force-push to `main`, create tags, or publish releases or packages; the maintainer does those.

If your change would alter a check's meaning, the report schema, a severity, a threshold, or the sandbox, call that out at the top of the pull request and wait for maintainer approval.

## Reporting results and false positives

If you ran Aethens on your own tasks, the "I ran Aethens on X" issue template is the most useful feedback you can give. To report a finding Aethens got wrong, use the false-positive template and include the report JSON plus the one-line repro command.

Please do not name defects in other people's benchmarks in a public issue before their maintainers have been told privately; see [docs/DISCLOSURE.md](docs/DISCLOSURE.md).

## Security

Report vulnerabilities privately through GitHub's Security advisory form, not in a public issue. See [SECURITY.md](SECURITY.md).

## Getting help

- Questions and ideas: [GitHub Discussions](https://github.com/beastrog/aethens/discussions)
- Bugs, features, and check proposals: the issue templates
- Community chat: a Discord server may be added later; there is no invite yet
