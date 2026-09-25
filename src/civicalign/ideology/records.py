"""The versioned input tables for Pillars 4-6, and their validators.

Every record carries where it came from (source, URL, the snapshot's content
key and SHA-256 for the file, and when CivicAlign first retrieved that content)
and whether it is a test fixture. A validator either returns no problems or
lists them; the store refuses a record that has any.

Tables
------
senator_ideology       one row per Senate member of a Congress in Voteview's
                       member file, plus any seated senator Voteview has not
                       scored yet. Both first-dimension scores are stored:
                       nominate_dim1 (the Pillars 4-6 default) and
                       nokken_poole_dim1 (extra data only). `seated` comes from
                       the congress-legislators roster. Key: bioguide_id, congress.

constituency_ideology  one row per geography per public-opinion model version:
                       the estimate, its standard error and the survey period,
                       in the source's OWN units. Nothing here is on the
                       Voteview scale. Key: geography_type, geography_id,
                       methodology_version.

ideology_bridge        a mapping from a public-opinion model into the legislator
                       model's space. Status NONE, PROVISIONAL or VALIDATED; the
                       fields a status requires are enforced. (Schema only in
                       Step 1; no bridge record is written until Step 2.)
                       Key: bridge_version.

committee_membership_events
                       what CivicAlign observed about a standing committee's
                       membership, one event per change: observed_joined,
                       observed_left, observed_role_changed. The date is when
                       CivicAlign first retrieved the source content showing the
                       change -- an OBSERVED date, never an official appointment
                       date. Start and end dates for a membership are derived
                       from these events (see membership_intervals).
                       Key: congress, committee_id, bioguide_id.
"""
import re

SENATE_SEATS = 100
STATUSES = ("NONE", "PROVISIONAL", "VALIDATED")
EVENTS = ("observed_joined", "observed_left", "observed_role_changed")
OBSERVED_DATE_BASIS = ("observed in a CivicAlign snapshot of unitedstates/congress-legislators "
                       "committee-membership-current.json: the date CivicAlign first retrieved content "
                       "showing this change; not an official appointment or departure date")
BASELINE_NOTE = "first CivicAlign observation of this committee: the membership may have begun earlier"
SCALE_NOTE_AIP = ("American Ideology Project survey ideal-point scale (standardised within the survey; "
                  "no common metric with Voteview legislator scores)")

SOURCE_FIELDS = {"source": str, "source_url": str, "source_version": str, "source_sha256": str,
                 "retrieved_at": str, "fixture": bool}

TABLES = {
    "senator_ideology": {
        "key": ("bioguide_id", "congress"),
        "fields": {"senator_id": (str, type(None)), "bioguide_id": str, "congress": int, "chamber": str, "state": str,
                   "name": str, "voteview_party_code": (str, type(None)), "voteview_row": bool,
                   "nominate_dim1": (float, type(None)), "nokken_poole_dim1": (float, type(None)),
                   "nominate_number_of_votes": (int, type(None)), "seated": bool,
                   "roster_source_version": str, "roster_retrieved_at": str, **SOURCE_FIELDS},
    },
    "constituency_ideology": {
        "key": ("geography_type", "geography_id", "methodology_version"),
        "fields": {"geography_type": str, "geography_id": str, "geography_name": str, "estimate": float,
                   "standard_error": float, "survey_period": str, "wave": int, "sample_size": (int, type(None)),
                   "methodology_version": str, "scale": str, **SOURCE_FIELDS},
    },
    "ideology_bridge": {
        "key": ("bridge_version",),
        "fields": {"bridge_version": str, "status": str, "public_model_version": (str, type(None)),
                   "legislator_model_version": (str, type(None)), "transformation_method": (str, type(None)),
                   "transformation_parameters": (dict, type(None)), "validation_metrics": (dict, type(None)),
                   "created_at": str, "notes": str},
    },
    "committee_membership_events": {
        "key": ("congress", "committee_id", "bioguide_id"),
        "fields": {"congress": int, "committee_id": str, "bioguide_id": str, "member_name": str, "event": str,
                   "observed_date": str, "date_basis": str, "baseline": bool, "baseline_note": (str, type(None)),
                   "rank": (int, type(None)), "title": (str, type(None)), "side": (str, type(None)),
                   "in_current_roster": bool, **SOURCE_FIELDS},
    },
}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def key_of(table: str, rec: dict) -> tuple:
    return tuple(rec[k] for k in TABLES[table]["key"])


