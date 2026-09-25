"""Pillars 4-6, Step 3: versioned result records and incremental recomputation.

Inputs here are invented FIXTURE records (states ZA..ZC, bioguide ids FX..)
written straight into a temporary store. Every incremental result is checked
against a full recompute of the same inputs."""
import dataclasses
import json

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import bridge as B
from civicalign.ideology import compute as C
from civicalign.ideology import records as R
from civicalign.ideology.store import Table

PROV = {"source": "FIXTURE", "source_url": "file://FIXTURE", "source_version": "FIXTURE-v1", "source_sha256": "0" * 64,
        "retrieved_at": "2026-01-05T11:00:00Z", "fixture": True}


def senator(b, state, score, seated=True, retrieved="2026-01-05T11:00:00Z"):
    return {"senator_id": "9" + b[2:], "bioguide_id": b, "congress": 119, "chamber": "Senate", "state": state,
            "name": f"FIXTURE Senator {b}", "voteview_party_code": "100", "voteview_row": True, "nominate_dim1": score,
            "nokken_poole_dim1": score, "nominate_number_of_votes": 100, "seated": seated, "roster_source_version": "FIXTURE",
            "roster_retrieved_at": retrieved, **PROV, "retrieved_at": retrieved}


def public(state, est):
    return {"geography_type": "state", "geography_id": state, "geography_name": f"FIXTURE {state}", "estimate": est,
            "standard_error": 0.05, "survey_period": "FIXTURE", "wave": 2020, "sample_size": 100,
            "methodology_version": "FIXTURE wave 2020", "scale": R.SCALE_NOTE_AIP, **PROV}


def population(state, n):
    return {"geography_type": "state", "geography_id": state, "geography_name": f"FIXTURE {state}", "population": n,
            "measurement_year": 2024, "vintage": "Vintage 2024", "estimate_type": "FIXTURE", **PROV}


def event(cid, b, ev="observed_joined", date="2026-01-05", baseline=True, title=None):
    left = ev == "observed_left"
    return {"congress": 119, "committee_id": cid, "bioguide_id": b, "member_name": f"FIXTURE Senator {b}", "event": ev,
            "observed_date": date, "date_basis": R.OBSERVED_DATE_BASIS, "baseline": baseline,
            "baseline_note": R.BASELINE_NOTE if baseline else None, "rank": None if left else 1, "title": None if left else title,
            "side": None if left else "majority", "in_current_roster": True, **PROV, "retrieved_at": f"{date}T11:00:00Z"}


SENATORS = [senator("FXA1", "ZA", -0.4), senator("FXA2", "ZA", -0.2), senator("FXB1", "ZB", 0.5), senator("FXB2", "ZB", 0.7),
            senator("FXC1", "ZC", 0.1), senator("FXC2", "ZC", 0.3)]
MEMBERS = {"SSZA": ["FXA1", "FXB1", "FXC1"], "SSZB": ["FXA2", "FXB2", "FXC2"], "SSZC": ["FXA1", "FXB2"]}


@pytest.fixture
def cfg(tmp_path):
    c = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "FIXTURE_ideology")
    Table(c.ideology_dir, "senator_ideology").append(SENATORS, "FIXTURE")
    Table(c.ideology_dir, "constituency_ideology").append([public("ZA", -0.1), public("ZB", 0.3), public("ZC", 0.0)], "FIXTURE")
    Table(c.ideology_dir, "state_population").append([population("ZA", 1000), population("ZB", 100), population("ZC", 300)], "FIXTURE")
    Table(c.ideology_dir, "committee_membership_events").append([event(cid, b) for cid, ms in MEMBERS.items() for b in ms], "FIXTURE")
    B.register_defaults(c, "FIXTURE")
    return c


def full_results(c, into):
    """A full recompute of the same inputs, in a separate copy of the store."""
    import shutil
    other = dataclasses.replace(c, ideology_dir=into)
    shutil.copytree(c.ideology_dir, into, ignore=shutil.ignore_patterns("metrics", "metrics_index.jsonl"))
    C.compute(other, force_full=True, now="FIXTURE")
    return C.load_record(other, C.index(other)[-1]["input_key"])["results"]


