"""Senate bills classified by their primary sponsor's voting-record score.

    PYTHONPATH=src python -m civicalign.ideology.bills [--dry-run] [--tally]

A deterministic data layer for later Pillar 5 outcome counts and Pillar 6
committee bill-flow counts. Nothing here is displayed yet, and nothing here is
an input to the Pillars 4-6 calculations.

Source: the GovInfo bill-status archive for the Congress's Senate bills
(BILLSTATUS-<congress>-s.zip), read only if its bytes match the verified source
snapshot. For every bill: its type, number, title and introduction date; the
primary sponsor's name and Bioguide id; the latest action and any public laws;
and each Senate standing committee (code SS + two letters) with whether it was
referred the bill ("Referred To"), reported it ("Reported By" or "Reported
Original Measure") or was discharged of it ("Discharged From").

Sponsor score: the sponsor's nominate_dim1 from the stored senator_ideology
table (Voteview HSall_members.csv, the Congress's Senate rows), matched on the
Bioguide id. Classification rule sponsor_nominate_dim1_sign_v1:

    score < 0   LIBERAL_SPONSOR
    score > 0   CONSERVATIVE_SPONSOR
    score == 0  ZERO_SCORE_SPONSOR
    no sponsor, no Bioguide id, no Voteview row for the Congress, or no score  UNKNOWN (with the reason)

This is a SPONSOR-BASED classification. It describes the sponsor's voting
record, never the bill's content: every record carries the fixed wording
"Bill sponsored by a senator with a negative/positive DW-NOMINATE score" and
the basis statement, so nothing downstream can present the sponsor's score as
the bill's ideology.

The classification is fixed arithmetic on stored numbers. It reads no model,
calls no network service, and runs no external program (tested).

Versioning: one record per bill, key (congress, bill_id), stored append-only and
hash-chained like every Engine B table. A bill whose archive content (SHA-256
of its XML), sponsor score record and rule are all unchanged keeps its stored
record, so an unchanged archive writes nothing; source_version and retrieved_at
therefore name the archive version in which the bill's current content was
first seen.
"""
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile

from ..config import DEFAULT, Config
from . import ingest as I
from . import records as R
from .store import Table

TABLE = "bill_sponsor_classifications"
BILL_SOURCE = "GovInfo bill-status bulk data (BILLSTATUS), Senate bills"
BILL_URL = "https://www.govinfo.gov/bulkdata/BILLSTATUS/{congress}/s/{member}"
SCORE_SOURCE = "Voteview HSall_members.csv nominate_dim1 (stored senator_ideology table)"


def _text(node, path):
    v = node.findtext(path)
    return v.strip() if isinstance(v, str) and v.strip() else None


