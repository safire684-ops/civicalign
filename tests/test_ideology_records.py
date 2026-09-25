"""Pillars 4-6, Step 1: versioned records, the append-only store, and the ingest.

Fixture tests use the invented files in tests/fixtures/ideology/ (see its
README): they are copied under the real file names into a temporary folder
with a snapshot record marked "fixture": true, and every record they produce
must carry fixture: true. Real-data tests ingest the current verified snapshot
into a temporary folder; nothing in this file writes to data/ideology/."""
import copy
import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import ingest as I
from civicalign.ideology import records as R
from civicalign.ideology.store import StoreError, Table

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "ideology"
FILES = {"HSall_members.csv": "FIXTURE_HSall_members.csv", "legislators-current.json": "FIXTURE_legislators-current.json",
         "committee-membership-current.json": "FIXTURE_committee-membership-current.v1.json",
         "aip_states_ideology_v2022a.tab": "FIXTURE_aip.tab", "NST-EST2024-ALLDATA.csv": "FIXTURE_NST-EST2024-ALLDATA.csv"}


def _entry(raw: Path, name: str, changed: str) -> dict:
    data = (raw / name).read_bytes()
    return {"name": f"FIXTURE {name}", "url": f"file://FIXTURE/{name}", "file": name, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "content_key": "FIXTURE-" + hashlib.sha256(data).hexdigest()[:16],
            "changed": True, "content_changed_utc": changed, "checked_utc": changed, "vintage": "FIXTURE", "critical": True, "fixture": True}


def fixture_raw(tmp: Path, committees: str = "FIXTURE_committee-membership-current.v1.json", when="2026-01-05T11:00:00Z") -> "dataclasses":
    raw = tmp / "FIXTURE_raw"
    raw.mkdir(parents=True, exist_ok=True)
    for real, fx in {**FILES, "committee-membership-current.json": committees}.items():
        shutil.copy(FIX / fx, raw / real)
    old = json.loads((raw / "SNAPSHOT.json").read_text()) if (raw / "SNAPSHOT.json").exists() else None
    entries = []
    for real in FILES:
        prev = next((e for e in (old or {}).get("sources", []) if e["file"] == real), None)
        e = _entry(raw, real, when)
        if prev and prev["sha256"] == e["sha256"]:
            e["content_changed_utc"] = prev["content_changed_utc"]      # unchanged content keeps its first-retrieved date
        entries.append(e)
    (raw / "SNAPSHOT.json").write_text(json.dumps({"run_utc": when, "accepted": True, "sources": entries}))
    return dataclasses.replace(DEFAULT, raw_dir=raw, ideology_dir=tmp / "FIXTURE_ideology")


# ---- validators ------------------------------------------------------------------

def _senator(**over):
    base = {"senator_id": "900001", "bioguide_id": "FX00001", "congress": 119, "chamber": "Senate", "state": "ZZ",
            "name": "FIXTURE Senator Alpha", "voteview_party_code": "100", "voteview_row": True, "nominate_dim1": -0.4,
            "nokken_poole_dim1": -0.35, "nominate_number_of_votes": 500, "seated": True, "roster_source_version": "FIXTURE",
            "roster_retrieved_at": "2026-01-05T11:00:00Z", "source": "FIXTURE", "source_url": "file://FIXTURE",
            "source_version": "FIXTURE", "source_sha256": "0" * 64, "retrieved_at": "2026-01-05T11:00:00Z", "fixture": True}
    base.update(over)
    return base


def _bridge(**over):
    base = {"bridge_version": "FIXTURE-none", "status": "NONE", "public_model_version": None, "legislator_model_version": None,
            "transformation_method": None, "transformation_parameters": None, "validation_metrics": None,
            "created_at": "2026-01-05T11:00:00Z", "notes": "FIXTURE"}
    base.update(over)
    return base