def test_first_compute_is_full_and_a_rerun_writes_nothing(cfg):
    r = C.compute(cfg, now="2026-01-06T00:00:00Z")
    assert r["mode"] == "full" and r["written"]
    rec = C.load_record(cfg, r["input_key"])
    assert rec["fixture"] is True and rec["previous_key"] is None
    p5 = rec["results"]["pillar5"]
    # hand-worked: plain mean (-0.4 - 0.2 + 0.5 + 0.7 + 0.1 + 0.3) / 6 = 1.0 / 6; weights 500, 500, 50, 50, 150, 150 (total 1400)
    # weighted mean (-200 - 100 + 25 + 35 + 15 + 45) / 1400 = -180 / 1400
    assert p5["plain_center"]["value"] == pytest.approx(1.0 / 6) and p5["population_weighted_center"]["value"] == pytest.approx(-180 / 1400)
    assert p5["population_weighting_difference"]["value"] == pytest.approx(1.0 / 6 + 180 / 1400)
    assert rec["computed_in"] == {"pillar4": r["input_key"], "pillar5": r["input_key"], "pillar6": {c: r["input_key"] for c in MEMBERS}}
    before = sorted((p.name, p.read_bytes()) for p in (cfg.ideology_dir / "metrics").iterdir())
    assert C.compute(cfg) == {"mode": "unchanged", "input_key": r["input_key"], "written": False}
    assert sorted((p.name, p.read_bytes()) for p in (cfg.ideology_dir / "metrics").iterdir()) == before and len(C.index(cfg)) == 1
    assert C.verify(cfg) == []


def test_a_membership_change_recomputes_only_that_committee(cfg, tmp_path):
    first = C.compute(cfg, now="t1")["input_key"]
    Table(cfg.ideology_dir, "committee_membership_events").append(
        [event("SSZA", "FXB1", "observed_left", "2026-02-10", baseline=False),
         event("SSZA", "FXA2", "observed_joined", "2026-02-10", baseline=False)], "FIXTURE")
    r = C.compute(cfg, now="t2")
    assert r["mode"] == "committees_only" and r["committees_recomputed"] == ["SSZA"]
    rec = C.load_record(cfg, r["input_key"])
    assert rec["previous_key"] == first
    assert rec["computed_in"]["pillar6"] == {"SSZA": r["input_key"], "SSZB": first, "SSZC": first}
    assert rec["computed_in"]["pillar4"] == first and rec["computed_in"]["pillar5"] == first
    # SSZA is now FXA1 (-0.4), FXC1 (0.1), FXA2 (-0.2): median -0.2
    assert rec["results"]["pillar6"]["SSZA"]["committee_median"]["value"] == pytest.approx(-0.2)
    assert rec["versions"]["committee_membership"]["latest_observed_date"] == "2026-02-10"
    assert json.loads(json.dumps(rec["results"])) == json.loads(json.dumps(full_results(cfg, tmp_path / "full"))), \
        "a carried result equals a full recompute"
    assert C.verify(cfg) == []


def test_a_role_change_is_a_membership_change_but_does_not_move_a_median(cfg):
    C.compute(cfg, now="t1")
    Table(cfg.ideology_dir, "committee_membership_events").append(
        [event("SSZB", "FXB2", "observed_role_changed", "2026-02-10", baseline=False, title="Chairman")], "FIXTURE")
    r = C.compute(cfg, now="t2")
    assert r["mode"] == "committees_only" and r["committees_recomputed"] == ["SSZB"]


def test_a_removed_committee_is_dropped_not_carried(cfg, tmp_path):
    C.compute(cfg, now="t1")
    Table(cfg.ideology_dir, "committee_membership_events").append(
        [event("SSZC", b, "observed_left", "2026-02-10", baseline=False) for b in MEMBERS["SSZC"]], "FIXTURE")
    r = C.compute(cfg, now="t2")
    rec = C.load_record(cfg, r["input_key"])
    assert r["mode"] == "committees_only" and "SSZC" not in rec["results"]["pillar6"]
    assert json.loads(json.dumps(rec["results"])) == json.loads(json.dumps(full_results(cfg, tmp_path / "full")))


