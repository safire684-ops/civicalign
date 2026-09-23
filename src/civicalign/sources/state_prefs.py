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
import csv
from abc import ABC, abstractmethod
from pathlib import Path


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


class AmericanIdeologyProject(StateCoordinateSource):
    """The bridged joint-scaling dataset the specification requires.

    Tausanovitch & Warshaw, American Ideology Project, "Subnational ideology and
    presidential vote estimates (v2022)", Harvard Dataverse doi:10.7910/DVN/BQKU4M,
    file aip_states_ideology_v2022a.tab, column `mrp_ideology`.

    These are multilevel regression and poststratification estimates of state
    publics' ideology. CAVEAT: the project's codebook says the survey ideal points
    "lack an absolute scale" and are standardised to mean 0, standard deviation 1
    on their own; nothing ties that scale to Voteview's Nokken-Poole scores. Both
    happen to fall inside [-1, +1], so the tool puts them on one line as an
    approximation and labels the distance a rough comparison, not a measurement.

    Both sides sit inside the metric space X = [-1, +1]. State publics are far
    more tightly clustered (-0.47 to +0.35) than senators (-0.74 to +0.94), which
    is the expected shape: legislators are more polarised than the people who
    elect them, and that difference is the substance of Pillar 4, not an artifact.

    Each estimate carries `mrp_ideology_se`, so uncertainty CAN be propagated into
    the alignment gap -- unlike the senator scores, whose standard errors Voteview
    does not publish.
    """

    name = "american_ideology_project"
    is_bridged = True
    citation = ("Tausanovitch & Warshaw, American Ideology Project v2022, "
                "Harvard Dataverse doi:10.7910/DVN/BQKU4M")

    def __init__(self, path: Path, year: int = 2020,
                 populations: dict[str, int] | None = None) -> None:
        self.year = year
        self._coords: dict[str, float] = {}
        self._se: dict[str, float] = {}
        self._pop: dict[str, int] = {}
        self._load(path)
        if populations:
            # current Census estimates replace the file's static 2020 counts, so
            # the national centre tracks domestic migration
            self._pop = {k: populations[k] for k in self._coords if k in populations}
            self.population_source = "Census Bureau vintage 2024 estimates"
        else:
            self.population_source = "2020 census counts carried in the ideology file"

    def _load(self, path: Path) -> None:
        with path.open() as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if int(row["presidential_year"]) != self.year:
                    continue
                usps = row["abb"].strip().strip('"')
                self._coords[usps] = float(row["mrp_ideology"])
                self._se[usps] = float(row["mrp_ideology_se"])
                self._pop[usps] = int(row["population_2020"])
        if not self._coords:
            raise ValueError(f"no {self.year} rows found in {path}")

    def state(self, usps: str) -> float | None:
        return self._coords.get(usps)

    def state_se(self, usps: str) -> float | None:
        return self._se.get(usps)

    def national(self, electorate: str) -> float | None:
        """Population-weighted centre of the national public.

        The specification asks for the median voter of the aggregate national
        electorate. This dataset resolves to states, not individuals, so the
        population-weighted mean of state centres is the available approximation.
        The distribution of state centres is close to symmetric, so mean and median
        land within about 0.01 of each other, but it is an approximation and is
        labelled as one. DC is included: its residents are part of the national
        public even though they elect no senator.
        """
        if not self._coords:
            return None
        total = sum(self._pop[s] for s in self._coords)
        return sum(self._coords[s] * self._pop[s] for s in self._coords) / total


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


def build(name: str, path: Path | None = None, year: int = 2020,
          populations: dict[str, int] | None = None) -> StateCoordinateSource:
    if name == "unavailable":
        return Unavailable()
    if name == "american_ideology_project":
        if path is None:
            raise ValueError("american_ideology_project needs the data file path")
        return AmericanIdeologyProject(path, year, populations)
    raise ValueError(f"unknown state source {name!r}")
