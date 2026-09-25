"""Pillar 4 reference anchors: three recognisable figures on the senator scale.

    PYTHONPATH=src python -m civicalign.ideology.anchors [--dry-run]

So an ordinary reader can place a senator's score, Pillar 4 shows exactly
three well-known figures on the same Voteview nominate_dim1 scale:

    Bernie Sanders  a current senator: his own Voteview score
    Joe Biden       his Senate voting record (Delaware), not his presidency
    JD Vance        his Senate voting record (Ohio), not his vice presidency

Each score is the one Voteview publishes in HSall_members.csv, read from the
verified source snapshot (a file whose bytes do not match the snapshot is
refused) and stored as a versioned record in reference_anchors. Voteview
estimates one nominate_dim1 per legislator for a whole congressional career,
so the value must be the same on every House and Senate row of that
legislator; if it is not, the anchor is refused rather than averaged.
Voteview's "President" rows are a different estimate (from positions a
president announced, not votes cast) under a different id, and are never used.

These are visual reference points ONLY. No calculation reads this module or
the reference_anchors table: not the Pillar 5 centres, not the weights, not
any median, mean or drift, and not the result key (tested).
"""
import argparse
import csv
import json
import sys

from ..config import DEFAULT, Config
from . import ingest as I
from . import records as R
from .store import Table

COUNT = 3

# Chosen by the user on 2026-09-25. The labels say whose voting record the score comes from.
ANCHORS = (
    {"anchor_id": "sanders", "bioguide_id": "S000033", "display_name": "Bernie Sanders",
     "record_basis": ("current senator (Vermont); Voteview gives one score for his whole congressional record: "
                      "House 1991-2007 and Senate since 2007")},
    {"anchor_id": "biden", "bioguide_id": "B000444", "display_name": "Joe Biden",
     "record_basis": "Senate voting record (Delaware, 1973-2009); not his presidency"},
    {"anchor_id": "vance", "bioguide_id": "V000137", "display_name": "JD Vance",
     "record_basis": "Senate voting record (Ohio, 2023-2025); not his vice presidency"},
)


class AnchorError(ValueError):
    pass


def _check_count(specs) -> None:
    ids = [s["anchor_id"] for s in specs]
    if len(specs) != COUNT or len(set(ids)) != COUNT or len({s["bioguide_id"] for s in specs}) != COUNT:
        raise AnchorError(f"Pillar 4 shows exactly {COUNT} distinct anchors, got {ids}")


def anchor_from_rows(spec: dict, rows: list[dict]) -> dict:
    """The Voteview fields for one anchor from member-file rows (no provenance).
    The legislator is the Voteview id on the person's Senate rows; every House
    and Senate row of that id must carry the same nominate_dim1."""
    b = spec["bioguide_id"]
    senate_ids = {r["icpsr"] for r in rows if r["bioguide_id"] == b and r["chamber"] == "Senate"}
    if len(senate_ids) != 1:
        raise AnchorError(f"{b}: expected one Voteview Senate id, found {sorted(senate_ids)}")
    icpsr = senate_ids.pop()
    mine = [r for r in rows if r["icpsr"] == icpsr and r["chamber"] in ("House", "Senate")]
    scores = {r["nominate_dim1"] for r in mine if r["nominate_dim1"] not in ("", None)}
    if len(scores) != 1:
        raise AnchorError(f"{b}: expected one nominate_dim1 across the career, found {sorted(scores)}")
    congresses, votes = {}, {}
    for r in mine:
        ch, c = r["chamber"], int(r["congress"])
        lo, hi = congresses.get(ch, [c, c])
        congresses[ch] = [min(lo, c), max(hi, c)]
        votes[ch] = votes.get(ch, 0) + (I._int(r.get("nominate_number_of_votes")) or 0)
    return {"anchor_id": spec["anchor_id"], "bioguide_id": b, "display_name": spec["display_name"],
            "record_basis": spec["record_basis"], "voteview_icpsr": icpsr, "voteview_name": mine[0]["bioname"],
            "score_column": "nominate_dim1", "nominate_dim1": float(scores.pop()),
            "congresses": dict(sorted(congresses.items())), "number_of_votes": dict(sorted(votes.items())), "use": R.ANCHOR_USE}


def anchor_records(cfg: Config, snap: dict, specs=ANCHORS) -> list[dict]:
    """The anchor records from the verified Voteview member file."""
    _check_count(specs)
    prov = I.provenance(I.source_entry(cfg, snap, cfg.members_csv.name), I.VOTEVIEW)
    wanted = {s["bioguide_id"] for s in specs}
    with cfg.members_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    icpsrs = {r["icpsr"] for r in rows if r["bioguide_id"] in wanted}
    rows = [r for r in rows if r["icpsr"] in icpsrs]
    return [{**anchor_from_rows(s, rows), **prov} for s in specs]


def register(cfg: Config = DEFAULT, dry_run: bool = False, specs=ANCHORS) -> int:
    """Append new anchor versions. Returns how many were (or would be) written."""
    snap = I.snapshot(cfg)
    t = Table(cfg.ideology_dir, "reference_anchors")
    rows = anchor_records(cfg, snap, specs)
    return len(t.plan(rows)) if dry_run else t.append(rows, snap["run_utc"])


def current(cfg: Config = DEFAULT, specs=ANCHORS) -> list[dict]:
    """The stored anchors, in the order of `specs`; refuses anything but exactly those three."""
    _check_count(specs)
    by_id = {r["anchor_id"]: r for r in Table(cfg.ideology_dir, "reference_anchors").current()}
    missing = [s["anchor_id"] for s in specs if s["anchor_id"] not in by_id]
    extra = sorted(set(by_id) - {s["anchor_id"] for s in specs})
    if missing or extra:
        raise AnchorError(f"stored anchors do not match the configured three (missing {missing}, extra {extra}): run anchors")
    return [by_id[s["anchor_id"]] for s in specs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        n = register(DEFAULT, a.dry_run)
    except (I.SnapshotMismatch, AnchorError) as e:
        print(f"ANCHORS REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"reference anchors: {n} new version(s) {'would be ' if a.dry_run else ''}written")
    if not a.dry_run:
        print(json.dumps([{k: r[k] for k in ("display_name", "nominate_dim1", "congresses", "number_of_votes")} for r in current(DEFAULT)], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
