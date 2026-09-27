"""Build the Pillars 4-6 pages from the saved Engine B results and the methodology registry.

    PYTHONPATH=src python -m civicalign.build_pages [--out DIR] [--check]

Reads only
    the latest saved result record     data/ideology/metrics/<key>.json (via compute.index / load_record)
    the methodology registry           ideology/methodology.py
    the three Pillar 4 anchors         data/ideology/reference_anchors.jsonl (via anchors.current)
    official committee names          data/ideology/committee_names.jsonl (congress-legislators committee list)
    Pillar 5 legislative outcomes     data/ideology/bill_sponsor_classifications.jsonl and
                                      senate_bill_outcomes.jsonl (via bill_tallies.passed_senate_tally)
    Pillar 6 bills per committee      data/ideology/bill_sponsor_classifications.jsonl (via
                                      bill_tallies.committee_tallies), with each sponsor's current
                                      score from senator_ideology (bills.current_sponsor_scores)
    each senator's current party      the congress-legislators roster (legislators-current.json), read
                                      only if its bytes match the verified snapshot; its version is
                                      recorded in the page's provenance (identity data, not ideology)
and writes the published pages
    demo/senator-check.html            the three views, data embedded
    demo/methodology.html              every registry entry, with this build's versions
from the templates in src/civicalign/templates/ (outside demo/, which is what the
site publishes). Nothing is calculated here: every number
is a value from the record (or an anchor record), rounded for display to the
registry's decimals, and carries the id of its registry entry so the page can
show its methodology. A number whose path has no registry entry stops the build.

Presentation (ideology/display.py, never a calculation input): each value on
Voteview's scale also carries its display position, (nominate_dim1 + 1) x 50, as
a whole number (p0) and with one decimal (p1); each difference carries its size in
display points (pts); senators carry their side label; and the Senate and
committee sentences are generated here by fixed rules, so the page and the
supervisor can check every word against the stored numbers. Survey estimates of
the public never get a display position.

A committee whose code has no official name in committee_names stops the
build: a name is never guessed.

No Engine A import, no Pillar 1 content. The 0-100 display position is a position
on a line only: never a score, grade, rating, rank or alignment, never "/100".
"""
import argparse
import html
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .config import DEFAULT, Config
from .ideology import anchors as A
from .ideology import bill_outcomes as BO
from .ideology import bill_tallies as BT
from .ideology import bills as BL
from .ideology import compute as C
from .ideology import display as DS
from .ideology import ingest as I
from .ideology import methodology as M
from .ideology.store import Table, sha
from .sources.population import USPS

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).resolve().parent / "templates"
OUT = ROOT / "demo"
PAGES = ("senator-check.html", "methodology.html")
STATE_NAMES = {v: k for k, v in USPS.items()}

# Differences keep their sign on display.
SIGNED = {"p5.weighting_difference", "p5.median_difference", "p6.committee_senate_drift",
          "p4.distance", "p5.chamber_public_gap", "p6.committee_public_drift"}
# Values on Voteview's scale that the page shows as a display position, and differences shown in display points.
POSITIONS = {"p4.senator_score", "p4.reference_anchor", "p5.plain_mean", "p5.weighted_mean", "p5.plain_median",
             "p5.weighted_median", "p6.committee_median", "p6.bill_sponsor_score"}
POINTS = {"p5.weighting_difference", "p5.median_difference", "p6.committee_senate_drift"}
VIEW_TITLES = {"senator_state": "Senator / State (Pillar 4)", "senate_nation": "Senate / Nation (Pillar 5)",
               "committee_senate_nation": "Committee / Senate / Nation (Pillar 6)"}


class BuildError(RuntimeError):
    pass


# ---- formatting --------------------------------------------------------------------------

def fmt(value, decimals, signed=False) -> str:
    """Rounded half-up from the stored decimal text; U+2212 for minus; + only on differences."""
    if decimals is None:
        return f"{value:,}"
    d = Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if d == 0:
        d = abs(d)
    text = f"{abs(d):.{decimals}f}"
    return ("\u2212" if d < 0 else "+" if signed and d > 0 else "") + text


