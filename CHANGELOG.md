# Changelog

All notable changes are recorded here. The format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

### Added
- B1: project skeleton, typed models (Task, Candidate, Finding, Report), typed errors, `make check`, CI workflow.
- B2: aethens-task/v1 loader and validator with typed errors; two example tasks; docs/task-format.md.
- B3: runner with Docker default (no network, memory/CPU/pids limits, read-only rootfs, all capabilities dropped, no-new-privileges, non-root, disposable copy, guaranteed cleanup) and explicit unsafe-local mode.
- B4: checks C001 (gold sanity) and C002 (flakiness), minimal `aethens audit` (JSON), first bench fixtures with manifest.
