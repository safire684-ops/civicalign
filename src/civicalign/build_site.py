"""Build the integrated CivicAlign site: Senators, Bills, Committees, Senate as a Whole, About.

    PYTHONPATH=src python -m civicalign.build_site [--out DIR] [--check]

Reuses build_pages.payload() for every Engine B number (nothing is recalculated) and joins
the legislative drop (legislative.load) through verified ids. Writes
    demo/civicalign.html        the page, with the core data embedded
    demo/data/*.json            the drop's files byte for byte, plus derived.json, engine_bills.json and
                                bill_details.json (each bill's sponsor, official summary and latest action)
A failed join stops the build. The senator-to-state comparison stays unavailable while the
bridge is NONE, and survey estimates never receive a display position.
"""
import argparse
import csv
import html.parser
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import build_pages as BP
from . import health as H
from . import legislative as L
from . import record_votes as RV
from .config import DEFAULT, Config
from .ideology import bills as BL
from .ideology import display as DS
from .ideology import ingest as I
from .ideology.store import Table

OUT = BP.OUT
TEMPLATE = Path(__file__).resolve().parent / "templates" / "site.template.html"
PAGE = "civicalign.html"
COPIED = ("votes.json", "positions.json", "bills.json", "committee_votes.json", "nominations.json")
PARTY = {"Democrat": "D", "Republican": "R", "Independent": "I"}
LETTER = {v: k for k, v in PARTY.items()}
ARCHIVES = {"s": "billflow_zip", "hr": "billflow_house_zip", "sjres": "billstatus_sjres_zip", "hjres": "billstatus_hjres_zip",
            "sres": "billstatus_sres_zip", "sconres": "billstatus_sconres_zip", "hconres": "billstatus_hconres_zip"}
# The Census Bureau's four statistical regions (census.gov/geographies/reference-maps, "Census Regions and Divisions").
REGIONS = {"Northeast": "CT ME MA NH RI VT NJ NY PA", "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
           "South": "DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX", "West": "AZ CO ID MT NV NM UT WY AK CA HI OR WA"}
ARCHIVE_SOURCES = ("bill flow", "bill flow (House bills)", "joint resolutions (Senate)", "joint resolutions (House)",
                   "simple resolutions (Senate)", "concurrent resolutions (Senate)", "concurrent resolutions (House)")
REGION = {st: r for r, sts in REGIONS.items() for st in sts.split()}
PARTY_WORD = {"D": "Democrat", "R": "Republican", "I": "Independent", "ID": "Independent", "L": "Libertarian"}


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def archives(cfg: Config) -> dict[str, zipfile.ZipFile]:
    """The bill-status archives the snapshot verified. A resolution archive that wasn't fetched is left
    out (its bills show "Not available"); one on disk that differs from the snapshot stops the build."""
    snap = I.snapshot(cfg)
    names = {s.get("file") for s in snap["sources"]}
    out = {}
    for kind, attr in ARCHIVES.items():
        path = getattr(cfg, attr)
        if kind in ("sres", "sconres", "hconres") and path.name not in names:
            continue
        I.source_entry(cfg, snap, path.name)        # refuses a file that is not the verified one
        out[kind] = zipfile.ZipFile(path)
    return out


def policy_areas(cfg: Config, bills: list[dict]) -> dict[str, str | None]:
    """Each bill's official policy area, from the bill-status archives the snapshot verified.
    Measure types with no archive in the snapshot (and bills with no area yet) are None."""
    archives_ = archives(cfg)
    out = {}
    for b in bills:
        z, member = archives_.get(b["type"]), f"BILLSTATUS-{cfg.congress}{b['type']}{b['number']}.xml"
        area = None
        if z is not None and member in z.namelist():
            node = ET.fromstring(z.read(member)).find("bill")
            area = (node.findtext("policyArea/name") or "").strip() or None if node is not None else None
        out[b["id"]] = area
    return out


class _Paragraphs(html.parser.HTMLParser):
    """An official summary's HTML as plain paragraphs: one per <p> or <li>, tags dropped, text kept."""
    BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "div", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.buf = [], []

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.out.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data):
        self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def paragraphs(markup: str) -> list[str]:
    p = _Paragraphs()
    p.feed(markup or "")
    p.close()
    return p.out


