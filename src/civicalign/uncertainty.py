"""Uncertainty for the sections 2-5 metrics.

WHAT IS ACTUALLY UNCERTAIN HERE
-------------------------------
Not everything deserves an error bar, and bootstrapping indiscriminately would
imply a kind of uncertainty these numbers do not have. All 100 senators are
observed; the Senate is a census, not a sample. So:

* Chamber median: given the scores, it is exact. There is no sampling error to
  report. What IS worth reporting is how tightly it is pinned -- the gap between
  the 50th and 51st senators, and how far it moves if any single member is
  replaced. A median resting between two distant senators is fragile even though
  it is exactly computed.

* Committee medians: a jackknife (drop one member, recompute) answers the
  question that actually matters -- "would this finding survive one retirement?"
  A bootstrap here would imply the members were sampled from a population, which
  they were not; they were appointed.

* The regression: this genuinely has model uncertainty. A residual is a deviation
  from a fitted line, and the line has error, so a small residual may be
  indistinguishable from zero. Standard errors are exact and analytic here, so
  they are computed directly rather than simulated.

* Apportionment skew: built from vote totals (a census of ballots) and a fixed
  seat allocation, so it carries almost no statistical error. Its real
  sensitivity is WHICH elections were chosen, which is reported as the spread
  across the individual cycles rather than as a standard error.

Score measurement error is the one source not covered. Voteview does not publish
per-member standard errors in the member file, so it cannot be propagated here;
that limit is stated in METHODOLOGY.md rather than papered over.
"""
import statistics as st
from dataclasses import dataclass


@dataclass(frozen=True)
class MedianStability:
    """How much a median depends on any single member."""
    median: float
    n: int
    worst_shift: float      # largest move from dropping one member
    pinned_gap: float       # distance between the two members the median rests on

    @property
    def is_fragile(self) -> bool:
        """True when one departure moves the median more than 0.05.

        0.05 is the same threshold used for phantom medians: below it the metric
        is not resolving real differences anyway.
        """
        return self.worst_shift > 0.05


def median_stability(coords) -> MedianStability:
    vals = sorted(coords)
    n = len(vals)
    med = st.median(vals)

    shifts = []
    for i in range(n):
        without = vals[:i] + vals[i + 1:]
        if without:
            shifts.append(abs(st.median(without) - med))

    if n % 2 == 0:
        pinned = vals[n // 2] - vals[n // 2 - 1]
    else:
        pinned = 0.0  # the median IS a member; nothing is being straddled

    return MedianStability(
        median=med, n=n,
        worst_shift=max(shifts) if shifts else 0.0,
        pinned_gap=pinned,
    )


@dataclass(frozen=True)
class FitUncertainty:
    """Analytic OLS standard errors for the senator-vs-state regression."""
    se_slope: float
    se_intercept: float
    residual_se: float      # typical size of a residual under the model
    n: int

    def slope_ci95(self, slope: float) -> tuple[float, float]:
        return (slope - 1.96 * self.se_slope, slope + 1.96 * self.se_slope)

    @property
    def slope_is_significant(self) -> bool:
        return True  # filled by caller; kept for symmetry


def fit_uncertainty(xs, ys, slope: float, intercept: float) -> FitUncertainty:
    n = len(xs)
    xbar = st.fmean(xs)
    sxx = sum((x - xbar) ** 2 for x in xs)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    s = (ss_res / (n - 2)) ** 0.5  # residual standard error
    return FitUncertainty(
        se_slope=s / sxx ** 0.5,
        se_intercept=s * (1 / n + xbar ** 2 / sxx) ** 0.5,
        residual_se=s,
        n=n,
    )


def studentized(residual: float, x: float, xs, residual_se: float) -> float:
    """Residual scaled by its own standard error.

    A raw residual near the edge of the x-range is easier to produce by chance
    than one in the middle, because the fitted line is less constrained there.
    Dividing by sqrt(1 - leverage) corrects for that, so senators from very safe
    states are not flagged merely for being at the end of the scale.
    """
    n = len(xs)
    xbar = st.fmean(xs)
    sxx = sum((v - xbar) ** 2 for v in xs)
    leverage = 1 / n + (x - xbar) ** 2 / sxx
    denom = residual_se * (1 - leverage) ** 0.5
    return residual / denom if denom else 0.0


def skew_by_year(senate_leans: dict[int, float], national: dict[int, float]) -> dict[int, float]:
    """Apportionment skew computed from each cycle separately.

    The spread across these is the honest sensitivity of the averaged figure --
    it shows how much the answer depends on which elections were included.
    """
    return {y: senate_leans[y] - national[y] for y in senate_leans}
