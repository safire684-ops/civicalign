"""State and national median-voter coordinates -- the bridging problem.

WHY THIS IS A SEPARATE, SWAPPABLE MODULE
----------------------------------------
DW-NOMINATE places senators on a scale derived from how they vote on bills.
Surveys place voters on a scale derived from what they tell a pollster. Those
are two different rulers with two different zero points. Subtracting one from
the other is subtracting Celsius from Fahrenheit: it returns a number, and the
number means nothing.

"Bridging" means finding something present in both datasets so the rulers can be
lined up. Everything in Pillars 4 and the national half of 5 depends on it.
Nothing else in this codebase does -- committee drift, chamber pivots and party
medians are all senator-to-senator and live on one ruler already.

So this module is deliberately the only place that needs replacing, and the
default deliberately REFUSES to guess.
"""
from abc import ABC, abstractmethod


class StateCoordinateSource(ABC):
    """Maps a state (and the nation) into the same space as senator scores."""

    name: str
    is_bridged: bool  # False => outputs are a proxy and must be labelled as such
    citation: str

    @abstractmethod
    def state(self, usps: str) -> float | None:
        """Median voter coordinate for a state, or None if unavailable."""

    @abstractmethod
    def national(self, electorate: str) -> float | None:
        """Median voter coordinate for the national electorate, or None."""


class Unavailable(StateCoordinateSource):
    """The honest default: no bridged data loaded, so Pillar 4 does not run.

    This exists so that a missing dataset produces a visible gap in the product
    rather than a plausible-looking fabricated number.
    """

    name = "unavailable"
    is_bridged = False
    citation = "none - no public-opinion source configured"

    def state(self, usps: str) -> float | None:
        return None

    def national(self, electorate: str) -> float | None:
        return None


class TausanovitchWarshaw(StateCoordinateSource):
    """Option A: published bridged MRP estimates. RECOMMENDED starting point.

    Tausanovitch & Warshaw (2013), "Measuring Constituent Policy Preferences in
    Congress, State Legislatures, and Cities", Journal of Politics. Their
    estimates are built to be comparable with legislator scores, so the bridge is
    already done and peer-reviewed -- which matters more for a public
    accountability site than doing it ourselves.

    TODO: drop their state table in data/raw/ and fill in _load(). One linear map
    onto the senator scale, fit with senators as shared anchors.
    """

    name = "tausanovitch_warshaw"
    is_bridged = True
    citation = "Tausanovitch & Warshaw 2013, J. of Politics"

    def __init__(self) -> None:
        self._coords: dict[str, float] = {}
        raise NotImplementedError(
            "Download the T&W state estimates into data/raw/ and implement _load(). "
            "Until then Config.state_source stays 'unavailable'."
        )

    def state(self, usps: str) -> float | None:
        return self._coords.get(usps)

    def national(self, electorate: str) -> float | None:
        raise NotImplementedError


class LinearProxy(StateCoordinateSource):
    """Option C: a state ideology index stretched onto [-1, 1].

    NOT A BRIDGE. Correlated with the right answer, but the resulting distances
    are not real distances. Usable as an internal placeholder; if it ever reaches
    the frontend, the frontend must say so, because the whole pitch of this
    project is mathematical rigor.
    """

    name = "linear_proxy"
    is_bridged = False
    citation = "proxy - e.g. Berry et al. citizen ideology, linearly rescaled"

    def __init__(self, index: dict[str, float], lo: float = 0.0, hi: float = 100.0):
        # index values run lo..hi (Berry et al. is 0..100, liberal to conservative)
        self._coords = {
            st: ((v - lo) / (hi - lo)) * 2.0 - 1.0 for st, v in index.items()
        }

    def state(self, usps: str) -> float | None:
        return self._coords.get(usps)

    def national(self, electorate: str) -> float | None:
        if not self._coords:
            return None
        # NOTE: this is the median of state medians, which is NOT the same as the
        # population-weighted median of individual voters. The spec asks for the
        # latter. Another reason this class is a placeholder.
        vals = sorted(self._coords.values())
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def build(name: str) -> StateCoordinateSource:
    if name == "unavailable":
        return Unavailable()
    if name == "tausanovitch_warshaw":
        return TausanovitchWarshaw()
    raise ValueError(f"unknown state source {name!r} (linear_proxy needs an index passed in)")
