# Licensing

Aethens is licensed under the [Apache License, Version 2.0](../LICENSE). Anyone may use, modify, and use it commercially, including in proprietary products, subject to the conditions of that licence: preserve the licence and copyright notices, state significant changes, and include a readable copy of `NOTICE` when you redistribute. Apache-2.0 does not grant trademark rights in the name "Aethens".

The `LICENSE` file is the official Apache-2.0 legal text. Third-party attributions required when distributing this repository (or a substantial portion of it) are collected in [`NOTICE`](../NOTICE). Dependency licences were checked on 2026-11-27.

Runtime and development dependencies are listed from `pyproject.toml` and the resolved `uv.lock`. Website packages are listed from `website/package.json` and `website/package-lock.json`. GitHub Actions are those referenced in `.github/workflows/`.

## Runtime (the `aethens` package)

The published software has a single runtime dependency.

| package | locked version | licence | role |
|---|---|---|---|
| PyYAML | 6.0.3 | MIT | parse `task.yaml` |

The Python standard library, used throughout, is licensed under the [Python Software Foundation License Version 2](https://docs.python.org/3/license.html) (permissive).

## Build and development

Declared in `[build-system]`, `[dependency-groups] dev`, or pulled in by those tools and locked in `uv.lock`. None of these are imported by the `aethens` runtime package.

| package | locked / declared version | licence | role |
|---|---|---|---|
| hatchling | `>=1.33` (build-system) | MIT | build backend |
| ruff | 0.17.5 | MIT | lint and format |
| mypy | 2.4.1 | MIT | type check |
| mypy-extensions | 1.2.0 | MIT | mypy |
| pytest | 9.2.0 | MIT | tests |
| jsonschema | 4.26.0 | MIT | schema tests |
| types-PyYAML | 6.0.12.20261113 | Apache-2.0 | type stubs |
| typing-extensions | 4.16.0 | PSF-2.0 | typing |
| attrs | 26.1.0 | MIT | jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | jsonschema |
| referencing | 0.37.0 | MIT | jsonschema |
| rpds-py | 2026.9.1 | MIT | jsonschema |
| pluggy | 1.7.0 | MIT | pytest |
| iniconfig | 2.3.1 | MIT | pytest |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | pytest |
| pygments | 2.21.0 | BSD-2-Clause | pytest |
| colorama | 0.4.6 | BSD | pytest (Windows) |
| pathspec | 1.1.1 | MPL-2.0 | mypy |
| librt | 0.16.0 | MIT | mypy |
| ast-serialize | 0.13.1 | MIT | locked transitives |
| build (CI release job) | 1.6.1 | MIT | sdist/wheel |
| twine (CI release job) | 7.0.0 | Apache-2.0 | package check |

`pathspec` is Mozilla Public License 2.0, a weak file-level copyleft. It is a development tool only. Using it unchanged does not change the licence of Aethens. If you modify `pathspec` itself and redistribute that modified file, MPL-2.0 requires you to share the modified file under MPL-2.0.

No GPL, AGPL, or non-commercial Python packages appear in `uv.lock`.

## Website (`website/`)

The marketing site is also Apache-2.0 (`website/LICENSE` is the same official text). Direct dependencies:

| package | locked version | licence | role |
|---|---|---|---|
| astro | 7.4.13 | MIT | site generator |
| tailwindcss | 4.3.5 | MIT | CSS |
| @tailwindcss/vite | 4.3.5 | MIT | Tailwind Vite plugin |
| @fontsource/ibm-plex-sans | 5.3.0 | OFL-1.1 | font |
| @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 | font |
| @fontsource/newsreader | 5.3.0 | OFL-1.1 | font |
| puppeteer-core | 25.19.0 | Apache-2.0 | local screenshots (dev) |

The 343 locked npm packages are almost all MIT, Apache-2.0, ISC, BSD, 0BSD, BlueOak-1.0.0, or CC0-1.0. Two families need a closer look and do not change the licence of Aethens itself:

- **lightningcss** (1.33.0, and its platform packages) is MPL-2.0. Tailwind uses it at build time to generate CSS. The built CSS is not an MPL-covered source file.
- **sharp** (pulled by Astro for optional image optimisation) depends on **@img/sharp-libvips-***, which is LGPL-3.0-or-later (some Windows/wasm builds also Apache-2.0 and MIT). These are optional native binaries used on the machine that *builds* the site. They are not shipped in the Aethens Python package, and a static Pages deploy should not include the libvips binaries. If you redistribute a container or installer that includes `sharp` / libvips, LGPL-3.0 obligations apply to those binaries (offer object files or a way to relink against a modified libvips, and keep the LGPL notices).

The bundled IBM Plex and Newsreader fonts are under the SIL Open Font License 1.1. You may embed them in the site; you may not sell the fonts as a standalone font package, and you must keep the OFL notice when you redistribute the font files.

## GitHub Actions

Third-party actions used in `.github/workflows/`, all pinned by commit SHA. Licences checked from each action repository's GitHub licence metadata on 2026-11-27.

| action | licence |
|---|---|
| actions/checkout | MIT |
| actions/setup-python | MIT |
| actions/setup-node | MIT |
| actions/configure-pages | MIT |
| actions/upload-pages-artifact | MIT |
| actions/deploy-pages | MIT |
| actions/upload-artifact | MIT |
| actions/download-artifact | MIT |
| pypa/gh-action-pypi-publish | BSD-3-Clause |
| release-drafter/release-drafter | ISC |

The composite action in this repository (`action.yml`) is Apache-2.0 with the rest of Aethens.

## Bench data and vendored samples

Original tasks under `bench/tasks/` are Apache-2.0. Third-party datasets must be recorded in [`bench/LICENSES.md`](../bench/LICENSES.md) before they are committed. The current external bench, licences checked on 2026-11-18:

| dataset | licence | redistributing derived task files |
|---|---|---|
| OpenAI HumanEval (github.com/openai/human-eval) | MIT, Copyright (c) OpenAI (https://openai.com) | Yes, including commercially, if you keep the copyright and permission notices. A small sample is committed under `bench/external/sample/tasks/` with those notices in each file. The full dataset is downloaded at run time into the gitignored `bench/external/data/`. |
| EvalPlus HumanEval+ (huggingface.co/datasets/evalplus/humanevalplus) | Apache-2.0 | Yes, subject to Apache-2.0, including a note that the committed sample is modified (numpy helper replaced). Sample under `bench/external/sample/oracle/`. |

Vendored code: `src/aethens/sandbox/swebench_grading.py` copies the log parsers and grading rules of swebench 5.0.2 (MIT, Copyright (c) 2023 Carlos E Jimenez, John Yang, Alexander Wettig, Shunyu Yao, Kexin Pei, Ofir Press, Karthik R Narasimhan); the full notice is kept in the file and summarised in `NOTICE`. The importers (`aethens import`) commit no benchmark data; their licences are recorded in `bench/LICENSES.md`.

Datasets considered and skipped because the data licence is unclear, or because they need network-built images, are listed in `bench/LICENSES.md`. Do not commit or publish them until that is resolved.

Importers for other public benchmarks (MBPP+, BigCodeBench, SWE-bench Verified, Terminal-Bench, and similar) must follow the same rule: record the licence, prefer gitignored downloads over committing large exports, and do not redistribute a dataset whose card states no licence.

## Adding a dependency

Keep new dependencies minimal and permissively licensed (MIT, BSD, Apache-2.0, ISC, PSF, or similar). Record the choice in `docs/DECISIONS.md` and update this file and `NOTICE` when a notice must travel with redistributions. Copyleft (GPL, AGPL, LGPL), non-commercial, and unknown licences need maintainer approval before they are added.
