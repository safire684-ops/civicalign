"""State partisan lean from actual election results.

WHY THIS EXISTS
---------------
DW-NOMINATE contains legislators only. Voteview publishes exactly four datasets
-- Member Ideology, Congressional Votes, Members' Votes, Congressional Parties --
and all four are roll calls and the people who cast them. There is no public or
voter position anywhere in it, so senator-vs-public cannot be a subtraction
inside that data.

But it does not have to be a subtraction. Election results ARE public behaviour,
measured directly, with no survey and no scaling assumption. Two-party
presidential vote share per state is a clean, checkable measure of what a state's
voters actually did.

That gives two honest comparisons that need no shared ruler:
  1. Regress senator ideology on state vote share and read the RESIDUAL. This
     never subtracts the two scales, so their units never have to match.
  2. Compare committee vote share to national vote share -- share against share,
     identical units on both sides.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

USPS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


@dataclass(frozen=True)
class StateLean:
    usps: str
    gop_two_party: float  # 0..1 share of the two-party vote
    total_votes: int

    @property
    def centered(self) -> float:
        """Share expressed as distance from an even split. Positive = GOP-leaning."""
        return self.gop_two_party - 0.5


@dataclass(frozen=True)
class ElectionLean:
    year: int
    states: dict[str, StateLean]
    national_gop_two_party: float
    national_total_votes: int

    def lean(self, usps: str) -> float | None:
        s = self.states.get(usps)
        return s.gop_two_party if s else None

    @property
    def national_centered(self) -> float:
        return self.national_gop_two_party - 0.5


def load_county_results(path: Path, year: int = 2024) -> ElectionLean:
    """Aggregate county-level results to states.

    County data is used rather than a state-level file because it is verifiable:
    the state totals are reproducible from the rows, so a reader can check them.
    DC is aggregated but carries no senators, so it drops out downstream.
    """
    gop: dict[str, float] = {}
    dem: dict[str, float] = {}
    tot: dict[str, float] = {}

    with path.open() as fh:
        for row in csv.DictReader(fh):
            usps = USPS.get(row["state_name"])
            if usps is None:
                continue
            gop[usps] = gop.get(usps, 0.0) + float(row["votes_gop"])
            dem[usps] = dem.get(usps, 0.0) + float(row["votes_dem"])
            tot[usps] = tot.get(usps, 0.0) + float(row["total_votes"])

    states = {
        usps: StateLean(
            usps=usps,
            gop_two_party=gop[usps] / (gop[usps] + dem[usps]),
            total_votes=int(tot[usps]),
        )
        for usps in gop
        if (gop[usps] + dem[usps]) > 0
    }

    ng, nd = sum(gop.values()), sum(dem.values())
    return ElectionLean(
        year=year,
        states=states,
        national_gop_two_party=ng / (ng + nd),
        national_total_votes=int(sum(tot.values())),
    )
