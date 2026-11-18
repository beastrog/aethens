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