@pytest.mark.parametrize("change", ["senator", "population", "public", "setting", "seat"])
def test_any_other_change_recomputes_everything(cfg, change):
    C.compute(cfg, now="t1")
    c = cfg
    if change == "senator":
        Table(cfg.ideology_dir, "senator_ideology").append([senator("FXA1", "ZA", -0.45, retrieved="2026-03-01T11:00:00Z")], "FIXTURE")
    elif change == "population":
        Table(cfg.ideology_dir, "state_population").append([population("ZA", 1100)], "FIXTURE")
    elif change == "public":
        Table(cfg.ideology_dir, "constituency_ideology").append([public("ZA", -0.12)], "FIXTURE")
    elif change == "setting":
        c = dataclasses.replace(cfg, pillar5_weighting_method="population_weighted_median_v1")
    elif change == "seat":
        Table(cfg.ideology_dir, "senator_ideology").append([senator("FXC2", "ZC", 0.3, seated=False)], "FIXTURE")
    r = C.compute(c, now="t2")
    rec = C.load_record(c, r["input_key"])
    assert r["mode"] == "full" and set(rec["computed_in"]["pillar6"].values()) == {r["input_key"]}
    assert rec["computed_in"]["pillar4"] == rec["computed_in"]["pillar5"] == r["input_key"]
    if change == "senator":
        assert rec["versions"]["measurement_date"] == "2026-03-01", "the measurement date follows the newest input"
    if change == "setting":
        assert rec["settings"]["weighting_method"] == "population_weighted_median_v1"
        assert rec["results"]["pillar5"]["population_weighted_center"]["method"] == "population_weighted_median_v1"


def test_earlier_results_are_never_overwritten(cfg):
    keys = [C.compute(cfg, now="t1")["input_key"]]
    snapshots = {}
    for i, v in enumerate((-0.41, -0.42, -0.4)):
        snapshots.update({p.name: p.read_bytes() for p in (cfg.ideology_dir / "metrics").iterdir()})
        Table(cfg.ideology_dir, "senator_ideology").append([senator("FXA1", "ZA", v)], "FIXTURE")
        keys.append(C.compute(cfg, now=f"t{i + 2}")["input_key"])
        for name, data in snapshots.items():
            assert (cfg.ideology_dir / "metrics" / name).read_bytes() == data, "an earlier result was rewritten"
    assert len(set(keys)) == 4, "returning to an earlier score is a new input version (a new record_id), so a new result"
    assert [e["input_key"] for e in C.index(cfg)] == keys and C.verify(cfg) == []


def test_tampering_and_orphans_are_detected(cfg):
    key = C.compute(cfg, now="t1")["input_key"]
    f = cfg.ideology_dir / "metrics" / f"{key}.json"
    original = f.read_text()
    f.write_text(original.replace('"mode":"full"', '"mode":"FULL"'))
    assert any("does not match its recorded hash" in p for p in C.verify(cfg))
    f.write_text(original)
    (cfg.ideology_dir / "metrics" / ("0" * 64 + ".json")).write_text("{}")
    assert any("not in the index" in p for p in C.verify(cfg))


def test_a_result_computed_from_stale_inputs_is_reported(cfg):
    C.compute(cfg, now="t1")
    Table(cfg.ideology_dir, "senator_ideology").append([senator("FXA1", "ZA", -0.5)], "FIXTURE")
    assert any("no longer current" in p for p in C.verify(cfg))


def test_an_unindexed_result_file_is_never_overwritten(cfg):
    p = C.plan(cfg)
    (cfg.ideology_dir / "metrics").mkdir(parents=True)
    (cfg.ideology_dir / "metrics" / f"{p['input_key']}.json").write_text("{}")
    with pytest.raises(C.ComputeError, match="refusing to overwrite"):
        C.compute(cfg)


def test_committed_results_verify():
    if not C.index(DEFAULT):
        pytest.skip("no committed results")
    assert C.verify(DEFAULT) == []
    assert all(e["fixture"] is False for e in C.index(DEFAULT))
    rec = C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])
    v = rec["versions"]
    assert v["bridge"]["status"] == "NONE" and v["national_public"] == "UNRESOLVED" and v["legislator_model"]["score_column"] == "nominate_dim1"
    assert v["weighting"]["primary_method"] == "population_weighted_mean_v1"
    assert all(r["distance"]["status"] == "NOT_AVAILABLE" for r in rec["results"]["pillar4"])
