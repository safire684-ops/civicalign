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

    # State partisan lean from real election results. This is what makes Pillar 4
    # work WITHOUT bridged survey data: see representation.py. Election results are
    # public behaviour measured directly, so no scaling assumption is needed.
    # Averaged over three presidential cycles, each weighted equally. One
    # election is noisier and over-reacts to a single candidate; three is steadier
    # but slower to reflect a state that is genuinely shifting. StateLean.swing
    # exposes how much movement the average is hiding for each state.
    election_years: tuple[int, ...] = (2016, 2020, 2024)

    # Where state median-voter coordinates come from. See sources/state_prefs.py.
    #   "american_ideology_project" -> the bridged joint-scaling estimates the
    #       specification requires: state publics on the SAME ideological scale as
    #       roll-call scores, so the absolute distance in Pillar 4 is a legal
    #       subtraction. Tausanovitch & Warshaw, doi:10.7910/DVN/BQKU4M.
    #   "unavailable" -> Pillar 4 refuses to compute.
    state_source: str = "american_ideology_project"

    # Which wave of the bridged estimates. 2020 is the most recent PUBLISHED
    # wave: v2022 is the newest release of the dataset and its 2020 wave is built
    # from surveys fielded 2017-2021. No 2024 wave exists to ingest.
    ideology_year: int = 2020

    # A senator needs at least this many recorded votes before their position is
    # published. A score built on a handful of votes moves sharply with each new
    # one, so a newly seated member would otherwise be shown a volatile number.
    #
    # Nobody in the 119th is currently below it -- the fewest is 37 votes and the
    # median is 873 -- so today this guard changes nothing. It exists for the
    # opening months of a new Congress, when it changes everything.
    min_roll_calls: int = 30

    # Census vintage for population weighting of US_m. Re-weighting each year keeps
    # the national centre current as people move between states, instead of freezing
    # it at one decennial count.
    population_year: int = 2024

    # A committee CCD smaller than this is not a finding. Observed CCDs run
    # 0.01-0.31 while internal committee spreads run 1.07-1.68, and with ~20
    # members the median lands exactly on one senator's score, so the metric is
    # quantized. Anything under this threshold gets flagged, not published.
    ccd_noise_floor: float = 0.10

    raw_dir: Path = field(default=RAW)
    processed_dir: Path = field(default=PROCESSED)

    # ---- Engine B (Pillars 4-6) -------------------------------------------------
    # The legislator score Pillars 4-6 use. nominate_dim1 is the default by
    # decision; nokken_poole_dim1 is stored beside it as extra data only.
    pillars_score_column: str = "nominate_dim1"
    # Standing committees only: four-character codes with this prefix (SS*).
    # Select (SL*) and joint committees and subcommittees are not included.
    standing_committee_prefix: str = "SS"
    # The versioned, append-only input and result tables.
    ideology_dir: Path = field(default=ROOT / "data" / "ideology")
    # Which American Ideology Project wave is shown for each state (all waves are stored).
    pillars_aip_wave: int = 2020
    # The bridge from public-opinion estimates to the legislator scale. "none-v0"
    # is status NONE: no senator-to-public comparison is computed.
    active_bridge_version: str = "none-v0"
    # Pillar 5's population-weighted Senate centre: the PRIMARY method, which
    # gives the main comparison (plain Senate mean vs population-weighted Senate
    # mean). The weighted median (population_weighted_median_v1) is computed and
    # stored as a secondary comparison for methodology/details. Neither is a
    # settled scientific definition. See ideology/pillars.py WEIGHTING_METHODS.
    pillar5_weighting_method: str = "population_weighted_mean_v1"
    # Census measurement year and vintage for the weights.
    pillar5_population_year: int = 2024
    pillar5_population_vintage: str = "Vintage 2024"

    @property
    def billflow_zip(self) -> Path:
        return self.raw_dir / f"BILLSTATUS-{self.congress}-s.zip"

    @property
    def billflow_house_zip(self) -> Path:
        return self.raw_dir / f"BILLSTATUS-{self.congress}-hr.zip"

    # Joint resolutions, for Pillar 1's vote binding (non-critical sources).
    @property
    def billstatus_sjres_zip(self) -> Path:
        return self.raw_dir / f"BILLSTATUS-{self.congress}-sjres.zip"

    @property
    def billstatus_hjres_zip(self) -> Path:
        return self.raw_dir / f"BILLSTATUS-{self.congress}-hjres.zip"

    # Pillar 1 binding artefacts: raw fetches (ignored by git) and the tracked bindings.
    @property
    def explain_raw_dir(self) -> Path:
        return self.raw_dir / "explanations"

    @property
    def bindings_dir(self) -> Path:
        return ROOT / "data" / "explanations" / str(self.congress)

    @property
    def rollcalls_csv(self) -> Path:
        return self.raw_dir / f"S{self.congress}_rollcalls.csv"

    @property
    def votes_csv(self) -> Path:
        return self.raw_dir / f"S{self.congress}_votes.csv"

    @property
    def population_csv(self) -> Path:
        return self.raw_dir / "NST-EST2024-ALLDATA.csv"

    @property
    def ideology_tab(self) -> Path:
        return self.raw_dir / "aip_states_ideology_v2022a.tab"

    @property
    def elections_csv(self) -> Path:
        return self.raw_dir / "mit_president_1976_2024.csv"

    @property
    def members_csv(self) -> Path:
        return self.raw_dir / "HSall_members.csv"

    @property
    def roster_json(self) -> Path:
        return self.raw_dir / "legislators-current.json"

    @property
    def committees_json(self) -> Path:
        return self.raw_dir / "committee-membership-current.json"

    # Official committee names and codes (Engine B: Pillar 6 committee names).
    @property
    def committee_list_json(self) -> Path:
        return self.raw_dir / "committees-current.json"


DEFAULT = Config()
