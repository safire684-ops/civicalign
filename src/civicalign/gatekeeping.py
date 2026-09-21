"""Pillar 6 by revealed behaviour: which bills a committee buries.

Every bill inherits the ideological position of the senator who sponsored it.
For each committee we then ask how often a liberal-sponsored bill survives versus
a conservative-sponsored one. The difference is the Gatekeeping Bias Index.

THE CORRECTION THAT MATTERS
---------------------------
A raw index mostly measures which party holds the majority, not anything specific
to the committee. Chamber-wide in the 119th, liberal-sponsored bills are reported
out 6.6% of the time and conservative-sponsored 9.0% -- a baseline gap of +2.4
points that applies everywhere. Subtracting it leaves the part that is about this
committee, exactly as the state-lean measure is reported against the Senate's own
average rather than the nation's.
"""
import statistics as st
from dataclasses import dataclass

from .sources.billflow import BillReferral


@dataclass(frozen=True)
class Gatekeeping:
    code: str
    lib_referred: int
    lib_reported: int
    con_referred: int
    con_reported: int
    baseline_gbi: float

    @property
    def survival_liberal(self) -> float:
        return 100 * self.lib_reported / self.lib_referred if self.lib_referred else 0.0

    @property
    def survival_conservative(self) -> float:
        return 100 * self.con_reported / self.con_referred if self.con_referred else 0.0

    @property
    def gbi(self) -> float:
        """Raw index: conservative survival minus liberal survival, in points."""
        return self.survival_conservative - self.survival_liberal

    @property
    def gbi_vs_baseline(self) -> float:
        """The committee-specific part, with chamber-wide majority control removed."""
        return self.gbi - self.baseline_gbi

    @property
    def referred(self) -> int:
        return self.lib_referred + self.con_referred

    @property
    def reported(self) -> int:
        return self.lib_reported + self.con_reported

    @property
    def is_reportable(self) -> bool:
        """Enough bills on both sides for the rates to mean anything.

        Below this a single bill moves the index by whole points.
        """
        return self.lib_referred >= 25 and self.con_referred >= 25


def gatekeeping(referrals: list[BillReferral],
                scores: dict[str, float]) -> tuple[list[Gatekeeping], float]:
    """Index per committee, plus the chamber-wide baseline it is measured against."""
    per: dict[str, dict[str, int]] = {}
    tot = {"lib_r": 0, "lib_p": 0, "con_r": 0, "con_p": 0}

    for ref in referrals:
        x = scores.get(ref.sponsor)
        if x is None:
            continue  # House sponsor, or a senator held back by the vote threshold
        side = "lib" if x < 0 else "con"
        d = per.setdefault(ref.committee,
                           {"lib_r": 0, "lib_p": 0, "con_r": 0, "con_p": 0})
        d[side + "_r"] += 1
        tot[side + "_r"] += 1
        if ref.reported:
            d[side + "_p"] += 1
            tot[side + "_p"] += 1

    base = ((100 * tot["con_p"] / tot["con_r"] if tot["con_r"] else 0.0)
            - (100 * tot["lib_p"] / tot["lib_r"] if tot["lib_r"] else 0.0))

    out = [
        Gatekeeping(code=code, lib_referred=d["lib_r"], lib_reported=d["lib_p"],
                    con_referred=d["con_r"], con_reported=d["con_p"],
                    baseline_gbi=base)
        for code, d in per.items()
    ]
    out.sort(key=lambda g: -g.gbi_vs_baseline)
    return out, base
