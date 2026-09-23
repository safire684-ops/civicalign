"""Section 4 / Pillar 5: chamber vs. national alignment."""
from dataclasses import dataclass

from .space import median, nth_from_left
from .sources.rosters import Senator


@dataclass(frozen=True)
class ChamberStats:
    n: int
    median: float

    # The median senator is not who decides things. Legislation needs 60 votes
    # for cloture, so the 60th senator from the left is the real pivot; in the
    # 119th they sit 0.13 to the RIGHT of the median. Nominations need only a
    # simple majority since the 2013 and 2017 rules changes, so pass 51 for those.
    pivot: float
    pivot_n: int

    # Agenda control sits with the majority party's median, not the chamber's.
    majority_party: str
    majority_median: float
    minority_median: float

    # Signed. Positive => the chamber sits conservative of the nation.
    # None until a bridged national coordinate exists -- see sources/state_prefs.
    # Survey-scale national estimate, carried for the voter-side chart only. It is
    # never subtracted from the (Voteview-scale) median: the scales are not bridged.
    national_coord: float | None

    @property
    def party_gap(self) -> float:
        """Distance between the two party medians: polarization in one figure."""
        return abs(self.majority_median - self.minority_median)


def chamber_stats(
    scores: dict[str, float],
    roster: dict[str, Senator],
    majority: str,
    cloture_threshold: int = 60,
    national_coord: float | None = None,
) -> ChamberStats:
    vals = list(scores.values())
    maj = [v for b, v in scores.items() if roster[b].party == majority]
    minor = [v for b, v in scores.items() if roster[b].party != majority]

    ch_median = median(vals)

    return ChamberStats(
        n=len(vals),
        median=ch_median,
        pivot=nth_from_left(vals, cloture_threshold),
        pivot_n=cloture_threshold,
        majority_party=majority,
        majority_median=median(maj),
        minority_median=median(minor),
        national_coord=national_coord,
    )
