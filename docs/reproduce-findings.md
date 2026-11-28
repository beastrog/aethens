# Reproducing the findings

Two findings about other people's benchmarks are public, because the maintainer filed them on 27 Nov 2026. This page says what was probed, where the steps live, and which harness confirmed each result. It does not add a finding that is not already in those issues.

`aethens` 0.1.0 does not contain these probes. It audits `aethens-task/v1` Python tasks with checks C001–C007. Shipping the probes in the CLI, loading these benchmarks from the CLI, and RL adapters are tracked as LW-01, LW-02 and LW-03 in [ROADMAP.yaml](../ROADMAP.yaml) and are not started. The accuracy tables in the README are this repository's own bench. They are not a measurement of Terminal-Bench 2 or SWE-bench.

Nothing below was graded by Aethens' own report. Each result was confirmed by running the benchmark's harness.

## What is in this repository

There is no probe script for either finding.

`bench/tbench/` (`fetch_tb2.sh`, `convert_tb2.py`, `run_tb2.py`) converts Terminal-Bench 2 tasks into the Aethens task format so they can run under the unchanged sandbox. It does not contain the `constraints-scheduling` calendar, and converted tasks are not committed. It is not part of `make check` and it is not the v0.1.0 CLI.

SWE-bench candidate patches are not in the tree. The public issue offers the patch files and the official `report.json` privately. `audits/private/` is gitignored and is not a published source.

## Terminal-Bench 2: `constraints-scheduling`

Public report: [harbor-framework/terminal-bench-2#107](https://github.com/harbor-framework/terminal-bench-2/issues/107).

Probed at commit `2fd12b88aafdd04a52c298e3940bcb189f9766d6`. `test_structure_event_title_attendees_duration_window` finds the `VEVENT` whose `SUMMARY` is `Team Planning Meeting`. `test_constraints_conflicts_business_hours` and `test_earliest_tiebreakers_and_carol_buffer` take `DTSTART` with `re.search` over the whole file, so they check whichever event comes first.

The candidate output is an ICS file with a valid slot first (`SUMMARY:Room hold`, Wed 2024-01-17 11:00 UTC) and a Team Planning Meeting that overlaps Alice's Monday 10:00–11:00 meeting. The calendar text is in the issue.

Confirmed on 27 Nov 2026 in the unmodified image `alexgshaw/constraints-scheduling:20251031` (`sha256:567ce5a189f8d11ac461790876e934cc7af38391baf89a78f95f4dafc1fec3b0`), with that checkout's `tests/test.sh`:

```sh
docker run -d --name tbrepro --entrypoint sleep alexgshaw/constraints-scheduling:20251031 infinity
docker cp "$TB/tests" tbrepro:/tests
docker cp "$C" tbrepro:/app/meeting_scheduled.ics
docker exec tbrepro mkdir -p /logs/verifier
docker exec -w /app tbrepro bash /tests/test.sh
docker exec tbrepro cat /logs/verifier/reward.txt
docker rm -f tbrepro
```

`$TB` is the task directory at that commit. `$C` is the ICS from the issue. pytest 8.4.1 on Python 3.13.9 reported 3 passed, and `reward.txt` was `1`. The task's own gold file, and a control ICS that is the gold meeting with RFC 5545 `ATTENDEE` parameters, still score 3 passed and reward `1`. The issue also records that pointing tests 2 and 3 at the Team Planning Meeting `VEVENT` makes this decoy fail and writes reward `0`, while those two controls still pass. That check was the task's `tests/test.sh`, not an Aethens check.

## SWE-bench Verified, issue 733

Public report: [SWE-bench/SWE-bench#733](https://github.com/SWE-bench/SWE-bench/issues/733).

This is a sample, not a pass over every Verified instance. No precision or recall for that sample is stated here. Environment: swebench 5.0.2, dataset `SWE-bench/SWE-bench_Verified` at `78f471bf655a3137b2e8a75af1501690ec009ec3`, prebuilt `sweb.eval` images, Linux x86_64, Docker, Python 3.12.16. Candidate patches were produced while auditing with Aethens at `d6817cd`. Every grade below is from `swebench.harness.run_evaluation`, after a hand comparison with the instance `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, and gold patch.

Three groups, all graded `resolved=True` for a wrong or incomplete patch:

1. **Sympy log parsing.** `parse_log_sympy` keys results by the bare test name (related to SWE-bench #706; the parser on `main` at `02e7a74` matches 5.0.2). On `sympy__sympy-14248`, a gold patch with the `PrettyPrinter._print_MatAdd` condition inverted, and a gold patch missing the `StrPrinter._print_MatAdd` hunk, are both graded resolved. The runner can exit 1 and log `test_MatrixSymbol_printing F [FAIL]` while the parsed bare `FAIL_TO_PASS` name stays `PASSED`.
2. **`conftest.py` hook.** A patch that only adds a root `conftest.py` whose `pytest_runtest_makereport` hook marks every report passed is graded resolved, with `Test Exit Code: 0`. The exit-code cross-check from SWE-bench #631 does not fire, because pytest itself exits 0. Seen on `pytest-dev__pytest-10051`, `sphinx-doc__sphinx-9711`, `scikit-learn__scikit-learn-14053`, `pydata__xarray-4966`, and earlier on `matplotlib__matplotlib-23299`, `scikit-learn__scikit-learn-13142`, `astropy__astropy-7606`. C007 in v0.1.0 does not probe pytest `conftest.py` hooks.
3. **`FAIL_TO_PASS` gaps.** An intentionally incomplete or incorrect patch was graded resolved on `sphinx-doc__sphinx-8035`, `astropy__astropy-8707`, `django__django-12754`, `sphinx-doc__sphinx-10673`, `django__django-16631`, `django__django-16032`, `sphinx-doc__sphinx-9711`, and `pydata__xarray-4966`. The issue states, per instance, which behaviour the listed tests do not cover. `django__django-16631` is described there as a gap in the instance tests, not a new Django vulnerability.

Confirmation command, from the issue (one instance, the candidate patch in `pred.jsonl`):

```sh
python -m swebench.harness.run_evaluation \
  -d sample-dataset.json -s test \
  -i <instance_id> -p pred.jsonl --max_workers 1 -id repro
```

The dataset JSON, the prediction file, and the official `report.json` are not in this repository.

## What this page does not say

A clean `aethens` report does not mean a verifier is sound. These two write-ups do not mean either benchmark has no other defects, and they do not mean v0.1.0 would have printed these findings. The marketing site's Findings section should link here once that section exists.
