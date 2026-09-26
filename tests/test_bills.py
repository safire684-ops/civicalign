"""Senate bills classified by their primary sponsor's nominate_dim1: the data layer.

Fixture tests build an invented bill-status archive (FIXTURE bills, fake FX ids,
non-existent states) in a temporary folder, with a snapshot record marked
fixture, and store invented senator_ideology rows. Real-data tests read the
committed table and the local raw files (skipped if absent). Nothing here writes
to data/ideology/.
"""
import ast
import copy
import csv
import dataclasses
import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import bill_tallies as T
from civicalign.ideology import bills as BL
from civicalign.ideology import ingest as I
from civicalign.ideology import records as R
from civicalign.ideology.store import Table

ROOT = Path(__file__).resolve().parents[1]
WHEN = "2026-01-05T11:00:00Z"


# ---- fixtures ------------------------------------------------------------------------------------

def senator(b, score, seated=True, voteview_row=True):
    return {"senator_id": ("9" + b[2:]) if voteview_row else None, "bioguide_id": b, "congress": 119, "chamber": "Senate",
            "state": "ZZ", "name": f"FIXTURE Senator {b}", "voteview_party_code": "100" if voteview_row else None,
            "voteview_row": voteview_row, "nominate_dim1": score, "nokken_poole_dim1": score, "nominate_number_of_votes": 100 if voteview_row else None,
            "seated": seated, "roster_source_version": "FIXTURE", "roster_retrieved_at": WHEN, "source": "FIXTURE",
            "source_url": "file://FIXTURE", "source_version": "FIXTURE-v1", "source_sha256": "0" * 64, "retrieved_at": WHEN, "fixture": True}


SENATORS = [senator("FX00001", -0.4), senator("FX00002", 0.5), senator("FX00009", 0.0), senator("FX00010", None, voteview_row=False)]


def committee(code, chamber="Senate", *acts):
    items = "".join(f"<item><name>{n}</name><date>{d}</date></item>" for n, d in acts)
    return f"<item><systemCode>{code}</systemCode><name>FIXTURE {code}</name><chamber>{chamber}</chamber><activities>{items}</activities></item>"


def bill_xml(number, sponsor=None, bioguide=True, committees="", laws="", congress=119, btype="S", by_request="N"):
    sp = ""
    if sponsor:
        bg = f"<bioguideId>{sponsor}</bioguideId>" if bioguide else ""
        sp = f"<sponsors><item>{bg}<fullName>Sen. FIXTURE {sponsor} [X-ZZ]</fullName><isByRequest>{by_request}</isByRequest></item></sponsors>"
    return (f"<billStatus><bill><number>{number}</number><updateDate>2026-01-01T00:00:00Z</updateDate><type>{btype}</type>"
            f"<introducedDate>2025-02-01</introducedDate><congress>{congress}</congress><committees>{committees}</committees>"
            f"{sp}<title>FIXTURE bill {number}</title><laws>{laws}</laws>"
            f"<latestAction><actionDate>2025-03-01</actionDate><text>FIXTURE latest action</text></latestAction></bill></billStatus>").encode()


BILLS = {
    "BILLSTATUS-119s1.xml": bill_xml(1, "FX00001", committees=committee("ssbk00", "Senate", ("Referred To", "2025-02-01T00:00:00Z"),
                                                                       ("Reported By", "2025-05-01T00:00:00Z"))),
    "BILLSTATUS-119s2.xml": bill_xml(2, "FX00002", committees=committee("ssbk00", "Senate", ("Referred To", "2025-02-02T00:00:00Z"))
                                     + committee("ssfi00", "Senate", ("Referred To", "2025-02-02T00:00:00Z"), ("Discharged From", "2025-06-01T00:00:00Z"))
                                     + committee("slin00", "Senate", ("Referred To", "2025-02-02T00:00:00Z"))
                                     + committee("hsju00", "House", ("Referred To", "2025-02-02T00:00:00Z"))),
    "BILLSTATUS-119s3.xml": bill_xml(3, "FX00009", committees=committee("ssbk00", "Senate", ("Reported Original Measure", "2025-04-01T00:00:00Z"))),
    "BILLSTATUS-119s4.xml": bill_xml(4, "FX00010", laws="<item><type>Public Law</type><number>119-99</number></item>"),
    "BILLSTATUS-119s5.xml": bill_xml(5, "FX00099"),
    "BILLSTATUS-119s6.xml": bill_xml(6, None),
    "BILLSTATUS-119s7.xml": bill_xml(7, "FX00002", bioguide=False),
}


