"""Section 2: the shared one-dimensional metric space X = [-1.0, +1.0].

-1.0 is the progressive boundary, +1.0 the conservative boundary. Senator
coordinates arrive already inside X because DW-NOMINATE constrains members to a
unit circle, so no rescaling is applied on the senator side.

CAVEAT worth repeating on the public methodology page: this whole space assumes
politics fits on one line. That holds up well for congressional roll-call voting,
where one dimension explains most of the variance. It holds up considerably worse
for voters, whose economic and social views do not line up as neatly. So "this
senator is 0.4 away from their state" is a real measurement of one particular
summary of politics -- not of politics.
"""
import statistics as st

LOWER = -1.0
UPPER = 1.0
MAX_DISTANCE = UPPER - LOWER  # 2.0


def contains(x: float) -> bool:
    return LOWER <= x <= UPPER


def median(values) -> float:
    """Median over X. With an even count this averages the two middle values,
    which is what a 100-member chamber requires (the 50th and 51st)."""
    vals = [v for v in values if v is not None]
    if not vals:
        raise ValueError("no values to take a median of")
    return st.median(vals)


def nth_from_left(values, n: int) -> float:
    """The nth-most-progressive coordinate, 1-indexed.

    n=60 is the cloture pivot for legislation: the senator who actually decides
    whether a bill advances, who is not the median senator.
    """
    vals = sorted(v for v in values if v is not None)
    if not 1 <= n <= len(vals):
        raise ValueError(f"n={n} outside 1..{len(vals)}")
    return vals[n - 1]
