"""Section 5 / Pillar 6: institutional committee drift."""
from dataclasses import dataclass

from .space import median
from .sources.rosters import CommitteeMember, Senator, find_chair


@dataclass(frozen=True)
class CommitteeStats:
    code: str
    n_scored: int
    n_members: int
    median: float

    ccd: float          # committee median - chamber median
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

    noise_floor: float

    @property
    def is_noise(self) -> bool:
        """CCD below the floor is not a finding.

        Two reasons: the drift is a small fraction of the committee's internal
        spread, and with ~20 members the median lands exactly on one senator's
        score, so the metric is quantized -- identical CCDs recur across
        unrelated committees purely as an artifact.
        """
        return abs(self.ccd) < self.noise_floor

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
    majority: str,
    national_coord: float | None = None,
    noise_floor: float = 0.10,
    min_scored: int = 5,
) -> CommitteeStats | None:
    coords = [scores[m.bioguide] for m in members if m.bioguide in scores]
    if len(coords) < min_scored:
        return None  # too small for a median to mean anything

    cm = median(coords)
    chair = find_chair(members)
    chair_coord = scores.get(chair.bioguide) if chair else None

    maj = [
        scores[m.bioguide] for m in members
        if m.bioguide in scores and roster[m.bioguide].party == majority
    ]

    return CommitteeStats(
        code=code,
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
    )