def write_archive(cfg, bills: dict, when=WHEN):
    path = cfg.raw_dir / cfg.billflow_zip.name
    with zipfile.ZipFile(path, "w") as z:
        for name, data in bills.items():
            z.writestr(name, data)
    snap = json.loads((cfg.raw_dir / "SNAPSHOT.json").read_text())
    data = path.read_bytes()
    entry = {"name": "FIXTURE bills", "url": "file://FIXTURE/bills.zip", "file": path.name, "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest(), "content_key": "FIXTURE-" + hashlib.sha256(data).hexdigest()[:16],
             "changed": True, "content_changed_utc": when, "checked_utc": when, "vintage": "FIXTURE", "critical": True, "fixture": True}
    snap["sources"] = [s for s in snap["sources"] if s["file"] != path.name] + [entry]
    (cfg.raw_dir / "SNAPSHOT.json").write_text(json.dumps(snap))


@pytest.fixture
def cfg(tmp_path):
    raw = tmp_path / "FIXTURE_raw"; raw.mkdir()
    (raw / "SNAPSHOT.json").write_text(json.dumps({"run_utc": WHEN, "accepted": True, "sources": []}))
    c = dataclasses.replace(DEFAULT, raw_dir=raw, ideology_dir=tmp_path / "FIXTURE_ideology")
    Table(c.ideology_dir, "senator_ideology").append(SENATORS, "FIXTURE")
    write_archive(c, BILLS)
    return c


def by_id(cfg):
    return {r["bill_id"]: r for r in BL.current(cfg)}


# ---- sponsor mapping, Voteview lookup and gating --------------------------------------------------------

def test_sponsor_bioguide_mapping_and_voteview_lookup(cfg):
    assert BL.run(cfg)["new_versions_written"] == 7
    b = by_id(cfg)
    rids = {l["content"]["bioguide_id"]: l["record_id"] for l in Table(cfg.ideology_dir, "senator_ideology").lines()}
    assert (b["S1"]["sponsor_bioguide_id"], b["S1"]["sponsor_nominate_dim1"], b["S1"]["sponsor_score_record_id"]) == ("FX00001", -0.4, rids["FX00001"])
    assert (b["S2"]["sponsor_bioguide_id"], b["S2"]["sponsor_nominate_dim1"]) == ("FX00002", 0.5)
    assert b["S1"]["primary_sponsor_name"] == "Sen. FIXTURE FX00001 [X-ZZ]"
    assert b["S1"]["sponsor_score_source"] == BL.SCORE_SOURCE and b["S1"]["sponsor_score_source_version"] == "FIXTURE-v1"
    assert all(r["fixture"] and r["source_url"] == "file://FIXTURE/bills.zip" for r in b.values())
    assert b["S1"]["bill_source_url"].endswith("/BILLSTATUS/119/s/BILLSTATUS-119s1.xml")


@pytest.mark.parametrize("score,cls", [(-0.001, "LIBERAL_SPONSOR"), (0.001, "CONSERVATIVE_SPONSOR"), (0.0, "ZERO_SCORE_SPONSOR"),
                                       (-1.0, "LIBERAL_SPONSOR"), (1.0, "CONSERVATIVE_SPONSOR"), (None, "UNKNOWN")])
def test_the_sign_decides_the_class(score, cls):
    assert BL.classify(score) == cls


def test_positive_negative_and_zero_records(cfg):
    BL.run(cfg)
    b = by_id(cfg)
    assert [b[i]["sponsor_classification"] for i in ("S1", "S2", "S3")] == ["LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR"]
    assert b["S1"]["sponsor_classification_label"] == "Bill sponsored by a senator with a negative DW-NOMINATE score"
    assert b["S2"]["sponsor_classification_label"] == "Bill sponsored by a senator with a positive DW-NOMINATE score"
    assert all("not the content or ideology of the bill" in r["classification_basis"] for r in b.values())