def bill_record(xml: bytes) -> dict:
    """What the official bill-status record says about one bill: sponsor, latest official summary,
    latest action, introduced date and latest text. Nothing is rewritten or inferred."""
    node = ET.fromstring(xml).find("bill")
    t = lambda e, tag: (e.findtext(tag) or "").strip() if e is not None else ""
    sp = node.find("sponsors/item")
    sponsor = None
    if sp is not None:
        party = t(sp, "party")
        sponsor = {"id": t(sp, "bioguideId"), "name": " ".join(x for x in (t(sp, "firstName"), t(sp, "middleName"), t(sp, "lastName")) if x),
                   "full": t(sp, "fullName"), "party": party, "party_name": PARTY_WORD.get(party), "state": t(sp, "state")}
    summaries = node.findall("summaries/summary")
    summary = None
    if summaries:
        s = max(summaries, key=lambda x: (t(x, "actionDate"), t(x, "updateDate"), t(x, "versionCode")))
        summary = {"version": t(s, "versionCode"), "action": t(s, "actionDesc"), "date": t(s, "actionDate")[:10],
                   "updated": t(s, "updateDate")[:10],
                   "paragraphs": paragraphs(s.findtext("text") or s.findtext("cdata/text") or ""), "count": len(summaries)}   # some records nest the text in <cdata>
    la = node.find("latestAction")
    texts = [it for it in node.findall("textVersions/item")]
    latest_text = None
    if texts:
        it = max(texts, key=lambda x: t(x, "date"))
        urls = [t(f, "url") for f in it.findall("formats/item") if t(f, "url")]
        url = next((u for ext in (".htm", ".pdf") for u in urls if u.endswith(ext)), urls[0] if urls else None)   # readable formats first
        latest_text = {"name": t(it, "type"), "date": t(it, "date")[:10], "url": url}
    return {"sponsor": sponsor, "summary": summary, "introduced": t(node, "introducedDate")[:10] or None,
            "latest_action": {"date": t(la, "actionDate")[:10], "text": t(la, "text")} if la is not None and t(la, "text") else None,
            "text": latest_text, "title": t(node, "title"),
            "short_title": next((t(i, "title") for i in node.findall("titles/item") if "Short Title" in t(i, "titleType") and t(i, "title")), None)}


def bill_details(cfg: Config, bills: list[dict]) -> dict[str, dict]:
    """Each bill's official record (bill_record), or None where its archive or file isn't available."""
    zs = archives(cfg)
    out = {}
    for b in bills:
        z, member = zs.get(b["type"]), f"BILLSTATUS-{cfg.congress}{b['type']}{b['number']}.xml"
        if z is None or member not in z.namelist():
            out[b["id"]] = None
            continue
        rec = bill_record(z.read(member))
        rec["source"] = f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{cfg.congress}/{b['type']}/{member}"
        out[b["id"]] = rec
    return out


def committee_members(cfg: Config) -> dict[str, list[dict]]:
    """Current members per committee from the verified membership events (never from the drop)."""
    members: dict[str, list[dict]] = {}
    for e in Table(cfg.ideology_dir, "committee_membership_events").current():
        if e["congress"] == cfg.congress and e["event"] != "observed_left":
            members.setdefault(e["committee_id"], []).append(
                {"id": e["bioguide_id"], "title": e.get("title"), "rank": e.get("rank"), "side": e.get("side")})
    return members


