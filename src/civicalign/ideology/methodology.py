"""The methodology registry: one entry for every number Pillars 4-6 display.

Each entry says where the number comes from (raw source), what is done to the
source (transformation), how it is calculated (formula), which recorded
versions it depends on, and its limitations. The page builder and the tests
read this registry; a number with no entry may not be displayed.

Entry fields
    id              stable name, e.g. "p5.weighted_mean"
    label           plain-language name
    pillar          4, 5 or 6
    views           where it is shown: senator_state (Pillar 4), senate_nation (Pillar 5),
                    committee_senate_nation (Pillar 6)
    placement       main (shown in the view) or details (methodology/details only)
    kind            quantity  a result.py quantity in the result record
                    count     a whole number in the result record
                    reference a Pillar 4 anchor from the reference_anchors table (not a result)
    paths           where it sits in a result record's "results"; "*" stands for any
                    senator (Pillar 4) or any committee (Pillar 6)
    units           what the number is measured in
    decimals        how many decimals to display (None: shown as given, e.g. a count)
    sources         keys of SOURCES
    transformation  what is done to the raw source before the formula
    formula         how the number is calculated
    versions        keys of the result record's "versions" that trace it (for a
                    reference: the fields of the anchor record that do)
    limitations     what the number does not tell you
    not_available   when and why it is NOT_AVAILABLE (None if it always has a value)
    extra_fields    other fields of the quantity shown with it (e.g. a standard error)

Everything here describes the PRIMARY Pillar 5 method, population_weighted_mean_v1;
coverage() refuses a result record computed with any other configured method.
"""
from . import anchors as A
from . import ingest as I
from . import national as N
from . import pillars as P

PRIMARY_METHOD = "population_weighted_mean_v1"
SECONDARY_METHOD = "population_weighted_median_v1"
VIEWS = ("senator_state", "senate_nation", "committee_senate_nation")
PLACEMENTS = ("main", "details")
KINDS = ("quantity", "count", "reference")

SOURCES = {
    "voteview": {"name": I.VOTEVIEW, "stored_in": "senator_ideology (reference_anchors for the anchors)",
                 "citation": "Lewis, Poole, Rosenthal, Boche, Rudkin and Sonnet, Voteview: Congressional Roll-Call Votes Database"},
    "roster": {"name": I.ROSTER, "stored_in": "senator_ideology (the seated flag)", "citation": None},
    "aip": {"name": I.AIP, "stored_in": "constituency_ideology", "citation": f"Tausanovitch and Warshaw, {I.AIP_URL}"},
    "census": {"name": I.CENSUS, "stored_in": "state_population", "citation": None},
    "committees": {"name": I.COMMITTEES, "stored_in": "committee_membership_events", "citation": None},
    "bridge": {"name": "CivicAlign bridge registry (bridge.py)", "stored_in": "ideology_bridge", "citation": None},
    "national": {"name": "CivicAlign national public estimate (national.py): UNRESOLVED", "stored_in": None, "citation": None},
}

LEGISLATOR = "Voteview DW-NOMINATE first dimension (nominate_dim1)"
PUBLIC = "American Ideology Project mrp_ideology, wave 2020 (survey scale; not the Voteview scale)"

SCORE_LIMITS = (
    "One number summarises a voting record along the main dimension of roll-call voting; it does not capture every issue.",
    "Estimated from recorded roll-call votes only: missed votes, and bills that never reached a vote, are not included.",
    "Voteview re-estimates scores as new votes are recorded, so a score can shift slightly between source snapshots.",
    "The score describes a voting pattern relative to other members of Congress; it is not a judgment of any person.",
)
CANDIDATE_LIMITS = (
    "A candidate method, not a settled scientific definition (status CANDIDATE_METHOD_NOT_FINAL).",
    "Weights count residents (Census July 1 estimates), not adults, citizens or voters.",
    "An unscored seated senator's share of their state's weight is left out with them.",
    "Open questions: " + P.OPEN_QUESTIONS + ".",
)
MEDIAN_LIMITS = (
    "The Senate is split by an empty stretch between the two parties; a median can jump across it when a few senators "
    "change, so the median is shown only as a secondary comparison.",
)
NO_BRIDGE = ("needs a bridge placing public estimates on the senator scale; the active bridge none-v0 has status NONE, "
             "so no such conversion exists")
