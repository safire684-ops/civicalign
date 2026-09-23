"""Section 3 / Pillar 4: a senator's position and their state's estimate, kept separate.

The senator coordinate is a Voteview (Nokken-Poole) score. The state coordinate is
an American Ideology Project survey estimate. They are two measurement systems
without a validated bridge, so this module deliberately computes NOTHING that
combines them: no gap, no score, no rank, no "crosses over". It only carries the
two numbers side by side so the page can show each on its own scale.

A direct senator-versus-state alignment measure requires a validated statistical
bridge between voter and legislator scales. CivicAlign does not currently have
that bridge. Earlier versions of this module computed |x - s|, a percentage score,
a rank and a crossing flag; they were removed as invalid, not merely hidden.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Positions:
    bioguide: str
    name: str
    state: str
    senator_coord: float          # Voteview scale
    state_coord: float | None     # survey scale; None when no estimate exists


def positions(bioguide, name, state, senator_coord, state_coord) -> Positions:
    return Positions(bioguide, name, state, senator_coord, state_coord)