def data_dates(cfg: Config, drop: dict, meta: dict) -> dict:
    """When each source was last checked and what it covers. A source retrieved before the
    current verified snapshot is an older snapshot, and the page says so."""
    snap = I.snapshot(cfg)
    today = snap["run_utc"][:10]
    sources = {s["name"]: s for s in snap["sources"]}
    def row(label, checked, changed, covers, note=None):
        return {"label": label, "checked": checked[:10], "changed": changed[:10] if changed else None, "covers": covers, "note": note,
                "status": "Latest available" if checked[:10] >= today else "Older snapshot"}
    def snapped(label, names, covers, note=None):
        picked = [sources[n] for n in names]
        return row(label, min(p["checked_utc"] for p in picked), max(p["content_changed_utc"] for p in picked), covers, note)
    with cfg.rollcalls_csv.open() as fh:
        last_roll = max(r["date"] for r in csv.DictReader(fh))
    made = drop["manifest"]["generated_at"]
    floor, committee = max(v["date"] for v in drop["votes"]), max(c["date"] for c in drop["committee_votes"])
    senate = json.loads((cfg.explain_raw_dir / "senate" / "PROVENANCE.json").read_text())
    pulled = max(r["checked_utc"] for r in senate["records"].values())
    record = RV.compare(cfg)
    sync = json.loads(RV.status_path(cfg).read_text()) if RV.status_path(cfg).exists() else {}
    record_checked = sync["checked_utc"] if sync.get("state") == "ok" else max((r["retrieved_utc"] for r in RV.read_jsonl(RV.store_path(cfg))), default=today)
    rows = [snapped("Senator positions", ["senator scores"], f"Votes through {last_roll}"),
            snapped("Voteview roll-call list", ["floor roll calls", "senator votes"], f"Votes through {last_roll}"),
            snapped("Who is seated", ["seated senators"], "Current roster"),
            snapped("Committee membership", ["committee rosters", "committee names"], "Current committees"),
            snapped("Senate bills, passage and law, policy areas", ["bill flow", "bill flow (House bills)", "joint resolutions (Senate)", "joint resolutions (House)"], "Official bill-status files"),
            snapped("Bill sponsors, official summaries and status", [n for n in ARCHIVE_SOURCES if n in sources], "Official bill-status files",
                    "Summaries are written by the Congressional Research Service at the Library of Congress."),
            snapped("State survey estimates", ["state ideology"], f"Survey wave {meta['aip_wave']}", "Shown on their own scale only."),
            snapped("State populations", ["state populations"], f"Census {meta['population'].split(',')[0]}"),
            row("Floor votes, senator votes, bills and nominations", made, made, f"Votes through {floor}"),
            snapped("Newer floor votes, provisional", ["floor roll calls"], f"Votes through {last_roll}", "From Voteview, because the files above don't have them yet. Question, result and counts only."),
            row("Committee votes", made, made, f"Votes through {committee}"),
            row("Official vote lists (Congressional Record)", record_checked, record_checked, f"{record['counts']['verified']} of {len(record['votes'])} roll calls match", "The Senate's printed list of how each senator voted, read from GovInfo."),
            row("Official Senate vote records (used for cross-checks)", pulled, pulled, f"{len(senate['records'])} passage votes", senate["note"])]
    return {"snapshot": today, "floor_through": floor, "rows": rows}


def with_record(extra: dict, cfg: Config) -> dict:
    """Each provisional vote with what the Congressional Record says about it."""
    votes = RV.compare(cfg)["votes"]
    for v in extra["votes"]:
        c = votes.get(v["id"], {"status": "pending"})
        v["official_record"] = {"status": c["status"], "url": c.get("url"), "issue": c.get("issue"), "changes": c.get("changes", [])}
    return extra


def record_summary(cfg: Config) -> dict:
    c = RV.compare(cfg)
    return {"counts": c["counts"], "total": len(c["votes"]),
            "conflicts": sorted(k for k, v in c["votes"].items() if v["status"] == "conflict"),
            "pending": sorted(k for k, v in c["votes"].items() if v["status"] == "pending"),
            "changes": sorted(k for k, v in c["votes"].items() if v.get("changes"))}


def bill_status(bill: dict, votes: dict[str, dict], outcomes: dict[str, dict]) -> dict:
    """What the data can say: the last Senate floor vote, plus passage and enactment for Senate bills."""
    last = max((votes[v] for v in bill["votes"]), key=lambda v: (v["date"], v["session"], v["number"]), default=None)
    status = {"last_vote": last["id"] if last else None, "last_date": last["date"] if last else None, "last_result": last["result"] if last else None}
    o = outcomes.get(bill["id"].upper()) if bill["type"] == "s" else None
    if o:
        status.update(passed_senate=o["passed_senate"], passed_date=o["passed_senate_date"], enacted=o["enacted"],
                      public_law=o["public_law_number"], law_pending=o["public_law_number_pending"])
    return status