NO_NATIONAL = ("needs a national public estimate, whose definition is unresolved (national.py lists the candidates), "
               "and a bridge placing it on the senator scale")
COMMITTEE_LIMITS = (
    "Descriptive only: where a committee's current members sit compared with the Senate. It says nothing about what "
    "a committee did or decided, or why any bill passed or failed.",
    "Membership is what CivicAlign observed in a source snapshot on the stated date, not an official appointment date.",
    "With an even number of members whose two middle members sit on opposite sides of the party gap, the median falls "
    "where no member sits.",
    "Standing committees only; subcommittees, select and joint committees are not included.",
)
P5_VERSIONS = ("congress", "measurement_date", "legislator_model", "population", "weighting")


def _e(id, label, pillar, views, placement, kind, paths, units, decimals, sources, transformation, formula, versions,
       limitations, not_available=None, extra_fields=()):
    return {"id": id, "label": label, "pillar": pillar, "views": tuple(views), "placement": placement, "kind": kind,
            "paths": tuple(paths), "units": units, "decimals": decimals, "sources": tuple(sources),
            "transformation": transformation, "formula": formula, "versions": tuple(versions),
            "limitations": tuple(limitations), "not_available": not_available, "extra_fields": tuple(extra_fields)}


_M, _D = f"pillar5.details.methods.{PRIMARY_METHOD}", f"pillar5.details.methods.{SECONDARY_METHOD}"