def test_senator_records_are_strict():
    assert R.validate("senator_ideology", _senator()) == []
    assert R.validate("senator_ideology", {**_senator(), "alignment": 0.3}), "no extra fields"
    assert R.validate("senator_ideology", {k: v for k, v in _senator().items() if k != "nokken_poole_dim1"}), "both scores are required fields"
    assert R.validate("senator_ideology", _senator(nominate_dim1=1)), "a score must be a float, not an int"
    assert R.validate("senator_ideology", _senator(nominate_dim1=1.2)), "outside Voteview's [-1, 1]"
    assert R.validate("senator_ideology", _senator(voteview_row=False)), "no Voteview row means no Voteview values"
    assert R.validate("senator_ideology", _senator(voteview_row=False, senator_id=None, nominate_dim1=None, nokken_poole_dim1=None)) == []
    assert R.validate("senator_ideology", _senator(retrieved_at="yesterday"))


def test_bridge_records_require_what_their_status_claims():
    assert R.validate("ideology_bridge", _bridge()) == []
    assert R.validate("ideology_bridge", _bridge(status="MAYBE"))
    assert R.validate("ideology_bridge", _bridge(transformation_method="linear")), "a NONE bridge carries no method"
    prov = dict(status="PROVISIONAL", public_model_version="FIXTURE public", legislator_model_version="FIXTURE legislator")
    assert R.validate("ideology_bridge", _bridge(**prov)), "PROVISIONAL needs method and parameters"
    ok = _bridge(**prov, transformation_method="FIXTURE affine", transformation_parameters={"a": 0.0, "b": 1.0})
    assert R.validate("ideology_bridge", ok) == []
    assert R.validate("ideology_bridge", {**ok, "status": "VALIDATED"}), "VALIDATED needs validation metrics"
    assert R.validate("ideology_bridge", {**ok, "status": "VALIDATED", "validation_metrics": {"FIXTURE": 1.0}}) == []


def test_committee_events_say_their_dates_are_observed():
    cfg = fixture_raw(Path(__import__("tempfile").mkdtemp()))
    ev = I.committee_event_records(cfg, I.snapshot(cfg), {})[0]
    assert R.validate("committee_membership_events", ev) == []
    assert "not an official appointment" in ev["date_basis"]
    assert R.validate("committee_membership_events", {**ev, "date_basis": "appointed"}), "the observed-date label cannot be dropped"
    assert R.validate("committee_membership_events", {**ev, "observed_date": "2026-1-5"})
    assert R.validate("committee_membership_events", {**ev, "baseline": False}), "the baseline note goes with the baseline flag"
    assert R.validate("committee_membership_events", {**ev, "event": "observed_left"}), "a departure carries no role"


def test_constituency_records_stay_in_their_own_units():
    cfg = fixture_raw(Path(__import__("tempfile").mkdtemp()))
    rows = I.constituency_records(cfg, I.snapshot(cfg))
    assert all(R.validate("constituency_ideology", r) == [] for r in rows)
    assert all("no common metric with Voteview" in r["scale"] for r in rows)
    assert R.validate("constituency_ideology", {**rows[0], "standard_error": -0.1})
    assert R.validate("constituency_ideology", {**rows[0], "geography_type": "county"})


# ---- the store ----------------------------------------------------------------------

def test_store_appends_only_changes_and_chains_versions(tmp_path):
    t = Table(tmp_path, "senator_ideology")
    a, b = _senator(), _senator(nominate_dim1=-0.41)
    assert t.append([a], "run1") == 1
    before = t.path.read_bytes()
    assert t.append([a], "run2") == 0, "an unchanged record writes nothing"
    assert t.append([b], "run3") == 1 and t.append([a], "run4") == 1, "a value returning to an earlier one is a new version"
    assert t.path.read_bytes().startswith(before), "earlier lines are never rewritten"
    hist = t.history(("FX00001", 119))
    assert [h["content"]["nominate_dim1"] for h in hist] == [-0.4, -0.41, -0.4]
    assert hist[1]["prev_record_id"] == hist[0]["record_id"] and hist[2]["prev_record_id"] == hist[1]["record_id"]
    assert hist[0]["record_id"] != hist[2]["record_id"], "the same content at a different point in the chain has its own id"
    assert t.latest()[("FX00001", 119)]["content"]["nominate_dim1"] == -0.4
    assert t.verify() == []


def test_store_refuses_invalid_or_duplicate_records(tmp_path):
    t = Table(tmp_path, "senator_ideology")
    with pytest.raises(StoreError):
        t.append([_senator(nominate_dim1=3.0)], "run")
    with pytest.raises(StoreError):
        t.append([_senator(), _senator(nominate_dim1=-0.3)], "run")
    assert not t.path.exists(), "a refused batch writes nothing"
    with pytest.raises(StoreError):
        Table(tmp_path, "alignment_scores")


