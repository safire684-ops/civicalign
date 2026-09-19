"""State partisan lean, averaged over the last three presidential elections.

WHY THIS EXISTS
---------------
DW-NOMINATE contains legislators only. Voteview publishes exactly four datasets
-- Member Ideology, Congressional Votes, Members' Votes, Congressional Parties --
and all four are roll calls and the people who cast them. Its scores do update
live as new votes are recorded, but no version of them holds a position for the
public, so senator-vs-public cannot be a subtraction inside that data.

It does not have to be a subtraction. Election results ARE public behaviour,
measured directly, with no survey and no scaling assumption. That gives two
comparisons needing no shared ruler (see representation.py):
  1. Regress senator ideology on state vote share; read the residual.
  2. Compare Senate-seat vote share to national vote share -- share against
     share, identical units.

SOURCE
------
MIT Election Data and Science Lab, "U.S. President 1976-2024", Harvard Dataverse
doi:10.7910/DVN/42MVDX, file 1976-2024-president.csv.

Chosen after rejecting a county-level alternative whose 2016 file understated
California's Democratic vote by 1.4 million. This file reproduces the official
national totals to within a few dozen votes for 2016 and exactly for 2024.

TWO DATA QUIRKS HANDLED HERE
----------------------------
1. Fusion voting: a candidate can appear on several party lines in one state (NY
   especially). Votes are therefore summed per CANDIDATE across every line, not
   taken from a single party row. Summing by party instead loses ~292k Trump
   votes in 2016.
2. DC 2020 has `writein` mislabelled as True for the major candidates. DC has no
   senators so it never reaches a metric, but it is why a naive filter appears to
   lose a "state" and ~333k Biden votes.
"""
import csv
import statistics as st
from dataclasses import dataclass
from pathlib import Path

# The two major-party nominees per cycle, matched as substrings of MIT's
# "candidate" field so every fusion line for that person is captured.
NOMINEES: dict[int, tuple[str, str]] = {
    2016: ("TRUMP", "CLINTON"),
    2020: ("TRUMP", "BIDEN"),
    2024: ("TRUMP", "HARRIS"),
}

DEFAULT_YEARS = (2016, 2020, 2024)


@dataclass(frozen=True)
class StateLean:
    usps: str
    gop_two_party: float          # averaged across the included elections, 0..1
    by_year: dict[int, float]     # each election's own share, for trend display

    @property
    def centered(self) -> float:
        """Share expressed as distance from an even split. Positive = GOP-leaning."""
        return self.gop_two_party - 0.5

    @property
    def swing(self) -> float:
        """Most GOP year minus least GOP year: how settled this state is.

        A large swing means the average is hiding real movement, so a senator's
        residual against that average deserves less weight.
        """
        v = self.by_year.values()
        return max(v) - min(v)


@dataclass(frozen=True)
class ElectionLean:
    years: tuple[int, ...]
    states: dict[str, StateLean]
    national_gop_two_party: float
    national_by_year: dict[int, float]

    def lean(self, usps: str) -> float | None:
        s = self.states.get(usps)
        return s.gop_two_party if s else None

    def state_lean(self, usps: str) -> StateLean | None:
        return self.states.get(usps)

    @property
    def label(self) -> str:
        return "/".join(str(y) for y in self.years)

    @property
    def national_centered(self) -> float:
        return self.national_gop_two_party - 0.5


def load_mit_president(path: Path, years: tuple[int, ...] = DEFAULT_YEARS) -> ElectionLean:
    """Average two-party GOP share per state over the given elections.

    Each election is weighted equally, which is the convention used by partisan
    lean indices such as Cook PVI. Weighting recent elections more heavily would
    track a genuinely shifting state faster at the cost of stability; that is a
    judgement call, so it is left as an explicit equal weighting rather than a
    silent choice.
    """
    gop: dict[int, dict[str, float]] = {y: {} for y in years}
    dem: dict[int, dict[str, float]] = {y: {} for y in years}

    with path.open() as fh:
        for row in csv.DictReader(fh):
            try:
                year = int(row["year"])
            except (KeyError, ValueError):
                continue
            if year not in gop:
                continue
            if row["office"].strip().upper() != "US PRESIDENT":
                continue
            if row["writein"].strip().upper() == "TRUE":
                continue  # drops DC 2020, which has no senators anyway
            try:
                votes = float(row["candidatevotes"])
            except (KeyError, ValueError):
                continue

            gop_name, dem_name = NOMINEES[year]
            candidate = row["candidate"].upper()
            usps = row["state_po"].strip()

            # summed per candidate across every party line: fusion-aware
            if gop_name in candidate:
                gop[year][usps] = gop[year].get(usps, 0.0) + votes
            elif dem_name in candidate:
                dem[year][usps] = dem[year].get(usps, 0.0) + votes

    per_year_share: dict[int, dict[str, float]] = {}
    national_by_year: dict[int, float] = {}
    for year in years:
        shares = {}
        for usps, g in gop[year].items():
            d = dem[year].get(usps, 0.0)
            if g + d > 0:
                shares[usps] = g / (g + d)
        per_year_share[year] = shares
        ng, nd = sum(gop[year].values()), sum(dem[year].values())
        national_by_year[year] = ng / (ng + nd)

    # keep only states present in every included election, so the average is
    # over a consistent set rather than silently mixing 2-year and 3-year means
    common = set.intersection(*(set(per_year_share[y]) for y in years))
    states = {
        usps: StateLean(
            usps=usps,
            gop_two_party=st.fmean(per_year_share[y][usps] for y in years),
            by_year={y: per_year_share[y][usps] for y in years},
        )
        for usps in common
    }

    return ElectionLean(
        years=tuple(years),
        states=states,
        national_gop_two_party=st.fmean(national_by_year[y] for y in years),
        national_by_year=national_by_year,
    )