ENTRIES = (
    # ---- Pillar 4: senator / state --------------------------------------------------------
    _e("p4.senator_score", "Senator's voting-record score", 4, ["senator_state"], "main", "quantity",
       ["pillar4.*.senator_score"], LEGISLATOR, 3, ["voteview", "roster"],
       "The senator's row for this Congress in Voteview's member file, joined to the current roster (seated senators only).",
       "nominate_dim1 as Voteview publishes it; no rescaling.",
       ["congress", "legislator_model"], SCORE_LIMITS + (
           "Senators with few recorded votes have less certain scores.",),
       not_available="a seated senator Voteview has not scored yet has no score (never a predecessor's)"),
    _e("p4.state_public_estimate", "State public's estimated ideology", 4, ["senator_state"], "main", "quantity",
       ["pillar4.*.state_public_estimate"], PUBLIC, 2, ["aip"],
       "The state's row for survey wave 2020 in the American Ideology Project state file, in the survey's own units.",
       "mrp_ideology as published (multilevel regression and poststratification of survey responses), with its standard error.",
       ["public_model"], (
           "On the survey's own scale: it cannot be compared with senator scores, and no distance between them is shown.",
           "An estimate with uncertainty: the standard error is shown beside it.",
           "Wave 2020 pools survey responses from its stated survey period, not a single day.",
           "Which population it describes (adults, citizens or voters) is defined by the American Ideology Project, not by CivicAlign.",
       ), not_available="no American Ideology Project estimate for the state in the configured wave",
       extra_fields=["standard_error", "survey_period"]),
    _e("p4.state_on_senator_scale", "State public on the senator scale", 4, ["senator_state"], "main", "quantity",
       ["pillar4.*.state_on_senator_scale"], "legislator scale", 3, ["aip", "bridge"],
       "The state estimate converted by the active bridge.", "bridge.to_common(active bridge, estimate, standard error).",
       ["bridge", "public_model"], ("Requires a validated (or clearly provisional) bridge; none exists.",),
       not_available=NO_BRIDGE),
    _e("p4.distance", "Distance between senator and state public", 4, ["senator_state"], "main", "quantity",
       ["pillar4.*.distance"], LEGISLATOR, 3, ["voteview", "aip", "bridge"],
       "Both numbers on the senator scale.", "|senator score - state public on the senator scale|.",
       ["bridge", "legislator_model", "public_model"], ("Not calculated until a bridge exists.",),
       not_available=NO_BRIDGE),
    _e("p4.reference_anchor", "Reference figures on the senator scale", 4, ["senator_state"], "main", "reference",
       [], LEGISLATOR, 3, ["voteview"],
       ("Each figure's rows in Voteview's member file under the Voteview id of their Senate record (House and Senate "
        "rows only; Voteview's separate President rows are excluded)."),
       "nominate_dim1 as Voteview publishes it, which must be the same on every row of that id; no rescaling.",
       ["source_version", "source_sha256", "retrieved_at", "congresses", "number_of_votes"], (
           "Visual reference points only: never an input to any calculation, weight, centre, median, mean or drift.",
           "Joe Biden's and JD Vance's scores come only from their Senate votes; a presidency or vice presidency casts no "
           "roll-call votes, and Voteview's separate President estimate is not used.",
           "Bernie Sanders is also a current senator, so he appears among the senators too; his reference point is the "
           "same number, estimated from his House and Senate votes together.",
           "JD Vance's Senate record is short (two Congresses), so his score is less certain than the others'.",
           "Voteview gives each legislator one score for a whole career; comparing records from different decades "
           "relies on DW-NOMINATE's assumptions about how the scale holds over time.",
           "The three were chosen as recognisable names spread across the scale; the choice is editorial and says "
           "nothing about any senator being like or unlike them.",
       ) + SCORE_LIMITS[:3]),

    # ---- Pillar 5: Senate / nation -------------------------------------------------------------
    _e("p5.active_senators", "Senators included", 5, ["senate_nation"], "main", "count",
       ["pillar5.active_senators"], "senators", None, ["voteview", "roster"],
       "Seated senators (roster) who have a Voteview score.", "count of seated, scored senators.",
       ["congress", "legislator_model"], ("A seated senator Voteview has not scored yet is listed separately and left out.",)),
    _e("p5.plain_mean", "Senate average (each senator counted once)", 5, ["senate_nation"], "main", "quantity",
       ["pillar5.plain_center", "pillar5.details.chamber_mean", f"{_M}.plain_center"], LEGISLATOR, 3, ["voteview", "roster"],
       "Active senators' nominate_dim1.", "sum of scores / number of active senators.",
       P5_VERSIONS, SCORE_LIMITS[:3] + ("Every senator counts the same, whatever the size of their state.",)),
    _e("p5.weighted_mean", "Senate average weighted by population represented", 5, ["senate_nation"], "main", "quantity",
       ["pillar5.population_weighted_center", f"{_M}.population_weighted_center"], LEGISLATOR, 3,
       ["voteview", "roster", "census"],
       ("Each active senator weighted by their state's population divided by the number of senators the state has "
        "seated (a vacancy gives the sitting senator the whole state)."),
       "sum of (score x weight) / sum of weights  [" + P.WEIGHTING_METHODS[PRIMARY_METHOD]["definition"] + "]",
       P5_VERSIONS, SCORE_LIMITS[:3] + CANDIDATE_LIMITS),
    _e("p5.weighting_difference", "Difference made by population weighting", 5, ["senate_nation"], "main", "quantity",
       ["pillar5.population_weighting_difference", f"{_M}.population_weighting_difference"], LEGISLATOR, 3,
       ["voteview", "roster", "census"],
       "The two averages above.", "Senate average - population-weighted Senate average (sign kept).",
       P5_VERSIONS, CANDIDATE_LIMITS + (
           "Positive means the population-weighted average sits to the left of (below) the plain average on the Voteview scale.",)),
    _e("p5.plain_median", "Senate median", 5, ["senate_nation", "committee_senate_nation"], "details", "quantity",
       ["pillar5.details.chamber_median", f"{_D}.plain_center"], LEGISLATOR, 3, ["voteview", "roster"],
       "Active senators' nominate_dim1.", "median of active senators' scores (with 100 senators, the average of the middle two).",
       P5_VERSIONS, SCORE_LIMITS[:3] + MEDIAN_LIMITS + (
           "Pillar 6 measures each committee against this Senate median.",)),
    _e("p5.weighted_median", "Senate median weighted by population represented", 5, ["senate_nation"], "details", "quantity",
       [f"{_D}.population_weighted_center"], LEGISLATOR, 3, ["voteview", "roster", "census"],
       "The same weights as the weighted average.",
       "first score at which the running total of weight reaches half of all weight  ["
       + P.WEIGHTING_METHODS[SECONDARY_METHOD]["definition"] + "]",
       P5_VERSIONS, MEDIAN_LIMITS + CANDIDATE_LIMITS),
    _e("p5.median_difference", "Difference made by population weighting (medians)", 5, ["senate_nation"], "details", "quantity",
       [f"{_D}.population_weighting_difference"], LEGISLATOR, 3, ["voteview", "roster", "census"],
       "The two medians above.", "Senate median - population-weighted Senate median (sign kept).",
       P5_VERSIONS, MEDIAN_LIMITS + CANDIDATE_LIMITS),
    _e("p5.national_public", "National public centre", 5, ["senate_nation", "committee_senate_nation"], "main", "quantity",
       ["pillar5.national_public"], "legislator scale", 3, ["national", "bridge"],
       "Not defined yet.", "None chosen: " + "; ".join(N.CANDIDATE_DEFINITIONS) + ".",
       ["national_public", "bridge"], ("A population-weighted average of state estimates is not treated as the national median.",),
       not_available=NO_NATIONAL),
    _e("p5.chamber_public_gap", "Gap between Senate and national public", 5, ["senate_nation"], "main", "quantity",
       ["pillar5.chamber_public_gap"], LEGISLATOR, 3, ["voteview", "national", "bridge"],
       "The Senate centre and the national public centre on the senator scale.", "Senate centre - national public centre.",
       ["national_public", "bridge"], ("Not calculated until the national estimate is defined and a bridge exists.",),
       not_available=NO_NATIONAL),

    # ---- Pillar 6: committee / Senate / nation ----------------------------------------------------
    _e("p6.members_listed", "Committee members listed", 6, ["committee_senate_nation"], "main", "count",
       ["pillar6.*.members_listed"], "senators", None, ["committees"],
       "Current members of the standing committee in the latest observed membership.", "count of current members.",
       ["committee_membership"], COMMITTEE_LIMITS[1:2]),
    _e("p6.members_scored", "Committee members with a score", 6, ["committee_senate_nation"], "main", "count",
       ["pillar6.*.members_scored"], "senators", None, ["committees", "voteview", "roster"],
       "Current members who are seated senators with a Voteview score.", "count of those members.",
       ["committee_membership", "legislator_model"], ("Members without a score are listed and left out of the median.",)),
    _e("p6.committee_median", "Committee median", 6, ["committee_senate_nation"], "main", "quantity",
       ["pillar6.*.committee_median"], LEGISLATOR, 3, ["committees", "voteview", "roster"],
       "Current members' nominate_dim1 (seated, scored members only).", "median of those scores.",
       ["committee_membership", "legislator_model", "congress"], SCORE_LIMITS[:3] + COMMITTEE_LIMITS,
       not_available="a committee with no scored current members has no median"),
    _e("p6.committee_senate_drift", "Committee median minus Senate median", 6, ["committee_senate_nation"], "main", "quantity",
       ["pillar6.*.committee_senate_drift"], LEGISLATOR, 3, ["committees", "voteview", "roster"],
       "The committee median and the Senate median.", "committee median - Senate median (sign kept).",
       ["committee_membership", "legislator_model", "congress"], COMMITTEE_LIMITS + (
           "Positive means the committee median sits to the right of (above) the Senate median on the Voteview scale.",),
       not_available="no committee median"),
    _e("p6.committee_public_drift", "Committee median minus national public centre", 6, ["committee_senate_nation"], "main",
       "quantity", ["pillar6.*.committee_public_drift"], LEGISLATOR, 3, ["committees", "voteview", "national", "bridge"],
       "The committee median and the national public centre on the senator scale.",
       "committee median - national public centre.", ["committee_membership", "national_public", "bridge"],
       COMMITTEE_LIMITS[:1], not_available=NO_NATIONAL),
)
REGISTRY = {e["id"]: e for e in ENTRIES}