def assemble(cfg: Config = DEFAULT) -> tuple[dict, dict, dict]:
    """(core, derived, engine_bills)."""
    from .ideology import bill_outcomes as BO
    d = BP.payload(cfg)
    drop = L.load(cfg)
    scores = {b: v["score"] for b, v in BL.current_sponsor_scores(cfg).items()}
    bad = L.problems(drop, set(scores))
    if bad:
        raise BP.BuildError("the legislative data does not join: " + "; ".join(bad[:5]))

    extra = with_record(L.supplement(drop, cfg), cfg)
    all_votes = drop["votes"] + extra["votes"]

    # ---- senators: identity and terms from the drop, positions from Engine B ----
    seated = {s["id"]: (st, s) for st in d["p4"]["states"] for s in st["senators"]}
    members = committee_members(cfg)
    names = {c["code"]: c["name"] for c in d["p6"]["committees"]}
    on = {}
    for code, ms in members.items():
        for m in ms:
            on.setdefault(m["id"], []).append({"code": code, "name": names.get(code, code), "title": m["title"]})
    senators = []
    tally: dict[str, dict] = {s["id"]: {"Yea": 0, "Nay": 0, "Present": 0, "Not Voting": 0} for s in drop["senators"]}
    for m in [*drop["positions"].values(), *extra["positions"].values()]:
        for sid, pos in m.items():
            tally.setdefault(sid, {"Yea": 0, "Nay": 0, "Present": 0, "Not Voting": 0})[pos] += 1
    # a senator seated after the drop was made has no floor votes yet, but still belongs on the site
    people = drop["senators"] + [{"id": i, "name": e["name"], "last_name": e["short"], "party": LETTER.get(e["party"], e["party"]), "caucus": None, "state": st["code"], "terms": []}
                                 for i, (st, e) in seated.items() if i not in tally]
    for s in people:
        tally.setdefault(s["id"], {"Yea": 0, "Nay": 0, "Present": 0, "Not Voting": 0})
        st, e = seated.get(s["id"], (None, None))
        v = scores.get(s["id"])
        pos = e["senator_score"] if e else ({"m": "p4.senator_score", "s": "AVAILABLE", "v": v, "d": BP.fmt(v, 3),
                                             "p0": DS.position_text(v, 0), "p1": DS.position_text(v, 1)} if v is not None else None)
        senators.append({
            "id": s["id"], "name": e["name"] if e else s["name"], "last": s["last_name"], "party": e["party"] if e else PARTY.get(s["party"], s["party"]),
            "party_name": LETTER.get(e["party"], e["party"]) if e else s["party"], "caucus": s["caucus"], "state": s["state"], "state_name": BP.STATE_NAMES.get(s["state"], s["state"]),
            "region": REGION.get(s["state"]), "seated": bool(e), "since": min((t["start"] for t in s["terms"]), default=None), "term_end": max((t["end"] for t in s["terms"]), default=None),
            "side": DS.side_label(v), "position": pos, "committees": sorted(on.get(s["id"], []), key=lambda c: c["name"]), "tally": tally[s["id"]],
            "public": {k: e[k] for k in ("state_public_estimate", "state_on_senator_scale", "distance")} if e else None})
    senators.sort(key=lambda x: (x["last"], x["name"]))

    # ---- committees: Engine B's cards with their verified members ----
    party = {s["id"]: s for s in senators}
    committees = []
    for c in d["p6"]["committees"]:
        roster = sorted((m for m in members.get(c["code"], []) if m["id"] in party), key=lambda m: (party[m["id"]]["party"], party[m["id"]]["last"]))
        flow = c["bills"]
        committees.append({
            **{k: c[k] for k in ("code", "name", "official_name", "name_source", "name_retrieved", "left_out", "sentence",
                                 "committee_median", "committee_senate_drift", "committee_public_drift", "listed", "scored")},
            "members": roster, "referred": flow["referred"]["total"]["v"], "reported": flow["reported"]["total"]["v"], "reported_without_referral": flow["reported_without_referral"]["v"]})
    for cv in drop["committee_votes"]:     # a committee with verified votes but no Engine B membership (e.g. Intelligence)
        code = cv["committee"]["code"]
        if code not in names:
            names[code] = cv["committee"]["name"]
            committees.append({"code": code, "name": cv["committee"]["name"].removeprefix("Senate ").replace("Select Committee on ", ""),
                               "official_name": cv["committee"]["name"], "members": [], "votes_only": True})

    p5, O = d["p5"], d["p5"]["outcomes"]
    trim = lambda n: {k: n[k] for k in ("v", "d", "m", "p0", "p1", "pts", "s", "r") if k in n}
    core = {
        "meta": {**{k: d["meta"][k] for k in ("input_key", "congress", "measurement_date", "committee_observed", "score_column", "aip_wave",
                                              "population", "bridge", "method_status", "identity_source")},
                 "input_versions": O["meta"]["input_versions"], "latest_archive_retrieved": O["meta"]["latest_archive_retrieved"],
                 "legislative": {"generated_at": drop["manifest"]["generated_at"], "imported_at": drop["manifest"]["imported_at"],
                                 "counts": drop["meta"]["counts"], "notes": drop["meta"]["notes"], "files": drop["manifest"]["files"]}},
        "senators": senators, "committees": committees, "anchors": [{"name": a["name"], "short": a["short"], "basis": a["basis"], "score": trim(a["score"])} for a in d["p4"]["anchors"]],
        "senate": {"plain": trim(p5["plain"]), "weighted": trim(p5["weighted"]), "diff": trim(p5["diff"]), "median": trim(p5["median"]), "active": trim(p5["active"]),
                   "wording": p5["wording"], "national": {"s": p5["national"]["s"], "r": p5["national"]["r"]}, "gap": {"s": p5["gap"]["s"], "r": p5["gap"]["r"]},
                   "passed": {k: trim(O["passed_senate"][k]) for k in ("total", "LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")},
                   "enacted": {k: trim(O["enacted"][k]) for k in ("total", "LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN", "public_law_number_recorded", "public_law_number_pending")}},
        "rules": d["display_rules"] + [{"id": L.EVIDENCE_RULE, "label": "Issue Positions: which votes are shown", "rule": L.EVIDENCE_TEXT, "limits": []},
                                       {"id": L.PARTY_RULE, "label": "Votes where party majorities were opposed", "rule": L.PARTY_TEXT, "limits": []}],
        "dates": data_dates(cfg, drop, d["meta"]), "reconcile": L.reconcile(drop, cfg),
        "record": record_summary(cfg), "health": H.report(cfg),
    }

    # ---- derived: only what the verified inputs determine ----
    votes = {v["id"]: v for v in all_votes}
    newer = {}
    for v in extra["votes"]:
        if v["bill"]:
            newer.setdefault(v["bill"], []).append(v["id"])
    outcomes = {o["bill_id"]: o for o in BO.current(cfg)}
    derived = {"evidence": {v["id"]: L.vote_evidence(v) for v in all_votes},
               "parties": {v["id"]: L.party_majorities(v["by_party"]) for v in all_votes},
               "supplement": [v["id"] for v in extra["votes"]],
               "policy_area": policy_areas(cfg, drop["bills"]),
               "status": {b["id"]: bill_status({**b, "votes": b["votes"] + newer.get(b["id"], [])}, votes, outcomes) for b in drop["bills"]}}
    engine_bills = {"outcomes": {"passed": {k: O["passed_senate"][k]["ids"] for k in ("LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")},
                                 "enacted": {k: O["enacted"][k]["ids"] for k in ("LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")}, "bills": O["bills"]},
                    "committee_bills": d["p6"]["bills"], "sponsors": {k: {"p0": v["score"].get("p0"), "d": v["score"].get("d")} for k, v in d["p6"]["sponsors"].items()}}
    return core, derived, engine_bills


