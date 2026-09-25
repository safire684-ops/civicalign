"""Pillars 4, 5 and 6: pure calculations over the versioned inputs.

Every function takes plain records and returns quantities in the result.py
shape (value, status, units, reason). No function reads files, and nothing is
rescaled: senator quantities are in Voteview nominate_dim1 units, public
estimates in the American Ideology Project's own units, and the two are never
combined without a bridge.

Pillar 4, per seated senator
  senator_score          nominate_dim1
  state_public_estimate  AIP estimate and its standard error, AIP units
  state_on_senator_scale NOT_AVAILABLE unless a bridge places it there
  distance               |senator_score - state_on_senator_scale|; NOT_AVAILABLE without it

Pillar 5
  chamber_median                  median of active senators' nominate_dim1
  population_weighted_center      the configured weighting method (below)
  equal_state_representation_difference
                                  chamber_median - population_weighted_center, sign kept
  national_public, chamber_public_gap
                                  NOT_AVAILABLE (national definition unresolved, no bridge)

Pillar 6, per standing committee
  committee_median                median of current members' nominate_dim1
  committee_senate_drift          committee_median - chamber_median, sign kept
  committee_public_drift          NOT_AVAILABLE (no national estimate, no bridge)

"Active senators" are the senators the roster lists as seated who have a
Voteview score; a seated senator Voteview has not scored is listed as unscored
and left out of every median.
"""
import statistics
from fractions import Fraction

from . import bridge as B
from .result import available, not_available

LEGISLATOR_UNITS = "Voteview DW-NOMINATE first dimension ({column})"
PUBLIC_UNITS = "American Ideology Project mrp_ideology, wave {wave} (survey scale; not the Voteview scale)"


class InputError(ValueError):
    pass


def split_active(senators: list[dict], column: str) -> tuple[list[dict], list[dict]]:
    """(seated senators with a score in `column`, seated senators without one)."""
    seated = [s for s in senators if s["seated"]]
    return [s for s in seated if s[column] is not None], [s for s in seated if s[column] is None]


# ---- the population-weighted centre: named, swappable methods ------------------------------

def senator_weights(seated: list[dict], populations: dict[str, int]) -> dict[str, Fraction]:
    """Each seated senator's share of their state's population: the state's
    population divided by the number of senators it currently has seated (so a
    state with a vacancy gives its whole weight to the sitting senator).
    Exact fractions, so a tie at exactly half the total is detected exactly."""
    per_state: dict[str, int] = {}
    for s in seated:
        per_state[s["state"]] = per_state.get(s["state"], 0) + 1
    missing = sorted(st for st in per_state if st not in populations)
    if missing:
        raise InputError(f"no population for {missing}")
    return {s["bioguide_id"]: Fraction(populations[s["state"]], per_state[s["state"]]) for s in seated}


def weighted_median_v1(points: list[tuple[float, Fraction]]) -> float:
    """population_weighted_median_v1: sort by score; walk the cumulative weight;
    the centre is the first score at which it reaches half the total weight. If
    it lands exactly on half, the centre is the average of that score and the
    next -- the same rule as an ordinary median with an even count."""
    if not points:
        raise InputError("no weighted points")
    pts = sorted(points, key=lambda p: p[0])
    half = sum(w for _, w in pts) / 2
    cum = Fraction(0)
    for i, (x, w) in enumerate(pts):
        cum += w
        if cum == half:
            return (x + pts[i + 1][0]) / 2
        if cum > half:
            return x
    raise InputError("weights did not reach half their total")   # pragma: no cover


WEIGHTING_METHODS = {
    "population_weighted_median_v1": {
        "function": weighted_median_v1,
        "status": "CURRENT_METHOD_NOT_FINAL",
        "definition": ("weighted median of active senators' scores; each senator weighted by their state's population "
                       "divided by the number of senators the state has seated; a cumulative weight exactly at half "
                       "the total averages that score with the next"),
        "open_questions": ("median or mean; residents or adults, citizens or voters; how to treat unscored senators, "
                           "whose share of their state's weight is currently left out with them"),
    },
}