def _type_ok(value, t) -> bool:
    types = t if isinstance(t, tuple) else (t,)
    if isinstance(value, bool) and bool not in types:
        return False
    if float in types and isinstance(value, int) and not isinstance(value, bool):
        return False  # scores must be stored as floats, never silently as ints
    return isinstance(value, types)


def validate(table: str, rec: dict) -> list[str]:
    """Problems with one record; an empty list means it may be stored."""
    spec = TABLES.get(table)
    if spec is None:
        return [f"unknown table {table!r}"]
    fields = spec["fields"]
    errs = [f"unexpected field {k!r}" for k in sorted(set(rec) - set(fields))]
    errs += [f"missing field {k!r}" for k in sorted(set(fields) - set(rec))]
    if errs:
        return errs
    errs += [f"{k}: expected {fields[k]}" for k in fields if not _type_ok(rec[k], fields[k])]
    if errs:
        return errs
    if "retrieved_at" in rec and not STAMP.match(rec["retrieved_at"]):
        errs.append("retrieved_at must be a UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    if table == "senator_ideology":
        for col in ("nominate_dim1", "nokken_poole_dim1"):
            if rec[col] is not None and not -1.0 <= rec[col] <= 1.0:
                errs.append(f"{col} {rec[col]} outside Voteview's [-1, 1]")
        if not rec["voteview_row"] and (rec["senator_id"] or rec["nominate_dim1"] is not None or rec["nokken_poole_dim1"] is not None):
            errs.append("a senator with no Voteview row cannot carry Voteview values")
        if rec["chamber"] != "Senate" or not re.fullmatch(r"[A-Z]{2}", rec["state"]):
            errs.append("chamber must be Senate and state a two-letter code")
    elif table == "constituency_ideology":
        if rec["standard_error"] < 0:
            errs.append("standard_error cannot be negative")
        if rec["geography_type"] not in ("state", "nation"):
            errs.append("geography_type must be state or nation")
    elif table == "ideology_bridge":
        st = rec["status"]
        if st not in STATUSES:
            errs.append(f"status must be one of {STATUSES}")
        elif st == "NONE" and any(rec[k] is not None for k in ("transformation_method", "transformation_parameters", "validation_metrics")):
            errs.append("a NONE bridge carries no method, parameters or validation")
        elif st in ("PROVISIONAL", "VALIDATED") and not (rec["transformation_method"] and rec["transformation_parameters"]
                                                           and rec["public_model_version"] and rec["legislator_model_version"]):
            errs.append(f"a {st} bridge needs its method, parameters and both model versions")
        if st == "VALIDATED" and not rec["validation_metrics"]:
            errs.append("a VALIDATED bridge needs validation metrics")
    elif table == "committee_membership_events":
        if rec["event"] not in EVENTS:
            errs.append(f"event must be one of {EVENTS}")
        if not DATE.match(rec["observed_date"]):
            errs.append("observed_date must be YYYY-MM-DD")
        if rec["date_basis"] != OBSERVED_DATE_BASIS:
            errs.append("date_basis must state that the date is observed, not official")
        if rec["baseline"] != (rec["baseline_note"] == BASELINE_NOTE):
            errs.append("a baseline event carries the baseline note, and only a baseline event")
        if rec["event"] == "observed_left" and any(rec[k] is not None for k in ("rank", "title", "side")):
            errs.append("an observed_left event carries no rank, title or side")
    return errs


def membership_intervals(events: list[dict]) -> list[dict]:
    """Derive memberships from the event log, in log order. Dates are observed:
    observed_start_date is when CivicAlign first saw the member on the committee
    (for a baseline event, the first observation of all), observed_end_date is
    when CivicAlign first saw them absent (None while still present)."""
    open_: dict[tuple, dict] = {}
    out: list[dict] = []
    for e in events:
        k = (e["congress"], e["committee_id"], e["bioguide_id"])
        if e["event"] == "observed_joined":
            open_[k] = {"congress": e["congress"], "committee_id": e["committee_id"], "bioguide_id": e["bioguide_id"],
                        "member_name": e["member_name"], "observed_start_date": e["observed_date"], "observed_end_date": None,
                        "start_is_first_observation": e["baseline"], "rank": e["rank"], "title": e["title"], "side": e["side"],
                        "date_basis": e["date_basis"]}
        elif e["event"] == "observed_role_changed" and k in open_:
            open_[k].update(rank=e["rank"], title=e["title"], side=e["side"])
        elif e["event"] == "observed_left" and k in open_:
            iv = open_.pop(k)
            iv["observed_end_date"] = e["observed_date"]
            out.append(iv)
    return out + list(open_.values())
