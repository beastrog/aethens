# Contributing

Thanks for helping. Aethens is small on purpose: Python tasks, Docker isolation, honest numbers.

## Setup

```sh
uv sync                 # or: python -m pip install -e . && pip install ruff mypy pytest jsonschema types-PyYAML
docker pull python:3.12-slim
make check              # ruff, mypy --strict, pytest, bench regression gate
```

Docker tests are marked `docker`. Without Docker they are skipped with a "NOT VERIFIED" reason;
`AETHENS_REQUIRE_DOCKER=1` turns a missing daemon into a failure (CI sets it).

## Rules that matter most

- Library first: only `src/aethens/cli/` prints or sets exit codes.
- No `shell=True`, no string-built commands, no network calls in tests, no telemetry, no secrets.
- Never run task code in the Aethens process; use the runner.
- Tests first. Never weaken or delete a test to get green.
- A new check needs a planted-defect bench task, a clean control, a unit test and updated bench numbers.
  README numbers are generated (`python bench/render_readme.py`), never typed.
- Changes to check semantics, the report schema, severities, thresholds or Docker isolation settings
  need maintainer approval and a CHANGELOG entry.
- Keep dependencies minimal and permissively licensed; record new ones in docs/DECISIONS.md.

## Reporting results

If you ran Aethens on your own tasks, the "I ran Aethens on X" issue template is the most useful
feedback you can give, including false positives and misses.
