"""Ingest the verified source snapshot into the versioned Pillars 4-6 tables.

    PYTHONPATH=src python -m civicalign.ideology.ingest [--dry-run]

Reads only files the snapshot (data/raw/SNAPSHOT.json) accepted, and refuses a
file whose bytes no longer match the snapshot's SHA-256, so every record names
the exact content it came from. Writes new versions only; an ingest of an
unchanged snapshot writes nothing.

    senator_ideology            Voteview HSall_members.csv, every Senate row of the
                                Congress, joined to the congress-legislators roster
    constituency_ideology       American Ideology Project state estimates, every wave
    state_population            Census state population estimates, every year of the vintage
    committee_membership_events congress-legislators committee-membership-current.json,
                                standing committees only, as observed changes
    committee_names             congress-legislators committees-current.json: each Senate
                                standing committee's official name

No metric is computed here, and nothing is read from Engine A.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from ..config import DEFAULT, Config
from ..sources.population import USPS
from . import records as R
from .store import Table

VOTEVIEW = "Voteview (voteview.com, UCLA): member ideology file HSall_members.csv"
ROSTER = "unitedstates/congress-legislators: legislators-current.json"
AIP = ("American Ideology Project (Tausanovitch & Warshaw), subnational ideology estimates v2022, "
       "file aip_states_ideology_v2022a.tab, column mrp_ideology")
AIP_URL = "https://doi.org/10.7910/DVN/BQKU4M"
COMMITTEES = "unitedstates/congress-legislators: committee-membership-current.json"
COMMITTEE_LIST = "unitedstates/congress-legislators: committees-current.json"
VOTEVIEW_PARTY = {"100": "Democrat", "200": "Republican", "328": "Independent"}


class SnapshotMismatch(RuntimeError):
    pass


def snapshot(cfg: Config) -> dict:
    path = cfg.raw_dir / "SNAPSHOT.json"
    if not path.exists():
        raise SnapshotMismatch(f"no snapshot record at {path}: fetch sources first")
    snap = json.loads(path.read_text())
    if not snap.get("accepted"):
        raise SnapshotMismatch("the last snapshot was not accepted")
    return snap


def source_entry(cfg: Config, snap: dict, filename: str) -> dict:
    """The snapshot's record for a file, after checking the file on disk is
    byte-for-byte the content the snapshot accepted."""
    entry = next((s for s in snap["sources"] if s["file"] == filename), None)
    if entry is None:
        raise SnapshotMismatch(f"{filename} is not in the snapshot")
    path = cfg.raw_dir / filename
    if not path.exists():
        raise SnapshotMismatch(f"{filename} is missing from {cfg.raw_dir}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SnapshotMismatch(f"{filename} on disk does not match the snapshot (sha256 {digest[:12]} vs {entry['sha256'][:12]})")
    return entry


def provenance(entry: dict, source: str) -> dict:
    """Source fields for a record. retrieved_at is when CivicAlign first
    retrieved THIS content (the snapshot's content-changed time), so an
    unchanged file keeps its date and re-ingesting it writes nothing."""
    return {"source": source, "source_url": entry["url"], "source_version": str(entry["content_key"]),
            "source_sha256": entry["sha256"], "retrieved_at": entry["content_changed_utc"],
            "fixture": bool(entry.get("fixture", False))}


def _float(v):
    return float(v) if v not in ("", None) else None


def _int(v):
    try:
        return int(float(v)) if v not in ("", None) else None
    except ValueError:
        return None


# ---- senators ------------------------------------------------------------------

def roster(cfg: Config) -> dict[str, dict]:
    """Seated senators from the roster: bioguide -> {name, state}."""
    out = {}
    for p in json.loads(cfg.roster_json.read_text()):
        term = p["terms"][-1]
        if term["type"] == "sen":
            out[p["id"]["bioguide"]] = {"name": p["name"].get("official_full") or p["name"]["last"], "state": term["state"]}
    return out


def senator_records(cfg: Config, snap: dict) -> list[dict]:
    """Every Senate row of the Congress in Voteview's member file, plus any
    seated senator Voteview has not scored yet. Guards: one Voteview row per
    senator, the roster and Voteview agree on a seated senator's state, at most
    two seated senators per state, at most 100 seated."""
    vv = provenance(source_entry(cfg, snap, cfg.members_csv.name), VOTEVIEW)
    ro_entry = source_entry(cfg, snap, cfg.roster_json.name)
    seated = roster(cfg)
    rows: dict[str, dict] = {}
    with cfg.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] != "Senate" or row["congress"] != str(cfg.congress):
                continue
            b = row["bioguide_id"]
            if not b:
                raise SnapshotMismatch(f"Voteview Senate row without a bioguide id: icpsr {row['icpsr']}")
            if b in rows:
                raise SnapshotMismatch(f"two Voteview rows for {b} in the {cfg.congress}th Congress")
            rows[b] = row
    out = []
    for b, row in rows.items():
        if b in seated and seated[b]["state"] != row["state_abbrev"]:
            raise SnapshotMismatch(f"{b}: roster state {seated[b]['state']} but Voteview state {row['state_abbrev']}")
        out.append({"senator_id": row["icpsr"], "bioguide_id": b, "congress": cfg.congress, "chamber": "Senate",
                    "state": row["state_abbrev"], "name": row["bioname"], "voteview_party_code": row["party_code"], "voteview_row": True,
                    "nominate_dim1": _float(row.get("nominate_dim1")), "nokken_poole_dim1": _float(row.get("nokken_poole_dim1")),
                    "nominate_number_of_votes": _int(row.get("nominate_number_of_votes")), "seated": b in seated,
                    "roster_source_version": str(ro_entry["content_key"]), "roster_retrieved_at": ro_entry["content_changed_utc"], **vv})
    for b, s in seated.items():
        if b not in rows:   # seated but not yet in Voteview's file: recorded with no scores, never a predecessor's
            out.append({"senator_id": None, "bioguide_id": b, "congress": cfg.congress, "chamber": "Senate", "state": s["state"],
                        "name": s["name"], "voteview_party_code": None, "voteview_row": False, "nominate_dim1": None,
                        "nokken_poole_dim1": None, "nominate_number_of_votes": None, "seated": True,
                        "roster_source_version": str(ro_entry["content_key"]), "roster_retrieved_at": ro_entry["content_changed_utc"], **vv})
    per_state: dict[str, int] = {}
    for r in out:
        if r["seated"]:
            per_state[r["state"]] = per_state.get(r["state"], 0) + 1
    crowded = {s: n for s, n in per_state.items() if n > 2}
    if crowded or sum(per_state.values()) > R.SENATE_SEATS:
        raise SnapshotMismatch(f"seated senators do not fit the Senate: {crowded or sum(per_state.values())}")
    return sorted(out, key=lambda r: (r["state"], r["bioguide_id"]))


# ---- state publics -------------------------------------------------------------------

def constituency_records(cfg: Config, snap: dict) -> list[dict]:
    """Every AIP state row, every wave, in AIP's own units."""
    prov = provenance(source_entry(cfg, snap, cfg.ideology_tab.name), AIP)
    prov["source_url"] = AIP_URL if not prov["fixture"] else prov["source_url"]
    out = []
    with cfg.ideology_tab.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            usps = row["abb"].strip().strip('"')
            wave = int(row["presidential_year"])
            out.append({"geography_type": "state", "geography_id": usps, "geography_name": row["state"].strip().strip('"'),
                        "estimate": float(row["mrp_ideology"]), "standard_error": float(row["mrp_ideology_se"]),
                        "survey_period": row["survey_period"].strip().strip('"'), "wave": wave, "sample_size": _int(row.get("sample_size")),
                        "methodology_version": f"AIP v2022a mrp_ideology, presidential-year wave {wave}", "scale": R.SCALE_NOTE_AIP, **prov})
    if not out:
        raise SnapshotMismatch("no rows in the AIP file")
    return sorted(out, key=lambda r: (r["wave"], r["geography_id"]))


# ---- state populations -------------------------------------------------------------------

CENSUS = "U.S. Census Bureau, Vintage 2024 national and state population estimates (NST-EST2024-ALLDATA.csv)"


def population_records(cfg: Config, snap: dict) -> list[dict]:
    """Every POPESTIMATE<year> column for the 50 states and DC (SUMLEV 040).
    The vintage is read from the file name (NST-EST<vintage>); each year is a
    July 1 estimate from that vintage."""
    prov = provenance(source_entry(cfg, snap, cfg.population_csv.name), CENSUS)
    m = re.search(r"NST-EST(\d{4})", cfg.population_csv.name)
    if not m:
        raise SnapshotMismatch(f"cannot read the Census vintage from {cfg.population_csv.name}")
    vintage = f"Vintage {m.group(1)}"
    out = []
    with cfg.population_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("SUMLEV") != "040" or row["NAME"] not in USPS:
                continue
            for col, val in row.items():
                ym = re.fullmatch(r"POPESTIMATE(\d{4})", col or "")
                if ym and val:
                    out.append({"geography_type": "state", "geography_id": USPS[row["NAME"]], "geography_name": row["NAME"],
                                "population": int(val), "measurement_year": int(ym.group(1)), "vintage": vintage,
                                "estimate_type": "resident population estimate, July 1 of the measurement year", **prov})
    states = {r["geography_id"] for r in out}
    if len(states) != 51:
        raise SnapshotMismatch(f"expected 50 states and DC in the Census file, found {len(states)}")
    return sorted(out, key=lambda r: (r["measurement_year"], r["geography_id"]))


# ---- committee membership --------------------------------------------------------------

def committee_event_records(cfg: Config, snap: dict, current: dict[tuple, dict]) -> list[dict]:
    """Observed changes since the last ingest. `current` is the table's current
    version per key. A member present now and absent from `current` (or last
    seen leaving) is observed_joined; a present member whose rank, title or side
    changed is observed_role_changed; a current member no longer listed is
    observed_left. The first ingest for a committee marks its events baseline."""
    entry = source_entry(cfg, snap, cfg.committees_json.name)
    prov = provenance(entry, COMMITTEES)
    observed = entry["content_changed_utc"][:10]
    seated = roster(cfg)
    data = json.loads(cfg.committees_json.read_text())
    prefix = cfg.standing_committee_prefix
    committees = sorted(c for c in data if c.startswith(prefix) and len(c) == 4)
    known = {k[1] for k in current}
    out = []
    now_keys = set()
    for code in committees:
        baseline = code not in known
        for m in data[code]:
            b = m.get("bioguide")
            if not b:
                continue
            k = (cfg.congress, code, b)
            now_keys.add(k)
            role = {"rank": _int(m.get("rank")), "title": m.get("title"), "side": m.get("party")}
            prev = current.get(k)
            if prev is None or prev["event"] == "observed_left":
                ev = "observed_joined"
            elif any(prev[f] != role[f] for f in role):
                ev = "observed_role_changed"
            else:
                continue
            first = baseline and ev == "observed_joined"
            out.append({"congress": cfg.congress, "committee_id": code, "bioguide_id": b, "member_name": m.get("name") or b,
                        "event": ev, "observed_date": observed, "date_basis": R.OBSERVED_DATE_BASIS, "baseline": first,
                        "baseline_note": R.BASELINE_NOTE if first else None, **role, "in_current_roster": b in seated, **prov})
    for k, prev in current.items():
        if k[0] == cfg.congress and prev["event"] != "observed_left" and k not in now_keys:
            out.append({**{f: prev[f] for f in ("congress", "committee_id", "bioguide_id", "member_name")},
                        "event": "observed_left", "observed_date": observed, "date_basis": R.OBSERVED_DATE_BASIS, "baseline": False,
                        "baseline_note": None, "rank": None, "title": None, "side": None,
                        "in_current_roster": k[2] in seated, **prov})
    return sorted(out, key=lambda r: (r["committee_id"], r["event"], r["bioguide_id"]))


# ---- committee names -----------------------------------------------------------------------

def committee_name_records(cfg: Config, snap: dict) -> list[dict]:
    """Every Senate standing committee's official name, with the short name the
    page shows. A name that does not have the expected official form is refused,
    never guessed at."""
    prov = provenance(source_entry(cfg, snap, cfg.committee_list_json.name), COMMITTEE_LIST)
    out = []
    for c in json.loads(cfg.committee_list_json.read_text()):
        code = c.get("thomas_id") or ""
        if c.get("type") != "senate" or not (code.startswith(cfg.standing_committee_prefix) and len(code) == 4):
            continue
        name = (c.get("name") or "").strip()
        m = R.COMMITTEE_NAME_PREFIX.match(name)
        if not m:
            raise SnapshotMismatch(f"{code}: official name {name!r} is not of the form 'Senate Committee on ...'")
        out.append({"committee_id": code, "official_name": name, "display_name": m.group("short"), **prov})
    if not out:
        raise SnapshotMismatch("no Senate standing committees in the committee list")
    return sorted(out, key=lambda r: r["committee_id"])


# ---- runner -------------------------------------------------------------------------------

def run(cfg: Config = DEFAULT, dry_run: bool = False) -> dict:
    snap = snapshot(cfg)
    tables = {t: Table(cfg.ideology_dir, t) for t in ("senator_ideology", "constituency_ideology", "state_population",
                                                       "committee_membership_events", "committee_names")}
    batches = {
        "senator_ideology": senator_records(cfg, snap),
        "constituency_ideology": constituency_records(cfg, snap),
        "state_population": population_records(cfg, snap),
        "committee_membership_events": committee_event_records(
            cfg, snap, {k: line["content"] for k, line in tables["committee_membership_events"].latest().items()}),
        "committee_names": committee_name_records(cfg, snap),
    }
    written = {}
    for name, rows in batches.items():
        written[name] = len(tables[name].plan(rows)) if dry_run else tables[name].append(rows, snap["run_utc"])
    return {"snapshot_run_utc": snap["run_utc"], "records_offered": {k: len(v) for k, v in batches.items()},
            "new_versions_written" if not dry_run else "new_versions_that_would_be_written": written}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        print(json.dumps(run(DEFAULT, a.dry_run), indent=1))
    except SnapshotMismatch as e:
        print(f"INGEST REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
