"""One vote from each senator's record, chosen by a neutral rule.

WHAT IS SHOWN
-------------
For every scored senator: how they voted on the bill with the most Senate floor
votes this Congress, on its passage vote where one exists. The bill's name, what
the vote was on, the date, the senator's recorded Yea or Nay, and a link to the
roll call at Voteview, which is where the vote data comes from.

THE SELECTION RULE
------------------
Candidate roll calls are those on a titled bill where the senator cast a Yea or
Nay. They are ranked: passage votes first, then cloture, then anything else;
within that, the bill with the most floor votes this Congress; ties broken by the
higher roll number (the more recent vote). The top-ranked roll call is shown.
Nothing about the senator's state, the vote's dividing line, or which way the
senator voted enters the choice, so the same rule picks the same bill for every
senator who voted on it.

WHAT THIS IS NOT
----------------
It is not evidence about the state's voters. A state's survey position summarises
one dimension of opinion; it does not say whether the state's voters supported or
opposed any particular bill, and no such claim is made or derived here. An earlier
version selected votes where the senator's vote disagreed with a "state side"
inferred from the vote's dividing line. That inference was unsupported and has
been removed. It is also not a claim about what the bill did in the world; that
plain-English consequence is Pillar 1's job and is not fabricated here.
"""
from dataclasses import dataclass
from typing import Iterable

from .sources.billflow import Bill
from .sources.rollcalls import RollCall

VOTEVIEW_ROLLCALL = "https://voteview.com/rollcall/RS{congress}{roll:04d}"


@dataclass(frozen=True)
class Receipt:
    bioguide: str
    roll: int
    date: str
    bill: str
    label: str
    question: str
    senator_vote: str      # "Yea" / "Nay", exactly as recorded
    url: str               # the roll call at Voteview


def _rank(rc: RollCall, votes_per_bill: dict[str, int]) -> tuple:
    q = rc.question.lower()
    kind = 0 if "passage" in q else (1 if "cloture" in q else 2)
    return (kind, -votes_per_bill.get(rc.bill, 0), -rc.number)


def receipts(rollcalls: list[RollCall], votes: dict[int, dict[str, bool]],
             bills: dict[str, Bill], senators: Iterable[str], congress: int,
             ) -> dict[str, Receipt]:
    """One vote per listed senator, by the rule in the module docstring."""
    wanted = set(senators)
    votes_per_bill: dict[str, int] = {}
    for rc in rollcalls:
        if rc.bill:
            votes_per_bill[rc.bill] = votes_per_bill.get(rc.bill, 0) + 1

    candidates: dict[str, list[RollCall]] = {}
    for rc in rollcalls:
        if not rc.bill:
            continue
        b = bills.get(rc.bill)
        if b is None or not (b.short or b.title):
            continue
        for bioguide in votes.get(rc.number, {}):
            if bioguide in wanted:
                candidates.setdefault(bioguide, []).append(rc)

    out: dict[str, Receipt] = {}
    for bioguide, rcs in candidates.items():
        rc = min(rcs, key=lambda r: _rank(r, votes_per_bill))
        b = bills[rc.bill]
        out[bioguide] = Receipt(
            bioguide=bioguide, roll=rc.number, date=rc.date, bill=rc.bill,
            label=b.short or b.title, question=rc.question,
            senator_vote="Yea" if votes[rc.number][bioguide] else "Nay",
            url=VOTEVIEW_ROLLCALL.format(congress=congress, roll=rc.number),
        )
    return out
