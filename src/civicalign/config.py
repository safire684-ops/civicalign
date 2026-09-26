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

    # Pillar 1 floor-vote evidence (pipeline.py): the Voteview column that orients
    # each roll call's Yea side. "nokken_poole_dim1" is re-estimated within each
    # Congress. (Pillars 4-6 use pillars_score_column, nominate_dim1, below.)
    score_column: str = "nokken_poole_dim1"

    # Presidential elections the snapshot's election-results file must contain
    # (agents/sources.py). No published figure uses them since the old Pillar 4
    # peer comparison was retired; the file is still fetched until the update
    # automation is revised.
    election_years: tuple[int, ...] = (2016, 2020, 2024)

    # The American Ideology Project wave the snapshot checks must find (2020 is the
    # most recent published wave; surveys fielded 2017-2021). Pillars 4-6 choose
    # their wave with pillars_aip_wave below.
    ideology_year: int = 2020

    # A senator needs at least this many recorded votes before their position is
    # published. A score built on a handful of votes moves sharply with each new
    # one, so a newly seated member would otherwise be shown a volatile number.
    #
    # Nobody in the 119th is currently below it -- the fewest is 37 votes and the
    # median is 873 -- so today this guard changes nothing. It exists for the
    # opening months of a new Congress, when it changes everything.
    min_roll_calls: int = 30

    # The Census estimate year the snapshot's population file must contain
    # (agents/sources.py). Pillar 5 chooses its weights with pillar5_population_year.
    population_year: int = 2024

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
