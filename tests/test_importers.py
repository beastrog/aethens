"""Importers: EvalPlus (MBPP+, HumanEval+), BigCodeBench, SWE-bench, Harbor scan, CLI import.

Records below are shortened copies of the real record shapes (field names and value types taken
from the public exports listed in bench/LICENSES.md); no network is used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import C001GoldSanity, CheckContext
from aethens.cli.main import main
from aethens.errors import ImporterError
from aethens.importers import TaskDraft, mbppplus_drafts, read_jsonl, write_task
from aethens.importers.bigcodebench import bigcodebench_drafts
from aethens.importers.common import EMPTY_MARKER, safe_id
from aethens.importers.evalplus import humanevalplus_drafts
from aethens.importers.harbor import scan_harbor_task
from aethens.importers.swebench import swebench_drafts
from aethens.models import Budget
from aethens.runner import DockerRunner

MBPP_TEST = """
from math import inf

def assertion(out, exp, atol):
    assert out == exp, f"out: {out}, exp: {exp}"


inputs = [[2, 3], [0, 0], [-1, 1]]
results = [5, 0, 0]
for i, (inp, exp) in enumerate(zip(inputs, results)):
    assertion(add(*inp), exp, 0)
"""

MBPP_ROW = {
    "task_id": 901,
    "code": "def add(a, b):\n    return a + b\n",
    "prompt": "Write a function to add two numbers.",
    "source_file": "x",
    "test_imports": [],
    "test_list": ["assert add(2, 3) == 5"],
    "test": MBPP_TEST,
}

HE_ROW = {
    "task_id": "HumanEval/7",
    "prompt": 'def inc(x: int) -> int:\n    """Return x + 1."""\n',
    "canonical_solution": "    return x + 1\n",
    "entry_point": "inc",
    "test": "def check(candidate):\n    assert candidate(1) == 2\n",
}

BCB_ROW = {
    "task_id": "BigCodeBench/12",
    "complete_prompt": 'def task_func(n):\n    """Double n."""\n',
    "canonical_solution": "    return 2 * n\n",
    "test": (
        "import unittest\nclass TestCases(unittest.TestCase):\n"
        "    def test_a(self):\n        self.assertEqual(task_func(2), 4)\n"
    ),
    "entry_point": "task_func",
    "libs": "[]",
}

SWE_SCRIPT = """#!/bin/bash
set -uxo pipefail
source /opt/miniconda3/bin/activate
conda activate testbed
cd /testbed
sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
python -m pip install -e .
git checkout abc123 tests/test_x.py
git apply -v - <<'EOF_1'
--- a/tests/test_x.py
+++ b/tests/test_x.py
@@ -1 +1 @@
-# /testbed stays inside the heredoc
+# /testbed stays inside the heredoc
EOF_1
: '>>>>> Start Test Output'
pytest -rA tests/test_x.py
: '>>>>> End Test Output'
git checkout abc123 tests/test_x.py
"""

SWE_ROW = {
    "instance_id": "octo__octo-42",
    "repo": "octo/octo",
    "image": "swebench/sweb.eval.x86_64.octo_1776_octo-42:latest",
    "eval_script": SWE_SCRIPT,
    "log_parser": "parse_log_pytest",
    "eval_type": "pass_and_fail",
    "patch": "diff --git a/x.py b/x.py\n",
    "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n",
    "FAIL_TO_PASS": json.dumps(["tests/test_x.py::test_new"]),
    "PASS_TO_PASS": json.dumps(["tests/test_x.py::test_old", "tests/test_x.py::test_skip"]),
    "problem_statement": "x is wrong",
}


def test_safe_id() -> None:
    assert safe_id("Mbpp/2", "mbpp-") == "mbpp-Mbpp-2"
    assert safe_id("django__django-11099", "swe-") == "swe-django__django-11099"
    with pytest.raises(ImporterError):
        safe_id("///")


def test_write_task_validates_and_refuses_overwrite(tmp_path: Path) -> None:
    draft = next(mbppplus_drafts([MBPP_ROW]))
    dest = write_task(draft, tmp_path)
    task = load_task(dest)
    assert task.id == "mbpp-901"
    assert task.verifier == ("python", "-m", "unittest", "discover", "-s", "tests")
    with pytest.raises(ImporterError, match="already exists"):
        write_task(draft, tmp_path)
    write_task(draft, tmp_path, overwrite=True)
    prov = json.loads((dest / "PROVENANCE.json").read_text())
    assert prov["upstream_id"] == "Mbpp/901" and prov["entry_point"] == "add"


def test_write_task_rejects_unsafe_paths(tmp_path: Path) -> None:
    draft = TaskDraft(
        id="bad",
        statement="s",
        starter={},
        gold={"../x.py": ""},
        tests={"t.py": ""},
        verifier=("python",),
        image="python:3.12-slim",
        timeout_s=10,
    )
    with pytest.raises(ImporterError, match="unsafe"):
        write_task(draft, tmp_path)


def test_read_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\n{"a": 2}\n')
    assert read_jsonl(p) == [{"a": 1}, {"a": 2}]
    p.write_text("[1]\n")
    with pytest.raises(ImporterError, match="object"):
        read_jsonl(p)
    with pytest.raises(ImporterError, match="no such file"):
        read_jsonl(tmp_path / "missing.jsonl")


def test_mbppplus_keeps_test_code_verbatim_and_stubs_starter(tmp_path: Path) -> None:
    dest = write_task(next(mbppplus_drafts([MBPP_ROW])), tmp_path)
    check = (dest / "tests" / "evalplus_check.py").read_text()
    assert check.endswith(MBPP_TEST)
    assert "raise NotImplementedError" in (dest / "starter" / "solution.py").read_text()
    assert "return a + b" in (dest / "gold" / "solution.py").read_text()
    assert "assert add(2, 3) == 5" in (dest / "statement.md").read_text()


def test_mbppplus_needs_one_entry_point() -> None:
    row = dict(MBPP_ROW, test="assert True\n")
    with pytest.raises(ImporterError, match="entry point"):
        list(mbppplus_drafts([row]))
    with pytest.raises(ImporterError, match="missing field"):
        list(mbppplus_drafts([{"task_id": 1}]))


def test_humanevalplus_calls_check_on_entry_point(tmp_path: Path) -> None:
    dest = write_task(next(humanevalplus_drafts([HE_ROW])), tmp_path)
    assert dest.name == "heplus-7"
    assert "ns[\"check\"](ns['inc'])" in (dest / "tests" / "test_evalplus.py").read_text()
    with pytest.raises(ImporterError, match="entry point"):
        list(humanevalplus_drafts([dict(HE_ROW, entry_point="not valid")]))


def test_bigcodebench_mirrors_module_layout(tmp_path: Path) -> None:
    dest = write_task(next(bigcodebench_drafts([BCB_ROW])), tmp_path)
    wrapper = (dest / "tests" / "test_bigcodebench.py").read_text()
    assert 'types.ModuleType("__test__")' in wrapper and 'os.environ["TZ"] = "UTC"' in wrapper
    assert (dest / "tests" / "bcb_check.py").read_text().endswith(BCB_ROW["test"])
    with pytest.raises(ImporterError, match="TestCases"):
        list(bigcodebench_drafts([dict(BCB_ROW, test="x = 1\n")]))


def test_swebench_task_layout(tmp_path: Path) -> None:
    dest = write_task(next(swebench_drafts([SWE_ROW])), tmp_path)
    task = load_task(dest)
    assert task.image == SWE_ROW["image"] and task.timeout_s == 1800
    assert (dest / "starter" / EMPTY_MARKER).exists()
    assert (dest / "gold" / "solution.patch").read_text() == SWE_ROW["patch"]
    assert (dest / "tests" / "swe_eval.sh").read_text() == SWE_SCRIPT
    spec = json.loads((dest / "tests" / "swe_spec.json").read_text())
    assert spec["FAIL_TO_PASS"] == ["tests/test_x.py::test_new"]
    assert spec["log_parser"] == "parse_log_pytest"
    for name in ("swe_harness.py", "swebench_grading.py", "swe_verify.sh"):
        assert (dest / "tests" / name).is_file()


def test_swebench_rejects_unsupported_records() -> None:
    with pytest.raises(ImporterError, match="eval_type"):
        list(swebench_drafts([dict(SWE_ROW, eval_type="fail_only")]))
    with pytest.raises(ImporterError, match="FAIL_TO_PASS"):
        list(swebench_drafts([{**SWE_ROW, "FAIL_TO_PASS": "[]"}]))
    with pytest.raises(ImporterError, match="eval_script"):
        list(swebench_drafts([{k: v for k, v in SWE_ROW.items() if k != "eval_script"}]))


def test_swe_harness_transform() -> None:
    from aethens.sandbox import swe_harness

    script, notes = swe_harness.transform(SWE_SCRIPT, "/work/.swe_testbed")
    lines = script.splitlines()
    assert "cd /work/.swe_testbed" in lines
    assert "-# /testbed stays inside the heredoc" in lines  # heredoc body untouched
    assert not any(line.startswith("python -m pip install") for line in lines)
    assert not any("locale-gen" in line and not line.startswith(":") for line in lines)
    end = lines.index(": '>>>>> End Test Output'")
    assert lines[end - 1] == "SWEBENCH_TEST_EXIT_CODE=$?"
    assert lines[end + 1] == 'echo ">>>>> Test Exit Code: $SWEBENCH_TEST_EXIT_CODE"'
    assert len(notes) == 2


def _log(body: str, code: int) -> str:
    return (
        "+ : '>>>>> Start Test Output'\n" + body + "\n+ : '>>>>> End Test Output'\n"
        f">>>>> Test Exit Code: {code}\n"
    )


def test_swe_harness_grade_follows_swebench_rules() -> None:
    from aethens.sandbox import swe_harness

    spec = json.loads(
        json.dumps(
            {
                "log_parser": "parse_log_pytest",
                "FAIL_TO_PASS": ["tests/test_x.py::test_new"],
                "PASS_TO_PASS": ["tests/test_x.py::test_old", "tests/test_x.py::test_skip"],
            }
        )
    )
    ok_log = _log(
        "PASSED tests/test_x.py::test_new\nPASSED tests/test_x.py::test_old\n"
        "SKIPPED tests/test_x.py::test_skip",
        0,
    )
    assert swe_harness.grade(ok_log, spec)[0] is True  # a skipped P2P test is maintained
    bad = _log("FAILED tests/test_x.py::test_new\nPASSED tests/test_x.py::test_old", 1)
    resolved, detail = swe_harness.grade(bad, spec)
    assert resolved is False and detail["F2P_failed"] == ["tests/test_x.py::test_new"]
    skipped_f2p = _log("SKIPPED tests/test_x.py::test_new\nPASSED tests/test_x.py::test_old", 0)
    assert swe_harness.grade(skipped_f2p, spec)[0] is False
    assert swe_harness.grade("no markers", spec)[0] is False
    lying = _log("PASSED tests/test_x.py::test_new\nPASSED tests/test_x.py::test_old", 2)
    assert "invalid" in swe_harness.grade(lying, spec)[1]


def test_harbor_scan(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "solution").mkdir()
    (tmp_path / "task.toml").write_text(
        '[task]\nname = "t/one"\n[environment]\ndocker_image = "img:1"\nallow_internet = true\n'
    )
    (tmp_path / "tests" / "test.sh").write_text("apt-get install -y curl\npytest /tests/x.py\n")
    (tmp_path / "solution" / "solve.sh").write_text("echo hi > out.txt\n")
    info = scan_harbor_task(tmp_path)
    assert info.name == "t/one" and info.docker_image == "img:1"
    assert info.tests_need_network and not info.solution_needs_network
    assert info.writes_outside_workdir and not info.runs_in_aethens_sandbox
    with pytest.raises(ImporterError, match=r"task\.toml"):
        scan_harbor_task(tmp_path / "tests")


def test_cli_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "rows.jsonl"
    src.write_text(json.dumps(MBPP_ROW) + "\n" + json.dumps(dict(MBPP_ROW, task_id=902)) + "\n")
    out = tmp_path / "out"
    assert main(["import", "mbppplus", str(src), str(out), "--only", "902"]) == 0
    assert [p.name for p in out.iterdir()] == ["mbpp-902"]
    assert main(["import", "mbppplus", str(src), str(out), "--only", "902"]) == 2
    assert "already exists" in capsys.readouterr().err
    assert main(["import", "swebench", str(src), str(out)]) == 2


@pytest.mark.docker
def test_imported_mbpp_task_runs_in_sandbox(tmp_path: Path) -> None:
    draft = next(mbppplus_drafts([MBPP_ROW], image="python:3.12-slim", timeout_s=30))
    task = load_task(write_task(draft, tmp_path))
    ctx = CheckContext(runner=DockerRunner(), seed=0, budget=Budget.SMOKE)
    assert C001GoldSanity().run(task, ctx) == []  # starter fails, gold passes
    bad = dict(MBPP_ROW, task_id=903, code="def add(a, b):\n    return a - b\n")
    task2 = load_task(write_task(next(mbppplus_drafts([bad], image="python:3.12-slim")), tmp_path))
    findings = C001GoldSanity().run(task2, ctx)
    assert [f.check_id for f in findings] == ["C001"]
