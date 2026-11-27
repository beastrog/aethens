"""SWE-bench verifier harness, copied into an imported task's tests/ and run INSIDE the sandbox.

Usage (the task's verifier): bash tests/swe_verify.sh  ->  python tests/swe_harness.py

It reproduces the official SWE-bench evaluation (swebench 5.0.2, run_evaluation.py and the
instance's eval_script) under Aethens' sandbox, which is read-only, non-root and offline:

1. copy the image's /testbed (including .git) into the disposable work directory, because the
   root filesystem is read-only;
2. if the work directory holds ``solution.patch`` (the gold overlay or a candidate), apply it with
   the same fallbacks as the official harness (git apply, --3way, --reject, patch --fuzz=5);
3. run the instance's official eval script with three mechanical changes, each printed in the log:
   ``/testbed`` -> the copy, ``pip install -e .`` lines -> skipped (site-packages is read-only; the
   copy is put first on PYTHONPATH instead, using the editable-install paths found in the env),
   and the ``locale-gen`` line -> skipped (needs root; the images already ship en_US.UTF-8);
   the test command's exit code is recorded after the end marker, as swebench 5.0.2 does;
4. grade the log with swebench's own parser and rules (vendored in swebench_grading.py):
   resolved means every FAIL_TO_PASS test passes and every PASS_TO_PASS test is maintained.

Exit code 0 = resolved, 1 = not resolved (the summary on stderr names the failing tests).
"""

from __future__ import annotations

import glob
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

g: Any = importlib.import_module("swebench_grading")  # vendored next to this file

TESTBED = "/testbed"
APPLY_CMDS = (
    ["git", "apply", "--verbose"],
    ["git", "apply", "--verbose", "--3way"],
    ["git", "apply", "--verbose", "--reject"],
    ["patch", "--batch", "--forward", "--fuzz=5", "-p1", "-i"],
)
_HEREDOC = re.compile(r"<<-?\s*'?\"?(\w+)'?\"?")


def editable_paths(copy: str) -> list[str]:
    """Paths under /testbed that the env's editable installs point at, mapped to the copy."""
    found: list[str] = []
    patterns = ("*.egg-link", "*.pth", "__editable__*finder.py")
    for sp in glob.glob("/opt/miniconda3/envs/testbed/lib/python*/site-packages"):
        for pat in patterns:
            for f in glob.glob(os.path.join(sp, pat)):
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                for m in re.findall(r"/testbed[^\s'\"]*", text):
                    p = m.rstrip("/")
                    if f.endswith("finder.py"):
                        p = os.path.dirname(p)
                    if p not in found:
                        found.append(p)
    out = [copy + p[len(TESTBED) :] for p in found if p == TESTBED or p.startswith(TESTBED + "/")]
    if copy not in out:
        out.append(copy)
    return out


def transform(script: str, copy: str) -> tuple[str, list[str]]:
    """The official eval script adapted to the sandbox. Returns (script, notes)."""
    notes: list[str] = []
    out: list[str] = []
    end_word = None
    for line in script.splitlines():
        if end_word is not None:
            out.append(line)
            if line.strip() == end_word:
                end_word = None
            continue
        m = _HEREDOC.search(line)
        stripped = line.strip()
        if re.match(r"^(python -m )?pip install (-e|--editable) \.?", stripped):
            notes.append("skipped editable reinstall: " + stripped)
            out.append(
                ": 'aethens: skipped (read-only sandbox): {}'".format(stripped.replace("'", ""))
            )
            continue
        if "locale-gen" in stripped:
            notes.append("skipped locale generation: " + stripped)
            out.append(": 'aethens: skipped locale-gen (needs root)'")
            continue
        new = line.replace(TESTBED, copy)
        if g.END_TEST_OUTPUT in new:
            out.append(f"{g.TEST_EXIT_CODE_VAR}=$?")
            out.append(new)
            out.append(f'echo "{g.TEST_EXIT_CODE}: ${g.TEST_EXIT_CODE_VAR}"')
        else:
            out.append(new)
        if m:
            end_word = m.group(1)
    return "\n".join(out) + "\n", notes


