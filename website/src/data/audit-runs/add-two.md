## Aethens report

Tool `aethens 0.1.0.dev0` · Budget: `smoke` · Seed: `0` · Checks run: C001, C002, C003, C004, C005, C006, C007 · Tasks: 1 · Duration: 73.6s

**0 error, 0 warning, 1 info**

| severity | check | task | title |
|---|---|---|---|
| info | C006 | add-two | No behaviour-preserving rewrite applies; C006 checked nothing for this task |

<details><summary><b>info</b> C006 <code>add-two</code>: No behaviour-preserving rewrite applies; C006 checked nothing for this task</summary>

C006 rewrites the gold's Python files and found no site it could prove safe.

- Observed: no rewrite sites
- Subject: `gold`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: Nothing was run for C006 on this task.

Reproduce:

```sh
aethens audit examples/add-two --check C006 --seed 0 --budget smoke
```

</details>

Info findings (C004 surviving mutants) may be semantically equivalent to the gold solution; review before acting. Findings rely on what was run; see each finding's limits.

### Coverage (what was established where nothing was found)

| check | task | statement |
|---|---|---|
| C002 | add-two | Gold verdict was 'pass' in all 6 runs: flake rate below 0.5 at 95% confidence (exact bound 0.402). |

