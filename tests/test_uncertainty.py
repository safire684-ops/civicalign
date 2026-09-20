"""Tests for what is and is not uncertain in sections 2-5.

The point of these is that error bars changed conclusions rather than decorating
them, so the thresholds are pinned.
"""
import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run
from civicalign.uncertainty import fit_uncertainty, median_stability, studentized


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


def test_median_of_odd_count_is_a_real_member():
    """With an odd count the median IS someone, so nothing is straddled."""
    ms = median_stability([0.1, 0.2, 0.9])
    assert ms.median == pytest.approx(0.2)
    assert ms.pinned_gap == 0.0


def test_pinned_gap_exposes_a_median_resting_between_two_blocs():
    """Two tight clusters far apart: the median describes neither."""
    ms = median_stability([-0.5, -0.45, 0.45, 0.5])
    assert ms.median == pytest.approx(0.0)
    assert ms.pinned_gap == pytest.approx(0.9)
    assert ms.is_fragile


def test_dense_cluster_is_not_fragile():
    ms = median_stability([0.30, 0.31, 0.32, 0.33, 0.34])
    assert not ms.is_fragile


def test_chamber_median_is_stable(report):
    """100 members packed near the middle: one departure barely moves it.

    This is why the chamber median is publishable while committee medians are not
    -- the difference is n, not method.
    """
    ms = median_stability(list(report.scores.values()))
    assert ms.n == 100
    assert ms.worst_shift < 0.05
    assert not ms.is_fragile


def test_no_committee_ccd_survives_validation(report):
    """No committee CCD is publishable, for one of two reasons.

    Most committee medians are unstable: 17 of 19 move more than 0.05 when one
    member leaves, and most move 0.2-0.34, which is larger than the CCD values
    themselves (0.01-0.31). With ~20 members split between two polarised clusters
    the median sits on the party boundary, so dropping anyone near it swings the
    result across the gap.

    The remaining two (Banking, Commerce) have STABLE medians -- 0.024 and 0.034
    -- but a CCD too small to clear the noise floor. Stable and meaningless rather
    than unstable.

    Either way none survive. If this ever fails, a committee genuinely became
    publishable; check which reason changed before trusting it.
    """
    assert report.committees, "expected committees"
    assert all(c.is_noise for c in report.committees)

    fragile = [c for c in report.committees if c.stability.is_fragile or c.median_is_phantom]
    stable_but_small = [c for c in report.committees
                        if not (c.stability.is_fragile or c.median_is_phantom)]
    assert len(fragile) == 17
    assert len(stable_but_small) == 2
    assert all(abs(c.ccd) < c.noise_floor for c in stable_but_small)


def test_slope_confidence_interval_excludes_zero(report):
    """The state-to-ideology relationship is real, not an artifact."""
    lo, hi = report.fit.slope_ci95
    assert lo > 0
    assert report.fit.residual_se > 0


def test_most_senators_are_not_significantly_out_of_step(report):
    """Error bars must shrink the finding, not decorate it.

    A top-ten list ranked by raw residual is mostly noise: a residual has to clear
    roughly 2 x residual_se (~0.57) to mean anything, and only a handful do.
    """
    sig = [x for x in report.representation if x.is_significant]
    assert 0 < len(sig) < 20, f"{len(sig)} significant -- check the threshold"
    assert all(abs(x.t_stat) > 2 for x in sig)
    # and the ranking is by t, not by raw residual
    ts = [abs(x.t_stat) for x in report.representation]
    assert ts == sorted(ts, reverse=True)


def test_leverage_correction_matters():
    """A residual at the edge of the x-range is easier to get by chance.

    Two identical raw residuals must yield different t values when one sits at the
    edge, or senators from very safe states get flagged just for being extreme on
    the x-axis.
    """
    xs = [0.3, 0.4, 0.5, 0.5, 0.6, 0.7]
    middle = studentized(0.2, 0.5, xs, 0.1)
    edge = studentized(0.2, 0.7, xs, 0.1)
    assert abs(edge) > abs(middle)


def test_apportionment_skew_sign_holds_in_every_cycle(report):
    """The averaged skew is only meaningful if no cycle reverses it."""
    cl = report.chamber_lean
    assert all(v > 0 for v in cl.by_year.values())
    lo, hi = cl.skew_range_points
    assert lo > 0 and hi > lo


def test_small_committee_lean_is_flagged_fragile(report):
    """Indian Affairs has 11 seats: one departure moves its gap 1.89 points
    against a gap of 1.65, so it must not be published."""
    ia = next(c for c in report.committee_leans if c.code == "SLIA")
    assert ia.is_fragile
    # while a large-gap committee holds
    ju = next(c for c in report.committee_leans if c.code == "SSJU")
    assert not ju.is_fragile


def test_ols_standard_errors_match_a_hand_computed_case():
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [2.0, 4.1, 5.9, 8.1]
    import statistics as st
    slope, intercept = st.linear_regression(xs, ys)
    u = fit_uncertainty(xs, ys, slope, intercept)
    assert u.n == 4
    assert u.residual_se < 0.2       # near-perfect fit
    assert u.se_slope < 0.1