def _word(w: str) -> str:
    return "-".join(("Mc" + p[2:].capitalize()) if p.upper().startswith("MC") and len(p) > 2 else p.capitalize()
                    for p in w.split("-"))


def surname(voteview: str) -> str:
    """'BLUNT ROCHESTER, Lisa' -> 'Blunt Rochester'"""
    return " ".join(_word(w) for w in voteview.partition(", ")[0].split())


def display_name(voteview: str) -> str:
    """'MCCONNELL, Addison Mitchell (Mitch)' -> 'Mitch McConnell'; 'KING, Angus Stanley, Jr.' -> 'Angus King Jr.'"""
    last, _, rest = voteview.partition(", ")
    suffix = ""
    m = re.search(r",\s*(Jr\.|Sr\.|II|III|IV)$", rest)
    if m:
        suffix, rest = " " + m.group(1), rest[:m.start()]
    nick = re.search(r"\(([^)]+)\)", rest)
    first = nick.group(1) if nick else (rest.split() or [""])[0]
    return f"{first} {surname(voteview)}{suffix}".strip()


def en_dash_years(text: str) -> str:
    return re.sub(r"(\d{4})-(\d{4})", "\\1\u2013\\2", text)


def short(h: str) -> str:
    return h[:12] + "\u2026" if isinstance(h, str) and re.fullmatch(r"[0-9a-f]{40,64}", h) else h


def version_lines(value, prefix="") -> list[str]:
    """A record 'versions' value as readable lines (hashes shortened, nothing dropped but their tails)."""
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            out += version_lines(v, f"{prefix}{k.replace('_', ' ')}: " if not isinstance(v, (dict, list)) else f"{prefix}{k.replace('_', ' ')} \u2014 ")
        return out
    if isinstance(value, list):
        if value and all(isinstance(v, int) for v in value):     # a Congress range [first, last]
            return [f"{prefix.rstrip(' —')}: {chr(8211).join(str(v) for v in value)}"]
        return [l for v in value for l in version_lines(v, prefix)]
    return [f"{prefix}{short(value) if value is not None else 'none'}"]


# ---- the data the page renders -------------------------------------------------------------

def number(path: str, q: dict, entry_id: str | None = None) -> dict:
    """One displayed number: value, display text, status, reason, units and its registry entry."""
    e = M.REGISTRY[entry_id] if entry_id else M.entry_for(path)
    out = {"m": e["id"], "p": path, "s": q["status"], "u": q["units"], "r": q.get("reason"), "v": q.get("value")}
    out["d"] = fmt(q["value"], e["decimals"], e["id"] in SIGNED) if q.get("value") is not None else None
    if out["v"] is not None and e["id"] in POSITIONS:
        out["p0"], out["p1"] = DS.position_text(out["v"], 0), DS.position_text(out["v"], 1)
    if out["v"] is not None and e["id"] in POINTS:
        out["pts"] = DS.points_text(out["v"])
    if "standard_error" in q:
        out["se"] = fmt(q["standard_error"], e["decimals"])
    if "survey_period" in q:
        out["period"] = q["survey_period"]
    return out


def count(path: str, value: int) -> dict:
    e = M.entry_for(path)
    if e["kind"] != "count":
        raise BuildError(f"{path} is registered as {e['kind']}, not a count")
    return {"m": e["id"], "p": path, "s": "AVAILABLE", "u": e["units"], "r": None, "v": value, "d": fmt(value, None)}


def committee_names(cfg: Config, codes) -> dict[str, dict]:
    """code -> the stored official-name record; a code without one stops the build."""
    names = {r["committee_id"]: r for r in Table(cfg.ideology_dir, "committee_names").current()}
    missing = sorted(c for c in codes if c not in names)
    if missing:
        raise BuildError(f"no official committee name for {missing} in committee_names: run ingest "
                         "(source: congress-legislators committees-current.json)")
    return names


def latest(cfg: Config) -> dict:
    idx = C.index(cfg)
    if not idx:
        raise BuildError("no saved result record: run compute")
    entry = idx[-1]
    mdir, _ = C.paths(cfg)
    body = (mdir / f"{entry['input_key']}.json").read_text().rstrip("\n")
    if sha(body) != entry["content_sha256"]:
        raise BuildError(f"result {entry['input_key']} does not match its index hash")
    return json.loads(body)