# ---- lookups and checks ------------------------------------------------------------------------

def normalise(path: str) -> str:
    """A concrete result path with the senator index or committee id replaced by "*"."""
    parts = path.split(".")
    if len(parts) > 1 and parts[0] in ("pillar4", "pillar6"):
        parts[1] = "*"
    return ".".join(parts)


def _by_path() -> dict[str, dict]:
    return {p: e for e in ENTRIES for p in e["paths"]}


def entry_for(path: str) -> dict:
    """The registry entry for a result path, or KeyError: an unregistered number may not be displayed."""
    e = _by_path().get(normalise(path))
    if e is None:
        raise KeyError(f"no methodology entry for {path!r}: it may not be displayed")
    return e


def walk(results: dict, prefix: str = "") -> tuple[list[str], list[str]]:
    """(paths of every quantity, paths of every whole number) in a result record's results."""
    quantities, counts = [], []
    items = results.items() if isinstance(results, dict) else enumerate(results)
    for k, v in items:
        p = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and "status" in v and "units" in v:
            quantities.append(p)
        elif isinstance(v, (dict, list)):
            q, c = walk(v, p)
            quantities += q
            counts += c
        elif isinstance(v, int) and not isinstance(v, bool):
            counts.append(p)
    return quantities, counts


def problems() -> list[str]:
    """Problems with the registry itself."""
    out = []
    if len(REGISTRY) != len(ENTRIES):
        out.append("duplicate entry ids")
    seen = {}
    for e in ENTRIES:
        for f in ("label", "units", "transformation", "formula", "limitations", "sources", "versions", "views"):
            if not e[f]:
                out.append(f"{e['id']}: {f} is empty")
        if e["pillar"] not in (4, 5, 6) or e["placement"] not in PLACEMENTS or e["kind"] not in KINDS:
            out.append(f"{e['id']}: pillar, placement or kind is not recognised")
        if set(e["views"]) - set(VIEWS):
            out.append(f"{e['id']}: unknown view")
        if set(e["sources"]) - set(SOURCES):
            out.append(f"{e['id']}: unknown source")
        if (e["kind"] == "reference") != (not e["paths"]):
            out.append(f"{e['id']}: a reference has no result path, and every other entry has one")
        for p in e["paths"]:
            if p in seen:
                out.append(f"{p} is claimed by {seen[p]} and {e['id']}")
            seen[p] = e["id"]
    if len([e for e in ENTRIES if e["kind"] == "reference"]) != 1:
        out.append("exactly one reference entry: the Pillar 4 anchors")
    return out


