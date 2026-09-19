"""Section 3 / Pillar 4: senator vs. state alignment gap.

Two deliberate departures from the spec, both explained below.
"""
from dataclasses import dataclass

from .space import MAX_DISTANCE


@dataclass(frozen=True)
class Alignment:
    bioguide: str
    name: str
    state: str
    senator_coord: float
    state_coord: float | None

    # Signed, senator minus state. The spec takes an absolute value immediately;
    # that throws away the most damning finding available. Two senators with an
    # identical gap of 0.5 can be in completely different situations: one is more
    # extreme than their state in the same direction, the other has crossed past
    # the middle to the OPPOSITE side of their own electorate. Keep the sign and
    # derive the absolute value for display.
    signed_gap: float | None
    abs_gap: float | None

    # The spec's score: (1 - gap/2) * 100. Retained for continuity, but it
    # compresses badly. The theoretical max distance is 2.0, while real senators
    # span about -0.75..+0.94 and state medians will bunch near the middle, so
    # real gaps run 0..~1.1 and this score almost never leaves 45-100%. Every
    # senator looks at least half-aligned, including the worst ones.
    spec_score: float | None

    # Preferred presentation: rank among all scored senators. "Worse aligned than
    # 94 of 100 senators" is both honest and legible.
    rank: int | None = None
    of: int | None = None

    @property
    def crosses_over(self) -> bool | None:
        """True when senator and state sit on opposite sides of centre --
        qualitatively worse than merely being more extreme."""
        if self.state_coord is None:
            return None
        return (self.senator_coord > 0) != (self.state_coord > 0)


def alignment(bioguide, name, state, senator_coord, state_coord) -> Alignment:
    if state_coord is None:
        return Alignment(bioguide, name, state, senator_coord, None, None, None, None)
    signed = senator_coord - state_coord
    absolute = abs(signed)
    return Alignment(
        bioguide=bioguide,
        name=name,
        state=state,
        senator_coord=senator_coord,
        state_coord=state_coord,
        signed_gap=signed,
        abs_gap=absolute,
        spec_score=(1 - absolute / MAX_DISTANCE) * 100,
    )


def rank_all(alignments: list[Alignment]) -> list[Alignment]:
    """Attach percentile-style ranks; rank 1 = worst aligned."""
    scored = [a for a in alignments if a.abs_gap is not None]
    scored.sort(key=lambda a: -a.abs_gap)
    total = len(scored)
    ranked = [
        Alignment(
            a.bioguide, a.name, a.state, a.senator_coord, a.state_coord,
            a.signed_gap, a.abs_gap, a.spec_score, rank=i + 1, of=total,
        )
        for i, a in enumerate(scored)
    ]
    return ranked + [a for a in alignments if a.abs_gap is None]
