"""Wires the sections together. One function, so tests and CLI share a path."""
from dataclasses import dataclass

from .config import Config, DEFAULT
from .sources import (billflow, elections, population, rollcalls, rosters,
                      state_prefs, voteview)
from .alignment import Alignment, alignment, rank_all
from .chamber import ChamberStats, chamber_stats
from .committees import CommitteeStats, committee_stats
from .gatekeeping import Gatekeeping, gatekeeping
from .landmarks import Landmark, landmarks
from .output_ideology import OutputIdeology, output_ideology
from .receipts import Receipt, receipts
from .representation import (ChamberLean, CommitteeLean, Fit, Representation,
                             chamber_lean, committee_lean, representations)


@dataclass
class Report:
    config: Config
    senators: dict[str, rosters.Senator]
    scores: dict[str, float]
    unscored: list[rosters.Senator]
    votes_cast: dict[str, int]
    chamber: ChamberStats
    committees: list[CommitteeStats]
    alignments: list[Alignment]
    state_source: state_prefs.StateCoordinateSource

    # Pillar 4 via regression on real election results -- no bridging required.
    election: elections.ElectionLean
    fit: Fit
    chamber_lean: ChamberLean
    representation: list[Representation]
    committee_leans: list[CommitteeLean]

    # Pillar 6 by revealed behaviour: which bills each committee has sent on so far.
    gatekeeping: list[Gatekeeping]
    gatekeeping_baseline: float
    # Distinct bills behind the gatekeeping counts (a bill sent to two committees
    # is two referrals but one bill). Only bills whose sponsor has a score count,
    # matching the gatekeeping rows.
    bills_referred_unique: int
    bills_reported_unique: int

    # Floor votes: familiar bills on the scale, one revealing vote per senator,
    # and where each committee's reported bills divided the chamber.
    landmarks: list[Landmark]
    receipts: dict[str, Receipt]
    output_ideology: list[OutputIdeology]

    @property
    def pillar4_available(self) -> bool:
        return any(a.abs_gap is not None for a in self.alignments)


def run(cfg: Config = DEFAULT) -> Report:
    roster = rosters.load_current_senators(cfg.roster_json)
    scores = voteview.load_scores(cfg.members_csv, cfg.congress, roster,
                                  cfg.score_column, cfg.min_roll_calls)
    votes_cast = voteview.roll_calls_cast(cfg.members_csv, cfg.congress, roster)
    majority = rosters.majority_party(roster)

    pops = population.load_populations(cfg.population_csv, cfg.population_year)
    src = state_prefs.build(cfg.state_source, cfg.ideology_tab, cfg.ideology_year, pops)
    national = src.national(cfg.electorate)

    ch = chamber_stats(scores, roster, majority, cfg.cloture_threshold, national)
    chamber_mean = __import__("statistics").fmean(scores.values())

    lean = elections.load_mit_president(cfg.elections_csv, cfg.election_years)
    fit, reps = representations(scores, roster, lean)
    chlean = chamber_lean(scores, roster, lean)

    committees, cleans = [], []
    cmte_rosters = rosters.load_senate_committees(cfg.committees_json)
    for code, members in cmte_rosters.items():
        cl = committee_lean(code, members, scores, roster, lean, chlean.senate_lean)
        if cl:
            cleans.append(cl)
    for code, members in cmte_rosters.items():
        cs = committee_stats(
            code, members, scores, roster, ch.median, chamber_mean, majority,
            national_coord=national, noise_floor=cfg.ccd_noise_floor,
        )
        if cs:
            committees.append(cs)
    committees.sort(key=lambda c: -abs(c.ccd_mean))
    cleans.sort(key=lambda c: -abs(c.gap))

    gks: list[Gatekeeping] = []
    gk_base = 0.0
    n_bills = n_reported = 0
    if cfg.billflow_zip.exists():
        refs = billflow.load_referrals(cfg.billflow_zip)
        gks, gk_base = gatekeeping(refs, scores)
        scored_refs = [x for x in refs if x.sponsor in scores and x.committee.startswith("S")]
        n_bills = len({x.bill for x in scored_refs})
        n_reported = len({x.bill for x in scored_refs if x.reported})

    lms: list[Landmark] = []
    rcpts: dict[str, Receipt] = {}
    oi: list[OutputIdeology] = []
    if cfg.rollcalls_csv.exists() and cfg.votes_csv.exists():
        bills = billflow.load_bills(cfg.billflow_zip, cfg.billflow_house_zip)
        icpsr = rollcalls.icpsr_to_bioguide(cfg.members_csv, cfg.congress)
        member_votes = rollcalls.load_votes(cfg.votes_csv, icpsr)
        rcs = rollcalls.load_rollcalls(cfg.rollcalls_csv, member_votes, scores)
        lms = landmarks(rcs, bills)
        rcpts = receipts(rcs, member_votes, bills, scores, cfg.congress)
        oi = output_ideology(rcs, bills, ch.median, national)

    aligns = rank_all([
        alignment(b, roster[b].name, roster[b].state, v, src.state(roster[b].state))
        for b, v in scores.items()
    ])

    return Report(
        config=cfg, senators=roster, scores=scores,
        unscored=voteview.unscored(roster, scores), votes_cast=votes_cast,
        chamber=ch, committees=committees, alignments=aligns, state_source=src,
        election=lean, fit=fit, chamber_lean=chlean, representation=reps,
        committee_leans=cleans, gatekeeping=gks, gatekeeping_baseline=gk_base,
        bills_referred_unique=n_bills, bills_reported_unique=n_reported,
        landmarks=lms, receipts=rcpts, output_ideology=oi,
    )