def coverage(record: dict) -> list[str]:
    """Problems between the registry and a result record: every displayed number
    has an entry, every entry has its number, and every version it cites exists."""
    out = []
    configured = record["results"]["pillar5"]["configured_method"]
    if configured != PRIMARY_METHOD:
        out.append(f"the registry describes {PRIMARY_METHOD} as the primary method, but the record used {configured}")
    quantities, counts = walk(record["results"])
    by_path = _by_path()
    found = {normalise(p) for p in quantities + counts}
    for kind, paths in (("quantity", quantities), ("count", counts)):
        for p in sorted({normalise(p) for p in paths}):
            e = by_path.get(p)
            if e is None or e["kind"] != kind:
                out.append(f"{kind} {p} has no methodology entry")
    for e in ENTRIES:
        if e["kind"] == "reference":
            continue
        for p in e["paths"]:
            if p not in found:
                out.append(f"{e['id']}: {p} is not in the record")
        missing = [v for v in e["versions"] if v not in record["versions"]]
        if missing:
            out.append(f"{e['id']}: versions {missing} are not in the record")
    return out


def anchor_problems(anchor_rows: list[dict]) -> list[str]:
    """Problems between the reference entry and the stored anchors."""
    e = next(e for e in ENTRIES if e["kind"] == "reference")
    out = [] if len(anchor_rows) == A.COUNT else [f"expected {A.COUNT} anchors, found {len(anchor_rows)}"]
    for r in anchor_rows:
        missing = [v for v in e["versions"] if v not in r]
        if missing:
            out.append(f"anchor {r.get('anchor_id')}: fields {missing} missing")
    return out
