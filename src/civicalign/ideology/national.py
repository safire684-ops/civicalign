"""The national public estimate: UNRESOLVED.

Pillar 5 compares the Senate with the national electorate, and Pillar 6 each
committee with it. Two things are missing:

1. A definition. The American Ideology Project publishes STATE estimates. A
   national centre could be defined several ways, and they are not the same
   quantity:
     - the population-weighted mean of the state estimates;
     - a population-weighted median of the state estimates;
     - an individual-level national estimate from the underlying survey (a
       median of respondents, poststratified), which the state file does not
       contain;
     - any of these weighted by adults, citizens, registered voters or voters
       rather than residents.
   None has been chosen. A population-weighted average of state estimates is
   NOT treated as the national median.

2. A bridge (see bridge.py). Even once defined, the national estimate is on the
   survey's scale and cannot be compared with the Senate until a bridge places
   it on the legislator scale.

So national() returns NOT_AVAILABLE, and so does everything that depends on it.
"""
from .result import not_available

CANDIDATE_DEFINITIONS = (
    "population-weighted mean of state estimates",
    "population-weighted median of state estimates",
    "individual-level national estimate from the underlying survey (not in the state file)",
    "any of the above weighted by adults, citizens, registered voters or voters instead of residents",
)


def national(bridge: dict | None = None) -> dict:
    return not_available("the national public estimate is unresolved: no definition has been chosen "
                         f"(candidates: {'; '.join(CANDIDATE_DEFINITIONS)}), and no bridge places it on the legislator scale",
                         "legislator scale", definition_status="UNRESOLVED")
