"""Stage 2 runner: classify every Senate roll call and bind the eligible ones.

    PYTHONPATH=src python -m civicalign.explain.bind [--offline]

Writes one tracked JSON per bound vote under data/explanations/<congress>/ and
an index. Historical records are never overwritten: when a source hash or a
status changes, the previous record is kept under "history". Nothing here calls
a model or produces a summary.
"""
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from ..config import DEFAULT, Config
from ..sources import billstatus, rollcalls, rosters
from ..sources.senate_votes import parse_senate_vote, senate_vote_url
from . import binding as B
from .fetch import Store

BINDING_SCHEMA = "civicalign.binding/1.0"


def lis_to_bioguide(cfg: Config) -> dict[str, str]:
    """LIS id -> bioguide for every CURRENT senator, from the roster's own ids."""
    people = json.loads(cfg.roster_json.read_text())
    return {p["id"]["lis"]: p["id"]["bioguide"] for p in people
            if p["terms"][-1]["type"] == "sen" and p["id"].get("lis")}


def _norm_name(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.upper() if ch.isalpha())


def voteview_members(cfg: Config) -> list[dict]:
    """Every Senate member row for this Congress in Voteview's member file,
    including members who have since left: bioguide, state, party letter,
    last and first name."""
    party = {"100": "D", "200": "R", "328": "I"}
    out = []
    with cfg.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] != "Senate" or row["congress"] != str(cfg.congress):
                continue
            last, _, first = row["bioname"].partition(",")
            out.append({"bioguide": row["bioguide_id"], "state": row["state_abbrev"], "party": party.get(row["party_code"], "?"),
                        "last": _norm_name(last), "first": _norm_name(first.split()[0] if first.split() else "")})
    return out


