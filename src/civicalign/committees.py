"""Section 5 / Pillar 6: institutional committee drift."""
from dataclasses import dataclass

import statistics as _st

from .space import median
from .sources.rosters import CommitteeMember, Senator, find_chair
from .uncertainty import MedianStability, median_stability


@dataclass(frozen=True)
class CommitteeStats:
    code: str
    n_scored: int
    n_members: int
    median: float

    # committee median - chamber median.
    #
    # READ WITH CARE. On an evenly split committee this number is largely an
    # artifact: the median lands between the party blocs, so it moves with the
    # seat ratio rather than with anyone's politics. In the 119th the four
    # committees with the largest CCD -- Environment, Appropriations, Budget,
    # Ethics -- are all evenly split, and each one's median sits 0.17 to 0.33
    # away from the nearest real senator. Those are the committees where CCD
    # means least, not most. `is_noise` now catches this.
    ccd: float
    cnd: float | None   # committee median - national median (needs bridging)

    # The chair, not the median, is the gatekeeper: the chair decides what gets a
    # hearing, and Pillar 6's stated purpose is explaining where bills get stuck.
    # In the 119th nearly every chair sits 0.6-0.8 right of their own committee's
    # median -- two to three times larger than any CCD. Pair it with
    # majority_median to separate genuine chair extremity from plain majority
    # control (chairs always come from the majority).
    chair_coord: float | None
    majority_median: float | None

    # Committees span 1.07-1.68 of the 2.0-wide space, so the median is a thin
    # summary of a widely dispersed group. Show the distribution, not the midpoint.
    spread: float
    coords: tuple[float, ...]

    # Pillar 6 as specified, using the committee MEAN rather than the median.
    # The mean accounts for the density and extremity of members on both sides,
    # so it does not fall into the empty gap between the two party clusters.
    # Measured against the CHAMBER MEAN, not the chamber median, so both sides of
    # the subtraction are the same statistic.
    #
    # Stability, worst one-member departure: mean 0.111 at worst, median 0.342.
    mean: float
    chamber_mean: float
    ccd_mean: float
    mean_jackknife: float

    noise_floor: float

    # Party composition. On an evenly split committee the median falls in the
    # empty space BETWEEN the two party clusters, where no senator actually sits.
    n_majority: int
    n_minority: int
    nearest_member: float

    # Would this finding survive one retirement? A jackknife answers that; a
    # bootstrap would imply members were sampled from a population, when in fact
    # they were appointed.
    stability: MedianStability

    @property
    def median_gap_to_nearest_member(self) -> float:
        """How far the median sits from the closest real senator.

        Large values mean the median is an artifact of the party split rather
        than anyone's position. On a 10-10 committee it can exceed 0.3 -- a third
        of the way across the usable space -- while describing nobody.
        """
        return abs(self.nearest_member - self.median)

    @property
    def median_is_phantom(self) -> bool:
        """True when no member sits near the median, so it describes no one."""
        return self.median_gap_to_nearest_member > 0.05

    @property
    def is_evenly_split(self) -> bool:
        return abs(self.n_majority - self.n_minority) <= 1

    @property
    def mean_signal_ratio(self) -> float:
        """Drift divided by how far one departure moves it."""
        return abs(self.ccd_mean) / self.mean_jackknife if self.mean_jackknife else 0.0

    @property
    def mean_is_usable(self) -> bool:
        """Drift at least twice the one-member shift."""
        return self.mean_signal_ratio >= 2.0

    @property
    def is_noise(self) -> bool:
        """CCD below the floor is not a finding.

        Two reasons: the drift is a small fraction of the committee's internal
        spread, and with ~20 members the median lands exactly on one senator's
        score, so the metric is quantized -- identical CCDs recur across
        unrelated committees purely as an artifact.
        """
        return (abs(self.ccd) < self.noise_floor
                or self.median_is_phantom
                or self.stability.is_fragile)

    @property
    def chair_vs_committee(self) -> float | None:
        if self.chair_coord is None:
            return None
        return self.chair_coord - self.median


def committee_stats(
    code: str,
    members: list[CommitteeMember],
    scores: dict[str, float],
    roster: dict[str, Senator],
    chamber_median: float,
    chamber_mean: float,
    majority: str,
    national_coord: float | None = None,
    noise_floor: float = 0.10,
    min_scored: int = 5,
) -> CommitteeStats | None:
    coords = [scores[m.bioguide] for m in members if m.bioguide in scores]
    if len(coords) < min_scored:
        return None  # too small for a median to mean anything

    cm = median(coords)
    cmean = _st.fmean(coords)
    jack = max(
        abs(_st.fmean(coords[:i] + coords[i + 1:]) - cmean)
        for i in range(len(coords))
    )
    nearest = min(coords, key=lambda v: abs(v - cm))
    chair = find_chair(members)
    chair_coord = scores.get(chair.bioguide) if chair else None

    maj = [
        scores[m.bioguide] for m in members
        if m.bioguide in scores and roster[m.bioguide].party == majority
    ]
    n_maj = len(maj)

    return CommitteeStats(
        code=code,
        mean=cmean,
        chamber_mean=chamber_mean,
        ccd_mean=cmean - chamber_mean,
        mean_jackknife=jack,
        n_scored=len(coords),
        n_members=len(members),
        median=cm,
        ccd=cm - chamber_median,
        cnd=(cm - national_coord) if national_coord is not None else None,
        chair_coord=chair_coord,
        majority_median=median(maj) if maj else None,
        spread=max(coords) - min(coords),
        coords=tuple(sorted(coords)),
        noise_floor=noise_floor,
        n_majority=n_maj,
        n_minority=len(coords) - n_maj,
        nearest_member=nearest,
        stability=median_stability(coords),
    )
