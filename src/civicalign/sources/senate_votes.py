"""The Senate's own record of a roll-call vote (senate.gov LIS XML).

One file per vote, keyed by (congress, session, vote number). It is the
first-party statement of WHAT was voted on: the question, the document or
amendment before the Senate, the result, the tallies, and every member's vote
by LIS id. Voteview is a secondary copy; the two are cross-checked, never merged.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

URL = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote{congress}{session}/vote_{congress}_{session}_{number:05d}.xml"


def senate_vote_url(congress: int, session: int, number: int) -> str:
    return URL.format(congress=congress, session=session, number=number)


@dataclass(frozen=True)
class SenateVote:
    congress: int
    session: int
    number: int                 # the Senate's vote number within the session
    date: str                   # YYYY-MM-DD, from vote_date
    time: str                   # "04:42 AM" as recorded
    question: str               # "On Passage of the Bill"
    question_text: str          # "On Passage of the Bill S. 2"
    title: str                  # "S. 2, As Amended"
    document_text: str
    result: str                 # "Bill Passed"
    result_text: str            # "Bill Passed (52-47)"
    majority_requirement: str   # "1/2", "3/5", "2/3"
    document_type: str          # "S.", "H.R.", "S.J.Res.", "H.J.Res.", "PN", ""
    document_number: str
    amendment_number: str
    amendment_to_document: str
    yeas: int
    nays: int
    present: int
    absent: int
    votes: dict[str, str]       # LIS id -> "Yea" | "Nay" | "Present" | "Not Voting"
    members: dict[str, dict]    # LIS id -> {last, first, state, party} as the Senate records them

    @property
    def measure(self) -> str:
        """Normalised measure id in Voteview's spelling: S2, HR6500, SJRES18, HJRES88."""
        return normalise_measure(self.document_type, self.document_number)

    @property
    def as_amended(self) -> bool:
        return "as amended" in self.title.lower()


def normalise_measure(doc_type: str, number: str) -> str:
    t = re.sub(r"[^A-Za-z]", "", doc_type or "").upper()
    n = re.sub(r"[^0-9]", "", number or "")
    return f"{t}{n}" if t and n else ""


def _date(raw: str) -> str:
    # "June 5, 2026,  04:42 AM"
    m = re.match(r"\s*([A-Za-z]+ \d{1,2}, \d{4})", raw or "")
    if not m:
        return ""
    return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")


def _time(raw: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2} [AP]M)\s*$", raw or "")
    return m.group(1) if m else ""


def parse_senate_vote(path: Path) -> SenateVote:
    r = ET.parse(path).getroot()
    if r.tag != "roll_call_vote":
        raise ValueError(f"{path.name}: not a Senate roll_call_vote document")
    g = lambda tag: (r.findtext(tag) or "").strip()
    d = r.find("document"); a = r.find("amendment"); c = r.find("count")
    dg = lambda tag: (d.findtext(tag) or "").strip() if d is not None else ""
    ag = lambda tag: (a.findtext(tag) or "").strip() if a is not None else ""
    cg = lambda tag: int((c.findtext(tag) or "0").strip() or 0) if c is not None else 0
    votes, members = {}, {}
    for m in r.findall("members/member"):
        lis = (m.findtext("lis_member_id") or "").strip()
        if lis:
            votes[lis] = (m.findtext("vote_cast") or "").strip()
            members[lis] = {"last": (m.findtext("last_name") or "").strip(), "first": (m.findtext("first_name") or "").strip(),
                            "state": (m.findtext("state") or "").strip(), "party": (m.findtext("party") or "").strip()}
    return SenateVote(
        congress=int(g("congress")), session=int(g("session")), number=int(g("vote_number")),
        date=_date(g("vote_date")), time=_time(g("vote_date")),
        question=g("question"), question_text=g("vote_question_text"), title=g("vote_title"),
        document_text=g("vote_document_text"), result=g("vote_result"), result_text=g("vote_result_text"),
        majority_requirement=g("majority_requirement"),
        document_type=dg("document_type"), document_number=dg("document_number"),
        amendment_number=ag("amendment_number"), amendment_to_document=ag("amendment_to_document_number"),
        yeas=cg("yeas"), nays=cg("nays"), present=cg("present"), absent=cg("absent"),
        votes=votes, members=members,
    )