def classify(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    return "LIBERAL_SPONSOR" if score < 0 else "CONSERVATIVE_SPONSOR" if score > 0 else "ZERO_SCORE_SPONSOR"


def parse_bill(xml: bytes) -> dict:
    """The fields of one bill-status XML file that this layer uses."""
    bill = ET.fromstring(xml).find("bill")
    if bill is None:
        raise I.SnapshotMismatch("a bill-status file has no <bill> element")
    sponsors = bill.findall("sponsors/item")
    sp = sponsors[0] if sponsors else None
    committees = {}
    for c in bill.findall("committees/item"):
        code = (_text(c, "systemCode") or "")[:4].upper()
        if not (code.startswith("SS") and len(code) == 4 and (_text(c, "chamber") or "") == "Senate"):
            continue
        acts = [(_text(a, "name") or "", _text(a, "date")) for a in c.findall("activities/item")]
        referred = sorted(d for n, d in acts if n == "Referred To" and d)
        reported = sorted(d for n, d in acts if n.startswith("Reported") and d)
        rec = committees.setdefault(code, {"committee_id": code, "referred": False, "referred_date": None,
                                           "reported": False, "reported_date": None, "discharged": False})
        rec["referred"] = rec["referred"] or any(n == "Referred To" for n, _ in acts)
        rec["reported"] = rec["reported"] or any(n.startswith("Reported") for n, _ in acts)
        rec["discharged"] = rec["discharged"] or any(n == "Discharged From" for n, _ in acts)
        rec["referred_date"] = min([x for x in (rec["referred_date"], *referred) if x], default=None)
        rec["reported_date"] = min([x for x in (rec["reported_date"], *reported) if x], default=None)
    laws = [f"{_text(l, 'type') or ''} {_text(l, 'number') or ''}".strip() for l in bill.findall("laws/item")]
    return {
        "congress": int(_text(bill, "congress")), "bill_type": (_text(bill, "type") or "").upper(),
        "bill_number": int(_text(bill, "number")), "title": _text(bill, "title") or "",
        "introduced_date": _text(bill, "introducedDate"), "update_date": _text(bill, "updateDate"),
        "sponsor_count": len(sponsors),
        "sponsor_name": _text(sp, "fullName") if sp is not None else None,
        "sponsor_bioguide": _text(sp, "bioguideId") if sp is not None else None,
        "sponsor_by_request": bool(sp is not None and _text(sp, "isByRequest") == "Y"),
        "latest_action_date": _text(bill, "latestAction/actionDate"), "latest_action_text": _text(bill, "latestAction/text"),
        "laws": laws, "committees": [committees[k] for k in sorted(committees)],
    }


def sponsor_score(bioguide: str | None, senators: dict[str, dict]) -> tuple[float | None, str | None, str | None, str | None]:
    """(score, senator_ideology record_id, its source_version, why UNKNOWN or None)."""
    if not bioguide:
        return None, None, None, "no primary sponsor Bioguide id in the bill-status record"
    line = senators.get(bioguide)
    if line is None:
        return None, None, None, f"sponsor {bioguide} has no Voteview Senate row for this Congress"
    c = line["content"]
    if c["nominate_dim1"] is None:
        return None, line["record_id"], c["source_version"], f"Voteview has not scored sponsor {bioguide} yet"
    return c["nominate_dim1"], line["record_id"], c["source_version"], None


def build_record(parsed: dict, fingerprint: str, member: str, senators: dict[str, dict], prov: dict) -> dict:
    if parsed["sponsor_count"] == 0:
        score, rid, sver, why = None, None, None, "the bill-status record lists no primary sponsor"
    else:
        score, rid, sver, why = sponsor_score(parsed["sponsor_bioguide"], senators)
    cls = classify(score)
    return {
        "congress": parsed["congress"], "bill_type": parsed["bill_type"], "bill_number": parsed["bill_number"],
        "bill_id": f"{parsed['bill_type']}{parsed['bill_number']}", "title": parsed["title"],
        "introduced_date": parsed["introduced_date"], "primary_sponsor_name": parsed["sponsor_name"],
        "sponsor_bioguide_id": parsed["sponsor_bioguide"], "sponsor_by_request": parsed["sponsor_by_request"],
        "sponsor_nominate_dim1": score, "sponsor_classification": cls,
        "sponsor_classification_label": R.SPONSOR_LABELS[cls],
        "classification_basis": R.SPONSOR_BASIS, "classification_rule": R.SPONSOR_RULE, "unknown_reason": why,
        "sponsor_score_source": SCORE_SOURCE if rid else None, "sponsor_score_record_id": rid,
        "sponsor_score_source_version": sver,
        "bill_source": BILL_SOURCE, "bill_source_url": BILL_URL.format(congress=parsed["congress"], member=member),
        "bill_fingerprint": fingerprint, "bill_update_date": parsed["update_date"],
        "bill_status": {"latest_action_date": parsed["latest_action_date"], "latest_action_text": parsed["latest_action_text"],
                        "laws": parsed["laws"]},
        "referred_committees": parsed["committees"], **prov,
    }


def bill_records(cfg: Config, snap: dict, current: dict[tuple, dict]) -> list[dict]:
    """Every Senate bill of the Congress in the verified archive, classified. A bill
    whose content, sponsor score record and rule are unchanged keeps its stored record."""
    entry = I.source_entry(cfg, snap, cfg.billflow_zip.name)
    prov = I.provenance(entry, BILL_SOURCE)
    senators = {l["content"]["bioguide_id"]: l for l in Table(cfg.ideology_dir, "senator_ideology").latest().values()
                if l["content"]["congress"] == cfg.congress}
    if not senators:
        raise I.SnapshotMismatch("no senator_ideology rows for this Congress: run ingest first")
    out, seen = [], set()
    with zipfile.ZipFile(cfg.billflow_zip) as z:
        for member in sorted(n for n in z.namelist() if n.endswith(".xml")):
            data = z.read(member)
            parsed = parse_bill(data)
            if parsed["congress"] != cfg.congress or parsed["bill_type"] != "S":
                continue
            key = (parsed["congress"], f"{parsed['bill_type']}{parsed['bill_number']}")
            if key in seen:
                raise I.SnapshotMismatch(f"two bill-status files for {key}")
            seen.add(key)
            fp = hashlib.sha256(data).hexdigest()
            prev = current.get(key)
            _, rid, _, _ = (sponsor_score(parsed["sponsor_bioguide"], senators) if parsed["sponsor_count"]
                            else (None, None, None, None))
            if (prev is not None and prev["bill_fingerprint"] == fp and prev["sponsor_score_record_id"] == rid
                    and prev["classification_rule"] == R.SPONSOR_RULE):
                out.append(prev)          # unchanged: keep the stored record, so nothing is rewritten
            else:
                out.append(build_record(parsed, fp, member, senators, prov))
    if not out:
        raise I.SnapshotMismatch("no Senate bills of this Congress in the bill-status archive")
    return out


def run(cfg: Config = DEFAULT, dry_run: bool = False) -> dict:
    snap = I.snapshot(cfg)
    t = Table(cfg.ideology_dir, TABLE)
    rows = bill_records(cfg, snap, {k: line["content"] for k, line in t.latest().items()})
    written = len(t.plan(rows)) if dry_run else t.append(rows, snap["run_utc"])
    return {"bills": len(rows), ("new_versions_that_would_be_written" if dry_run else "new_versions_written"): written}


def current(cfg: Config = DEFAULT, congress: int | None = None) -> list[dict]:
    """The stored classification records for the Congress, in bill-number order."""
    congress = congress or cfg.congress
    rows = [r for r in Table(cfg.ideology_dir, TABLE).current() if r["congress"] == congress]
    return sorted(rows, key=lambda r: (r["bill_type"], r["bill_number"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tally", action="store_true", help="print the sponsor and committee tallies (counts only)")
    a = ap.parse_args()
    try:
        print(json.dumps(run(DEFAULT, a.dry_run), indent=1))
    except I.SnapshotMismatch as e:
        print(f"BILLS REFUSED: {e}", file=sys.stderr)
        return 1
    if a.tally:
        from .bill_tallies import committee_tallies, sponsor_tally
        rows = current(DEFAULT)
        s = sponsor_tally(rows)
        print(json.dumps({"all_senate_bills": {k: v["count"] for k, v in s["by_classification"].items()} | {"total": s["total"]},
                          "committees": {c: {"referred": v["referred"]["total"], "reported": v["reported"]["total"]}
                                         for c, v in committee_tallies(rows).items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
