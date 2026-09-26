"""Pillar 1 (Engine A) floor-vote evidence: one function, so tests and tools share a path.

Reads the roster, the senators' scores, the Senate roll calls and member votes,
and the bill-status archives, and returns the per-senator vote records
(receipts) and the most recent passage votes with every senator's Yea or Nay.
The Pillars 4-6 figures are not here: they live in civicalign.ideology and are
published by civicalign.build_pages.
"""
from dataclasses import dataclass

from .config import Config, DEFAULT
from .receipts import FloorVote, Receipt, receipts, recent_floor_votes
from .sources import billflow, rollcalls, rosters, voteview


@dataclass
class Report:
    config: Config
    senators: dict[str, rosters.Senator]
    scores: dict[str, float]
    unscored: list[rosters.Senator]
    # one recorded vote per senator, chosen by a fixed rule blind to how they voted
    receipts: dict[str, Receipt]
    # the most recent passage votes, every senator's Yea or Nay on each; no summary
    floor_votes: list[FloorVote]


def run(cfg: Config = DEFAULT) -> Report:
    roster = rosters.load_current_senators(cfg.roster_json)
    scores = voteview.load_scores(cfg.members_csv, cfg.congress, roster,
                                  cfg.score_column, cfg.min_roll_calls)
    rcpts: dict[str, Receipt] = {}
    fvs: list[FloorVote] = []
    if cfg.rollcalls_csv.exists() and cfg.votes_csv.exists():
        bills = billflow.load_bills(cfg.billflow_zip, cfg.billflow_house_zip)
        icpsr = rollcalls.icpsr_to_bioguide(cfg.members_csv, cfg.congress)
        member_votes = rollcalls.load_votes(cfg.votes_csv, icpsr)
        rcs = rollcalls.load_rollcalls(cfg.rollcalls_csv, member_votes, scores)
        rcpts = receipts(rcs, member_votes, bills, scores, cfg.congress)
        fvs = recent_floor_votes(rcs, member_votes, bills, cfg.congress)
    return Report(config=cfg, senators=roster, scores=scores, unscored=voteview.unscored(roster, scores),
                  receipts=rcpts, floor_votes=fvs)
