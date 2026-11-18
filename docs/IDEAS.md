# Ideas (not to be built without the owner's approval)

Ideas that came up during the build. AGENTS.md rule 14: write them here, do not build them.

- C005 exit-zero probe (stretch in the plan, not built in B5). A candidate whose module does
  `os._exit(0)` on import makes `python -m unittest` (and pytest) exit 0 before any test runs, so every
  harness that only looks at the exit code accepts it. Built naively, C005 would fire on nearly every
  task, including all bench controls (which use exactly that kind of harness), which breaks the
  "zero false positives on controls" gate. It needs an owner decision on severity and on what counts
  as a robust harness (for example requiring a results file or a test-count line) before it is built.
- Report C004 kill ratios per task in the Markdown summary (currently only in each survivor's evidence).
- Equivalent-mutant filter: skip `<` -> `<=` mutants where both branches return the same bound (seen on
  ctrl-clamp). Needs care not to hide real weaknesses.
