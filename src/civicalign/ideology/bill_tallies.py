"""Tallies over the sponsor-classified Senate bills, each traceable to exact bill ids.

Pure functions over bill_sponsor_classifications records (bills.current()).
Nothing here is displayed yet and nothing here chooses which bills matter:

- sponsor_tally(records, outcome_set=None) answers, for the Congress: how many
  bills are in the selected outcome set, and how many were sponsored by a
  senator with a negative (LIBERAL_SPONSOR), positive (CONSERVATIVE_SPONSOR) or
  zero score, or whose sponsor score is UNKNOWN. With no outcome set it counts
  every Senate bill and says that no outcome set has been chosen: which bills
  qualify for a public Pillar 5 outcome count is a separate, later decision.

- committee_tallies(records) answers, for each Senate standing committee: bills
  referred ("Referred To"), bills reported ("Reported By" or "Reported Original
  Measure", which includes original measures a committee reported without a
  referral), and reported-of-referred, each split by sponsor class.

Every count is the length of the sorted list of bill ids returned beside it, so
any number can be traced to the exact bills behind it. The classes describe
each bill's SPONSOR's voting record, not the bill (records.SPONSOR_BASIS).
"""
from . import records as R

OUTCOME_SET_NOT_CHOSEN = ("every Senate bill of the Congress: no outcome set has been chosen yet (which bills "
                          "qualify for a public Pillar 5 outcome count is a separate decision)")


def by_classification(records: list[dict]) -> dict:
    """{total, bill_ids, by_classification: {class: {count, bill_ids, label}}} over the given records."""
    ids = sorted({r["bill_id"] for r in records}, key=_order)
    if len(ids) != len(records):
        raise ValueError("a bill appears twice in the records being tallied")
    out = {"total": len(ids), "bill_ids": ids, "basis": R.SPONSOR_BASIS, "by_classification": {}}
    for cls in R.SPONSOR_CLASSES:
        cids = sorted((r["bill_id"] for r in records if r["sponsor_classification"] == cls), key=_order)
        out["by_classification"][cls] = {"count": len(cids), "bill_ids": cids, "label": R.SPONSOR_LABELS[cls]}
    return out


def _order(bill_id: str):
    head = bill_id.rstrip("0123456789")
    return (head, int(bill_id[len(head):] or 0))


def sponsor_tally(records: list[dict], outcome_set: set[str] | None = None, outcome_set_name: str | None = None) -> dict:
    """Pillar 5 support: the sponsor-class counts for the selected outcome set of bills.
    `outcome_set` is a set of bill ids (e.g. {"S1000", ...}); None means every Senate bill
    of the records' Congress, labelled as not yet chosen. Unknown ids are refused."""
    congresses = {r["congress"] for r in records}
    if len(congresses) > 1:
        raise ValueError(f"records from more than one Congress: {sorted(congresses)}")
    if outcome_set is None:
        chosen, name = records, OUTCOME_SET_NOT_CHOSEN
    else:
        known = {r["bill_id"] for r in records}
        missing = sorted(set(outcome_set) - known, key=_order)
        if missing:
            raise ValueError(f"outcome set names bills with no classification record: {missing[:10]}")
        if not outcome_set_name:
            raise ValueError("an outcome set needs a name that says how its bills were chosen")
        chosen, name = [r for r in records if r["bill_id"] in outcome_set], outcome_set_name
    return {"congress": next(iter(congresses), None), "outcome_set": name,
            "outcome_set_chosen": outcome_set is not None, **by_classification(chosen)}


def committee_tallies(records: list[dict]) -> dict[str, dict]:
    """Pillar 6 support: per Senate standing committee, bills referred, reported, and
    reported-of-referred, each split by sponsor class with the exact bill ids."""
    committees: dict[str, dict[str, list[dict]]] = {}
    for r in records:
        for c in r["referred_committees"]:
            slot = committees.setdefault(c["committee_id"], {"referred": [], "reported": [], "reported_of_referred": []})
            if c["referred"]:
                slot["referred"].append(r)
            if c["reported"]:
                slot["reported"].append(r)
            if c["referred"] and c["reported"]:
                slot["reported_of_referred"].append(r)
    return {cid: {k: by_classification(v) for k, v in slots.items()} for cid, slots in sorted(committees.items())}


def trace_problems(tally: dict) -> list[str]:
    """Every count equals its id list; the class lists partition the total; no id repeats."""
    out = []
    ids = tally["bill_ids"]
    if tally["total"] != len(ids) or len(set(ids)) != len(ids):
        out.append("total does not equal its distinct bill ids")
    union = []
    for cls, v in tally["by_classification"].items():
        if v["count"] != len(v["bill_ids"]):
            out.append(f"{cls}: count does not equal its bill ids")
        union += v["bill_ids"]
    if sorted(union, key=_order) != ids:
        out.append("the class lists do not partition the total")
    return out