def test_store_detects_edits_deletions_and_reordering(tmp_path):
    t = Table(tmp_path, "senator_ideology")
    for v in (-0.4, -0.41, -0.42):
        t.append([_senator(nominate_dim1=v)], "run")
    t.append([_senator(bioguide_id="FX00002", senator_id="900002", nominate_dim1=0.5)], "run")
    good = t.path.read_text().splitlines()
    edited = [json.loads(l) for l in good]; edited[1]["content"]["nominate_dim1"] = -0.9
    t.path.write_text("\n".join(json.dumps(l) for l in edited) + "\n")
    assert any("content_sha256" in p for p in t.verify())
    t.path.write_text("\n".join(good[:1] + good[2:]) + "\n")
    assert any("chain broken" in p for p in t.verify())
    t.path.write_text("\n".join([good[2], good[1], good[0], good[3]]) + "\n")
    assert any("chain broken" in p for p in t.verify())


# ---- ingest from fixtures ----------------------------------------------------------------

def test_ingest_refuses_files_that_do_not_match_the_snapshot(tmp_path):
    cfg = fixture_raw(tmp_path)
    (cfg.raw_dir / "HSall_members.csv").write_text((cfg.raw_dir / "HSall_members.csv").read_text().replace("-0.4,", "-0.9,"))
    with pytest.raises(I.SnapshotMismatch, match="does not match the snapshot"):
        I.run(cfg)
    cfg = fixture_raw(tmp_path / "b")
    snap = json.loads((cfg.raw_dir / "SNAPSHOT.json").read_text()); snap["accepted"] = False
    (cfg.raw_dir / "SNAPSHOT.json").write_text(json.dumps(snap))
    with pytest.raises(I.SnapshotMismatch, match="not accepted"):
        I.run(cfg)
    assert not cfg.ideology_dir.exists(), "a refused ingest writes nothing"


def test_senator_ingest_from_fixtures(tmp_path):
    cfg = fixture_raw(tmp_path)
    rows = {r["bioguide_id"]: r for r in I.senator_records(cfg, I.snapshot(cfg))}
    assert set(rows) == {"FX00001", "FX00002", "FX00003", "FX00004", "FX00006"}, "Senate rows of this Congress only, plus seated senators Voteview lacks"
    assert rows["FX00001"]["nominate_dim1"] == -0.4 and rows["FX00001"]["nokken_poole_dim1"] == -0.35, "both scores stored"
    assert rows["FX00004"]["seated"] is False and rows["FX00004"]["nominate_dim1"] == -0.2, "a departed member is kept, not seated"
    new = rows["FX00006"]
    assert new["seated"] and not new["voteview_row"] and new["nominate_dim1"] is None and new["senator_id"] is None, \
        "a seated senator Voteview has not scored gets no score, never a predecessor's"
    assert all(r["fixture"] is True and r["source_url"].startswith("file://FIXTURE") for r in rows.values())


def test_senator_ingest_fails_closed_on_impossible_seats(tmp_path):
    cfg = fixture_raw(tmp_path)
    roster = json.loads((cfg.raw_dir / "legislators-current.json").read_text())
    roster.append({"id": {"bioguide": "FX00004"}, "name": {"official_full": "FIXTURE Former Senator Delta"},
                   "terms": [{"type": "sen", "state": "ZY", "party": "Democrat"}]})
    (cfg.raw_dir / "legislators-current.json").write_text(json.dumps(roster))
    cfg = fixture_raw_rehash(cfg)
    with pytest.raises(I.SnapshotMismatch, match="do not fit the Senate"):
        I.senator_records(cfg, I.snapshot(cfg))
    cfg = fixture_raw(tmp_path / "b")
    csv_ = (cfg.raw_dir / "HSall_members.csv").read_text().replace('ZZ,100,,,"FIXTURE Senator, Alpha"', 'ZY,100,,,"FIXTURE Senator, Alpha"', 1)
    (cfg.raw_dir / "HSall_members.csv").write_text(csv_)
    cfg = fixture_raw_rehash(cfg)
    with pytest.raises(I.SnapshotMismatch, match="roster state"):
        I.senator_records(cfg, I.snapshot(cfg))


