"""Build the integrated CivicAlign site: Senators, Bills, Committees, Senate as a Whole, About.

    PYTHONPATH=src python -m civicalign.build_site [--out DIR] [--check]

Reuses build_pages.payload() for every Engine B number (nothing is recalculated) and joins
the legislative drop (legislative.load) through verified ids. Writes
    demo/civicalign.html        the page, with the core data embedded
    demo/data/*.json            the drop's files byte for byte, plus derived.json and engine_bills.json
A failed join stops the build. The senator-to-state comparison stays unavailable while the
bridge is NONE, and survey estimates never receive a display position.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import build_pages as BP
from . import legislative as L
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
ARCHIVES = {"s": "billflow_zip", "hr": "billflow_house_zip", "sjres": "billstatus_sjres_zip", "hjres": "billstatus_hjres_zip"}


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def policy_areas(cfg: Config, bills: list[dict]) -> dict[str, str | None]:
    """Each bill's official policy area, from the bill-status archives the snapshot verified.
    Measure types with no archive in the snapshot (and bills with no area yet) are None."""
    snap = I.snapshot(cfg)
    archives = {}
    for kind, attr in ARCHIVES.items():
        path = getattr(cfg, attr)
        I.source_entry(cfg, snap, path.name)        # refuses a file that is not the verified one
        archives[kind] = zipfile.ZipFile(path)
    out = {}
    for b in bills:
        z, member = archives.get(b["type"]), f"BILLSTATUS-{cfg.congress}{b['type']}{b['number']}.xml"
        area = None
        if z is not None and member in z.namelist():
            node = ET.fromstring(z.read(member)).find("bill")
            area = (node.findtext("policyArea/name") or "").strip() or None if node is not None else None
        out[b["id"]] = area
    return out


def committee_members(cfg: Config) -> dict[str, list[dict]]:
    """Current members per committee from the verified membership events (never from the drop)."""
    members: dict[str, list[dict]] = {}
    for e in Table(cfg.ideology_dir, "committee_membership_events").current():
        if e["congress"] == cfg.congress and e["event"] != "observed_left":
            members.setdefault(e["committee_id"], []).append(
                {"id": e["bioguide_id"], "title": e.get("title"), "rank": e.get("rank"), "side": e.get("side")})
    return members


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
    for m in drop["positions"].values():
        for sid, pos in m.items():
            tally[sid][pos] += 1
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
            "seated": bool(e), "since": min((t["start"] for t in s["terms"]), default=None), "term_end": max((t["end"] for t in s["terms"]), default=None),
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
        "rules": d["display_rules"] + [{"id": L.DIVISION_RULE, "label": "Votes that divided the two sides", "rule": L.DIVISION_TEXT, "limits": []}],
    }

    # ---- derived: only what the verified inputs determine ----
    votes = {v["id"]: v for v in drop["votes"]}
    outcomes = {o["bill_id"]: o for o in BO.current(cfg)}
    derived = {"division": {vid: L.vote_division(m, scores) for vid, m in drop["positions"].items()},
               "policy_area": policy_areas(cfg, drop["bills"]),
               "status": {b["id"]: bill_status(b, votes, outcomes) for b in drop["bills"]}}
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
             "data/derived.json": _dump(derived).encode(), "data/engine_bills.json": _dump(engine_bills).encode()}
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
