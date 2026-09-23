"""Every figure quoted in WHITEPAPER.md must match what the pipeline produces.

This is the mechanism that stops the prose and the code drifting apart. Three
specification documents were written before this repo existed and every
illustrative number in all three was wrong; the fix is not more careful writing,
it is a test that fails when a published claim stops being true.

Each check asserts that the string the pipeline generates appears in the document.
If a figure moves -- because data was refreshed, or a senator was replaced -- the
string disappears and this fails, naming what to update.
"""
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run

DOC = Path(__file__).resolve().parents[1] / "WHITEPAPER.md"


@pytest.fixture(scope="module")
def text():
    return DOC.read_text()


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


def assert_quoted(text: str, value: str, label: str):
    assert value in text, f"WHITEPAPER.md no longer quotes the current {label}: {value}"


def test_apportionment_skew_figures(text, report):
    c = report.chamber_lean
    lo, hi = c.skew_range_points
    assert_quoted(text, f"{c.skew_points:+.2f} points", "skew")
    assert_quoted(text, f"{c.senate_lean * 100:.2f}%", "per-seat state vote share")
    assert_quoted(text, f"{c.national_lean * 100:.2f}%", "national vote share")
    # each cycle's skew is quoted in the prose
    for y, v in c.by_year.items():
        assert_quoted(text, f"{v * 100:+.2f}".lstrip("+"), f"{y} skew")


def test_widest_gaps_table_is_current(text, report):
    """The five widest senator-to-state gaps, with both positions and the gap."""
    scored = sorted((a for a in report.alignments if a.abs_gap is not None),
                    key=lambda a: -a.abs_gap)[:5]
    for a in scored:
        assert a.name in text, f"{a.name} should be in the widest-gaps table"
        row = f"| {a.name} | {a.state} | {a.senator_coord:+.3f} | {a.state_coord:+.3f} | {a.abs_gap:.3f} |"
        assert row in text, f"row for {a.name} has moved: {row}"


def test_party_landmarks_are_current(text, report):
    """The middle Democrat and Republican quoted as landmarks must be live."""
    import statistics as st
    dem = st.median(v for b, v in report.scores.items() if report.senators[b].party == "Democrat")
    rep = st.median(v for b, v in report.scores.items() if report.senators[b].party == "Republican")
    assert f"{dem:+.3f}".replace("-", "−") in text
    assert f"{rep:+.3f}" in text
    assert "No bills are marked" in text


def test_committee_tables_are_current(text, report):
    """Members vs Senate and public, and where the bills passed divided the Senate."""
    ch = report.chamber
    for c in sorted(report.committees, key=lambda c: -abs(c.median - ch.median))[:6]:
        assert f"| {c.median:+.3f} | {c.median - ch.median:+.3f} | {c.cnd:+.3f} | {c.stability.worst_shift:.2f} |".replace("-", "−") in text \
            or f"| {c.median:+.3f} | {c.median - ch.median:+.3f} | {c.cnd:+.3f} | {c.stability.worst_shift:.2f} |" in text
    for o in report.output_ideology:
        if o.is_reportable:
            assert f"| {o.n_votes} | " in text
            assert f"{o.coi:+.3f}".replace("-", "−") in text or f"{o.coi:+.3f}" in text


def test_committee_claim_matches_the_code(text, report):
    """The document says 0 of 19 committee drift figures are reported."""
    usable = sum(1 for c in report.committees if not c.is_noise)
    total = len(report.committees)
    assert_quoted(text, f"**{usable} of {total}** committees", "committee count")

    fragile = sum(1 for c in report.committees
                  if c.stability.is_fragile or c.median_is_phantom)
    assert fragile == 17, f"prose says seventeen; code says {fragile}"


def test_chair_gaps_are_current(text, report):
    for code, label in [("SSEG", "Energy"), ("SSBU", "Budget"), ("SSCM", "Commerce")]:
        cs = next(c for c in report.committees if c.code == code)
        gap = cs.chair_coord - cs.majority_median
        assert_quoted(text, f"{label} {gap:+.3f}", f"{label} chair gap")


def test_scope_is_stated(text):
    """The document must say what it does not cover, so it cannot be read as a
    description of the whole system."""
    assert "sections 2" in text and "5" in text
    assert "Pillars 1" in text


def test_limits_section_exists(text):
    """Known limits are published, not buried. Each of these must be present."""
    for phrase in [
        "one dimension",
        "behaviour, not belief",
        "does not publish",
        "cannot be propagated",
    ]:
        assert phrase in text, f"WHITEPAPER.md no longer states the limit: {phrase!r}"


def test_json_export_marks_the_dead_metric(report):
    """The handoff format must flag what may not be displayed.

    Committee drift looks plausible and does not work. A front end building
    against this JSON cannot show it without ignoring an explicit flag.
    """
    from civicalign.export import to_dict

    d = to_dict(report)
    assert d["committee_drift"]["publishable"] is False
    assert "do not" in d["committee_drift"]["reason"].lower() or \
           "survive" in d["committee_drift"]["reason"].lower()

    for key in ("chamber", "apportionment_skew", "state_alignment",
                "committee_chairs", "committee_state_lean"):
        assert d[key]["publishable"] is True, f"{key} should be publishable"

    # per-committee flags too, so a consumer iterating the list is also safe
    assert all(c["publishable"] is False for c in d["committee_drift"]["committees"])
    assert d["state_alignment"]["n_significant"] == len(d["state_alignment"]["significant"])


def test_distinct_bill_counts_are_current(text, report):
    assert f"{report.bills_referred_unique:,} distinct bills" in text
    assert f"{sum(g.referred for g in report.gatekeeping):,}\nreferrals" in text or \
           f"{sum(g.referred for g in report.gatekeeping):,} referrals" in text.replace("\n", " ")
    assert f"{report.bills_reported_unique} have been sent on" in text