# ---- Pillar 4 ----------------------------------------------------------------------------

def pillar4(senators: list[dict], publics: dict[str, dict], bridge: dict, column: str, wave: int) -> list[dict]:
    out = []
    lunits, punits = LEGISLATOR_UNITS.format(column=column), PUBLIC_UNITS.format(wave=wave)
    for s in sorted((s for s in senators if s["seated"]), key=lambda s: (s["state"], s["bioguide_id"])):
        score = (available(s[column], lunits) if s[column] is not None
                 else not_available("Voteview has not published a score for this senator yet", lunits))
        pub = publics.get(s["state"])
        public = (available(pub["estimate"], punits, standard_error=pub["standard_error"], survey_period=pub["survey_period"])
                  if pub else not_available(f"no AIP estimate for {s['state']} in wave {wave}", punits))
        common = B.to_common(bridge, pub["estimate"] if pub else None, pub["standard_error"] if pub else None)
        if common["status"] == "NOT_AVAILABLE" or score["status"] == "NOT_AVAILABLE":
            distance = not_available("needs the state estimate on the senator scale: " + (common["reason"] or score["reason"]), lunits)
        else:   # pragma: no cover - unreachable while no bridge method exists
            distance = {**available(abs(score["value"] - common["value"]), lunits), "status": common["status"]}
        out.append({"bioguide_id": s["bioguide_id"], "name": s["name"], "state": s["state"],
                    "senator_score": score, "state_public_estimate": public,
                    "state_on_senator_scale": common, "distance": distance})
    return out


# ---- Pillar 5 ----------------------------------------------------------------------------

def pillar5(senators: list[dict], populations: dict[str, int], national: dict, column: str, method: str) -> dict:
    if method not in WEIGHTING_METHODS:
        raise InputError(f"unknown weighting method {method!r}; known: {sorted(WEIGHTING_METHODS)}")
    active, unscored = split_active(senators, column)
    if not active:
        raise InputError("no active senators with a score")
    units = LEGISLATOR_UNITS.format(column=column)
    median = statistics.median(s[column] for s in active)
    weights = senator_weights(active, populations)
    m = WEIGHTING_METHODS[method]
    center = m["function"]([(s[column], weights[s["bioguide_id"]]) for s in active])
    gap_reason = "needs the national public estimate on the senator scale: " + national["reason"]
    return {
        "active_senators": len(active),
        "unscored_seated_senators": [s["bioguide_id"] for s in unscored],
        "chamber_median": available(median, units, n=len(active)),
        "population_weighted_center": available(center, units, method=method, method_status=m["status"],
                                                definition=m["definition"], open_questions=m["open_questions"]),
        "equal_state_representation_difference": available(median - center, units,
                                                           formula="chamber_median - population_weighted_center"),
        "national_public": national,
        "chamber_public_gap": not_available(gap_reason, units),
    }


# ---- Pillar 6 ----------------------------------------------------------------------------

def pillar6(committees: dict[str, list[str]], senators: list[dict], chamber_median: float, national: dict, column: str) -> dict:
    """committees: committee_id -> bioguide ids of current members."""
    units = LEGISLATOR_UNITS.format(column=column)
    by_id = {s["bioguide_id"]: s for s in senators if s["seated"]}
    out = {}
    for cid in sorted(committees):
        members = committees[cid]
        scored = [by_id[b] for b in members if b in by_id and by_id[b][column] is not None]
        left_out = [b for b in members if b not in by_id or by_id[b][column] is None]
        if scored:
            cm = statistics.median(s[column] for s in scored)
            median = available(cm, units, n=len(scored))
            drift = available(cm - chamber_median, units, formula="committee_median - chamber_median")
        else:
            median = not_available("no scored current members", units)
            drift = not_available("no committee median", units)
        out[cid] = {"members_listed": len(members), "members_scored": len(scored), "members_left_out": left_out,
                    "committee_median": median, "committee_senate_drift": drift,
                    "committee_public_drift": not_available("needs the national public estimate on the senator scale: "
                                                            + national["reason"], units)}
    return out
