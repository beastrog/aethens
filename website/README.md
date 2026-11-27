# Aethens website

Marketing site for [Aethens](https://github.com/beastrog/aethens), an open-source (Apache-2.0)
Python CLI and GitHub Action that audits the verifiers of RL environments and code-task
benchmarks.

This is a static Astro site, deployed to GitHub Pages at
[https://beastrog.github.io/aethens/](https://beastrog.github.io/aethens/).
A Pages site is publicly reachable even when this repository is private.

## Stack

- [Astro](https://astro.build) (static output)
- [Tailwind CSS](https://tailwindcss.com) v4 via `@tailwindcss/vite`
- Self-hosted fonts: Newsreader, IBM Plex Sans, IBM Plex Mono (Fontsource)
- Bench figures are generated at build time from the repository's JSON, not typed into the page

`astro.config.mjs` sets `site` to `https://beastrog.github.io` and `base` to `/aethens`.

## Pages

A single page, `src/pages/index.astro`, with these sections:

1. Hero — pitch, install-from-source, GitHub Action quickstart, internal-bench ribbon
2. The problem — public citations only (OpenAI SWE-bench Verified retirement, SWE-Bench+, EvalPlus)
3. The checks — C001–C007, with what each can and cannot catch
4. Published accuracy — internal bench, C007, external HumanEval / HumanEval+ (including C004 precision 0.46)
5. Comparison — Aethens, rlgate, BenchJack, Assay, dated 18 Nov 2026
6. Example report — a real C005 run on `bench/tasks/order-alphabetical`
7. Audits for teams — paid audit enquiry and a hosted-CI waitlist (mailto placeholder)
8. Open source — link to the GitHub repo
9. Footer — Folric (`folric.ai`) as maintainer

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
