"""Which Senate bills passed the Senate, and which of those were enacted — from the official record.

    PYTHONPATH=src python -m civicalign.ideology.bill_outcomes [--dry-run] [--audit]

Source: the same verified GovInfo bill-status archive as bills.py (read only if
its bytes match the source snapshot). For every Senate bill of the Congress it
stores one senate_bill_outcomes record.

PASSED THE SENATE — rule senate_passage_loc17000_v1:
    the bill-status record has a Library of Congress action with actionCode
    17000 ("Passed/agreed to in Senate"), and no later Senate action vitiates
    the passage. The record keeps the evidence: every code-17000 action (date and
    text), the Senate's own floor action saying the bill passed (text starting
    "Passed Senate", or "... read the third time, and passed" for a bill passed
    on introduction), and whether an "Engrossed in Senate" text version exists.
    On the current archive the three always agree (tested). A bill with several
    passage actions is one bill: the passage date is the earliest code-17000 date.

ENACTED — rule enactment_signature_or_public_law_v1: the record shows a
presidential signature (an action "Signed by President"), or a public law is
recorded (its <laws> element or a "Became Public Law" action, which also covers
a law enacted without a signature or over a veto). A signed bill is law from the
signature; its public-law number can appear in the record days later, so the
number is not required. The record keeps the states apart: enacted,
enactment_basis (SIGNED_BY_PRESIDENT_AND_PUBLIC_LAW_RECORDED, PUBLIC_LAW_RECORDED,
or SIGNED_BY_PRESIDENT_PUBLIC_LAW_NUMBER_PENDING), public_law_number (or null),
public_law_number_pending, and the dates.

Fixed text and date matching on the official record; no model, no network call,
no external program. Records are append-only and hash-chained; a bill whose
archive content and rule are unchanged keeps its stored record, so an unchanged
archive writes nothing.
"""
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

from ..config import DEFAULT, Config
from . import bills as BL
from . import ingest as I
from . import records as R
from .store import Table

TABLE = "senate_bill_outcomes"
PASSAGE_CODE = "17000"
FLOOR_PASSED = re.compile(r"^Passed Senate\b|read the third time, and passed\b")
VITIATED = re.compile(r"\bpassage\b[^.]*\bvitiated\b|\bvitiated\b[^.]*\bpassage\b", re.I)


def _actions(bill) -> list[dict]:
    out = []
    for a in bill.findall("actions/item"):
        out.append({"date": BL._text(a, "actionDate"), "code": BL._text(a, "actionCode"),
                    "source": BL._text(a, "sourceSystem/name"), "text": BL._text(a, "text") or ""})
    return sorted(out, key=lambda a: (a["date"] or "", a["code"] or "", a["text"]))


def parse_outcome(xml: bytes) -> dict:
    bill = ET.fromstring(xml).find("bill")
    if bill is None:
        raise I.SnapshotMismatch("a bill-status file has no <bill> element")
    acts = _actions(bill)
    loc = [{"date": a["date"], "text": a["text"]} for a in acts if a["code"] == PASSAGE_CODE]
    floor = [{"date": a["date"], "text": a["text"]} for a in acts if a["source"] == "Senate" and FLOOR_PASSED.search(a["text"])]
    first = min((a["date"] for a in loc if a["date"]), default=None)
    vitiated = bool(first) and any(a["source"] == "Senate" and VITIATED.search(a["text"]) and (a["date"] or "") >= first for a in acts)
    passed = bool(loc) and not vitiated
    numbers = [BL._text(l, "number") for l in bill.findall("laws/item") if BL._text(l, "number")]
    became = [a for a in acts if a["text"].startswith("Became Public Law")]
    if not numbers:       # a "Became Public Law No: 119-99." action alone also records the number
        numbers = [m.group(1) for a in became for m in [re.search(r"Became Public Law No:\s*([\d-]+)", a["text"])] if m]
    signed = [a["date"] for a in acts if a["text"].startswith("Signed by President") and a["date"]]
    law = bool(numbers) or bool(became)
    enacted = bool(signed) or law
    basis = (None if not enacted else "SIGNED_BY_PRESIDENT_AND_PUBLIC_LAW_RECORDED" if signed and law
             else "PUBLIC_LAW_RECORDED" if law else "SIGNED_BY_PRESIDENT_PUBLIC_LAW_NUMBER_PENDING")
    law_dates = [a["date"] for a in became if a["date"]]
    engrossed = any((BL._text(v, "type") or "") == "Engrossed in Senate" for v in bill.findall("textVersions/item"))
    return {"congress": int(BL._text(bill, "congress")), "bill_type": (BL._text(bill, "type") or "").upper(),
            "bill_number": int(BL._text(bill, "number")), "passed_senate": passed, "passed_senate_date": first if passed else None,
            "loc_passage_actions": loc, "senate_floor_passage_actions": floor, "engrossed_in_senate": engrossed,
            "passage_vitiated": vitiated, "enactment_rule": R.ENACTMENT_RULE, "enacted": enacted, "enactment_basis": basis,
            "enacted_date": min([d for d in (min(signed) if signed else None, min(law_dates) if law_dates else None) if d],
                                default=None) if enacted else None,
            "signed_by_president": bool(signed), "signed_date": min(signed) if signed else None,
            "public_law_number": numbers[0] if numbers else None, "public_law_number_pending": enacted and not numbers,
            "became_public_law_date": min(law_dates) if law_dates else None}


