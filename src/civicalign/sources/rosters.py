"""Authoritative current-membership data from unitedstates/congress-legislators.

This is the ONLY thing that decides who currently holds a seat. Voteview's
member file cannot answer that question -- see sources/voteview.py.
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Senator:
    bioguide: str
    name: str
    state: str
    party: str  # "Republican" | "Democrat" | "Independent"
    # The caucus the roster records for an Independent ("Democrat" for Sanders
    # and King today); None for members of the two parties and for anyone whose
    # term carries no caucus field. Read, never inferred.
    caucus: str | None = None


@dataclass(frozen=True)
class CommitteeMember:
    bioguide: str
    title: str | None  # "Chairman", "Ranking Member", "Vice Chairman", or None


def load_current_senators(path: Path) -> dict[str, Senator]:
    """Exactly the 100 people seated right now, keyed by bioguide id."""
    people = json.loads(path.read_text())
    out: dict[str, Senator] = {}
    for p in people:
        term = p["terms"][-1]
        if term["type"] != "sen":
            continue
        bioguide = p["id"]["bioguide"]
        out[bioguide] = Senator(
            bioguide=bioguide,
            name=p["name"].get("official_full") or p["name"]["last"],
            state=term["state"],
            party=term.get("party", "Unknown"),
            caucus=term.get("caucus"),
        )
    return out


def load_senate_committees(path: Path) -> dict[str, list[CommitteeMember]]:
    """Senate standing (SS*) and select (SL*) committees only.

    Four-character codes are top-level committees; longer codes are
    subcommittees, which would double-count their parent's members.
    """
    raw = json.loads(path.read_text())
    out: dict[str, list[CommitteeMember]] = {}
    for code, members in raw.items():
        if not code.startswith(("SS", "SL")) or len(code) != 4:
            continue
        out[code] = [
            CommitteeMember(bioguide=m["bioguide"], title=m.get("title"))
            for m in members
            if m.get("bioguide")
        ]
    return out


def majority_party(senators: dict[str, Senator]) -> str:
    counts: dict[str, int] = {}
    for s in senators.values():
        counts[s.party] = counts.get(s.party, 0) + 1
    return max(counts, key=counts.get)


CHAIR_TITLES = {"Chairman", "Chair", "Chairwoman"}


def find_chair(members: list[CommitteeMember]) -> CommitteeMember | None:
    return next((m for m in members if m.title in CHAIR_TITLES), None)
