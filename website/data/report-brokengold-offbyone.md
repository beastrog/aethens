## Aethens report

Tool `aethens 0.1.0.dev0` · Budget: `standard` · Seed: `0` · Checks run: C001 · Tasks: 1 · Duration: 1.4s

**1 error, 0 warning, 0 info**

| severity | check | task | title |
|---|---|---|---|
| error | C001 | brokengold-offbyone | Gold solution fails the verifier |

<details><summary><b>error</b> C001 <code>brokengold-offbyone</code>: Gold solution fails the verifier</summary>

The reference solution, overlaid onto the starter, did not pass the verifier. Either the gold solution or the tests are wrong; until this is fixed, no result from this task can be trusted.

- Observed: exit code 1: expected exit code 0
- Subject: `gold`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: One run each of the starting state and the gold solution. A flaky verifier can cause or hide this (see C002). The tool cannot tell whether the tests or the gold solution are wrong.

Reproduce:

```sh
aethens audit bench/tasks/brokengold-offbyone --check C001 --seed 0 --budget standard
```

stderr (tail):

```text
F.
======================================================================
FAIL: test_three (test_seq.TestCountUp.test_three)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_seq.py", line 8, in test_three
    self.assertEqual(count_up(3), [1, 2, 3])
AssertionError: Lists differ: [1, 2] != [1, 2, 3]

Second list contains 1 additional elements.
First extra element 2:
3

- [1, 2]
+ [1, 2, 3]
?      +++


----------------------------------------------------------------------
Ran 2 tests in 0.001s

FAILED (failures=1)
```

</details>

Info findings (C004 surviving mutants) may be semantically equivalent to the gold solution; review before acting. Findings rely on what was run; see each finding's limits.

