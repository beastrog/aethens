# Real-world results: Aethens on public benchmarks

This page reports how Aethens behaves on public benchmarks it did not write: what was run, how
long it took, and how accurate each check was after **every finding was checked by hand**. It is
about Aethens' accuracy, not a list of other people's bugs.

**Disclosure.** Per [DISCLOSURE.md](DISCLOSURE.md), findings about third-party benchmarks stay in
the gitignored `audits/private/` directory until the maintainers have been told and the waiting
period has passed. This page therefore gives per-check tallies and finding *classes*, never task
ids or new defects. Nothing has been sent to anyone yet; drafts await the owner.

## What was run (27 Nov 2026)

| benchmark (export) | licence | tasks | checks | wall time | tool errors |
|---|---|---|---|---|---|
| MBPP+ (HF `evalplus/mbppplus`) | Apache-2.0 (MBPP: CC-BY-4.0) | 378 | C001 C002 C004 C006 | 1144.8 s (6 workers) | 0 |
| HumanEval+ (HF `evalplus/humanevalplus`) | Apache-2.0 (HumanEval: MIT) | 164 | C001 C002 C004 C006 | 704.9 s (5 workers) | 0 |

Seed 0, budget `standard`, default sandbox (no network, read-only rootfs, non-root, 1 GiB, 1 CPU,
256 pids). One host (8 vCPUs), shared with other Aethens jobs during the runs, so times are upper
bounds. Per task: median 14.0 s (MBPP+) and 14.4 s (HumanEval+); slowest 341.6 s and 213.7 s.
BigCodeBench and SWE-bench Verified import and run (see [importers.md](importers.md)); full audits
of those are not done yet. Terminal-Bench 2: 0 of 89 tasks can run in the current sandbox (D-084).

## Accuracy, every finding checked by hand

Verdict scale: **TP** = a valid input (allowed by the statement and inside the task's own test
domain) on which the accepted candidate is wrong, reproduced in the sandbox; **FP-equivalent** =
the mutant behaves like the gold on every valid input; **FP-out-of-domain** = it differs only on
inputs the statement excludes; **uncertain** = the statement or the gold is ambiguous there.

| check | benchmark | findings | TP | FP | uncertain | notes |
|---|---|---|---|---|---|---|
| C001 gold sanity | MBPP+ | 1 | 0 | 1 | 0 | FP from Aethens' 1 GiB limit: the gold passes with 4 GiB |
| C001 gold sanity | HumanEval+ | 1 | 1 | 0 | 0 | matches a defect already reported publicly by others |
| C002 flakiness | both | 0 | - | - | - | 542 golds, each 11/11 passes: flake rate < 0.25 at 95% |
| C006 over-specification | both | 0 | - | - | - | |
| C004 surviving mutants, no filter | MBPP+ | 74 | 16 | 52 (41 equiv., 11 out-of-domain) | 6 | precision 23.5% of decided |
| C004 with D-065 filter | MBPP+ | 14 | 5 | 4 | 5 | 55.6%; keeps 5 of the 16 TPs |
| C004 with D-065 + D-087 (PR #22, awaiting owner approval) | MBPP+ | 17 | 8 | 4 | 5 | 66.7%; keeps 8 of the 16 TPs |
| C004 with D-065 filter | HumanEval+ | 5 | 2 | 3 (out-of-domain) | 0 | 30 more survivors filtered |

Every TP was reproduced in the sandbox with `bench/real/reproduce_verdicts.py`: the task's full
verifier accepts the mutant, and gold and mutant return different results on the stated input.

Classes of confirmed weaknesses (no task ids until disclosure):
- a generated test helper that computes a comparison but never asserts it, so any output passes;
- missing edge inputs: one-element and two-element lists, a single small number, negative inputs
  that the task's own inputs already include elsewhere, values in (0, 1) for float lists;
- a reference test that rejects every solution, the reference included.

## What this taught us about Aethens

1. **C004's equivalent-mutant filter trades recall for precision, and real data shows how much.**
   On MBPP+ the D-065 filter cut reported survivors from 74 to 14 and raised precision from 23.5%
   to 55.6%, but hid 11 of 16 confirmed TPs. Most hidden TPs differ from the gold on a single
   specific input that the input derivation does not produce.
2. **A real bug in the filter (fix proposed as D-087, PR #22).** Golds that return objects without value equality
   (`re.Match`) looked nondeterministic to the probe, so it kept only the inputs where they returned
   None and declared "return None" mutants equivalent. Comparing such objects by `repr`, and making
   the verdict inconclusive when the gold disagrees with itself, recovers 3 TPs and adds no FP.
3. **Out-of-domain counterexamples are the main remaining FP class** (duplicates in a
   duplicate-free array, a prime where the statement excludes primes). The probe has no spec;
   precondition inference is in IDEAS.
4. **C001 needs to say when the cause may be a resource limit.** The MBPP+ C001 finding was an
   out-of-memory kill at 1 GiB; the wording "gold or tests are wrong" overstates it. Proposed
   change (needs owner approval): name the limit when the gold was OOM-killed or timed out.
5. **Fidelity caveat.** Aethens runs the HF exports' test code verbatim. The official EvalPlus
   harness uses its own oracle, so a defect in an export does not always affect EvalPlus scores
   (and vice versa). Every finding records which harness it applies to.

## Reproduce

```bash
uv run --no-project --with pyarrow python bench/real/fetch_real.py mbppplus   # pinned sha256
uv run python bench/external/fetch.py        # HumanEval+ (HF revision d32357cf, pinned sha256)
docker build -t aethens-evalplus:py3.12 bench/real/images/evalplus
uv run aethens import mbppplus bench/real/data/mbppplus.jsonl bench/real/tasks/mbppplus
uv run aethens import humanevalplus bench/external/data/HumanEvalPlus.jsonl bench/real/tasks/heplus
uv run python bench/real/run_real.py bench/real/tasks/mbppplus OUT \
    --check C001 --check C002 --check C004 --check C006 --workers 6 --seed 0 --budget standard
uv run python bench/real/reproduce_verdicts.py OUT bench/real/tasks/mbppplus VERDICTS.json
```

The manual verdict files (`verdicts.json`, one entry and reason per finding) are in
`audits/private/` and will be published with the findings after disclosure.