def test_the_validator_refuses_a_class_or_label_that_does_not_follow_the_score(cfg):
    BL.run(cfg)
    rec = by_id(cfg)["S1"]
    assert R.validate(R_TABLE, rec) == []
    for bad in ({"sponsor_classification": "CONSERVATIVE_SPONSOR"}, {"sponsor_classification_label": "A liberal bill"},
                {"classification_basis": "the bill's ideology"}, {"sponsor_nominate_dim1": None},
                {"sponsor_classification": "UNKNOWN", "sponsor_nominate_dim1": None, "unknown_reason": None}):
        assert R.validate(R_TABLE, {**rec, **bad}), bad


R_TABLE = "bill_sponsor_classifications"


def test_unknown_sponsor_is_handled(cfg):
    BL.run(cfg)
    b = by_id(cfg)
    assert (b["S6"]["sponsor_classification"], b["S6"]["sponsor_bioguide_id"]) == ("UNKNOWN", None)
    assert "no primary sponsor" in b["S6"]["unknown_reason"]
    assert b["S7"]["sponsor_classification"] == "UNKNOWN" and "no primary sponsor Bioguide id" in b["S7"]["unknown_reason"]
    assert b["S6"]["sponsor_classification_label"] == "Sponsor's DW-NOMINATE score not available"


def test_missing_or_unscored_voteview_record_is_handled(cfg):
    BL.run(cfg)
    b = by_id(cfg)
    assert b["S5"]["sponsor_classification"] == "UNKNOWN" and "has no Voteview Senate row" in b["S5"]["unknown_reason"]
    assert b["S5"]["sponsor_score_record_id"] is None and b["S5"]["sponsor_nominate_dim1"] is None
    assert b["S4"]["sponsor_classification"] == "UNKNOWN" and "has not scored" in b["S4"]["unknown_reason"]
    assert b["S4"]["sponsor_score_record_id"] is not None, "the unscored senator's record is still named"


def test_committees_status_and_non_senate_bills(cfg):
    BL.run(cfg)
    b = by_id(cfg)
    assert b["S1"]["referred_committees"] == [{"committee_id": "SSBK", "referred": True, "referred_date": "2025-02-01T00:00:00Z",
                                               "reported": True, "reported_date": "2025-05-01T00:00:00Z", "discharged": False}]
    assert [c["committee_id"] for c in b["S2"]["referred_committees"]] == ["SSBK", "SSFI"], "select and House committees are left out"
    assert b["S2"]["referred_committees"][1]["discharged"] and not b["S2"]["referred_committees"][1]["reported"]
    assert (b["S3"]["referred_committees"][0]["referred"], b["S3"]["referred_committees"][0]["reported"]) == (False, True)
    assert b["S4"]["bill_status"] == {"latest_action_date": "2025-03-01", "latest_action_text": "FIXTURE latest action", "laws": ["Public Law 119-99"]}


def test_other_congresses_and_types_are_left_out(cfg):
    write_archive(cfg, {**BILLS, "BILLSTATUS-118s9.xml": bill_xml(9, "FX00001", congress=118),
                        "BILLSTATUS-119sres9.xml": bill_xml(9, "FX00001", btype="SRES")})
    BL.run(cfg)
    assert set(by_id(cfg)) == {f"S{i}" for i in range(1, 8)}


# ---- every tally traces to exact bill ids ---------------------------------------------------------------------

def test_sponsor_tally_traces_to_bill_ids(cfg):
    BL.run(cfg)
    t = T.sponsor_tally(BL.current(cfg))
    assert T.trace_problems(t) == []
    assert t["outcome_set_chosen"] is False and "no outcome set has been chosen" in t["outcome_set"]
    got = {k: v["bill_ids"] for k, v in t["by_classification"].items()}
    assert got == {"LIBERAL_SPONSOR": ["S1"], "CONSERVATIVE_SPONSOR": ["S2"], "ZERO_SCORE_SPONSOR": ["S3"],
                   "UNKNOWN": ["S4", "S5", "S6", "S7"]}
    sub = T.sponsor_tally(BL.current(cfg), {"S1", "S5"}, "FIXTURE outcome set")
    assert (sub["total"], sub["outcome_set"], sub["by_classification"]["UNKNOWN"]["bill_ids"]) == (2, "FIXTURE outcome set", ["S5"])
    with pytest.raises(ValueError, match="no classification record"):
        T.sponsor_tally(BL.current(cfg), {"S999"}, "FIXTURE")
    with pytest.raises(ValueError, match="needs a name"):
        T.sponsor_tally(BL.current(cfg), {"S1"})


