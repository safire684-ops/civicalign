"""Pillars 4-6, Step 4 part 1: the methodology registry and the Pillar 4 reference anchors.

Fixture tests use the invented files in tests/fixtures/ideology/ through the
same helper as test_ideology_records.py. Real-data tests read the committed
tables and result record, and the local raw Voteview file (skipped if absent).
Nothing here writes to data/ideology/."""
import ast
import copy
import csv
import dataclasses
import json
import re
import shutil
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import anchors as A
from civicalign.ideology import compute as C
from civicalign.ideology import methodology as M
from civicalign.ideology import records as R
from civicalign.ideology.store import Table
from test_ideology_records import fixture_raw

ROOT = Path(__file__).resolve().parents[1]
IDEOLOGY = ROOT / "src" / "civicalign" / "ideology"


@pytest.fixture(scope="module")
def record():
    idx = C.index(DEFAULT)
    if not idx:
        pytest.skip("no committed Pillars 4-6 result")
    return C.load_record(DEFAULT, idx[-1]["input_key"])


# ---- the registry --------------------------------------------------------------------------------

def test_the_registry_is_complete_and_consistent():
    assert M.problems() == []
    for e in M.ENTRIES:
        assert e["limitations"] and all(isinstance(x, str) and x for x in e["limitations"]), e["id"]
        if e["kind"] == "quantity" and e["id"] in ("p4.state_on_senator_scale", "p4.distance", "p5.national_public",
                                                    "p5.chamber_public_gap", "p6.committee_public_drift"):
            assert e["not_available"], f"{e['id']} is always NOT_AVAILABLE today and must say why"


def test_every_number_in_the_committed_result_has_an_entry(record):
    assert M.coverage(record) == []


def test_coverage_catches_an_unregistered_or_missing_number(record):
    extra = copy.deepcopy(record)
    extra["results"]["pillar5"]["new_quantity"] = {"value": 1.0, "status": "AVAILABLE", "units": "x", "reason": None}
    assert any("pillar5.new_quantity has no methodology entry" in p for p in M.coverage(extra))
    count = copy.deepcopy(record)
    count["results"]["pillar5"]["new_count"] = 7
    assert any("pillar5.new_count has no methodology entry" in p for p in M.coverage(count))
    missing = copy.deepcopy(record)
    del missing["results"]["pillar5"]["population_weighting_difference"]
    assert any("p5.weighting_difference" in p for p in M.coverage(missing))
    other = copy.deepcopy(record)
    other["results"]["pillar5"]["configured_method"] = M.SECONDARY_METHOD
    assert any("primary method" in p for p in M.coverage(other))
    noversion = copy.deepcopy(record)
    del noversion["versions"]["population"]
    assert any("versions ['population']" in p for p in M.coverage(noversion))


def test_entry_for_finds_any_senator_or_committee_and_refuses_the_rest():
    assert M.entry_for("pillar6.SSAP.committee_senate_drift")["id"] == "p6.committee_senate_drift"
    assert M.entry_for("pillar4.17.senator_score")["id"] == "p4.senator_score"
    assert M.entry_for("pillar5.details.chamber_median")["id"] == "p5.plain_median"
    with pytest.raises(KeyError):
        M.entry_for("pillar5.something_new")


def test_pillar5_main_comparison_is_the_mean_and_medians_are_details_only():
    main = {e["id"] for e in M.ENTRIES if e["pillar"] == 5 and e["placement"] == "main" and e["kind"] == "quantity"}
    assert {"p5.plain_mean", "p5.weighted_mean", "p5.weighting_difference"} <= main
    assert all(M.REGISTRY[i]["placement"] == "details" for i in ("p5.plain_median", "p5.weighted_median", "p5.median_difference"))
    assert "pillar5.plain_center" in M.REGISTRY["p5.plain_mean"]["paths"]
    assert M.PRIMARY_METHOD == DEFAULT.pillar5_weighting_method


def test_registry_text_has_no_evaluative_labels_or_causal_claims():
    banned = r"\b(extreme|extremist|moderate|centrist|radical|fringe|biased|good|bad|misaligned|aligned|gatekeep\w*|obstruct\w*|block(?:ed|s)?|betray\w*|defian\w*|rank(?:ing|ed)?)\b"
    for f in ("methodology.py", "anchors.py"):
        tree = ast.parse((IDEOLOGY / f).read_text())
        text = " ".join(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and not n.value.startswith(("\n", "Pillar", "Pillars", "The methodology")))
        hits = re.findall(banned, text, flags=re.I)
        assert not hits, (f, hits)
    for e in M.ENTRIES:
        assert not re.search(r"representative score|representation score", json.dumps(e), flags=re.I)