def methods_payload(record: dict, anchors: list[dict], outcome_versions: dict, billflow_versions: dict) -> dict:
    out = {}
    for e in M.ENTRIES:
        if e["kind"] == "outcome":
            versions = [l for k in e["versions"] for l in version_lines(outcome_versions[k], f"{k.replace('_', ' ')} \u2014 ")]
        elif e["kind"] == "billflow":
            versions = [l for k in e["versions"] for l in version_lines(billflow_versions[k], f"{k.replace('_', ' ')} \u2014 ")]
        elif e["kind"] == "reference":
            versions = [f"{a['display_name']}: " + "; ".join(version_lines({k: a[k] for k in e["versions"]})) for a in anchors]
        else:
            versions = [l for k in e["versions"] for l in version_lines(record["versions"][k], f"{k.replace('_', ' ')} \u2014 ")]
        out[e["id"]] = {"label": e["label"], "units": e["units"], "views": [VIEW_TITLES[v] for v in e["views"]],
                        "placement": e["placement"], "transformation": e["transformation"], "formula": e["formula"],
                        "sources": [M.SOURCES[s]["name"] + (f" ({M.SOURCES[s]['citation']})" if M.SOURCES[s]["citation"] else "")
                                    for s in e["sources"]],
                        "versions": versions, "limitations": list(e["limitations"]), "not_available": e["not_available"]}
    return out


SPONSOR_KEYS = ("LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")


def outcomes_payload(cfg: Config) -> tuple[dict, dict]:
    """Pillar 5 legislative outcomes from the saved bill tables: every count with the exact
    bill ids behind it, the bills themselves (for "See bills"), and the versions and rules."""
    cls, outs = BL.current(cfg), BO.current(cfg)
    if not cls or not outs:
        raise BuildError("no saved bill classifications or outcomes: run python -m civicalign.ideology.bills and bill_outcomes")
    t = BT.passed_senate_tally(cls, outs)
    for part in ("passed_senate", "enacted"):
        probs = BT.trace_problems(t[part])
        if probs:
            raise BuildError(f"the {part} tally does not trace to its bill ids: {probs}")
    by_c, by_o = {r["bill_id"]: r for r in cls}, {r["bill_id"]: r for r in outs}

    def count(path, ids):
        n = number(path, {"value": len(ids), "status": "AVAILABLE", "units": "Senate bills", "reason": None})
        return {**n, "ids": list(ids)}

    data = {}
    for part in ("passed_senate", "enacted"):
        tally = t[part]
        data[part] = {"total": count(f"outcomes.{part}.total", tally["bill_ids"]), "set": tally["outcome_set"],
                      **{k: count(f"outcomes.{part}.{k}", tally["by_classification"][k]["bill_ids"]) for k in SPONSOR_KEYS}}
    data["enacted"]["public_law_number_recorded"] = count("outcomes.enacted.public_law_number_recorded",
                                                          t["public_law_number_recorded"]["bill_ids"])
    data["enacted"]["public_law_number_pending"] = count("outcomes.enacted.public_law_number_pending",
                                                         t["public_law_number_pending"]["bill_ids"])
    data["bills"] = {}
    now = BL.current_sponsor_scores(cfg)       # a sponsor's exact current score comes only from senator_ideology
    for b in t["passed_senate"]["bill_ids"]:
        c, o = by_c[b], by_o[b]
        data["bills"][b] = {"label": f"S. {c['bill_number']}", "title": c["title"], "sponsor": c["primary_sponsor_name"],
                            "url": f"https://www.congress.gov/bill/{c['congress']}th-congress/senate-bill/{c['bill_number']}",
                            "passed": o["passed_senate_date"], "enacted": o["enacted"], "law": o["public_law_number"],
                            "pending": o["public_law_number_pending"], "signed": o["signed_date"],
                            "sponsor_score": (now.get(c["sponsor_bioguide_id"]) or {}).get("score")}
        s = data["bills"][b]["sponsor_score"]
        data["bills"][b]["sponsor_p0"] = DS.position_text(s, 0) if s is not None else None
    counted = [by_c[b] for b in t["passed_senate"]["bill_ids"]] + [by_o[b] for b in t["passed_senate"]["bill_ids"]]
    archive = sorted({(r["source_version"], r["retrieved_at"]) for r in counted}, key=lambda x: x[1])
    versions = {
        "bill_archive_versions": [{"source_version": v, "retrieved_at": d} for v, d in archive],
        "outcome_rule": t["outcome_rule"], "enactment_rule": t["enactment_rule"],
        "classification_rule": sorted({by_c[b]["classification_rule"] for b in t["passed_senate"]["bill_ids"]}),
        "sponsor_score_versions": sorted({by_c[b]["sponsor_score_source_version"] or "none" for b in t["passed_senate"]["bill_ids"]}),
    }
    data["meta"] = {"table_fingerprints": BO.table_fingerprints(cfg), "input_versions": BO.input_versions(cfg),
                    "outcome_rule": t["outcome_rule"], "enactment_rule": t["enactment_rule"],
                    "classification_rule": versions["classification_rule"],
                    "latest_archive_retrieved": archive[-1][1][:10] if archive else None}
    return data, versions


