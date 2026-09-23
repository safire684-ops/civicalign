"""Pillar 6, Metric 1: where the bills a committee let through actually divided
the Senate.

A committee's members tell you who sits there. The bills it reported out, and
where their floor votes split the chamber, tell you what it did. For each
committee, take every floor roll call on a bill that committee reported, and the
median of their cutpoints is where the Senate split on that committee's bills.
Its distance from the Senate median is the drift. (It is a Voteview-scale figure
and is never compared with the survey-scale public estimate.)

Sample sizes are small, because most floor action in a session is nominations
and House bills that no Senate committee reported. Committees under the minimum
are held back rather than shown on three data points.
"""
import statistics as st
from dataclasses import dataclass

from .sources.billflow import Bill
from .sources.rollcalls import RollCall


@dataclass(frozen=True)
class OutputIdeology:
    code: str
    n_votes: int
    coi: float
    vs_senate: float

    @property
    def is_reportable(self) -> bool:
        return self.n_votes >= 7


def output_ideology(rollcalls: list[RollCall], bills: dict[str, Bill],
                    chamber_median: float) -> list[OutputIdeology]:
    by_cmte: dict[str, list[float]] = {}
    for rc in rollcalls:
        if rc.cutpoint is None or not rc.bill:
            continue
        b = bills.get(rc.bill)
        if b is None:
            continue
        for code in b.reported_by:
            by_cmte.setdefault(code, []).append(rc.cutpoint)
    out = []
    for code, cps in by_cmte.items():
        m = st.median(cps)
        out.append(OutputIdeology(
            code=code, n_votes=len(cps), coi=m, vs_senate=m - chamber_median))
    out.sort(key=lambda o: -o.n_votes)
    return out
