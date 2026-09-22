"""A real vote where a senator's gap from their state showed up.

For each floor vote we know the dividing line (cutpoint) and which side voted
Yea. A state's position falls on one side of that line, which implies the vote a
senator sitting exactly at the state's position would most likely have cast. A
"receipt" is a vote where the senator cast the other one.

WHAT THIS IS NOT
----------------
It is not a claim about what the bill did in the world. That plain-English
consequence is Pillar 1's job and is not fabricated here. The receipt names the
bill, what the vote was on, how the senator voted, and which way the state's
position points. All four are in the public record.

The vote chosen is the most recognisable one available: passage votes on the
bills with the most floor action, then cloture, then anything else.
"""
from dataclasses import dataclass

from .sources.billflow import Bill
from .sources.rollcalls import RollCall


@dataclass(frozen=True)
class Receipt:
    bioguide: str
    roll: int
    date: str
    bill: str
    label: str
    question: str
    senator_vote: str      # "Yea" / "Nay"
    state_implied: str     # "Yea" / "Nay"
    cutpoint: float


def _rank(rc: RollCall, bills: dict[str, Bill], votes_per_bill: dict[str, int]) -> tuple:
    q = rc.question.lower()
    kind = 0 if "passage" in q else (1 if "cloture" in q else 2)
    return (kind, -votes_per_bill.get(rc.bill, 0), -rc.number)


def receipts(rollcalls: list[RollCall], votes: dict[int, dict[str, bool]],
             bills: dict[str, Bill], state_pos: dict[str, float | None],
             ) -> dict[str, Receipt]:
    """One receipt per senator who has a divergent vote on a titled bill."""
    votes_per_bill: dict[str, int] = {}
    for rc in rollcalls:
        if rc.bill:
            votes_per_bill[rc.bill] = votes_per_bill.get(rc.bill, 0) + 1

    candidates: dict[str, list[RollCall]] = {}
    for rc in rollcalls:
        if rc.cutpoint is None or rc.yea_is_right is None or not rc.bill:
            continue
        b = bills.get(rc.bill)
        if b is None or not (b.short or b.title):
            continue
        for bioguide, voted_yea in votes.get(rc.number, {}).items():
            s_k = state_pos.get(bioguide)
            if s_k is None:
                continue
            state_yea = (s_k > rc.cutpoint) == rc.yea_is_right
            if voted_yea != state_yea:
                candidates.setdefault(bioguide, []).append(rc)

    out: dict[str, Receipt] = {}
    for bioguide, rcs in candidates.items():
        rc = min(rcs, key=lambda r: _rank(r, bills, votes_per_bill))
        b = bills[rc.bill]
        voted_yea = votes[rc.number][bioguide]
        out[bioguide] = Receipt(
            bioguide=bioguide, roll=rc.number, date=rc.date, bill=rc.bill,
            label=b.short or b.title, question=rc.question,
            senator_vote="Yea" if voted_yea else "Nay",
            state_implied="Nay" if voted_yea else "Yea",
            cutpoint=rc.cutpoint,
        )
    return out
