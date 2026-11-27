<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <img src="assets/wordmark-light.svg" alt="Aethens" width="320">
</picture>

# Documentation

Guides and generated records for [Aethens](https://github.com/beastrog/aethens), the open-source verifier auditor.

[![CI](https://github.com/beastrog/aethens/actions/workflows/ci.yml/badge.svg)](https://github.com/beastrog/aethens/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-1f6feb.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab.svg)](../pyproject.toml)

</div>

## Start here

| Document | What it is |
|---|---|
| [../README.md](../README.md) | Product overview, quickstart, published accuracy, comparison |
| [task-format.md](task-format.md) | The `aethens-task/v1` directory layout Aethens reads |
| [report-schema.json](report-schema.json) | The `aethens-report/v2` report schema |
| [EXTERNAL_BENCH.md](EXTERNAL_BENCH.md) | External-bench method, ground truth, and generated results (HumanEval / HumanEval+) |
| [REAL_WORLD_RESULTS.md](REAL_WORLD_RESULTS.md) | Audits of public benchmarks (MBPP+, HumanEval+) with every finding checked by hand; per-check TP/FP tallies |
| [../bench/external/README.md](../bench/external/README.md) | How to fetch, convert, and rerun the external bench |

## Run and report it

| Document | What it is |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Setup, `make check`, and the rules that matter most |
| [../SUPPORT.md](../SUPPORT.md) | How to get help: Discussions, issue templates, disclosure |
| [../SECURITY.md](../SECURITY.md) | How to report a vulnerability; Docker isolation limits |
| [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Contributor Covenant |
| [../GOVERNANCE.md](../GOVERNANCE.md) | How the project is maintained |
| [DISCLOSURE.md](DISCLOSURE.md) | How findings about other people's benchmarks are handled |
| [LICENSING.md](LICENSING.md) | Third-party notices and dependency licences |
| [../NOTICE](../NOTICE) | Apache-2.0 NOTICE shipped in the sdist |

## Design record

These files are the project's working notes. Numbers in [EXTERNAL_BENCH.md](EXTERNAL_BENCH.md) are generated from JSON; do not edit them by hand.

| Document | What it is |
|---|---|
| [COMPETITIVE.md](COMPETITIVE.md) | Survey of other auditor tools, 18 Nov 2026, from public sources |
| [DECISIONS.md](DECISIONS.md) | Design decisions and new dependencies |
| [STATUS.md](STATUS.md) | What is done, what is next, and what was not verified |
| [IDEAS.md](IDEAS.md) | Ideas not scheduled to build |
| [AETHENS_PLAN.md](AETHENS_PLAN.md) | Original plan (source of truth with `AGENTS.md` and `ROADMAP.yaml`) |

The marketing site, which reads `bench/results.json` and `bench/external/results.json` at build time, is at [beastrog.github.io/aethens](https://beastrog.github.io/aethens/). Questions and audit enquiries: [GitHub Discussions](https://github.com/beastrog/aethens/discussions). Founder: [Ani Dey](https://linkedin.com/in/aniruddha-dey-887b26312/).
