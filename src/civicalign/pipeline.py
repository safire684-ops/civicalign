"""Wires the sections together. One function, so tests and CLI share a path."""
from dataclasses import dataclass

from .config import Config, DEFAULT
from .sources import elections, population, rosters, state_prefs, voteview
from .alignment import Alignment, alignment, rank_all
from .chamber import ChamberStats, chamber_stats
from .committees import CommitteeStats, committee_stats
from .representation import (ChamberLean, CommitteeLean, Fit, Representation,
                             chamber_lean, committee_lean, representations)


@dataclass
class Report:
    config: Config
    senators: dict[str, rosters.Senator]
    scores: dict[str, float]
    unscored: list[rosters.Senator]
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

    @property
    def pillar4_available(self) -> bool:
        return any(a.abs_gap is not None for a in self.alignments)


def run(cfg: Config = DEFAULT) -> Report:
    roster = rosters.load_current_senators(cfg.roster_json)
    scores = voteview.load_scores(cfg.members_csv, cfg.congress, roster, cfg.score_column)
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

    aligns = rank_all([
        alignment(b, roster[b].name, roster[b].state, v, src.state(roster[b].state))
        for b, v in scores.items()
    ])

    return Report(
        config=cfg, senators=roster, scores=scores,
        unscored=voteview.unscored(roster, scores),
        chamber=ch, committees=committees, alignments=aligns, state_source=src,
        election=lean, fit=fit, chamber_lean=chlean, representation=reps,
        committee_leans=cleans,
    )
