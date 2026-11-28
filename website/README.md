# Aethens website

Marketing site for [Aethens](https://github.com/beastrog/aethens), an open-source (Apache-2.0)
Python CLI and GitHub Action that audits the verifiers of RL environments and code-task
benchmarks.

This is a static Astro site, deployed to GitHub Pages at
[https://beastrog.github.io/aethens/](https://beastrog.github.io/aethens/).

## Stack

- [Astro](https://astro.build) (static output)
- [Tailwind CSS](https://tailwindcss.com) v4 via `@tailwindcss/vite`
- Self-hosted fonts: Newsreader, IBM Plex Sans, IBM Plex Mono (Fontsource)
- Bench figures are generated at build time from the repository's JSON, not typed into the page

`astro.config.mjs` sets `site` to `https://beastrog.github.io` and `base` to `/aethens`.

## Pages

The home page (`src/pages/index.astro`) is short: hero and install command, a four-item "what it does" strip, a findings teaser (Terminal-Bench 2 and SWE-bench issue 733), and links to the detail pages. The header links to those pages.

1. How it works — the problem (OpenAI SWE-bench Verified retirement, SWE-Bench+, EvalPlus), checks C001–C007, and a real C005 report
2. Findings — Terminal-Bench 2 (full reward, 3/3) and SWE-bench Verified (issue 733)
3. Accuracy — internal bench, C007, external HumanEval / HumanEval+ (C004 precision 0.8158 with the equivalent-mutant filter, 0.4615 without; both from `bench/external/results.json`), then the comparison with rlgate, BenchJack, and Assay (18 Nov 2026)
4. Docs — getting started, CLI, checks, GitHub Action, report format, FAQ
5. Roadmap — what 0.1.0 is not, expert audits, hosted CI marked "Not available", open-source status
6. Footer — GitHub, Discussions, and the founder LinkedIn

## Numbers, and how to refresh them

The generator reads, from the repository root:

- `bench/results.json`
- `bench/external/results.json`

Labels and provenance notes live in `website/data/bench/meta.json`.

`npm run numbers` (also run automatically by `npm run build` and `npm run dev`) writes
`website/src/data/numbers.json` from those files. Do not edit `src/data/numbers.json` by hand.
When a new bench run lands, update the date and note in `meta.json` and rebuild.

## Run locally

Needs Node 20+. From this `website/` folder, inside a full Aethens checkout:

```sh
npm install
npm run dev
```

The dev server listens on `http://127.0.0.1:4321/aethens/` (the `/aethens` base path is required).

## Build

```sh
npm run build
```

Static files are written to `dist/`, already prefixed for `/aethens/`. Preview:

```sh
npm run preview
```

GitHub Pages is deployed by `.github/workflows/pages.yml` on a push to `main` that touches
`website/**` or the bench result JSON, and on `workflow_dispatch`.

## Licence

Apache License 2.0, same as Aethens. See `LICENSE`.
