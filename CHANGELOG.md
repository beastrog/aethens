# Changelog

All notable changes are recorded here. The format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Added
- D1: check C005 (test order and isolation): reruns the tests reversed, in seeded shuffles and one at a time, and reports every test whose verdict changes and reproduces. Bench grows to 26 tasks; order-alphabetical and order-generated are now caught (expected check moved to C005).
- B1: project skeleton, typed models (Task, Candidate, Finding, Report), typed errors, `make check`, CI workflow.
- B2: aethens-task/v1 loader and validator with typed errors; two example tasks; docs/task-format.md.
- B3: runner with Docker default (no network, memory/CPU/pids limits, read-only rootfs, all capabilities dropped, no-new-privileges, non-root, disposable copy, guaranteed cleanup) and explicit unsafe-local mode.
- B4: checks C001 (gold sanity) and C002 (flakiness), minimal `aethens audit` (JSON), first bench fixtures with manifest.
- B5: checks C003 (labeled candidates, label_source aware) and C004 (AST mutation probes, info only); bench grows to 15 tasks.
- B6: aethens-report/v1 JSON Schema, Markdown reports, full `aethens audit` CLI with exit codes 0/1/2/3, bench runner with precision/recall and a baseline regression gate; bench grows to 22 tasks.
- B7: composite GitHub Action, README with generated bench numbers and limits, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, issue templates, disclosure policy, release workflow with Trusted Publishing.