def fixture_raw_rehash(cfg):
    """Re-record the fixture snapshot after a test edits a fixture file."""
    snap = json.loads((cfg.raw_dir / "SNAPSHOT.json").read_text())
    for e in snap["sources"]:
        data = (cfg.raw_dir / e["file"]).read_bytes()
        e["sha256"] = hashlib.sha256(data).hexdigest()
    (cfg.raw_dir / "SNAPSHOT.json").write_text(json.dumps(snap))
    return cfg


def test_constituency_ingest_keeps_every_wave_with_its_error(tmp_path):
    cfg = fixture_raw(tmp_path)
    rows = I.constituency_records(cfg, I.snapshot(cfg))
    assert [(r["geography_id"], r["wave"]) for r in rows] == [("ZY", 2016), ("ZZ", 2016), ("ZY", 2020), ("ZZ", 2020)]
    zz = next(r for r in rows if r["geography_id"] == "ZZ" and r["wave"] == 2020)
    assert (zz["estimate"], zz["standard_error"], zz["survey_period"], zz["sample_size"]) == (0.15, 0.06, "2017-2020", 450)
    assert zz["methodology_version"] == "AIP v2022a mrp_ideology, presidential-year wave 2020"
    assert not any(r["geography_type"] == "nation" for r in rows), "no national estimate is ingested: its definition is unresolved"


def test_committee_ingest_records_observed_changes(tmp_path):
    cfg = fixture_raw(tmp_path, when="2026-01-05T11:00:00Z")
    first = I.run(cfg)
    t = Table(cfg.ideology_dir, "committee_membership_events")
    evs = t.current()
    assert {e["committee_id"] for e in evs} == {"SSZZ"}, "standing committees only: no subcommittee, select or House committee"
    assert all(e["event"] == "observed_joined" and e["baseline"] and e["observed_date"] == "2026-01-05" for e in evs)
    assert I.run(cfg)["new_versions_written"] == {"senator_ideology": 0, "constituency_ideology": 0, "state_population": 0, "committee_membership_events": 0}, \
        "re-ingesting an unchanged snapshot writes nothing"
    # a later snapshot with a changed roster
    cfg = fixture_raw(tmp_path, committees="FIXTURE_committee-membership-current.v2.json", when="2026-02-10T11:00:00Z")
    I.run(cfg)
    by = {(e["committee_id"], e["bioguide_id"]): e for e in t.current()}
    assert by[("SSZZ", "FX00002")]["event"] == "observed_left" and by[("SSZZ", "FX00002")]["observed_date"] == "2026-02-10"
    assert by[("SSZZ", "FX00003")]["event"] == "observed_role_changed" and by[("SSZZ", "FX00003")]["title"] == "Chairman"
    assert by[("SSZZ", "FX00006")]["event"] == "observed_joined" and not by[("SSZZ", "FX00006")]["baseline"]
    assert by[("SSZY", "FX00002")]["baseline"], "a committee seen for the first time gets baseline events"
    assert by[("SSZZ", "FX00001")]["event"] == "observed_joined" and by[("SSZZ", "FX00001")]["observed_date"] == "2026-01-05", "unchanged members get no new event"
    ivs = {(i["committee_id"], i["bioguide_id"]): i for i in R.membership_intervals([l["content"] for l in t.lines()])}
    assert (ivs[("SSZZ", "FX00002")]["observed_start_date"], ivs[("SSZZ", "FX00002")]["observed_end_date"]) == ("2026-01-05", "2026-02-10")
    assert ivs[("SSZZ", "FX00002")]["start_is_first_observation"] is True
    assert ivs[("SSZZ", "FX00003")]["observed_end_date"] is None and ivs[("SSZZ", "FX00003")]["title"] == "Chairman"
    assert ivs[("SSZZ", "FX00006")]["start_is_first_observation"] is False
    assert all("not an official appointment" in i["date_basis"] for i in ivs.values())
    for table in ("senator_ideology", "constituency_ideology", "state_population", "committee_membership_events"):
        tb = Table(cfg.ideology_dir, table)
        assert tb.verify() == [] and all(l["content"]["fixture"] is True for l in tb.lines())


