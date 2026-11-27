## Aethens report

Tool `aethens 0.1.0.dev0` · Budget: `smoke` · Seed: `0` · Checks run: C005 · Tasks: 1 · Duration: 32.1s

**1 error, 0 warning, 0 info**

| severity | check | task | title |
|---|---|---|---|
| error | C005 | order-alphabetical | Test verdict depends on test order or isolation: test_reg.TestRegistry.test_b_lookup |

<details><summary><b>error</b> C005 <code>order-alphabetical</code>: Test verdict depends on test order or isolation: test_reg.TestRegistry.test_b_lookup</summary>

test_reg.TestRegistry.test_b_lookup gives 'pass' in the verifier's default order but a different verdict in reversed order: error; in shuffled order (driver seed 4228934073): error; alone in a fresh process: error. It passes only because of state left behind by tests that run before it in the default order (or it is broken by tests that run before it in another order). Solutions are judged by an accident of test order. Both the baseline and the changed order were run twice with the same PYTHONHASHSEED and gave the same verdicts.

- Observed: default order: pass; in reversed order: error
- Subject: `test:test_reg.TestRegistry.test_b_lookup`; confidence: `confirmed`; seed: `0`
- Command: `python .aethens/order_driver.py reverse -- discover -s tests`
- Limits: Orders tried: default, reversed, 1 seeded shuffle(s) and up to 10 tests alone (budget smoke). Dependence that only shows in an order not tried is missed, and so is a run that crashes before reporting per-test verdicts. The driver adds .aethens/ to the work directory; tests that list the work directory could notice it.

Reproduce:

```sh
aethens audit bench/tasks/order-alphabetical --check C005 --seed 0 --budget smoke
```

stderr (tail):

```text
test_b_lookup (test_reg.TestRegistry.test_b_lookup) ... ERROR
test_a_register (test_reg.TestRegistry.test_a_register) ... ok

======================================================================
ERROR: test_b_lookup (test_reg.TestRegistry.test_b_lookup)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_reg.py", line 14, in test_b_lookup
    self.assertEqual(lookup("x"), 1)
                     ^^^^^^^^^^^
  File "/work/reg.py", line 9, in lookup
    return _REGISTRY[name]
           ~~~~~~~~~^^^^^^
KeyError: 'x'

----------------------------------------------------------------------
Ran 2 tests in 0.001s

FAILED (errors=1)
```

stdout (tail):

```text

AETHENS-ORDER-RESULT {"v": 1, "mode": "reverse", "tests": ["test_reg.TestRegistry.test_a_register", "test_reg.TestRegistry.test_b_lookup"], "count": 2, "run": [[1, "E"], [0, "P"]], "fixture_errors": 0}
```

</details>

Info findings (C004 surviving mutants) may be semantically equivalent to the gold solution; review before acting. Findings rely on what was run; see each finding's limits.

