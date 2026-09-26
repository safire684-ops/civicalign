"""The public README describes the current product, not retired methods.

Current = Engine B (Pillars 4-6) as rebuilt, and Engine A (Pillar 1). The old
Pillars 4-6 documents live under docs/archive/ with an ARCHIVED banner.

The README is the first thing a reader of the repository sees. It must not
present the retired regression as the Pillar 4 method, rank senators, compare a
senator's score directly with the voter estimate, carry alignment or defiance
language, quote test counts that go stale, or suggest that generated vote
explanations exist."""
import re
from pathlib import Path

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
    for phrase in ("nominate_dim1", "no senator-to-state distance is calculated", "status none",
                   "visual reference points only", "never an input to any calculation",
                   "weighted by the population they represent", "candidate method, not a final scientific standard",
                   "secondary comparison, shown only in details", "the national public estimate is **unresolved**",
                   "committee median minus the senate median", "committees-current.json", "append-only",
                   "rebuilds daily", "the supervisor", "no 0–100", "stage 3", "one development run was stopped",
                   "no generated explanation is currently published", "in the daily automated update"):
        assert phrase.lower() in LOW, phrase
    assert "does not rank politicians" in LOW and "does not claim to measure whether a senator represents their voters" in LOW


def test_named_code_exists():
    for rel in ("src/civicalign/ideology/pillars.py", "src/civicalign/build_pages.py", "src/civicalign/explain/relevance.py",
                "src/civicalign/explain/context.py", "src/civicalign/explain/bind.py", "scripts/fetch_data.sh",
                "scripts/report.sh", "scripts/update.sh", "scripts/build_pages.sh", "HANDOFF.md", "METHODOLOGY.md",
                "docs/ENGINE_B_DATA_FLOW.md", "docs/archive/README.md"):
        assert (ROOT / rel).exists(), rel


def test_every_code_file_the_docs_name_exists():
    missing = []
    for doc in ("README.md", "METHODOLOGY.md", "docs/ENGINE_B_DATA_FLOW.md"):
        for rel in set(re.findall(r"[\w/]+\.py", (ROOT / doc).read_text())):
            name = rel.split("/")[-1]
            if not list((ROOT / "src" / "civicalign").rglob(name)):
                missing.append(f"{doc}: {rel}")
    assert not missing, missing


def test_superseded_documents_are_archived_with_a_banner():
    for name in ("DONE.md", "WHITEPAPER.md", "WHITEPAPER_CORRECTIONS.md", "METHODOLOGY_SECTIONS_2_5.md",
                 "PILLAR6_BILLFLOW_FEASIBILITY.md"):
        assert not (ROOT / name).exists(), f"{name} belongs in docs/archive/"
        assert (ROOT / "docs" / "archive" / name).read_text().startswith("> **ARCHIVED — historical only.**"), name


def test_the_data_flow_document_covers_every_step():
    flow = (ROOT / "docs" / "ENGINE_B_DATA_FLOW.md").read_text()
    for cmd in ("civicalign.agents", "civicalign.ideology.ingest", "civicalign.ideology.bridge", "civicalign.ideology.anchors",
                "civicalign.ideology.compute", "civicalign.build_pages", "civicalign.agents.supervisor"):
        assert cmd in flow, cmd
    for table in ("senator_ideology", "constituency_ideology", "state_population", "committee_membership_events",
                  "committee_names", "ideology_bridge", "reference_anchors", "metrics_index"):
        assert table in flow, table
