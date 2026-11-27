# ruff: noqa
# mypy: ignore-errors
"""SWE-bench log parsers and grading rules, vendored from swebench 5.0.2 (PyPI) for use INSIDE the
sandbox by aethens.sandbox.swe_harness. Only the import lines were changed (TestStatus and the
markers are defined here); the parser and grading functions are verbatim copies of
swebench/harness/log_parsers/python.py and swebench/harness/grading.py.

MIT License

Copyright (c) 2023 Carlos E Jimenez, John Yang, Alexander Wettig, Shunyu Yao, Kexin Pei, Ofir Press, Karthik R Narasimhan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

TestSpec = Any  # type-only in the parsers


class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    XFAIL = "XFAIL"


APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
RESET_FAILED = ">>>>> Reset Failed"
TESTS_ERROR = ">>>>> Tests Errored"
TESTS_TIMEOUT = ">>>>> Tests Timed Out"
START_TEST_OUTPUT = ">>>>> Start Test Output"
END_TEST_OUTPUT = ">>>>> End Test Output"
TEST_EXIT_CODE = ">>>>> Test Exit Code"
TEST_EXIT_CODE_VAR = "SWEBENCH_TEST_EXIT_CODE"

# ---- swebench/harness/log_parsers/python.py (verbatim below this line) ----
import re


_SKIP_SUMMARY_COUNT = re.compile(r"^\[\d+\]$")


def _is_skip_summary(status: str, name: str) -> bool:
    """True for pytest's ``SKIPPED [N] path:line: reason`` summary, where [N] is not a test.

    Deliberately scoped to SKIPPED. Wrapped progress lines produce a similar
    ``PASSED [100%]`` artifact, but PASS_TO_PASS for pytest-dev__pytest-5262 and
    -7521 literally expects ``[100%]``, so dropping it fails those instances.
    TODO(john-b-yang): repair those two P2P lists, then widen this to any
    bare bracketed count.
    """
    return status == TestStatus.SKIPPED.value and bool(_SKIP_SUMMARY_COUNT.match(name))


def parse_log_pytest(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    for line in log.split("\n"):
        if any([line.startswith(x.value) for x in TestStatus]):
            # Additional parsing for FAILED status
            if line.startswith(TestStatus.FAILED.value):
                line = line.replace(" - ", " ")
            test_case = line.split()
            if len(test_case) <= 1:
                continue
            if _is_skip_summary(test_case[0], test_case[1]):
                continue
            test_status_map[test_case[1]] = test_case[0]
    return test_status_map


def parse_log_pytest_options(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework with options

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    option_pattern = re.compile(r"(.*?)\[(.*)\]")
    test_status_map = {}
    for line in log.split("\n"):
        if any([line.startswith(x.value) for x in TestStatus]):
            # Additional parsing for FAILED status
            if line.startswith(TestStatus.FAILED.value):
                line = line.replace(" - ", " ")
            test_case = line.split()
            if len(test_case) <= 1:
                continue
            if _is_skip_summary(test_case[0], test_case[1]):
                continue
            has_option = option_pattern.search(test_case[1])
            if has_option:
                main, option = has_option.groups()
                if option.startswith("/") and not option.startswith("//") and "*" not in option:
                    option = "/" + option.split("/")[-1]
                test_name = f"{main}[{option}]"
            else:
                test_name = test_case[1]
            test_status_map[test_name] = test_case[0]
    return test_status_map


def parse_log_django(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with Django tester framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    lines = log.split("\n")

    prev_test = None
    for line in lines:
        line = line.strip()

        # This isn't ideal but the test output spans multiple lines
        if "--version is equivalent to version" in line:
            test_status_map["--version is equivalent to version"] = TestStatus.PASSED.value

        # Log it in case of error
        if " ... " in line:
            prev_test = line.split(" ... ")[0]

        pass_suffixes = (" ... ok", " ... OK", " ...  OK")
        for suffix in pass_suffixes:
            if line.endswith(suffix):
                # TODO: Temporary, exclusive fix for django__django-7188
                # The proper fix should involve somehow getting the test results to
                # print on a separate line, rather than the same line
                if line.strip().startswith(
                    "Applying sites.0002_alter_domain_unique...test_no_migrations"
                ):
                    line = line.split("...", 1)[-1].strip()
                test = line.rsplit(suffix, 1)[0]
                test_status_map[test] = TestStatus.PASSED.value
                break
        if " ... skipped" in line:
            test = line.split(" ... skipped")[0]
            test_status_map[test] = TestStatus.SKIPPED.value
        if line.endswith(" ... FAIL"):
            test = line.split(" ... FAIL")[0]
            test_status_map[test] = TestStatus.FAILED.value
        if line.startswith("FAIL:"):
            test = line.split()[1].strip()
            test_status_map[test] = TestStatus.FAILED.value
        if line.endswith(" ... ERROR"):
            test = line.split(" ... ERROR")[0]
            test_status_map[test] = TestStatus.ERROR.value
        if line.startswith("ERROR:"):
            test = line.split()[1].strip()
            test_status_map[test] = TestStatus.ERROR.value

        if line.lstrip().startswith("ok") and prev_test is not None:
            # It means the test passed, but there's some additional output (including new lines)
            # between "..." and "ok" message
            test = prev_test
            test_status_map[test] = TestStatus.PASSED.value

    # TODO: This is very brittle, we should do better
    # There's a bug in the django logger, such that sometimes a test output near the end gets
    # interrupted by a particular long multiline print statement.
    # We have observed this in one of 3 forms:
    # - "{test_name} ... Testing against Django installed in {*} silenced.\nok"
    # - "{test_name} ... Internal Server Error: \/(.*)\/\nok"
    # - "{test_name} ... System check identified no issues (0 silenced).\nok"
    patterns = [
        r"^(.*?)\s\.\.\.\sTesting\ against\ Django\ installed\ in\ ((?s:.*?))\ silenced\)\.\nok$",
        r"^(.*?)\s\.\.\.\sInternal\ Server\ Error:\ \/(.*)\/\nok$",
        r"^(.*?)\s\.\.\.\sSystem check identified no issues \(0 silenced\)\nok$",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, log, re.MULTILINE):
            test_name = match.group(1)
            test_status_map[test_name] = TestStatus.PASSED.value
    return test_status_map


def parse_log_pytest_v2(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework (Later Version)

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    escapes = "".join([chr(char) for char in range(1, 32)])
    for line in log.split("\n"):
        line = re.sub(r"\[(\d+)m", "", line)
        translator = str.maketrans("", "", escapes)
        line = line.translate(translator)
        if any([line.startswith(x.value) for x in TestStatus]):
            if line.startswith(TestStatus.FAILED.value):
                # drop the trailing " - <assertion message>" so it can't enter the id
                line = line.split(" - ", 1)[0]
            test_case = line.split()
            if len(test_case) >= 2 and not _is_skip_summary(test_case[0], test_case[1]):
                test_status_map[" ".join(test_case[1:])] = test_case[0]
        # Support older pytest versions by checking if the line ends with the test status
        elif any([line.endswith(x.value) for x in TestStatus]):
            test_case = line.split()
            if len(test_case) >= 2:
                test_status_map[" ".join(test_case[:-1])] = test_case[-1]
    return test_status_map


def parse_log_seaborn(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with seaborn testing framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    for line in log.split("\n"):
        parts = line.split()
        if len(parts) < 2:
            continue
        if line.startswith(TestStatus.FAILED.value):
            test_case = parts[1]
            test_status_map[test_case] = TestStatus.FAILED.value
        elif f" {TestStatus.PASSED.value} " in line:
            if parts[1] == TestStatus.PASSED.value:
                test_case = parts[0]
                test_status_map[test_case] = TestStatus.PASSED.value
        elif line.startswith(TestStatus.PASSED.value):
            test_case = parts[1]
            test_status_map[test_case] = TestStatus.PASSED.value
    return test_status_map


def parse_log_sympy(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with Sympy framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    pattern = r"(_*) (.*)\.py:(.*) (_*)"
    matches = re.findall(pattern, log)
    for match in matches:
        test_case = f"{match[1]}.py:{match[2]}"
        test_status_map[test_case] = TestStatus.FAILED.value
    for line in log.split("\n"):
        line = line.strip()
        if line.startswith("test_"):
            if line.endswith(" E"):
                test = line.split()[0]
                test_status_map[test] = TestStatus.ERROR.value
            if line.endswith(" F"):
                test = line.split()[0]
                test_status_map[test] = TestStatus.FAILED.value
            if line.endswith(" ok"):
                test = line.split()[0]
                test_status_map[test] = TestStatus.PASSED.value
    return test_status_map


def parse_log_matplotlib(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    for line in log.split("\n"):
        line = line.replace("MouseButton.LEFT", "1")
        line = line.replace("MouseButton.RIGHT", "3")
        if any([line.startswith(x.value) for x in TestStatus]):
            # Additional parsing for FAILED status
            if line.startswith(TestStatus.FAILED.value):
                line = line.replace(" - ", " ")
            test_case = line.split()
            if len(test_case) <= 1:
                continue
            if _is_skip_summary(test_case[0], test_case[1]):
                continue
            test_status_map[test_case[1]] = test_case[0]
    return test_status_map


parse_log_astroid = parse_log_pytest
parse_log_flask = parse_log_pytest
parse_log_marshmallow = parse_log_pytest
parse_log_pvlib = parse_log_pytest
parse_log_pyvista = parse_log_pytest
parse_log_sqlfluff = parse_log_pytest
parse_log_xarray = parse_log_pytest

parse_log_pydicom = parse_log_pytest_options
parse_log_requests = parse_log_pytest_options
parse_log_pylint = parse_log_pytest_options

parse_log_astropy = parse_log_pytest_v2
parse_log_scikit = parse_log_pytest_v2
parse_log_sphinx = parse_log_pytest_v2


MAP_REPO_TO_PARSER_PY = {
    "astropy/astropy": parse_log_astropy,
    "django/django": parse_log_django,
    "marshmallow-code/marshmallow": parse_log_marshmallow,
    "matplotlib/matplotlib": parse_log_matplotlib,
    "mwaskom/seaborn": parse_log_seaborn,
    "pallets/flask": parse_log_flask,
    "psf/requests": parse_log_requests,
    "pvlib/pvlib-python": parse_log_pvlib,
    "pydata/xarray": parse_log_xarray,
    "pydicom/pydicom": parse_log_pydicom,
    "pylint-dev/astroid": parse_log_astroid,
    "pylint-dev/pylint": parse_log_pylint,
    "pytest-dev/pytest": parse_log_pytest,
    "pyvista/pyvista": parse_log_pyvista,
    "scikit-learn/scikit-learn": parse_log_scikit,
    "sqlfluff/sqlfluff": parse_log_sqlfluff,
    "sphinx-doc/sphinx": parse_log_sphinx,
    "sympy/sympy": parse_log_sympy,
}

PARSER_REGISTRY = {name: fn for name, fn in globals().items() if name.startswith("parse_log_")}

# ---- swebench/harness/grading.py (selected functions, verbatim) ----
SUITE_RAN = re.compile(
    r"Executed [1-9]\d* of \d+"
    r"|TOTAL: [1-9]\d* (?:SUCCESS|FAILED)"
    r"|[1-9]\d* passing"
    r"|Tests:\s+[1-9]\d*"
    r"|Test Suites:\s+(?:\d+ \w+, )*[1-9]\d* total"
    r"|^# tests [1-9]\d*"
    # jasmine (marked) prints only this line on a clean run; its parser records
    # failures only, so without it an all-passing suite looks like it never ran
    r"|[1-9]\d* specs?, \d+ failures?"
    # openlayers' rendering harness logs "<case>': ok" per passing case at
    # --log-level info; it records no failures otherwise, so this is the only
    # positive evidence a silent (all-passing) run actually executed
    r"|': ok$",
    re.M,
)

TEST_EXIT_CODE_RE = re.compile(rf"{re.escape(TEST_EXIT_CODE)}:\s*(-?\d+)")


def parse_test_exit_code(content: str) -> int | None:
    """Return the recorded test command exit status, or None if absent."""
    match = TEST_EXIT_CODE_RE.search(content)
    return int(match.group(1)) if match else None


def _resolve_case(case: str, sm: dict[str, str]) -> str | None:
    """Return the status-map key for ``case``, tolerating truncated parametrized ids.

    676 expected ids in SWE-bench_Verified are truncated mid-parameter (issue #290),
    e.g. ``test_ogip_grammar_fail[log(photon``. For those only, prefix-match when the
    candidates agree on pass-vs-fail; exact ids keep exact-match semantics. Requires
    ``[`` to outnumber ``]`` so free-form non-pytest names never reach the fallback.

    TODO(john-b-yang): wrong placement — a pytest/Verified-specific data defect
    encoded in grading, which is meant to be benchmark-agnostic.
    TODO(john-b-yang): relocate by repairing the 676 truncated ids in a Verified
    revision (47 are ambiguous, needing manual resolution), then delete this.
    """
    if case in sm:
        return case
    if case.count("[") > case.count("]"):
        matches = [k for k in sm if k.startswith(case)]
        # PASSED and XFAIL grade identically, so compare outcome not raw status
        passing = {TestStatus.PASSED.value, TestStatus.XFAIL.value}
        if matches and len({sm[k] in passing for k in matches}) == 1:
            return matches[0]
    return None


def test_passed(case: str, sm: dict[str, str]) -> bool:
    key = _resolve_case(case, sm)
    return key is not None and sm[key] in [
        TestStatus.PASSED.value,
        TestStatus.XFAIL.value,
    ]


def test_maintained(case: str, sm: dict[str, str]) -> bool:
    """P2P semantics: a skipped test is not a regression, unlike for F2P."""
    key = _resolve_case(case, sm)
    return test_passed(case, sm) or (key is not None and sm[key] == TestStatus.SKIPPED.value)


def test_failed(case: str, sm: dict[str, str]) -> bool:
    key = _resolve_case(case, sm)
    return key is None or sm[key] in [
        TestStatus.FAILED.value,
        TestStatus.ERROR.value,
        # a skipped F2P test is not a resolution; without this, a patch that makes
        # every F2P test skip lands in neither list and scores RESOLVED_FULL
        TestStatus.SKIPPED.value,
    ]