BILLFLOW_PARTS = ("referred", "reported")


def committee_bills_payload(cfg: Config, codes) -> tuple[dict, dict, dict, dict, dict]:
    """Pillar 6 "Bills handled by this committee" from the saved bill_sponsor_classifications
    table, through bill_tallies.committee_tallies():

    per committee   bills referred and bills reported, each split by sponsor voting position,
                    and the reported bills with no referral to that committee; every count
                    carries its exact bill ids. Referred and reported are separate lists: a
                    committee can report a bill never recorded as referred to it, so reported
                    is not assumed to be a subset of referred.
    bills           each counted bill (for "See bills"): number, title, sponsor, sponsor class
                    and, per committee, the dates of its "Referred To" and "Reported" activities
    sponsors        each sponsor's CURRENT score, read only from senator_ideology
    meta, versions  the input versions and rules behind the counts

    Returns (per_committee, bills, sponsors, meta, versions)."""
    cls = BL.current(cfg)
    if not cls:
        raise BuildError("no saved bill classifications: run python -m civicalign.ideology.bills")
    tallies = BT.committee_tallies(cls)
    stray = sorted(set(tallies) - set(codes))
    if stray:
        raise BuildError(f"bills name standing committees with no Pillar 6 result: {stray}")
    empty = BT.by_classification([])

    def count(path, ids):
        n = number(path, {"value": len(ids), "status": "AVAILABLE", "units": "Senate bills", "reason": None})
        return {**n, "ids": list(ids)}

    per, counted = {}, set()
    for code in sorted(codes):
        slots = tallies.get(code, {})
        entry = {}
        for part in BILLFLOW_PARTS + ("reported_without_referral",):
            tally = slots.get(part, empty)
            probs = BT.trace_problems(tally)
            if probs:
                raise BuildError(f"{code} {part} does not trace to its bill ids: {probs}")
            counted |= set(tally["bill_ids"])
            if part == "reported_without_referral":
                entry[part] = count(f"committee_bills.{code}.{part}", tally["bill_ids"])
            else:
                entry[part] = {"total": count(f"committee_bills.{code}.{part}.total", tally["bill_ids"]),
                               **{k: count(f"committee_bills.{code}.{part}.{k}", tally["by_classification"][k]["bill_ids"])
                                  for k in SPONSOR_KEYS}}
        per[code] = entry
    by = {r["bill_id"]: r for r in cls}
    bills = {}
    for b in sorted(counted, key=BT._order):
        r = by[b]
        acts = {c["committee_id"]: [(c["referred_date"] or "date not recorded")[:10] if c["referred"] else None,
                                    (c["reported_date"] or "date not recorded")[:10] if c["reported"] else None]
                for c in r["referred_committees"] if c["referred"] or c["reported"]}
        bills[b] = {"n": r["bill_number"], "t": r["title"], "sp": r["sponsor_bioguide_id"], "sn": r["primary_sponsor_name"],
                    "c": r["sponsor_classification"], "a": acts}
    now = BL.current_sponsor_scores(cfg)       # a sponsor's exact current score comes only from senator_ideology
    sponsors = {}
    for bg in sorted({x["sp"] for x in bills.values() if x["sp"]}):
        cur = now.get(bg)
        q = ({"value": cur["score"], "status": "AVAILABLE", "units": M.LEGISLATOR, "reason": None} if cur and cur["score"] is not None
             else {"value": None, "status": "NOT_AVAILABLE", "units": M.LEGISLATOR,
                   "reason": M.REGISTRY["p6.bill_sponsor_score"]["not_available"]})
        sponsors[bg] = {"score": number(f"committee_bills.{bg}.sponsor_score", q),
                        "version": short(cur["source_version"]) if cur else None}
    rows = [by[b] for b in bills]
    archive = sorted({(r["source_version"], r["retrieved_at"]) for r in rows}, key=lambda x: x[1])
    versions = {
        "committee_bill_archive_versions": [{"source_version": v, "retrieved_at": d} for v, d in archive],
        "classification_rule": sorted({r["classification_rule"] for r in rows}),
        "committee_sponsor_score_versions": sorted({r["sponsor_score_source_version"] or "none" for r in rows}),
        "current_sponsor_score_versions": sorted({now[bg]["source_version"] for bg in sponsors if bg in now}),
    }
    meta = {"congress": cfg.congress, "input_versions": BO.input_versions(cfg), "classification_rule": versions["classification_rule"],
            "latest_archive_retrieved": archive[-1][1][:10] if archive else None}
    return per, bills, sponsors, meta, versions