# ---- the anchors: exactly three, labelled, visual only ----------------------------------------------

def test_exactly_three_anchors_with_honest_labels():
    assert [a["display_name"] for a in A.ANCHORS] == ["Bernie Sanders", "Joe Biden", "JD Vance"]
    assert A.COUNT == 3
    biden, vance = A.ANCHORS[1]["record_basis"], A.ANCHORS[2]["record_basis"]
    assert biden.startswith("Senate voting record") and "not his presidency" in biden
    assert vance.startswith("Senate voting record") and "not his vice presidency" in vance
    for bad in (A.ANCHORS[:2], A.ANCHORS + (A.ANCHORS[0],), (A.ANCHORS[0], A.ANCHORS[0], A.ANCHORS[1])):
        with pytest.raises(A.AnchorError):
            A._check_count(bad)


def _row(congress, chamber, icpsr, bioguide, score, votes=100):
    return {"congress": str(congress), "chamber": chamber, "icpsr": icpsr, "bioguide_id": bioguide, "bioname": "FIXTURE Person",
            "nominate_dim1": score, "nominate_number_of_votes": str(votes)}


SPEC = {"anchor_id": "fx", "bioguide_id": "FX00009", "display_name": "FIXTURE Person", "record_basis": "FIXTURE"}


def test_an_anchor_uses_its_senate_record_and_never_a_president_row():
    rows = [_row(100, "House", "900009", "FX00009", "-0.2", 50), _row(101, "Senate", "900009", "FX00009", "-0.2", 70),
            _row(103, "Senate", "900009", "FX00009", "-0.2", 80), _row(104, "President", "999999", "FX00009", "-0.9", 0)]
    a = A.anchor_from_rows(SPEC, rows)
    assert a["nominate_dim1"] == -0.2 and a["voteview_icpsr"] == "900009"
    assert a["congresses"] == {"House": [100, 100], "Senate": [101, 103]} and a["number_of_votes"] == {"House": 50, "Senate": 150}
    assert a["use"] == R.ANCHOR_USE and a["score_column"] == "nominate_dim1"


@pytest.mark.parametrize("rows", [
    [_row(101, "Senate", "900009", "FX00009", "-0.2"), _row(102, "Senate", "900009", "FX00009", "-0.3")],   # two scores: refused, never averaged
    [_row(101, "Senate", "900009", "FX00009", "-0.2"), _row(102, "Senate", "900010", "FX00009", "0.1")],    # two Senate ids (party switch)
    [_row(101, "House", "900009", "FX00009", "-0.2")],                                                       # no Senate record
    [],
])
def test_an_ambiguous_or_missing_anchor_is_refused(rows):
    with pytest.raises(A.AnchorError):
        A.anchor_from_rows(SPEC, rows)


def test_anchor_records_from_fixtures(tmp_path):
    cfg = fixture_raw(tmp_path)
    specs = tuple({"anchor_id": f"fx{i}", "bioguide_id": b, "display_name": f"FIXTURE {b}", "record_basis": "FIXTURE"}
                  for i, b in enumerate(("FX00001", "FX00002", "FX00004")))
    assert A.register(cfg, specs=specs) == 3
    assert A.register(cfg, specs=specs) == 0, "an unchanged snapshot writes nothing"
    got = A.current(cfg, specs)
    assert [r["nominate_dim1"] for r in got] == [-0.4, 0.5, -0.2]
    assert got[0]["congresses"] == {"Senate": [118, 119]} and got[0]["number_of_votes"] == {"Senate": 1000}
    assert all(r["fixture"] for r in got)
    assert Table(cfg.ideology_dir, "reference_anchors").verify() == []
    with pytest.raises(A.AnchorError):
        A.current(cfg, specs[:2] + ({**specs[2], "anchor_id": "other"},))


# ---- the anchors never affect a calculation ------------------------------------------------------------

