# Ideas (not to be built without the owner's approval)

Ideas that came up during the build. AGENTS.md rule 14: write them here, do not build them.

- C005 exit-zero probe (stretch in the plan, not built in B5). A candidate whose module does
  `os._exit(0)` on import makes `python -m unittest` (and pytest) exit 0 before any test runs, so every
  harness that only looks at the exit code accepts it. Built naively, C005 would fire on nearly every
  task, including all bench controls (which use exactly that kind of harness), which breaks the
  "zero false positives on controls" gate. It needs an owner decision on severity and on what counts
  as a robust harness (for example requiring a results file or a test-count line) before it is built.
  BUILT in D5 as C007 (owner-approved), with reward-hacking scored separately from the core metrics
  so the controls stay meaningful (DECISIONS D-060).
- C007 pytest probes: a `conftest.py` that forces every test to pass (e.g. a
  `pytest_runtest_makereport` hook) and pytest plugin autoloading. Not built: the default image has
  no pytest and runs have no network, so it could not be tested here.
- C007 probes for other gaming routes: writing expected-output files the harness reads, patching
  `builtins` used by the tests, reading the tests' expected values at run time from `tests/`.
- Report C004 kill ratios per task in the Markdown summary (currently only in each survivor's evidence).
- Equivalent-mutant filter: skip `<` -> `<=` mutants where both branches return the same bound (seen on
  ctrl-clamp). Needs care not to hide real weaknesses.
- C002: treat the C001 gold run as an extra sample, or add runs adaptively when all runs agree, to cut
  the 1-in-16 miss rate seen on order-generated (seed 0). Changes check semantics: owner decision.
- Order-dependence check: rerun the verifier with test order reversed or shuffled (needs a
  harness-specific hook, e.g. unittest's sortTestMethodsUsing or pytest-randomly), to catch
  order-alphabetical-style defects.
- C005 for pytest verifiers: list node ids with `--collect-only -q` and pass them in the wanted
  order (needs an image with pytest; pytest's handling of explicit node-id order should be read in
  its source first). Not built in D1.
- C005: treat a reordered run that crashes before reporting (e.g. a test calls `os._exit`) as a
  run-level finding; today such runs are skipped and the limits say so.
- External bench: add EvalPlus MBPP+ (re-check MBPP CC-BY-4.0 and MBPP+ Apache-2.0 first) and any
  public dataset with labelled flaky, order-dependent or over-specified tests, so C002/C005/C006 get
  real recall numbers, not only false-positive counts.

- (27 Nov 2026) Prime Intellect `verifiers` environment importer: run an environment's reward
  functions inside the sandbox on gold and on probe completions (D-085).
- (27 Nov 2026) Harbor / Terminal-Bench runner profile with dependencies baked at image build
  time (D-084, needs owner approval).
- (27 Nov 2026) Patch-hunk mutation for SWE-bench: mutate only the lines the gold patch touches
  (C004 currently needs whole Python files in gold/).
- C004: a CLI switch to turn the equivalent-mutant filter off (`--no-equivalence-filter`), and a
  deeper probe budget that also reuses inputs across survivors of the same task (D-065).
- C004: precondition inference for the equivalence probe (skip derived inputs the gold's own guards
  or docstring examples suggest are outside the domain) to cut the remaining false positives.
