"""Tests for the regression route into Pillar 4 and the vote-share skew.

The point of this approach is that it never subtracts two different scales, so
these tests pin the properties that make it valid.
"""
import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run
from civicalign.representation import Fit
from civicalign.sources import elections


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


# Official two-party GOP shares, for validating the aggregation end to end.
# Fusion voting and DC's mislabelled 2020 writein flag both break naive sums, so
# these are pinned rather than trusted.
OFFICIAL_TWO_PARTY = {2016: 0.4889, 2020: 0.4773, 2024: 0.5075}


@pytest.mark.parametrize("year", [2016, 2020, 2024])
def test_each_year_reproduces_the_official_national_result(report, year):
    got = report.election.national_by_year[year]
    assert got == pytest.approx(OFFICIAL_TWO_PARTY[year], abs=0.002)


def test_three_year_average_is_the_mean_of_the_three(report):
    e = report.election
    expected = sum(e.national_by_year[y] for y in e.years) / len(e.years)
    assert e.national_gop_two_party == pytest.approx(expected)


def test_every_state_has_all_three_elections(report):
    """States missing a year are dropped, so the average is over a consistent
    set rather than silently mixing 2-year and 3-year means."""
    for sl in report.election.states.values():
        assert set(sl.by_year) == set(report.election.years)


def test_all_fifty_states_present(report):
    """Every state with senators must carry a lean. DC has none, so 50."""
    senate_states = {s.state for s in report.senators.values()}
    assert len(senate_states) == 50
    assert all(report.election.lean(st) is not None for st in senate_states)


def test_swing_flags_states_the_average_hides(report):
    """A state that moved a lot across three cycles is less well described by its
    average, so the swing must be exposed rather than smoothed away."""
    fl = report.election.state_lean("FL")
    assert fl is not None
    assert fl.swing > 0.03  # Florida moved ~6 points across 2016-2024


def test_apportionment_skew_is_positive_and_modest(report):
    """Two senators per state over-weights small states.

    Sign is the substantive claim; the magnitude band just catches a units error
    (e.g. a fraction reported as a percentage).
    """
    cl = report.chamber_lean
    assert cl.n_seats == 100
    assert 0 < cl.skew_points < 10


def test_fit_explains_most_of_the_variance(report):
    """State election results should predict senator ideology well.

    If this collapses, either the join broke or the scales got mangled.
    """
    assert report.fit.n == 100
    assert report.fit.r_squared > 0.5
    assert report.fit.slope > 0  # more GOP-voting state => more conservative senator


def test_residuals_sum_to_about_zero(report):
    """A least-squares fit must leave residuals centred on zero.

    This is the property that makes a residual meaningful: it is deviation from
    the pattern, so the pattern itself cannot be biased.
    """
    total = sum(r.residual for r in report.representation)
    assert total == pytest.approx(0.0, abs=1e-9)


def test_residual_is_relative_not_absolute():
    """Shifting every senator equally must NOT change any residual.

    This is the honest limit of the method, pinned as a test: residuals measure
    position relative to the Senate-wide pattern, not absolute distance from
    voters. A uniform shift moves the baseline, not the outliers.
    """
    from civicalign.representation import representations
    from civicalign.sources.rosters import Senator

    roster = {
        "A": Senator("A", "A", "WY", "Republican"),
        "B": Senator("B", "B", "CA", "Democrat"),
        "C": Senator("C", "C", "OH", "Republican"),
    }
    def sl(usps, share):
        return elections.StateLean(usps, share, {2016: share, 2020: share, 2024: share})

    lean = elections.ElectionLean(
        years=(2016, 2020, 2024),
        states={"WY": sl("WY", 0.73), "CA": sl("CA", 0.40), "OH": sl("OH", 0.56)},
        national_gop_two_party=0.4915,
        national_by_year={2016: 0.4889, 2020: 0.4773, 2024: 0.5075},
    )
    base = {"A": 0.6, "B": -0.4, "C": 0.2}
    shifted = {k: v + 0.25 for k, v in base.items()}

    _, r1 = representations(base, roster, lean)
    _, r2 = representations(shifted, roster, lean)
    for a, b in zip(r1, r2):
        assert a.residual == pytest.approx(b.residual)


def test_committee_gap_vs_senate_removes_the_structural_skew(report):
    """vs-nation and vs-senate must differ by exactly the chamber skew."""
    skew = report.chamber_lean.skew
    for c in report.committee_leans:
        assert (c.gap - c.gap_vs_senate) == pytest.approx(skew)


def test_fit_predict_is_consistent():
    from civicalign.uncertainty import FitUncertainty

    f = Fit(slope=2.0, intercept=-1.0, r_squared=0.9, n=10,
            uncertainty=FitUncertainty(se_slope=0.1, se_intercept=0.05,
                                       residual_se=0.2, n=10))
    assert f.predict(0.5) == pytest.approx(0.0)
    lo, hi = f.slope_ci95
    assert lo < 2.0 < hi
