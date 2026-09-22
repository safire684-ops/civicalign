"""Senate floor votes from Voteview: every roll call's dividing line, and how
each senator voted on it.

Two files. S119_rollcalls.csv has one row per roll call with `nominate_mid_1`,
the point on the ideological line that best separates the Yeas from the Nays
(the cutpoint), plus the bill number and what the vote was on. S119_votes.csv has
one row per senator per roll call with how they voted.

WHICH SIDE IS YEA
-----------------
The cutpoint says where the line falls, not which side voted Yea. Rather than
rely on a sign convention, the Yea side is found from the votes themselves: if
the senators who voted Yea sit on average to the right of those who voted Nay,
Yea is the right-hand side. 892 of the 897 roll calls resolve this way; the rest
are near-unanimous and carry no line worth placing.
"""
import csv
import statistics as st
from dataclasses import dataclass
from pathlib import Path

YEA = {"1", "2", "3"}
NAY = {"4", "5", "6"}


@dataclass(frozen=True)
class RollCall:
    number: int
    date: str
    bill: str            # normalised, e.g. "HR1", "S5"; "" if none
    question: str        # "On Passage of the Bill", "On the Cloture Motion", ...
    result: str
    cutpoint: float | None
    yea_is_right: bool | None   # None when the vote was too lopsided to tell


def _norm_bill(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def icpsr_to_bioguide(members_csv: Path, congress: int) -> dict[str, str]:
    out = {}
    with members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["congress"] == str(congress) and row["chamber"] == "Senate":
                out[row["icpsr"]] = row["bioguide_id"]
    return out


def load_votes(votes_csv: Path, icpsr_map: dict[str, str]) -> dict[int, dict[str, bool]]:
    """{roll number: {bioguide: voted_yea}} for Yea/Nay votes only."""
    out: dict[int, dict[str, bool]] = {}
    with votes_csv.open() as fh:
        for row in csv.DictReader(fh):
            b = icpsr_map.get(row["icpsr"])
            if not b:
                continue
            code = row["cast_code"]
            if code in YEA:
                out.setdefault(int(row["rollnumber"]), {})[b] = True
            elif code in NAY:
                out.setdefault(int(row["rollnumber"]), {})[b] = False
    return out


def load_rollcalls(rollcalls_csv: Path, votes: dict[int, dict[str, bool]],
                   scores: dict[str, float]) -> list[RollCall]:
    out = []
    with rollcalls_csv.open() as fh:
        for row in csv.DictReader(fh):
            n = int(row["rollnumber"])
            cp = float(row["nominate_mid_1"]) if row["nominate_mid_1"] else None
            side = None
            v = votes.get(n, {})
            yeas = [scores[b] for b, y in v.items() if y and b in scores]
            nays = [scores[b] for b, y in v.items() if not y and b in scores]
            if len(yeas) >= 3 and len(nays) >= 3:
                side = st.fmean(yeas) > st.fmean(nays)
            out.append(RollCall(
                number=n, date=row["date"], bill=_norm_bill(row["bill_number"]),
                question=row["vote_question"].strip(), result=row["vote_result"].strip(),
                cutpoint=cp, yea_is_right=side,
            ))
    return out
