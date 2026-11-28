"""The public reproduction page stays inside the two filed issues."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "reproduce-findings.md"


def test_page_names_the_harness_and_the_limit() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "https://github.com/harbor-framework/terminal-bench-2/issues/107" in text
    assert "https://github.com/SWE-bench/SWE-bench/issues/733" in text
    assert "tests/test.sh" in text
    assert "reward.txt" in text
    assert "swebench.harness.run_evaluation" in text
    assert "not part of `make check`" in text or "not the v0.1.0 CLI" in text
    assert "0.1.0 does not contain these probes" in text
    assert "bench/tbench/" in text
    assert "LW-01" in text and "LW-02" in text and "LW-03" in text
    # The private audit tallies are not part of either public issue.
    for private in ("39/40", "73%", "F01", "F10"):
        assert private not in text


def test_readme_and_docs_index_link_the_page() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    index = (REPO / "docs" / "README.md").read_text(encoding="utf-8")
    disclosure = (REPO / "docs" / "DISCLOSURE.md").read_text(encoding="utf-8")
    assert "docs/reproduce-findings.md" in readme
    assert "reproduce-findings.md" in index
    assert "reproduce-findings.md" in disclosure


def test_roadmap_tracks_the_three_follow_ups_as_not_started() -> None:
    text = (REPO / "ROADMAP.yaml").read_text(encoding="utf-8")
    for item in ("LW-01", "LW-02", "LW-03"):
        assert item in text
    assert "status: NOT_STARTED" in text.split("launch_week:", 1)[1]
