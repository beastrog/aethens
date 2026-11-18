"""Repository hygiene for B7: workflows, the Action, release, README traceability."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
USES = re.compile(r"uses:\s*([^\s#]+)")


def _yaml(path: Path) -> Any:
    data = yaml.safe_load(path.read_text())
    # PyYAML parses the bare key `on` as boolean True.
    if isinstance(data, dict) and True in data:
        data["on"] = data.pop(True)
    return data


def test_required_files_exist() -> None:
    for name in (
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "action.yml",
        "docs/DISCLOSURE.md",
        "docs/task-format.md",
        "docs/report-schema.json",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/ran-it.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        ".github/workflows/action-selftest.yml",
    ):
        assert (REPO / name).is_file(), name


def test_all_third_party_actions_pinned_to_sha() -> None:
    for path in [*WORKFLOWS.glob("*.yml"), REPO / "action.yml"]:
        for ref in USES.findall(path.read_text()):
            if ref.startswith("./"):
                continue
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{path.name}: {ref}"


def test_no_secrets_and_no_pull_request_target() -> None:
    for path in [*WORKFLOWS.glob("*.yml"), REPO / "action.yml"]:
        text = path.read_text()
        assert not re.search(r"secrets\.[A-Za-z_]", text), path.name
        assert "secrets: inherit" not in text, path.name
        assert "pull_request_target" not in text, path.name


def test_ci_and_selftest_are_read_only() -> None:
    for name in ("ci.yml", "action-selftest.yml"):
        wf = _yaml(WORKFLOWS / name)
        assert wf["permissions"] == {"contents": "read"}, name
        assert "pull_request" in wf["on"], name
    assert set(_yaml(WORKFLOWS / "action-selftest.yml")["on"]) == {"pull_request"}


def test_release_uses_trusted_publishing_only_in_publish_job() -> None:
    wf = _yaml(WORKFLOWS / "release.yml")
    assert wf["on"] == {"release": {"types": ["published"]}}
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    with_id_token = [n for n, j in jobs.items() if j.get("permissions", {}).get("id-token")]
    assert with_id_token == ["publish"]
    assert jobs["publish"]["permissions"] == {"id-token": "write"}
    text = (WORKFLOWS / "release.yml").read_text()
    assert "pypa/gh-action-pypi-publish@" in text
    for job in jobs.values():
        for step in job["steps"]:
            inputs = {k.lower() for k in (step.get("with") or {})}
            assert not inputs & {"password", "user", "api-token", "token"}, step
    assert "PYPI_API_TOKEN" not in text.upper()


def test_action_inputs_never_interpolated_into_scripts() -> None:
    action = _yaml(REPO / "action.yml")
    assert action["runs"]["using"] == "composite"
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert "${{" not in step["run"], step.get("name")


def test_readme_numbers_match_bench_results() -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("render_readme", REPO / "bench" / "render_readme.py")
    assert spec and spec.loader
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    results = json.loads((REPO / "bench" / "results.json").read_text())
    readme = (REPO / "README.md").read_text()
    block = mod.render_block(results)
    assert block in readme, "README bench block is stale: run `python bench/render_readme.py`"


def test_readme_does_not_overclaim() -> None:
    text = (REPO / "README.md").read_text().lower()
    assert "cannot be exploited" not in text
    assert "self-authored" in text
    assert "known misses" in text


def test_action_audit_step_survives_findings_exit_code() -> None:
    # GitHub runs `shell: bash` with -e; without `set +e` a findings exit (1) would abort the step
    # before the report reaches the job summary and the exit-code output.
    action = _yaml(REPO / "action.yml")
    audit = next(s for s in action["runs"]["steps"] if s.get("id") == "audit")
    script = audit["run"]
    assert script.index("set +e") < script.index("aethens audit")
    assert 'exit "$code"' in script and "GITHUB_STEP_SUMMARY" in script