def test_no_calculation_module_reads_the_anchors_or_the_registry():
    for f in ("pillars.py", "compute.py", "inputs.py", "national.py", "bridge.py", "store.py", "records.py", "ingest.py", "result.py"):
        mods = []
        for node in ast.walk(ast.parse((IDEOLOGY / f).read_text())):
            if isinstance(node, ast.ImportFrom):
                mods += [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
        assert not [m for m in mods if "anchors" in m or "methodology" in m], (f, mods)
    assert "reference_anchors" not in (IDEOLOGY / "compute.py").read_text()


def test_the_result_key_and_numbers_ignore_the_anchors(record, tmp_path):
    if not (DEFAULT.ideology_dir / "reference_anchors.jsonl").exists():
        pytest.skip("no committed anchors")
    without = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "without")
    shutil.copytree(DEFAULT.ideology_dir, without.ideology_dir, ignore=shutil.ignore_patterns("reference_anchors.jsonl"))
    plan_without, plan_with = C.plan(without), C.plan(DEFAULT)
    assert plan_without["input_key"] == plan_with["input_key"] == record["input_key"]
    assert plan_with["mode"] == "unchanged"
    changed = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "changed")
    shutil.copytree(DEFAULT.ideology_dir, changed.ideology_dir, ignore=shutil.ignore_patterns("metrics", "metrics_index.jsonl"))
    t = Table(changed.ideology_dir, "reference_anchors")
    t.append([{**r, "nominate_dim1": -r["nominate_dim1"] or 0.5} for r in t.current()], "FIXTURE")   # a different anchor version
    C.compute(changed, force_full=True, now="FIXTURE")
    fresh = C.load_record(changed, C.index(changed)[-1]["input_key"])
    assert fresh["input_key"] == record["input_key"] and fresh["results"] == record["results"]


# ---- the committed anchors are the real Voteview values ---------------------------------------------

@pytest.fixture(scope="module")
def committed():
    if not (DEFAULT.ideology_dir / "reference_anchors.jsonl").exists():
        pytest.skip("no committed anchors")
    return A.current(DEFAULT)


def test_committed_anchors_verify(committed):
    t = Table(DEFAULT.ideology_dir, "reference_anchors")
    assert t.verify() == []
    assert all(not l["content"]["fixture"] for l in t.lines()), "fixtures never reach data/ideology"
    assert M.anchor_problems(committed) == []
    assert [r["anchor_id"] for r in committed] == ["sanders", "biden", "vance"]


def test_committed_anchors_match_the_raw_voteview_file(committed):
    if not DEFAULT.members_csv.exists():
        pytest.skip("no local Voteview file")
    snap = json.loads((DEFAULT.raw_dir / "SNAPSHOT.json").read_text())
    vv = next(s for s in snap["sources"] if s["file"] == DEFAULT.members_csv.name)
    if any(r["source_sha256"] != vv["sha256"] for r in committed):
        pytest.skip("the local snapshot is newer than the committed anchors: run anchors")
    rows = {}
    with DEFAULT.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["bioguide_id"] in ("S000033", "B000444", "V000137"):
                rows.setdefault((row["bioguide_id"], row["chamber"]), []).append(row)
    sanders, biden, vance = committed
    senate = {b: {float(r["nominate_dim1"]) for r in rows[(b, "Senate")]} for b in ("S000033", "B000444", "V000137")}
    assert senate == {"S000033": {sanders["nominate_dim1"]}, "B000444": {biden["nominate_dim1"]}, "V000137": {vance["nominate_dim1"]}}
    assert (sanders["nominate_dim1"], biden["nominate_dim1"], vance["nominate_dim1"]) == (-0.546, -0.314, 0.85)
    president = {float(r["nominate_dim1"]) for r in rows.get(("B000444", "President"), []) if r["nominate_dim1"]}
    assert president and biden["nominate_dim1"] not in president, "Biden's presidential estimate is a different number and is not used"
    assert set(biden["congresses"]) == {"Senate"} and set(vance["congresses"]) == {"Senate"}
    # the years in the labels match the Congresses they served in (a Congress begins in 1789 + 2 x (n - 1))
    for r in (biden, vance):
        first, last = r["congresses"]["Senate"]
        assert f"{1789 + 2 * (first - 1)}-{1789 + 2 * (last - 1)}" in r["record_basis"], r["record_basis"]


def test_sanders_anchor_is_the_same_number_as_his_senator_record(committed):
    sen = next(s for s in Table(DEFAULT.ideology_dir, "senator_ideology").current()
               if s["bioguide_id"] == "S000033" and s["congress"] == DEFAULT.congress)
    assert sen["seated"] and sen["nominate_dim1"] == committed[0]["nominate_dim1"]