def identity(cfg: Config) -> tuple[dict[str, str | None], dict]:
    """Each senator's current party (R, D, I) from the congress-legislators roster, read only if the
    file on disk is the one the verified snapshot accepted, and that roster's version for the page's
    provenance. Party is identity data: it is never stored in, or read from, senator_ideology."""
    try:
        snap = I.snapshot(cfg)
        entry = I.source_entry(cfg, snap, cfg.roster_json.name)
    except I.SnapshotMismatch as err:
        raise BuildError(f"the roster for party labels cannot be verified: {err}")
    party = {}
    for p in json.loads(cfg.roster_json.read_text()):
        term = p["terms"][-1]
        if term["type"] == "sen":
            party[p["id"]["bioguide"]] = DS.party_abbreviation(term.get("party"))
    source = {"source": I.ROSTER, "source_url": entry["url"], "source_version": str(entry["content_key"]),
              "source_sha256": entry["sha256"], "retrieved_at": entry["content_changed_utc"]}
    return party, source


def payload(cfg: Config = DEFAULT) -> dict:
    record = latest(cfg)
    problems = M.problems() + M.coverage(record)
    anchors = A.current(cfg)
    problems += M.anchor_problems(anchors)
    if problems:
        raise BuildError("methodology registry does not cover this record: " + "; ".join(problems))
    res = record["results"]
    p5, p6 = res["pillar5"], res["pillar6"]
    states: dict[str, list] = {}
    anchor_names = {a["bioguide_id"]: a["display_name"] for a in anchors}
    party, identity_source = identity(cfg)
    for i, s in enumerate(res["pillar4"]):
        base = f"pillar4.{i}"
        states.setdefault(s["state"], []).append({
            "id": s["bioguide_id"], "name": anchor_names.get(s["bioguide_id"]) or display_name(s["name"]),
            "short": surname(s["name"]), "party": party.get(s["bioguide_id"]),
            "side": DS.side_label(s["senator_score"]["value"]),
            **{k: number(f"{base}.{k}", s[k]) for k in ("senator_score", "state_public_estimate", "state_on_senator_scale", "distance")}})
    for sens in states.values():          # within a state, by surname: never by position
        sens.sort(key=lambda x: (x["short"], x["name"]))
    anchor_rows = [{"id": a["anchor_id"], "name": a["display_name"], "short": a["display_name"].split()[-1],
                    "basis": en_dash_years(a["record_basis"]), "bioguide": a["bioguide_id"],
                    "score": number(f"reference_anchors.{a['anchor_id']}.nominate_dim1",
                                    {"value": a["nominate_dim1"], "status": "AVAILABLE", "units": M.LEGISLATOR, "reason": None},
                                    "p4.reference_anchor")} for a in anchors]
    secondary = p5["details"]["methods"][M.SECONDARY_METHOD]
    primary_label = p5["population_weighted_center"]
    names = committee_names(cfg, p6)
    committees = [{"code": c, "name": names[c]["display_name"], "official_name": names[c]["official_name"],
                   "name_source": names[c]["source"], "name_retrieved": names[c]["retrieved_at"][:10],
                   "listed": count(f"pillar6.{c}.members_listed", v["members_listed"]),
                   "scored": count(f"pillar6.{c}.members_scored", v["members_scored"]), "left_out": v["members_left_out"],
                   **{k: number(f"pillar6.{c}.{k}", v[k]) for k in ("committee_median", "committee_senate_drift", "committee_public_drift")},
                   "sentence": DS.committee_sentence(v["committee_senate_drift"]["value"])}
                  for c, v in p6.items()]
    v = record["versions"]
    outcomes, outcome_versions = outcomes_payload(cfg)
    flow, flow_bills, flow_sponsors, flow_meta, flow_versions = committee_bills_payload(cfg, p6)
    for c in committees:
        c["bills"] = flow[c["code"]]
    return {
        "meta": {"input_key": record["input_key"], "input_key_short": record["input_key"][:8], "congress": v["congress"],
                 "measurement_date": v["measurement_date"], "score_column": v["legislator_model"]["score_column"],
                 "aip_wave": v["public_model"]["wave"], "bridge": f"{v['bridge']['bridge_version']} ({v['bridge']['status']})",
                 "population": f"{v['population']['vintage']}, {v['population']['measurement_year']}",
                 "committee_observed": v["committee_membership"]["latest_observed_date"],
                 "primary_method": p5["configured_method"], "method_status": primary_label["method_status"],
                 "identity_source": identity_source},
        "display_rules": [{"id": rid, "label": label, "rule": rule, "limits": list(limits)} for rid, label, rule, limits in DS.RULES],
        "methods": methods_payload(record, anchors, outcome_versions, flow_versions),
        "p4": {"states": [{"code": st, "name": STATE_NAMES.get(st, st), "senators": sens}
                          for st, sens in sorted(states.items(), key=lambda kv: STATE_NAMES.get(kv[0], kv[0]))],
               "anchors": anchor_rows},
        "p5": {"active": count("pillar5.active_senators", p5["active_senators"]),
               "unscored": p5["unscored_seated_senators"],
               "plain": number("pillar5.plain_center", p5["plain_center"]),
               "weighted": number("pillar5.population_weighted_center", p5["population_weighted_center"]),
               "diff": number("pillar5.population_weighting_difference", p5["population_weighting_difference"]),
               "median": number("pillar5.details.chamber_median", p5["details"]["chamber_median"]),
               "wmedian": number(f"pillar5.details.methods.{M.SECONDARY_METHOD}.population_weighted_center",
                                 secondary["population_weighted_center"]),
               "mdiff": number(f"pillar5.details.methods.{M.SECONDARY_METHOD}.population_weighting_difference",
                               secondary["population_weighting_difference"]),
               "national": number("pillar5.national_public", p5["national_public"]),
               "gap": number("pillar5.chamber_public_gap", p5["chamber_public_gap"]),
               "wording": {"position": DS.senate_position_sentence(p5["plain_center"]["value"]),
                           "shift": DS.population_shift_sentence(p5["population_weighting_difference"]["value"]),
                           "shift_words": DS.shift_words(p5["population_weighting_difference"]["value"]),
                           "shift_detail": DS.shift_detail_sentence(p5["population_weighting_difference"]["value"]),
                           "rules": [DS.SENATE_RULE, DS.SHIFT_RULE]},
               "outcomes": outcomes},
        "p6": {"senate_median": number("pillar5.details.chamber_median", p5["details"]["chamber_median"]),
               "national": number("pillar5.national_public", p5["national_public"]),
               "committees": sorted(committees, key=lambda c: c["name"]),
               "bills": flow_bills, "sponsors": flow_sponsors, "bill_meta": flow_meta},
    }