def build(cfg: Config = DEFAULT) -> dict[str, bytes]:
    """Published path -> exact bytes."""
    core, derived, engine_bills = assemble(cfg)
    template = TEMPLATE.read_text()
    if template.count("<!--DATA-->") != 1:
        raise BP.BuildError("site template must contain <!--DATA--> exactly once")
    embedded = f'<script id="data" type="application/json">{_dump(core).replace("</", "<" + chr(92) + "/")}</script>'
    pages = {PAGE: template.replace("<!--DATA-->", embedded).encode(),
             "data/derived.json": _dump(derived).encode(), "data/engine_bills.json": _dump(engine_bills).encode(),
             "data/bill_details.json": _dump(bill_details(cfg, L.load(cfg)["bills"])).encode(), "data/supplement.json": _dump(with_record(L.supplement(L.load(cfg), cfg), cfg)).encode()}
    d = L.latest_dir(cfg)
    for name in COPIED:
        pages[f"data/{name}"] = (d / name).read_bytes()
    return pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args()
    try:
        pages = build(DEFAULT)
    except (BP.BuildError, L.LegislativeError, I.SnapshotMismatch) as err:
        print(f"SITE BUILD REFUSED: {err}", file=sys.stderr)
        return 1
    if a.check:
        stale = [n for n, b in pages.items() if not (a.out / n).exists() or (a.out / n).read_bytes() != b]
        print("site is current" if not stale else f"stale: {stale}")
        return 1 if stale else 0
    for n, b in pages.items():
        (a.out / n).parent.mkdir(parents=True, exist_ok=True)
        (a.out / n).write_bytes(b)
    print(f"wrote {len(pages)} files under {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