def map_lis(senate, lis_map: dict[str, str], vv_members: list[dict], senate_members: dict[str, dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve every LIS id in a Senate record to a bioguide: the roster first;
    for a member no longer on the roster, an exact match of last name, first
    name, state and party against Voteview's member list. Ambiguity or no match
    leaves the id unmapped, which fails the member check. Returns
    (lis -> bioguide, lis -> how it was resolved)."""
    resolved, how = {}, {}
    for lis in senate.votes:
        if lis in lis_map:
            resolved[lis] = lis_map[lis]; how[lis] = "roster"
            continue
        m = senate_members.get(lis, {})
        cands = [v for v in vv_members if v["state"] == m.get("state") and v["party"] == m.get("party")
                 and v["last"] == _norm_name(m.get("last", "")) and v["first"] == _norm_name(m.get("first", "").split()[0] if m.get("first") else "")]
        if len(cands) == 1:
            resolved[lis] = cands[0]["bioguide"]; how[lis] = "voteview name+state+party"
    return resolved, how


def voteview_rows(cfg: Config) -> list[dict]:
    with cfg.rollcalls_csv.open() as fh:
        return [r for r in csv.DictReader(fh) if r["chamber"] == "Senate" and r["congress"] == str(cfg.congress)]


def _rollcall(row: dict) -> rollcalls.RollCall:
    return rollcalls.RollCall(number=int(row["rollnumber"]), date=row["date"],
                              bill=rollcalls._norm_bill(row["bill_number"]), question=row["vote_question"].strip(),
                              result=row["vote_result"].strip(), cutpoint=None, yea_is_right=None)


def member_votes_for(cfg: Config, rolls: set[int]) -> dict[int, dict[str, str]]:
    icpsr = rollcalls.icpsr_to_bioguide(cfg.members_csv, cfg.congress)
    out: dict[int, dict[str, str]] = {r: {} for r in rolls}
    with cfg.votes_csv.open() as fh:
        for row in csv.DictReader(fh):
            n = int(row["rollnumber"])
            if n not in out:
                continue
            b = icpsr.get(row["icpsr"])
            if not b:
                continue
            code = row["cast_code"]
            out[n][b] = "Yea" if code in ("1", "2", "3") else "Nay" if code in ("4", "5", "6") else "Other"
    return out


def passage_action(bill: billstatus.BillRecord | None, clerk: int, vote_date: str) -> tuple[str, bool]:
    """The bill's own action for this Senate vote, found by its recorded-vote link
    (chamber Senate, roll number = clerk number). Returns (text, linked)."""
    if bill is None:
        return "", False
    for a in bill.actions:
        for rv in a.recorded_votes:
            if rv.chamber == "Senate" and rv.number == clerk and (not vote_date or a.date == vote_date):
                return a.text, True
    return "", False


def verify(row: dict, senate, bill, mv: dict[str, str], lis_map: dict[str, str], linked: bool) -> tuple[str, list[dict]]:
    """Deterministic agreement checks across the three records."""
    checks = []
    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
    if senate is None:
        add("senate_record_exists", False, "not retrieved")
        return "UNAVAILABLE", checks
    add("senate_record_exists", True)
    add("identity_matches", senate.congress == int(row["congress"]) and senate.session == int(row["session"])
        and senate.number == int(row["clerk_rollnumber"]),
        f"senate {senate.congress}/{senate.session}/{senate.number} vs voteview {row['congress']}/{row['session']}/{row['clerk_rollnumber']}")
    add("date_compatible", senate.date == row["date"], f"senate {senate.date} vs voteview {row['date']}")
    add("question_matches", senate.question.strip() == row["vote_question"].strip(), f"{senate.question!r} vs {row['vote_question']!r}")
    add("tallies_match", senate.yeas == int(row["yea_count"]) and senate.nays == int(row["nay_count"]),
        f"senate {senate.yeas}-{senate.nays} vs voteview {row['yea_count']}-{row['nay_count']}")
    add("threshold_matches", senate.majority_requirement == row["majority_requirement"],
        f"{senate.majority_requirement} vs {row['majority_requirement']}")
    # member votes: Senate's LIS ids -> bioguide, compared with Voteview cast codes
    resolved, how = lis_map
    sen_by_b = {resolved.get(lis, lis): v for lis, v in senate.votes.items()}
    yea_s = {b for b, v in sen_by_b.items() if v == "Yea"}; nay_s = {b for b, v in sen_by_b.items() if v == "Nay"}
    yea_v = {b for b, v in mv.items() if v == "Yea"}; nay_v = {b for b, v in mv.items() if v == "Nay"}
    unmapped = [lis for lis in senate.votes if lis not in resolved]
    fallbacks = {lis: resolved[lis] for lis, h in how.items() if h != "roster"}
    add("member_votes_match", yea_s == yea_v and nay_s == nay_v and not unmapped,
        f"yea {len(yea_s)}/{len(yea_v)} nay {len(nay_s)}/{len(nay_v)}" + (f"; unmapped LIS ids {unmapped}" if unmapped else "")
        + (f"; former members matched by name+state+party {fallbacks}" if fallbacks else "")
        + (f"; yea diff {sorted(yea_s ^ yea_v)}" if yea_s != yea_v else "") + (f"; nay diff {sorted(nay_s ^ nay_v)}" if nay_s != nay_v else ""))
    vv_measure = rollcalls._norm_bill(row["bill_number"])
    add("measure_matches", (senate.measure == vv_measure) if vv_measure else senate.measure == "",
        f"senate {senate.measure!r} vs voteview {vv_measure!r}")
    if bill is not None:
        add("billstatus_present", True, bill.filename)
        add("billstatus_links_vote", linked, "recorded-vote link to this Senate vote number" if linked else "no recorded-vote link for this vote yet")
    else:
        add("billstatus_present", False, "no BILLSTATUS record in the archives")
    core = [c for c in checks if c["check"] not in ("billstatus_present", "billstatus_links_vote")]
    if not all(c["ok"] for c in core):
        return "FAILED", checks
    if bill is None or not linked:
        return "BOUND_AWAITING_BILLSTATUS", checks
    return "VERIFIED", checks


def build_binding(cfg: Config, row: dict, senate, bill, mv, lis_map, store: Store, offline: bool) -> dict:
    clerk = int(row["clerk_rollnumber"]); session = int(row["session"])
    action_text, linked = passage_action(bill, clerk, row["date"])
    cls = B.classify(_rollcall(row), senate, bill, action_text)
    status, checks = verify(row, senate, bill, mv, lis_map, linked)
    vv_measure = rollcalls._norm_bill(row["bill_number"])
    measure = (senate.measure if senate and senate.measure else vv_measure)
    mtype = B.MEASURE_TYPES.get("".join(ch for ch in measure if ch.isalpha()), "other") if measure else "other"

    text = B.select_text(cls.kind, bill, row["date"]) if cls.kind in B.SUPPORTED_KINDS else B.TextBinding(B.TEXT_NOT_REQUIRED, None, "vote kind not supported for explanation")
    text_rec = {"status": text.status, "version_code": None, "version_name": None, "version_date": None,
                "govinfo_url": None, "sha256": None, "bytes": None, "stage_attribute_matches": None,
                "selection_reason": text.selection_reason, "candidates": list(text.candidates)}
    if text.status == B.TEXT_BOUND and text.version is not None:
        v = text.version
        f = store.fetch(v.url, f"text/{Path(v.url).name}", min_bytes=500, offline=offline)
        text_rec.update({"version_code": v.code, "version_name": v.name, "version_date": v.date, "govinfo_url": v.url})
        if f.ok and f.path is not None:
            head = f.path.read_bytes()[:4000]
            sm = B.stage_matches(v.code, head)
            text_rec.update({"sha256": f.sha256, "bytes": f.size, "stage_attribute_matches": sm})
            if sm is False:
                text_rec["status"] = B.TEXT_AMBIGUOUS
                text_rec["selection_reason"] += f"; GovInfo file's bill-stage does not match {v.code}"
        else:
            text_rec["status"] = B.TEXT_PENDING
            text_rec["selection_reason"] += f"; text not retrievable ({f.message})"

    cra = B.cra_from_title(bill.title) if (bill is not None and mtype == "joint_resolution") else B.Cra(False)
    eligible = cls.summary_eligible and status == "VERIFIED" and text_rec["status"] == B.TEXT_BOUND
    head = B.HEADINGS.get(cls.kind); yn = B.YEA_NAY.get(cls.kind)
    nxt = B.next_step(measure, bill.origin_chamber if bill else None, bill.title if bill else "", cls.kind,
                      senate.title if senate else "", action_text, text_rec["version_code"] or "",
                      row["vote_result"].strip(), int(row["yea_count"]), int(row["nay_count"]), row["majority_requirement"],
                      B.house_passage_before(bill.actions, row["date"]) if bill else None)
    return {
        "schema": BINDING_SCHEMA,
        "vote": {"congress": int(row["congress"]), "session": session, "clerk_number": clerk,
                 "voteview_id": int(row["rollnumber"]), "date": row["date"],
                 "question": row["vote_question"].strip(), "result": row["vote_result"].strip(),
                 "required": row["majority_requirement"], "yeas": int(row["yea_count"]), "nays": int(row["nay_count"]),
                 "measure": vv_measure or None,
                 "senate_url": senate_vote_url(int(row["congress"]), session, clerk),
                 "senate_sha256": store.manifest.get(f"senate/vote_{row['congress']}_{session}_{clerk:05d}.xml", {}).get("sha256"),
                 "senate_title": senate.title if senate else None,
                 "senate_document_text": senate.document_text if senate else None,
                 "amendment_number": (senate.amendment_number or None) if senate else None,
                 "voteview_url": f"https://voteview.com/rollcall/RS{row['congress']}{int(row['rollnumber']):04d}"},
        "classification": {"kind": cls.kind, "summary_eligible": eligible, "kind_supported": cls.summary_eligible,
                           "basis": list(cls.basis), "conflict": cls.conflict or None},
        "object": {"type": mtype, "id": measure or None, "title": bill.title if bill else None,
                   "short_title": bill.short_title if bill else None, "origin_chamber": bill.origin_chamber if bill else None,
                   "billstatus_source": f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{cfg.congress}/{bill.bill_type.lower()}/{bill.filename}" if bill else None,
                   "billstatus_sha256": bill.sha256 if bill else None, "billstatus_update_date": bill.update_date if bill else None,
                   "passage_action_text": action_text or None},
        "text_binding": text_rec,
        "cra": {"is_cra": cra.is_cra, "agency": cra.agency, "rule_title": cra.rule_title, "title_form": cra.title_form,
                "consequence_ref": cra.consequence_ref, "underlying_rule_source": cra.underlying_rule_source,
                "underlying_rule_sha256": cra.underlying_rule_sha256},
        # the receipt scaffold: fixed per kind, never generated; the page does not read it yet
        "receipt": {"deciding": senate.question_text if senate else None,
                    "heading_success": head[0] if head else None, "heading_failure": head[1] if head else None,
                    "yea_means": yn[0] if yn else None, "nay_means": yn[1] if yn else None,
                    # (A) what this vote actually did, and (B) what follows it; a failed vote gets only a marked counterfactual
                    "vote_result": {"outcome": nxt.outcome, "official_result": row["vote_result"].strip(), "statement": nxt.result_statement},
                    "next_step": {"case": nxt.case, "actual": nxt.actual, "hypothetical": nxt.hypothetical, "basis": nxt.basis},
                    "sources": [s for s in [
                        {"what": "Senate roll-call record", "url": senate_vote_url(int(row["congress"]), session, clerk)},
                        {"what": "Bill status (GovInfo)", "url": f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{cfg.congress}/{bill.bill_type.lower()}/{bill.filename}"} if bill else None,
                        {"what": f"Text as voted on ({text_rec['version_name']})", "url": text_rec["govinfo_url"]} if text_rec["govinfo_url"] else None,
                        {"what": "Roll call at Voteview", "url": f"https://voteview.com/rollcall/RS{row['congress']}{int(row['rollnumber']):04d}"},
                    ] if s]},
        "verification": {"status": status, "checks": checks},
    }


def _strip_volatile(b: dict) -> dict:
    return {k: v for k, v in b.items() if k not in ("history", "recorded_utc")}


def write_binding(dir_: Path, b: dict) -> str:
    """Write or update one tracked binding, keeping history. Returns 'new', 'changed' or 'unchanged'."""
    from datetime import datetime, timezone
    dir_.mkdir(parents=True, exist_ok=True)
    v = b["vote"]
    path = dir_ / f"vote_{v['congress']}_{v['session']}_{v['clerk_number']:05d}.json"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if path.exists():
        old = json.loads(path.read_text())
        if _strip_volatile(old) == _strip_volatile(b):
            return "unchanged"
        hist = old.get("history", [])
        prev = _strip_volatile(old); prev["superseded_utc"] = stamp
        hist.append(prev)
        b = dict(b, history=hist, recorded_utc=stamp)
        path.write_text(json.dumps(b, indent=1, ensure_ascii=False) + "\n")
        return "changed"
    b = dict(b, history=[], recorded_utc=stamp)
    path.write_text(json.dumps(b, indent=1, ensure_ascii=False) + "\n")
    return "new"


def run(cfg: Config = DEFAULT, offline: bool = False, verbose: bool = True) -> dict:
    rows = voteview_rows(cfg)
    bills = billstatus.load_records(cfg.billflow_zip, cfg.billflow_house_zip, cfg.billstatus_sjres_zip, cfg.billstatus_hjres_zip)
    lis_map = lis_to_bioguide(cfg)
    vv_members = voteview_members(cfg)
    store = Store(cfg.explain_raw_dir)
    # classify everything from the official question; bind the supported kinds
    kinds = Counter()
    eligible_rows = []
    for row in rows:
        k = B.QUESTION_KINDS.get(row["vote_question"].strip(), B.OTHER)
        kinds[k] += 1
        if k in B.SUPPORTED_KINDS:
            eligible_rows.append(row)
    mv = member_votes_for(cfg, {int(r["rollnumber"]) for r in eligible_rows})
    outcomes = Counter(); text_statuses = Counter(); ver_statuses = Counter(); kinds_final = Counter(); writes = Counter()
    bindings = []
    for row in eligible_rows:
        session, clerk = int(row["session"]), int(row["clerk_rollnumber"])
        rel = f"senate/vote_{row['congress']}_{session}_{clerk:05d}.xml"
        f = store.fetch(senate_vote_url(int(row["congress"]), session, clerk), rel, offline=offline)
        senate = None
        if f.ok and f.path is not None:
            try:
                senate = parse_senate_vote(f.path)
            except Exception as e:  # noqa: BLE001 - a malformed record is a data fact to report, not a crash
                if verbose:
                    print(f"  senate xml unreadable for {rel}: {e}")
        measure = rollcalls._norm_bill(row["bill_number"])
        bill = bills.get(measure)
        per_vote_map = map_lis(senate, lis_map, vv_members, senate.members) if senate is not None else ({}, {})
        b = build_binding(cfg, row, senate, bill, mv.get(int(row["rollnumber"]), {}), per_vote_map, store, offline)
        bindings.append(b)
        writes[write_binding(cfg.bindings_dir, b)] += 1
        kinds_final[b["classification"]["kind"]] += 1
        ver_statuses[b["verification"]["status"]] += 1
        text_statuses[b["text_binding"]["status"]] += 1
        outcomes["eligible" if b["classification"]["summary_eligible"] else "not_eligible"] += 1
    store.save()
    index = {"schema": BINDING_SCHEMA, "congress": cfg.congress, "rule": {
                 "supported_kinds": sorted(B.SUPPORTED_KINDS), "pending_window_days": B.PENDING_WINDOW_DAYS,
                 "never_selected_versions": sorted(B.NEVER)},
             "classified": dict(kinds), "bound": [
                 {"file": f"vote_{b['vote']['congress']}_{b['vote']['session']}_{b['vote']['clerk_number']:05d}.json",
                  "measure": b["object"]["id"], "kind": b["classification"]["kind"], "verification": b["verification"]["status"],
                  "text": b["text_binding"]["status"], "summary_eligible": b["classification"]["summary_eligible"],
                  "cra": b["cra"]["is_cra"]} for b in sorted(bindings, key=lambda x: (x["vote"]["session"], x["vote"]["clerk_number"]))]}
    (cfg.bindings_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n")
    summary = {"classified": dict(kinds), "bound_kinds": dict(kinds_final), "verification": dict(ver_statuses),
               "text": dict(text_statuses), "eligibility": dict(outcomes), "writes": dict(writes)}
    if verbose:
        print(json.dumps(summary, indent=1))
    return summary


def main() -> int:
    offline = "--offline" in sys.argv
    run(DEFAULT, offline=offline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