def test_committee_tallies_trace_to_bill_ids(cfg):
    BL.run(cfg)
    c = T.committee_tallies(BL.current(cfg))
    assert set(c) == {"SSBK", "SSFI"}
    assert c["SSBK"]["referred"]["bill_ids"] == ["S1", "S2"] and c["SSBK"]["reported"]["bill_ids"] == ["S1", "S3"]
    assert c["SSBK"]["reported_of_referred"]["bill_ids"] == ["S1"]
    assert c["SSBK"]["reported"]["by_classification"]["ZERO_SCORE_SPONSOR"]["bill_ids"] == ["S3"]
    assert c["SSFI"]["reported"]["total"] == 0, "discharge is not a report"
    for slots in c.values():
        for tally in slots.values():
            assert T.trace_problems(tally) == []


def test_trace_problems_catch_a_bad_tally(cfg):
    BL.run(cfg)
    t = T.sponsor_tally(BL.current(cfg))
    bad = copy.deepcopy(t); bad["by_classification"]["LIBERAL_SPONSOR"]["count"] = 5
    assert T.trace_problems(bad)
    bad = copy.deepcopy(t); bad["by_classification"]["UNKNOWN"]["bill_ids"].append("S1")
    assert T.trace_problems(bad)


# ---- versioning: unchanged writes nothing; old records are never overwritten -------------------------------------

def test_rerunning_unchanged_data_writes_nothing(cfg):
    assert BL.run(cfg)["new_versions_written"] == 7
    before = (cfg.ideology_dir / "bill_sponsor_classifications.jsonl").read_text()
    write_archive(cfg, BILLS, when="2026-02-01T11:00:00Z")          # re-fetched, identical bills
    assert BL.run(cfg)["new_versions_written"] == 0
    assert (cfg.ideology_dir / "bill_sponsor_classifications.jsonl").read_text() == before


def test_a_changed_bill_or_sponsor_score_appends_and_never_overwrites(cfg):
    BL.run(cfg)
    t = Table(cfg.ideology_dir, "bill_sponsor_classifications")
    before = t.path.read_text()
    changed = dict(BILLS)
    changed["BILLSTATUS-119s1.xml"] = BILLS["BILLSTATUS-119s1.xml"].replace(b"FIXTURE latest action", b"FIXTURE newer action")
    write_archive(cfg, changed, when="2026-02-01T11:00:00Z")
    assert BL.run(cfg)["new_versions_written"] == 1, "only the changed bill gets a new version"
    after = t.path.read_text()
    assert after.startswith(before), "earlier lines are never rewritten"
    hist = t.history((119, "S1"))
    assert len(hist) == 2 and hist[1]["prev_record_id"] == hist[0]["record_id"]
    assert (hist[0]["content"]["retrieved_at"], hist[1]["content"]["retrieved_at"]) == (WHEN, "2026-02-01T11:00:00Z")
    assert by_id(cfg)["S2"]["retrieved_at"] == WHEN, "unchanged bills keep the date their content was first seen"
    # a new score for a sponsor re-classifies that sponsor's bills
    Table(cfg.ideology_dir, "senator_ideology").append([senator("FX00002", -0.1)], "FIXTURE")
    assert BL.run(cfg)["new_versions_written"] == 1          # only S2: S7 names no Bioguide id, so no score record
    assert by_id(cfg)["S2"]["sponsor_classification"] == "LIBERAL_SPONSOR"
    assert t.verify() == []


def test_a_mismatched_archive_is_refused(cfg):
    (cfg.raw_dir / cfg.billflow_zip.name).write_bytes(b"not the snapshot's archive")
    with pytest.raises(I.SnapshotMismatch):
        BL.run(cfg)


# ---- no language model, no network, no external program ------------------------------------------------------

