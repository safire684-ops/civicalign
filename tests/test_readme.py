"""The public README describes the current product, not retired methods.

The README is the first thing a reader of the repository sees. It must not
present the retired regression as the Pillar 4 method, rank senators, compare a
senator's score directly with the voter estimate, carry alignment or defiance
language, quote test counts that go stale, or suggest that generated vote
explanations exist."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
LOW = " ".join(README.lower().split())

RETIRED = [
    "most out of step", "significantly off", "senators significantly", "out of step with their own state",
    "residual", "predicted", "via regression", "explain **69%**", "r-squared", "state results explain",
    "alignment gap", "alignment score", "defian", "betray", "graveyard", "statistically aligned",
    "distance to the median voter", "absolute distance", "typical position based on",
    "most liberal", "most conservative", "most-drifted", "ranking of senators",
]


def test_no_retired_method_or_ranking_language():
    found = [p for p in RETIRED if p.lower() in LOW]
    assert not found, f"README carries retired wording: {found}"


def test_no_senator_tables_or_stale_counts():
    assert not re.search(r"^\|.*senator.*\|", README, re.I | re.M), "no per-senator tables"
    assert not re.search(r"\b\d+\s+tests\b", README), "test counts go stale; do not quote them"
    assert "| committee |" not in LOW


def test_describes_the_current_product():
    for phrase in ("caucus-group peer comparison", "±4 percentage points", "at least six peers", "±2, ±3, ±4 and ±5",
                   "never subtracted", "diagnostics", "same-scale comparisons of election results",
                   "descriptive comparisons of each committee", "stage 3", "has not started",
                   "no generated explanation exists or is published"):
        assert phrase.lower() in LOW, phrase
    assert "does not rank politicians" in LOW and "does not claim to measure whether a senator represents their voters" in LOW


def test_named_code_exists():
    for rel in ("src/civicalign/ideology/pillars.py", "src/civicalign/build_pages.py", "src/civicalign/explain/relevance.py",
                "src/civicalign/explain/context.py", "src/civicalign/explain/bind.py", "scripts/fetch_data.sh",
                "scripts/report.sh", "scripts/update.sh", "HANDOFF.md", "METHODOLOGY.md"):
        assert (ROOT / rel).exists(), rel


@pytest.mark.xfail(strict=True, reason="README and METHODOLOGY still describe the retired Pillars 4-6 code; "
                   "their rewrite is the pending docs task (approved Step 5 plan). Remove this marker when done.")
def test_every_code_file_the_docs_name_exists():
    missing = []
    for doc in ("README.md", "METHODOLOGY.md"):
        for rel in set(re.findall(r"[\w/]+\.py", (ROOT / doc).read_text())):
            name = rel.split("/")[-1]
            if not list((ROOT / "src" / "civicalign").rglob(name)):
                missing.append(f"{doc}: {rel}")
    assert not missing, missing
