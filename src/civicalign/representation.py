"""Pillar 4, done without a shared ruler; plus committees vs. the nation.

THE TRICK
---------
The blocker was that senator scores and public opinion live on different scales,
so subtracting them is meaningless. A regression sidesteps that entirely.

Fit  ideology = a + b * (state vote share)  across all 100 senators. The fitted
line says what ideology a state's election result typically predicts. The
RESIDUAL -- actual minus predicted -- says how far a senator sits from that
expectation. Units are ideology units throughout; the two scales are never
subtracted, so they never have to match.

WHAT THIS DOES AND DOES NOT ANSWER
----------------------------------
It answers: "is this senator more extreme than their state's own election result
predicts, compared with how every other senator relates to theirs?" That is a
real, checkable accountability claim.

It does NOT answer: "how far is this senator from their state's median voter in
absolute terms?" That still needs bridged survey data. The honest difference is
that this measure is RELATIVE to the pattern across all senators, rather than an
absolute distance. Every number here is defined by that pattern, so a shift in
the whole Senate moves the baseline, not just the outliers.
"""
import statistics as st
from dataclasses import dataclass

from .sources.elections import ElectionLean
from .sources.rosters import CommitteeMember, Senator


@dataclass(frozen=True)
class Fit:
    slope: float
    intercept: float
    r_squared: float
    n: int

    def predict(self, lean: float) -> float:
        return self.intercept + self.slope * lean


@dataclass(frozen=True)
class Representation:
    bioguide: str
    name: str
    state: str
    party: str
    ideology: float
    state_lean: float       # GOP two-party share, 0..1
    predicted: float
    residual: float         # + = more conservative than the state's result predicts
    rank: int | None = None
    of: int | None = None

    @property
    def direction(self) -> str:
        return "more conservative than state" if self.residual > 0 else "more liberal than state"


def fit_model(scores: dict[str, float], roster: dict[str, Senator],
              lean: ElectionLean) -> tuple[Fit, list[tuple[str, float, float]]]:
    pts = []
    for b, ideology in scores.items():
        sl = lean.lean(roster[b].state)
        if sl is not None:
            pts.append((b, sl, ideology))

    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    slope, intercept = st.linear_regression(xs, ys)

    ybar = st.fmean(ys)
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    return Fit(slope=slope, intercept=intercept, r_squared=r2, n=len(pts)), pts


def representations(scores: dict[str, float], roster: dict[str, Senator],
                    lean: ElectionLean) -> tuple[Fit, list[Representation]]:
    fit, pts = fit_model(scores, roster, lean)
    out = []
    for b, sl, ideology in pts:
        pred = fit.predict(sl)
        out.append(Representation(
            bioguide=b, name=roster[b].name, state=roster[b].state,
            party=roster[b].party, ideology=ideology, state_lean=sl,
            predicted=pred, residual=ideology - pred,
        ))
    out.sort(key=lambda r: -abs(r.residual))
    return fit, [
        Representation(r.bioguide, r.name, r.state, r.party, r.ideology,
                       r.state_lean, r.predicted, r.residual, rank=i + 1, of=len(out))
        for i, r in enumerate(out)
    ]


@dataclass(frozen=True)
class ChamberLean:
    """Pillar 5's apportionment skew, in vote-share units on both sides.

    Every state gets two senators regardless of population, so the Senate
    over-weights small states. Averaging each SEAT's state vote share and
    comparing it to the national vote share measures exactly that bias -- and
    because both sides are election results, no ideology scale is involved and no
    bridging is required.

    This is a structural claim about seats, not a claim about senators' opinions.
    """
    n_seats: int
    senate_lean: float      # seat-weighted mean state GOP two-party share
    national_lean: float
    skew: float             # + = the Senate's seats over-represent GOP-voting states

    @property
    def skew_points(self) -> float:
        return self.skew * 100


def chamber_lean(scores: dict[str, float], roster: dict[str, Senator],
                 lean: ElectionLean) -> ChamberLean:
    shares = []
    for b in scores:
        sl = lean.lean(roster[b].state)
        if sl is not None:
            shares.append(sl)  # one entry per seat, so small states count twice over
    mean = st.fmean(shares)
    return ChamberLean(
        n_seats=len(shares), senate_lean=mean,
        national_lean=lean.national_gop_two_party,
        skew=mean - lean.national_gop_two_party,
    )


@dataclass(frozen=True)
class CommitteeLean:
    """Committee vs. the nation, in vote-share units on BOTH sides.

    No scaling assumption at all: this compares election results to election
    results. It asks whether a committee's seats over-represent states that voted
    one way relative to how the country as a whole voted.
    """
    code: str
    n_seats: int
    mean_lean: float        # seat-weighted mean GOP two-party share
    national_lean: float
    senate_lean: float
    gap: float              # + = committee's states voted more GOP than the nation

    # vs. the Senate's own seat-weighted average. This is the committee-SPECIFIC
    # part. The gap against the nation mostly reflects two things that are not
    # about this committee at all: the Senate's structural small-state bias, and
    # the fact that the majority party holds most seats on every committee. This
    # field strips both out.
    gap_vs_senate: float

    @property
    def gap_points(self) -> float:
        """The gap in percentage points, which is how to present it."""
        return self.gap * 100

    @property
    def gap_vs_senate_points(self) -> float:
        return self.gap_vs_senate * 100


def committee_lean(code: str, members: list[CommitteeMember],
                   scores: dict[str, float], roster: dict[str, Senator],
                   lean: ElectionLean, senate_lean: float) -> CommitteeLean | None:
    shares = []
    for m in members:
        if m.bioguide not in scores:
            continue
        sl = lean.lean(roster[m.bioguide].state)
        if sl is not None:
            shares.append(sl)  # seat-weighted: a state with 2 members counts twice
    if len(shares) < 5:
        return None
    mean = st.fmean(shares)
    return CommitteeLean(
        code=code, n_seats=len(shares), mean_lean=mean,
        national_lean=lean.national_gop_two_party, senate_lean=senate_lean,
        gap=mean - lean.national_gop_two_party,
        gap_vs_senate=mean - senate_lean,
    )