def outcome_records(cfg: Config, snap: dict, current: dict[tuple, dict]) -> list[dict]:
    entry = I.source_entry(cfg, snap, cfg.billflow_zip.name)
    prov = I.provenance(entry, BL.BILL_SOURCE)
    out, seen = [], set()
    with zipfile.ZipFile(cfg.billflow_zip) as z:
        for member in sorted(n for n in z.namelist() if n.endswith(".xml")):
            data = z.read(member)
            o = parse_outcome(data)
            if o["congress"] != cfg.congress or o["bill_type"] != "S":
                continue
            key = (o["congress"], f"S{o['bill_number']}")
            if key in seen:
                raise I.SnapshotMismatch(f"two bill-status files for {key}")
            seen.add(key)
            if o["enacted"] and not o["passed_senate"]:
                raise I.SnapshotMismatch(f"{key[1]} is recorded as enacted but not as passing the Senate: the rule needs review")
            fp = hashlib.sha256(data).hexdigest()
            prev = current.get(key)
            if (prev is not None and prev["bill_fingerprint"] == fp and prev["outcome_rule"] == R.OUTCOME_RULE
                    and prev.get("enactment_rule") == R.ENACTMENT_RULE):
                out.append(prev)
                continue
            out.append({"congress": o["congress"], "bill_id": key[1], "outcome_rule": R.OUTCOME_RULE,
                        **{k: o[k] for k in ("passed_senate", "passed_senate_date", "loc_passage_actions",
                                             "senate_floor_passage_actions", "engrossed_in_senate", "passage_vitiated",
                                             "enactment_rule", "enacted", "enactment_basis", "enacted_date", "signed_by_president",
                                             "signed_date", "public_law_number", "public_law_number_pending",
                                             "became_public_law_date")},
                        "bill_fingerprint": fp, "bill_source_url": BL.BILL_URL.format(congress=o["congress"], member=member), **prov})
    if not out:
        raise I.SnapshotMismatch("no Senate bills of this Congress in the bill-status archive")
    return out


def run(cfg: Config = DEFAULT, dry_run: bool = False) -> dict:
    snap = I.snapshot(cfg)
    t = Table(cfg.ideology_dir, TABLE)
    rows = outcome_records(cfg, snap, {k: line["content"] for k, line in t.latest().items()})
    written = len(t.plan(rows)) if dry_run else t.append(rows, snap["run_utc"])
    return {"bills": len(rows), ("new_versions_that_would_be_written" if dry_run else "new_versions_written"): written}


def current(cfg: Config = DEFAULT, congress: int | None = None) -> list[dict]:
    congress = congress or cfg.congress
    return [r for r in Table(cfg.ideology_dir, TABLE).current() if r["congress"] == congress]


def evidence_disagreements(outcomes: list[dict]) -> list[str]:
    """Bills where the three independent passage signals do not agree (code 17000,
    the Senate floor action, the engrossed text). Empty on the current archive."""
    out = []
    for o in outcomes:
        signals = (bool(o["loc_passage_actions"]), bool(o["senate_floor_passage_actions"]), o["engrossed_in_senate"])
        if len(set(signals)) != 1:
            out.append(f"{o['bill_id']}: code 17000 {signals[0]}, floor action {signals[1]}, engrossed text {signals[2]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--audit", action="store_true", help="print the passed-Senate and enacted sponsor counts")
    a = ap.parse_args()
    try:
        print(json.dumps(run(DEFAULT, a.dry_run), indent=1))
    except I.SnapshotMismatch as e:
        print(f"OUTCOMES REFUSED: {e}", file=sys.stderr)
        return 1
    if a.audit:
        from .bill_tallies import passed_senate_tally
        t = passed_senate_tally(BL.current(DEFAULT), current(DEFAULT))
        print(json.dumps({k: {"total": v["total"], **{c: x["count"] for c, x in v["by_classification"].items()}}
                          for k, v in t.items() if isinstance(v, dict) and "by_classification" in v}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
