"""Every definitional choice that changes a published number lives here.

If a value in this file is wrong, the site publishes wrong numbers that still
look confident. Each field records *why* the default was chosen.
"""
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


@dataclass(frozen=True)
class Config:
    # Which Congress to score. 119 = 2025-2027.
    congress: int = 119

    # Which Voteview column supplies a senator's coordinate.
    #
    # "nokken_poole_dim1" is re-estimated within each Congress, so it MOVES over
    # a career -- required for any time series or drift claim.
    #
    # "nominate_dim1" is a single career-long constant per member. Murkowski is
    # 0.204 in all ten of her Congresses. Using it freezes every alignment gap
    # for life and makes year-over-year charts flat lines.
    #
    # Trade-off: Nokken-Poole is noisier and is estimated per-Congress, so it is
    # not strictly a common space ACROSS Congresses. Cross-Congress comparisons
    # must carry that caveat.
    score_column: str = "nokken_poole_dim1"

    # Cloture on legislation needs 60 votes, so the 60th senator from the left
    # is the real pivot for most bills. Nominations need only a simple majority
    # (rules changed 2013 and 2017), so set this to 51 for nomination analysis.
    cloture_threshold: int = 60

    # Who counts as "the electorate" for the national coordinate. Turnout
    # weighting moves this number, and every Pillar 5 headline depends on it.
    # Options: "adult_citizens" | "registered_voters" | "actual_voters"
    electorate: str = "adult_citizens"

    # Where state median-voter coordinates come from. See sources/state_prefs.py.
    #   "unavailable" -> Pillar 4 refuses to compute (honest default)
    #   "tausanovitch_warshaw" -> published bridged MRP estimates (Option A)
    #   "linear_proxy" -> stretched ideology index, NOT a real bridge (Option C)
    state_source: str = "unavailable"

    # A committee CCD smaller than this is not a finding. Observed CCDs run
    # 0.01-0.31 while internal committee spreads run 1.07-1.68, and with ~20
    # members the median lands exactly on one senator's score, so the metric is
    # quantized. Anything under this threshold gets flagged, not published.
    ccd_noise_floor: float = 0.10

    raw_dir: Path = field(default=RAW)
    processed_dir: Path = field(default=PROCESSED)

    @property
    def members_csv(self) -> Path:
        return self.raw_dir / "HSall_members.csv"

    @property
    def roster_json(self) -> Path:
        return self.raw_dir / "legislators-current.json"

    @property
    def committees_json(self) -> Path:
        return self.raw_dir / "committee-membership-current.json"


DEFAULT = Config()