def apply_patch(copy: str, patch: str) -> tuple[bool, str]:
    log = []
    for cmd in APPLY_CMDS:
        r = subprocess.run(
            [*cmd, patch], cwd=copy, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )
        log.append("$ {}\n{}".format(" ".join(cmd), r.stdout.decode("utf-8", "replace")))
        if r.returncode == 0:
            return True, "\n".join(log)
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=copy,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return False, "\n".join(log)


def grade(content: str, spec: dict[str, Any]) -> tuple[bool, dict[str, object]]:
    """swebench 5.0.2 get_logs_eval + get_eval_tests_report + get_resolution_status (FULL only)."""
    parser = g.PARSER_REGISTRY[str(spec["log_parser"])]
    bad = [
        c
        for c in (g.APPLY_PATCH_FAIL, g.RESET_FAILED, g.TESTS_ERROR, g.TESTS_TIMEOUT)
        if c in content
    ]
    if bad:
        return False, {"invalid": f"log contains {bad}"}
    if not (g.START_TEST_OUTPUT in content and g.END_TEST_OUTPUT in content):
        return False, {"invalid": "test output markers missing"}
    sliced = content.split(g.START_TEST_OUTPUT)[1].split(g.END_TEST_OUTPUT)[0]
    sm = parser(sliced, None)
    if not sm:
        sm = parser(content, None)
    if not sm and not g.SUITE_RAN.search(content):
        return False, {"invalid": "no parsed results and no sign the suite ran"}
    code = g.parse_test_exit_code(content)
    if (
        code not in (None, 0)
        and sm
        and not any(s in (g.TestStatus.FAILED.value, g.TestStatus.ERROR.value) for s in sm.values())
    ):
        return False, {"invalid": f"test command exited {code} but the log shows no failure"}
    f2p_fail = [
        t for t in spec["FAIL_TO_PASS"] if not g.test_passed(t, sm) and g.test_failed(t, sm)
    ]
    f2p_ok = [t for t in spec["FAIL_TO_PASS"] if g.test_passed(t, sm)]
    p2p_fail = [
        t for t in spec["PASS_TO_PASS"] if not g.test_maintained(t, sm) and g.test_failed(t, sm)
    ]
    p2p_ok = [t for t in spec["PASS_TO_PASS"] if g.test_maintained(t, sm)]
    f2p_rate = 1.0 if not (f2p_ok or f2p_fail) else len(f2p_ok) / (len(f2p_ok) + len(f2p_fail))
    p2p_rate = 1.0 if not (p2p_ok or p2p_fail) else len(p2p_ok) / (len(p2p_ok) + len(p2p_fail))
    detail: dict[str, object] = {
        "F2P_failed": f2p_fail,
        "P2P_failed": p2p_fail,
        "F2P_passed": len(f2p_ok),
        "P2P_passed": len(p2p_ok),
        "test_exit_code": code,
        "parsed_tests": len(sm),
    }
    return f2p_rate == 1 and p2p_rate == 1, detail


def main() -> int:
    work = os.getcwd()
    with open(os.path.join(HERE, "swe_spec.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    copy = os.path.join(work, ".swe_testbed")
    shutil.copytree(TESTBED, copy, symlinks=True)
    patch = os.path.join(work, "solution.patch")
    if os.path.exists(patch) and os.path.getsize(patch) > 0:
        ok, log = apply_patch(copy, patch)
        sys.stdout.write(log + "\n")
        if not ok:
            sys.stderr.write(f"aethens-swe: {g.APPLY_PATCH_FAIL}: solution.patch did not apply\n")
            return 1
    with open(os.path.join(HERE, "swe_eval.sh"), encoding="utf-8") as fh:
        script, notes = transform(fh.read(), copy)
    for n in notes:
        sys.stdout.write(f"aethens-swe: {n}\n")
    script_path = os.path.join(work, ".swe_eval_sandbox.sh")
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write(script)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        editable_paths(copy) + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    r = subprocess.run(
        ["bash", script_path],
        cwd=copy,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    content = r.stdout.decode("utf-8", "replace")
    sys.stdout.write(content)
    resolved, detail = grade(content, spec)
    sys.stderr.write(
        "aethens-swe: {} resolved={} {}\n".format(
            spec["instance_id"], resolved, json.dumps(detail, sort_keys=True)
        )
    )
    return 0 if resolved else 1


if __name__ == "__main__":
    sys.exit(main())