def test_population_ingest_is_versioned_by_year_and_vintage(tmp_path):
    cfg = fixture_raw(tmp_path)
    rows = I.population_records(cfg, I.snapshot(cfg))
    assert len(rows) == 102 and {r["measurement_year"] for r in rows} == {2023, 2024}, "51 areas x 2 years; Puerto Rico left out"
    ca = next(r for r in rows if r["geography_id"] == "CA" and r["measurement_year"] == 2024)
    assert ca["vintage"] == "Vintage 2024" and ca["population"] > 0 and ca["fixture"] is True
    assert all(R.validate("state_population", r) == [] for r in rows)
    assert R.validate("state_population", {**ca, "population": 0})
    t = Table(cfg.ideology_dir, "state_population")
    assert t.append(rows, "FIXTURE") == 102 and t.append(rows, "FIXTURE") == 0
    revised = [{**r, "population": r["population"] + 5} if r["geography_id"] == "CA" and r["measurement_year"] == 2023 else r for r in rows]
    assert t.append(revised, "FIXTURE") == 1, "a revised figure is a new version; the old one stays in the history"
    ca23 = next(r["population"] for r in rows if r["geography_id"] == "CA" and r["measurement_year"] == 2023)
    assert [h["content"]["population"] for h in t.history(("state", "CA", 2023, "Vintage 2024"))] == [ca23, ca23 + 5]


def test_engine_b_does_not_import_engine_a():
    import ast
    engine_a = ("explain", "evaluation", "receipts", "billflow", "billstatus", "senate_votes")
    for f in (ROOT / "src" / "civicalign" / "ideology").glob("*.py"):
        mods = []
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ImportFrom):
                mods += [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
        assert not [m for m in mods if any(x in m for x in engine_a)], (f.name, mods)


# ---- ingest from the real, verified snapshot (into a temporary folder) ----------------------------

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path_factory.mktemp("ideology"))
    try:
        first = I.run(cfg)
    except I.SnapshotMismatch as e:
        pytest.skip(f"local raw files do not match the snapshot: {e}")
    return cfg, first


def test_real_ingest_matches_the_senate(real):
    cfg, first = real
    rows = Table(cfg.ideology_dir, "senator_ideology").current()
    seated = [r for r in rows if r["seated"]]
    assert len(seated) == 100
    per_state = {}
    for r in seated:
        per_state[r["state"]] = per_state.get(r["state"], 0) + 1
    assert set(per_state.values()) == {2} and len(per_state) == 50
    assert all(isinstance(r["nominate_dim1"], float) and isinstance(r["nokken_poole_dim1"], float) for r in seated if r["voteview_row"])
    assert all(not r["fixture"] and r["source_url"].startswith("https://") for r in rows)
    departed = [r for r in rows if not r["seated"]]
    assert all(r["voteview_row"] for r in departed), "a member who left is kept with their record, not counted as seated"


def test_real_ingest_public_estimates_and_committees(real):
    cfg, first = real
    aip = Table(cfg.ideology_dir, "constituency_ideology").current()
    waves = {}
    for r in aip:
        waves.setdefault(r["wave"], set()).add(r["geography_id"])
    assert all(len(g) == 51 for g in waves.values()) and 2020 in waves, "50 states and DC in every wave"
    assert all(r["standard_error"] > 0 and r["source_url"] == I.AIP_URL for r in aip)
    evs = Table(cfg.ideology_dir, "committee_membership_events").current()
    assert {e["committee_id"] for e in evs} and all(e["committee_id"].startswith("SS") and len(e["committee_id"]) == 4 for e in evs)
    assert all(e["baseline"] and e["event"] == "observed_joined" for e in evs), "a fresh store sees every membership for the first time"
    assert I.run(cfg)["new_versions_written"] == {"senator_ideology": 0, "constituency_ideology": 0, "state_population": 0, "committee_membership_events": 0}


def test_committed_tables_verify():
    for table in ("senator_ideology", "constituency_ideology", "state_population", "committee_membership_events", "ideology_bridge"):
        t = Table(DEFAULT.ideology_dir, table)
        if not t.path.exists():
            pytest.skip("no committed Pillars 4-6 tables yet")
        assert t.verify() == [], table
        assert all(l["content"].get("fixture", False) is False for l in t.lines()), "fixtures never reach data/ideology"
