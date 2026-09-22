"""Familiar bills placed on the ideological line, so the scale means something.

A voter does not know what +0.3 is. They may know the Laken Riley Act or the
2025 reconciliation bill. Each floor vote has a cutpoint -- the point on the line
that best separates its Yeas from its Nays -- so a bill can be placed where its
votes divided the Senate. The bills with the most floor votes are the ones that
dominated the session, which is a fair proxy for "recognisable".
"""
import statistics as st
from dataclasses import dataclass

from .sources.billflow import Bill
from .sources.rollcalls import RollCall


@dataclass(frozen=True)
class Landmark:
    key: str
    label: str           # what a voter would call it
    cutpoint: float      # median cutpoint across its floor votes
    votes: int
    passed: bool


def _label(b: Bill) -> str:
    if b.short:
        return b.short
    t = b.title
    return t if len(t) <= 60 else t[:57].rsplit(" ", 1)[0] + "…"


def landmarks(rollcalls: list[RollCall], bills: dict[str, Bill],
              min_votes: int = 7, limit: int = 8) -> list[Landmark]:
    by_bill: dict[str, list[RollCall]] = {}
    for rc in rollcalls:
        if rc.bill and rc.cutpoint is not None:
            by_bill.setdefault(rc.bill, []).append(rc)
    out = []
    for key, rcs in by_bill.items():
        b = bills.get(key)
        if b is None or not (b.short or b.title) or len(rcs) < min_votes:
            continue
        passed = any("Passage" in r.question and "Passed" in r.result for r in rcs)
        out.append(Landmark(key=key, label=_label(b),
                            cutpoint=st.median(r.cutpoint for r in rcs),
                            votes=len(rcs), passed=passed))
    out.sort(key=lambda l: -l.votes)
    return out[:limit]