def test_no_llm_or_network_in_the_classification_pipeline():
    allowed = {"argparse", "hashlib", "json", "sys", "xml.etree.ElementTree", "zipfile", "__future__"}
    forbidden = re.compile(r"openai|anthropic|langchain|llama|transformers|huggingface|gpt-|claude|cohere|mistral|gemini|"
                           r"ollama|api\.|https?://(?!www\.govinfo\.gov)", re.I)
    for f in ("bills.py", "bill_tallies.py"):
        src = (ROOT / "src" / "civicalign" / "ideology" / f).read_text()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name in allowed, (f, a.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module in allowed, (f, node.module)
            elif isinstance(node, ast.ImportFrom):
                assert node.module in (None, "config", "ingest", "records", "store", "bill_tallies"), (f, node.module)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not forbidden.search(node.value), (f, node.value[:80])
        for banned in ("subprocess", "urllib", "requests", "http.client", "socket", "os.system", "Popen"):
            assert banned not in src, (f, banned)


def test_the_classification_is_not_a_calculation_input():
    for f in ("compute.py", "pillars.py", "inputs.py"):
        src = (ROOT / "src" / "civicalign" / "ideology" / f).read_text()
        assert "bill_sponsor_classifications" not in src and "bills" not in re.findall(r"from \.(\w+)", src), f


# ---- the committed table and the real archive ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    if not (DEFAULT.ideology_dir / "bill_sponsor_classifications.jsonl").exists():
        pytest.skip("no committed bill classifications")
    return BL.current(DEFAULT)


def test_committed_table_verifies_and_holds_no_fixtures(real):
    t = Table(DEFAULT.ideology_dir, "bill_sponsor_classifications")
    assert t.verify() == []
    assert all(not r["fixture"] for r in real)
    assert len({r["bill_id"] for r in real}) == len(real) > 1000


def test_real_sponsors_and_scores_match_the_raw_files(real):
    if not DEFAULT.billflow_zip.exists() or not DEFAULT.members_csv.exists():
        pytest.skip("no local raw files")
    snap = json.loads((DEFAULT.raw_dir / "SNAPSHOT.json").read_text())
    arch = next(s for s in snap["sources"] if s["file"] == DEFAULT.billflow_zip.name)
    if hashlib.sha256(DEFAULT.billflow_zip.read_bytes()).hexdigest() != arch["sha256"]:
        pytest.skip("the local archive is not the snapshot's")
    sponsors = {}
    with zipfile.ZipFile(DEFAULT.billflow_zip) as z:
        for n in z.namelist():
            text = z.read(n).decode()
            num = re.search(r"<bill>.*?<number>(\d+)</number>", text, re.S).group(1)
            m = re.search(r"<sponsors>\s*<item>\s*<bioguideId>(\w+)</bioguideId>", text)
            sponsors[f"S{num}"] = m.group(1) if m else None
    scores = {}
    with DEFAULT.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] == "Senate" and row["congress"] == str(DEFAULT.congress) and row["nominate_dim1"]:
                scores[row["bioguide_id"]] = float(row["nominate_dim1"])
    by = {r["bill_id"]: r for r in real}
    if set(by) != set(sponsors):
        pytest.skip("the committed table is from a different archive version than the local file")
    for bid, r in by.items():
        assert r["sponsor_bioguide_id"] == sponsors[bid], bid
        s = scores.get(sponsors[bid])
        assert r["sponsor_nominate_dim1"] == s, bid
        assert r["sponsor_classification"] == ("UNKNOWN" if s is None else "LIBERAL_SPONSOR" if s < 0
                                               else "CONSERVATIVE_SPONSOR" if s > 0 else "ZERO_SCORE_SPONSOR"), bid


def test_real_tallies_trace_to_bill_ids(real):
    t = T.sponsor_tally(real)
    assert T.trace_problems(t) == [] and t["total"] == len(real)
    for cid, slots in T.committee_tallies(real).items():
        assert re.fullmatch(r"SS[A-Z]{2}", cid)
        for tally in slots.values():
            assert T.trace_problems(tally) == [], cid
        assert set(slots["reported_of_referred"]["bill_ids"]) <= set(slots["referred"]["bill_ids"])
