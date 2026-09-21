"""Senator ideological coordinates from Voteview (voteview.com, UCLA).

Two traps are handled here, both of which silently corrupt published numbers:

1. SEAT DOUBLE-COUNTING. Filtering the member file on `congress == 119` yields
   104 Senate rows for 100 seats, because mid-term turnover leaves the departed
   member in the file alongside their replacement (FL, OH, OK, SC as of the
   119th). All four extras were Republicans, so a naive chamber median comes out
   at +0.3645 instead of the correct +0.3100 -- a 0.045 artifact, which is a
   large slice of an apportionment skew that is itself only 0.1-0.3 wide.
   Guarded by requiring a roster and rejecting any state with >2 senators.

2. FROZEN SCORES. See Config.score_column.
"""
import csv
from pathlib import Path

from .rosters import Senator


class SeatCountError(ValueError):
    """Raised when the scored set does not look like a real Senate."""


def load_scores(
    members_csv: Path,
    congress: int,
    roster: dict[str, Senator],
    column: str,
    min_roll_calls: int = 0,
) -> dict[str, float]:
    """Coordinate per seated senator, keyed by bioguide.

    `roster` is required, not optional: it is what makes the seat count correct.
    """
    scores: dict[str, float] = {}
    with members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] != "Senate" or row["congress"] != str(congress):
                continue
            bioguide = row["bioguide_id"]
            if bioguide not in roster:  # departed member, or a replacement's predecessor
                continue
            # too few votes: the estimate is not yet stable enough to publish
            try:
                cast = int(row.get("nominate_number_of_votes") or 0)
            except ValueError:
                cast = 0
            if cast < min_roll_calls:
                continue

            raw = row.get(column, "")
            if raw not in ("", None):
                scores[bioguide] = float(raw)
    _validate(scores, roster)
    return scores


def _validate(scores: dict[str, float], roster: dict[str, Senator]) -> None:
    per_state: dict[str, int] = {}
    for bioguide in scores:
        st = roster[bioguide].state
        per_state[st] = per_state.get(st, 0) + 1

    crowded = {s: n for s, n in per_state.items() if n > 2}
    if crowded:
        raise SeatCountError(f"more than 2 senators scored for {crowded}")

    if len(scores) > 100:
        raise SeatCountError(f"{len(scores)} senators scored; a Senate has 100")

    for value in scores.values():
        if not -1.0 <= value <= 1.0:
            raise SeatCountError(f"coordinate {value} outside the metric space [-1, 1]")


def unscored(roster: dict[str, Senator], scores: dict[str, float]) -> list[Senator]:
    """Seated senators with no published coordinate.

    Either Voteview has no score for them yet, or they are below the vote
    threshold. The front end shows these as "not enough voting record yet"
    rather than drawing a number.
    """
    return [s for b, s in roster.items() if b not in scores]


def roll_calls_cast(members_csv: Path, congress: int,
                    roster: dict[str, Senator]) -> dict[str, int]:
    """Votes cast per seated senator, for reporting why someone is unscored."""
    out: dict[str, int] = {}
    with members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if (row["chamber"] == "Senate" and row["congress"] == str(congress)
                    and row["bioguide_id"] in roster):
                try:
                    out[row["bioguide_id"]] = int(row.get("nominate_number_of_votes") or 0)
                except ValueError:
                    out[row["bioguide_id"]] = 0
    return out