# ---- the pages -------------------------------------------------------------------------------

def embed(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def e(t) -> str:
    return html.escape(str(t), quote=True)


def methodology_html(data: dict) -> str:
    meta, methods = data["meta"], data["methods"]
    parts = []
    for view, title in VIEW_TITLES.items():
        parts.append(f'<h2 id="view-{view}">{e(title)}</h2>')
        for eid, m in methods.items():
            if VIEW_TITLES[view] != m["views"][0]:
                continue
            na = f'<dt>When it is not available</dt><dd>{e(m["not_available"])}</dd>' if m["not_available"] else ""
            parts.append(
                f'<section class="entry" id="{e(eid)}"><h3>{e(m["label"])} <code>{e(eid)}</code></h3><dl>'
                f'<dt>Shown in</dt><dd>{e(", ".join(m["views"]))} &middot; {e("main view" if m["placement"] == "main" else "details only")}</dd>'
                f'<dt>Units</dt><dd>{e(m["units"])}</dd>'
                f'<dt>Raw source</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["sources"])}</ul></dd>'
                f'<dt>Transformation</dt><dd>{e(m["transformation"])}</dd>'
                f'<dt>Formula</dt><dd class="formula">{e(m["formula"])}</dd>'
                f'<dt>Versions in this build</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["versions"])}</ul></dd>'
                f'<dt>Limitations</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["limitations"])}</ul></dd>{na}</dl></section>')
    anchors = "".join(f'<tr><td>{e(a["name"])}</td><td class="n">{e(a["score"]["d"])}</td><td class="n">{e(a["score"]["p0"])}</td>'
                      f'<td>{e(a["basis"])}</td></tr>' for a in data["p4"]["anchors"])
    rules = "".join(f'<section class="entry" id="{e(r["id"])}"><h3>{e(r["label"])} <code>{e(r["id"])}</code></h3><dl>'
                    f'<dt>Rule</dt><dd class="formula">{e(r["rule"])}</dd>'
                    f'<dt>Limits</dt><dd><ul>{"".join(f"<li>{e(x)}</li>" for x in r["limits"])}</ul></dd></dl></section>'
                    for r in data["display_rules"])
    body = (f'<p class="asof">Result record <code>{e(meta["input_key"])}</code> &middot; measurement date '
            f'{e(meta["measurement_date"])} &middot; {e(meta["congress"])}th Congress &middot; score column '
            f'<code>{e(meta["score_column"])}</code> &middot; bridge {e(meta["bridge"])}</p>'
            f'<h2 id="anchors">Pillar 4 reference figures</h2><p>Visual reference points only. They are never an input to '
            f'any calculation.</p><table class="anchors"><tr><th>Figure</th><th>Voteview score</th><th>Display position</th>'
            f'<th>Record used</th></tr>{anchors}</table>'
            f'<h2 id="display-rules">How the page presents these numbers</h2><p>These rules only change how a stored number is '
            f'shown. Every calculation uses the Voteview values themselves.</p>{rules}'
            + "".join(parts))
    return body


def build(cfg: Config = DEFAULT) -> dict[str, str]:
    data = payload(cfg)
    page = (TEMPLATES / "senator-check.template.html").read_text()
    report = (TEMPLATES / "methodology.template.html").read_text()
    for marker, text in (("<!--DATA-->", page), ("<!--METHODOLOGY-->", report)):
        if text.count(marker) != 1:
            raise BuildError(f"template must contain {marker} exactly once")
    return {"senator-check.html": page.replace("<!--DATA-->", f'<script id="data" type="application/json">{embed(data)}</script>'),
            "methodology.html": report.replace("<!--METHODOLOGY-->", methodology_html(data))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args()
    try:
        pages = build(DEFAULT)
    except (BuildError, A.AnchorError) as err:
        print(f"BUILD REFUSED: {err}", file=sys.stderr)
        return 1
    if a.check:
        stale = [n for n, t in pages.items() if not (a.out / n).exists() or (a.out / n).read_text() != t]
        print("pages are current" if not stale else f"stale: {stale}")
        return 1 if stale else 0
    a.out.mkdir(parents=True, exist_ok=True)
    for n, t in pages.items():
        (a.out / n).write_text(t)
    print(f"wrote {', '.join(str(a.out / n) for n in pages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
