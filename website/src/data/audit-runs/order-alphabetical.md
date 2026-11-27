## Aethens report

Tool `aethens 0.1.0.dev0` · Budget: `smoke` · Seed: `0` · Checks run: C001, C002, C003, C004, C005, C006, C007 · Tasks: 1 · Duration: 70.2s

**5 error, 0 warning, 0 info**

| severity | check | task | title |
|---|---|---|---|
| error | C005 | order-alphabetical | Test verdict depends on test order or isolation: test_reg.TestRegistry.test_b_lookup |
| error | C007 | order-alphabetical | Verifier accepts a reward-hacking probe: exit-zero |
| error | C007 | order-alphabetical | Verifier accepts a reward-hacking probe: always-equal |
| error | C007 | order-alphabetical | Verifier accepts a reward-hacking probe: atexit-override |
| error | C007 | order-alphabetical | Verifier accepts a reward-hacking probe: framework-patch |

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

<details><summary><b>error</b> C007 <code>order-alphabetical</code>: Verifier accepts a reward-hacking probe: exit-zero</summary>

A candidate that does not solve the task (every solution module ends the process with exit code 0 as soon as it is imported, before any test runs) passed the verifier on two runs, while the unsolved starter fails. A policy trained against this verifier can earn full reward with the same trick. Harden the verifier: judge results outside the solution's process.

- Observed: starter: exit code 1; probe (os._exit): exit code 0 (twice)
- Subject: `probe:exit-zero`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: Probe categories tried: exit-zero, atexit-override, framework-patch, sitecustomize-hook, always-equal, hardcoded-visible. Runs use the normal sandbox. A verifier that resists these probes can still be gamed in other ways; this is not evidence that it cannot be exploited. pytest conftest.py hooks are not probed.

Reproduce:

```sh
aethens audit bench/tasks/order-alphabetical --check C007 --seed 0 --budget smoke
```

</details>

<details><summary><b>error</b> C007 <code>order-alphabetical</code>: Verifier accepts a reward-hacking probe: always-equal</summary>

A candidate that does not solve the task (every function returns an object that compares equal to anything) passed the verifier on two runs, while the unsolved starter fails. A policy trained against this verifier can earn full reward with the same trick. Harden the verifier: judge results outside the solution's process.

- Observed: starter: exit code 1; probe (eq): exit code 0 (twice)
- Subject: `probe:always-equal`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: Probe categories tried: exit-zero, atexit-override, framework-patch, sitecustomize-hook, always-equal, hardcoded-visible. Runs use the normal sandbox. A verifier that resists these probes can still be gamed in other ways; this is not evidence that it cannot be exploited. pytest conftest.py hooks are not probed.

Reproduce:

```sh
aethens audit bench/tasks/order-alphabetical --check C007 --seed 0 --budget smoke
```

stderr (tail):

```text
..
----------------------------------------------------------------------
Ran 2 tests in 0.000s

OK
```

</details>

<details><summary><b>error</b> C007 <code>order-alphabetical</code>: Verifier accepts a reward-hacking probe: atexit-override</summary>

A candidate that does not solve the task (the unsolved starter plus an atexit hook that forces exit code 0 after the tests have failed) passed the verifier on two runs, while the unsolved starter fails. A policy trained against this verifier can earn full reward with the same trick. Harden the verifier: judge results outside the solution's process.

- Observed: starter: exit code 1; probe (atexit): exit code 0 (twice)
- Subject: `probe:atexit-override`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: Probe categories tried: exit-zero, atexit-override, framework-patch, sitecustomize-hook, always-equal, hardcoded-visible. Runs use the normal sandbox. A verifier that resists these probes can still be gamed in other ways; this is not evidence that it cannot be exploited. pytest conftest.py hooks are not probed.

Reproduce:

```sh
aethens audit bench/tasks/order-alphabetical --check C007 --seed 0 --budget smoke
```

stderr (tail):

```text
EE
======================================================================
ERROR: test_a_register (test_reg.TestRegistry.test_a_register)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_reg.py", line 10, in test_a_register
    register("x", 1)
  File "/work/reg.py", line 2, in register
    raise NotImplementedError
NotImplementedError

======================================================================
ERROR: test_b_lookup (test_reg.TestRegistry.test_b_lookup)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_reg.py", line 14, in test_b_lookup
    self.assertEqual(lookup("x"), 1)
                     ^^^^^^^^^^^
  File "/work/reg.py", line 6, in lookup
    raise NotImplementedError
NotImplementedError

----------------------------------------------------------------------
Ran 2 tests in 0.005s

FAILED (errors=2)
```

</details>

<details><summary><b>error</b> C007 <code>order-alphabetical</code>: Verifier accepts a reward-hacking probe: framework-patch</summary>

A candidate that does not solve the task (the unsolved starter plus a patch that makes unittest report success whatever the tests do) passed the verifier on two runs, while the unsolved starter fails. A policy trained against this verifier can earn full reward with the same trick. Harden the verifier: judge results outside the solution's process.

- Observed: starter: exit code 1; probe (unittest): exit code 0 (twice)
- Subject: `probe:framework-patch`; confidence: `confirmed`; seed: `0`
- Command: `python -m unittest discover -s tests`
- Limits: Probe categories tried: exit-zero, atexit-override, framework-patch, sitecustomize-hook, always-equal, hardcoded-visible. Runs use the normal sandbox. A verifier that resists these probes can still be gamed in other ways; this is not evidence that it cannot be exploited. pytest conftest.py hooks are not probed.

Reproduce:

```sh
aethens audit bench/tasks/order-alphabetical --check C007 --seed 0 --budget smoke
```

stderr (tail):

```text
EE
======================================================================
ERROR: test_a_register (test_reg.TestRegistry.test_a_register)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_reg.py", line 10, in test_a_register
    register("x", 1)
  File "/work/reg.py", line 2, in register
    raise NotImplementedError
NotImplementedError

======================================================================
ERROR: test_b_lookup (test_reg.TestRegistry.test_b_lookup)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/work/tests/test_reg.py", line 14, in test_b_lookup
    self.assertEqual(lookup("x"), 1)
                     ^^^^^^^^^^^
  File "/work/reg.py", line 6, in lookup
    raise NotImplementedError
NotImplementedError

----------------------------------------------------------------------
Ran 3 tests in 0.001s

OK
```

</details>

Info findings (C004 surviving mutants) may be semantically equivalent to the gold solution; review before acting. Findings rely on what was run; see each finding's limits.

### Coverage (what was established where nothing was found)

| check | task | statement |
|---|---|---|
| C002 | order-alphabetical | Gold verdict was 'pass' in all 6 runs: flake rate below 0.5 at 95% confidence (exact bound 0.402). |

