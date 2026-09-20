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


def test_fit_figures(text, report):
    f = report.fit
    lo, hi = f.slope_ci95
    assert_quoted(text, f"{f.r_squared * 100:.0f}%", "r-squared as a percentage")
    assert_quoted(text, f"{f.slope:+.3f}", "slope")
    assert_quoted(text, f"[{lo:+.3f}, {hi:+.3f}]", "slope confidence interval")
    assert_quoted(text, f"{f.residual_se:.3f}", "residual standard error")
    assert_quoted(text, f"{2 * f.residual_se:.2f}", "significance threshold")


def test_significant_senators_are_listed_exactly(text, report):
    """The named senators, their states and their figures must all still hold.

    This is the highest-risk content in the document: named people with numbers
    attached. A senator leaving office or a data refresh must break this test
    rather than silently leave a false claim in print.
    """
    sig = [x for x in report.representation if x.is_significant]
    assert_quoted(text, f"**{len(sig)}** of", "count of significant senators")

    for x in sig:
        assert x.name in text, f"{x.name} is significant but not named in WHITEPAPER.md"
        assert_quoted(text, f"{x.residual:+.3f}".replace("-", "−"), f"{x.name} residual")
        assert_quoted(text, f"{x.t_stat:+.2f}".replace("-", "−"), f"{x.name} t-stat")

    # and nobody insignificant is presented as a finding
    names_in_table = [
        line for line in text.splitlines()
        if line.startswith("| ") and " | " in line
    ]
    table_blob = "\n".join(names_in_table)
    for x in report.representation:
        if not x.is_significant and abs(x.t_stat) > 1.5:
            assert x.name not in table_blob, (
                f"{x.name} is below the significance bar but appears in a table"
            )


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
