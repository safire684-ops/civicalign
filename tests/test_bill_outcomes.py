"""Pillar 5 outcome sets: Senate bills that passed the Senate, and which of those were enacted.

Enactment (rule enactment_signature_or_public_law_v1): a presidential signature
or a recorded public law. A signed bill is enacted even before its public-law
number appears; the number and its pending state are kept separately.

Fixture tests use invented bill-status records (FIXTURE titles, FX ids) in a
temporary folder. Real-data tests recount the committed tables from the raw
archive with separate code (skipped if the raw files are absent or another
version). Nothing here writes to data/ideology/.
"""
import ast
import copy
import dataclasses
import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import bill_outcomes as BO
from civicalign.ideology import bill_tallies as T
from civicalign.ideology import bills as BL
from civicalign.ideology import ingest as I
from civicalign.ideology import records as R
from civicalign.ideology.store import Table
from test_bills import SENATORS, WHEN, write_archive

ROOT = Path(__file__).resolve().parents[1]


def act(date, text, code=None, source="Senate"):
    c = f"<actionCode>{code}</actionCode>" if code else ""
    return f"<item><actionDate>{date}</actionDate><text>{text}</text>{c}<sourceSystem><name>{source}</name></sourceSystem></item>"


PASS_FLOOR = "Passed Senate without amendment by Unanimous Consent."
PASS_LOC = "Passed/agreed to in Senate: Passed Senate without amendment by Unanimous Consent."


def bill(number, sponsor, actions="", laws="", engrossed=False):
    tv = "<textVersions><item><type>Engrossed in Senate</type></item></textVersions>" if engrossed else "<textVersions/>"
    return (f"<billStatus><bill><number>{number}</number><updateDate>2026-01-01T00:00:00Z</updateDate><type>S</type>"
            f"<introducedDate>2025-02-01</introducedDate><congress>119</congress><committees/>"
            f"<actions>{actions}</actions><sponsors><item><bioguideId>{sponsor}</bioguideId><fullName>Sen. FIXTURE {sponsor}</fullName>"
            f"<isByRequest>N</isByRequest></item></sponsors><title>FIXTURE bill {number}</title><laws>{laws}</laws>{tv}"
            f"<latestAction><actionDate>2025-03-01</actionDate><text>FIXTURE</text></latestAction></bill></billStatus>").encode()


LAW = "<item><type>Public Law</type><number>119-99</number></item>"
BILLS = {
    # passed: code 17000, the floor action and the engrossed text
    "BILLSTATUS-119s1.xml": bill(1, "FX00001", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress"),
                                 engrossed=True),
    # passed twice over (two code-17000 actions): still one bill, earliest date
    "BILLSTATUS-119s2.xml": bill(2, "FX00002", act("2025-06-01", PASS_LOC, "17000", "Library of Congress")
                                 + act("2025-05-01", PASS_LOC, "17000", "Library of Congress") + act("2025-05-01", PASS_FLOOR), engrossed=True),
    # introduced only
    "BILLSTATUS-119s3.xml": bill(3, "FX00001", act("2025-02-01", "Introduced in Senate", "10000", "Library of Congress")),
    # passed and became law
    "BILLSTATUS-119s4.xml": bill(4, "FX00002", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress")
                                 + act("2025-07-01", "Signed by President.", "36000", "Library of Congress")
                                 + act("2025-07-02", "Became Public Law No: 119-99.", "36000", "Library of Congress"), laws=LAW, engrossed=True),
    # passed, signed, law number not yet recorded
    "BILLSTATUS-119s5.xml": bill(5, "FX00009", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress")
                                 + act("2025-09-25", "Signed by President.", "36000", "Library of Congress"), engrossed=True),
    # passage later vitiated
    "BILLSTATUS-119s6.xml": bill(6, "FX00001", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress")
                                 + act("2025-04-02", "By unanimous consent, passage of the bill was vitiated.")),
    # third reading vitiated, never passed (like S2882)
    "BILLSTATUS-119s7.xml": bill(7, "FX00002", act("2025-09-19", "Under the order of 9/19/2025, the third reading was vitiated.")),
    # became law with no signature action (law without signature, or a veto override), like S629
    "BILLSTATUS-119s9.xml": bill(9, "FX00001", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress")
                                 + act("2025-07-12", "Became Public Law No: 119-77.", "36000", "Library of Congress"),
                                 laws="<item><type>Public Law</type><number>119-77</number></item>", engrossed=True),
    # a "Became Public Law" action but no <laws> element yet: the number is read from the action
    "BILLSTATUS-119s10.xml": bill(10, "FX00002", act("2025-04-01", PASS_FLOOR) + act("2025-04-01", PASS_LOC, "17000", "Library of Congress")
                                  + act("2025-08-01", "Signed by President.", "36000", "Library of Congress")
                                  + act("2025-08-02", "Became Public Law No: 119-80.", "36000", "Library of Congress"), engrossed=True),
}


@pytest.fixture
def cfg(tmp_path):
    raw = tmp_path / "FIXTURE_raw"; raw.mkdir()
    (raw / "SNAPSHOT.json").write_text(json.dumps({"run_utc": WHEN, "accepted": True, "sources": []}))
    c = dataclasses.replace(DEFAULT, raw_dir=raw, ideology_dir=tmp_path / "FIXTURE_ideology")
    Table(c.ideology_dir, "senator_ideology").append(SENATORS, "FIXTURE")
    write_archive(c, BILLS)
    BL.run(c)
    BO.run(c)
    return c


def outcomes(cfg):
    return {r["bill_id"]: r for r in BO.current(cfg)}


# ---- the rule --------------------------------------------------------------------------------------

def test_passage_is_the_code_17000_action(cfg):
    o = outcomes(cfg)
    assert {b for b, r in o.items() if r["passed_senate"]} == {"S1", "S2", "S4", "S5", "S9", "S10"}
    assert o["S1"]["loc_passage_actions"] == [{"date": "2025-04-01", "text": PASS_LOC}]
    assert o["S1"]["senate_floor_passage_actions"] == [{"date": "2025-04-01", "text": PASS_FLOOR}] and o["S1"]["engrossed_in_senate"]
    assert not o["S3"]["passed_senate"] and o["S3"]["passed_senate_date"] is None


def test_a_bill_is_counted_once_however_many_actions_say_it_passed(cfg):
    o = outcomes(cfg)
    assert len(o["S2"]["loc_passage_actions"]) == 2 and o["S2"]["passed_senate_date"] == "2025-05-01"
    t = T.passed_senate_tally(BL.current(cfg), BO.current(cfg))
    assert t["passed_senate"]["bill_ids"].count("S2") == 1 and t["passed_senate"]["total"] == 6


def test_vitiated_passage_and_vitiated_third_reading_are_not_passage(cfg):
    o = outcomes(cfg)
    assert o["S6"]["passage_vitiated"] and not o["S6"]["passed_senate"]
    assert not o["S7"]["passed_senate"] and not o["S7"]["passage_vitiated"]


def test_passed_senate_and_enacted_are_separate(cfg):
    o = outcomes(cfg)
    s4 = o["S4"]      # signed, then the public law recorded
    assert (s4["enacted"], s4["enactment_basis"], s4["public_law_number"], s4["public_law_number_pending"]) == \
        (True, "SIGNED_BY_PRESIDENT_AND_PUBLIC_LAW_RECORDED", "119-99", False)
    assert (s4["signed_date"], s4["became_public_law_date"], s4["enacted_date"]) == ("2025-07-01", "2025-07-02", "2025-07-01")
    t = T.passed_senate_tally(BL.current(cfg), BO.current(cfg))
    assert set(t["enacted"]["bill_ids"]) <= set(t["passed_senate"]["bill_ids"])
    assert not o["S1"]["enacted"] and o["S1"]["enactment_basis"] is None and o["S1"]["public_law_number"] is None


def test_a_signed_bill_is_enacted_while_its_public_law_number_is_pending(cfg):
    s5 = outcomes(cfg)["S5"]
    assert (s5["enacted"], s5["enactment_basis"], s5["public_law_number"], s5["public_law_number_pending"], s5["enacted_date"]) == \
        (True, "SIGNED_BY_PRESIDENT_PUBLIC_LAW_NUMBER_PENDING", None, True, "2025-09-25")
    t = T.passed_senate_tally(BL.current(cfg), BO.current(cfg))
    assert "S5" in t["enacted"]["bill_ids"], "a signed bill is law before its number appears"
    assert t["public_law_number_pending"]["bill_ids"] == ["S5"]
    assert "enacted" in t["public_law_number_pending"]["note"] and "not yet law" not in t["public_law_number_pending"]["note"]


def test_a_public_law_without_a_signature_action_is_enacted(cfg):
    o = outcomes(cfg)
    assert (o["S9"]["enacted"], o["S9"]["enactment_basis"], o["S9"]["public_law_number"], o["S9"]["enacted_date"]) == \
        (True, "PUBLIC_LAW_RECORDED", "119-77", "2025-07-12")
    assert (o["S10"]["public_law_number"], o["S10"]["public_law_number_pending"]) == ("119-80", False), \
        "a Became Public Law action records the number even before the <laws> element"
    t = T.passed_senate_tally(BL.current(cfg), BO.current(cfg))
    assert t["enacted"]["bill_ids"] == ["S4", "S5", "S9", "S10"]
    assert t["public_law_number_recorded"]["bill_ids"] == ["S4", "S9", "S10"]


def test_the_breakdown_by_sponsor_class(cfg):
    t = T.passed_senate_tally(BL.current(cfg), BO.current(cfg))
    got = {k: v["bill_ids"] for k, v in t["passed_senate"]["by_classification"].items()}
    assert got == {"LIBERAL_SPONSOR": ["S1", "S9"], "CONSERVATIVE_SPONSOR": ["S2", "S4", "S10"], "ZERO_SCORE_SPONSOR": ["S5"], "UNKNOWN": []}
    law = {k: v["bill_ids"] for k, v in t["enacted"]["by_classification"].items()}
    assert law == {"LIBERAL_SPONSOR": ["S9"], "CONSERVATIVE_SPONSOR": ["S4", "S10"], "ZERO_SCORE_SPONSOR": ["S5"], "UNKNOWN": []}
    assert t["passed_senate"]["outcome_set"].startswith("Passed Senate") and t["passed_senate"]["outcome_set_chosen"]
    assert T.trace_problems(t["passed_senate"]) == [] and T.trace_problems(t["enacted"]) == []


@pytest.mark.parametrize("extra", [bill(8, "FX00001", laws=LAW),
                                   bill(8, "FX00001", act("2025-07-01", "Signed by President.", "36000", "Library of Congress"))])
def test_enactment_without_senate_passage_stops_the_build(cfg, extra):
    write_archive(cfg, {**BILLS, "BILLSTATUS-119s8.xml": extra}, when="2026-02-01T11:00:00Z")
    with pytest.raises(I.SnapshotMismatch, match="not as passing the Senate"):
        BO.run(cfg)


def test_the_validator_enforces_the_rule(cfg):
    rec = outcomes(cfg)["S1"]
    assert R.validate("senate_bill_outcomes", rec) == []
    for bad in ({"passed_senate": False}, {"passed_senate_date": None}, {"enacted": True},
                {"outcome_rule": "some_other_rule"}, {"loc_passage_actions": []}, {"enactment_rule": "number_required"}):
        assert R.validate("senate_bill_outcomes", {**rec, **bad}), bad
    signed = outcomes(cfg)["S5"]
    assert R.validate("senate_bill_outcomes", signed) == []
    for bad in ({"enacted": False, "enactment_basis": None, "enacted_date": None, "public_law_number_pending": False},
                {"enactment_basis": "PUBLIC_LAW_RECORDED"}, {"public_law_number_pending": False}):
        assert R.validate("senate_bill_outcomes", {**signed, **bad}), bad


def test_mismatched_classification_and_outcome_records_are_refused(cfg):
    cls, out = BL.current(cfg), BO.current(cfg)
    bad = copy.deepcopy(out); bad[0]["bill_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="different archive content"):
        T.passed_senate_tally(cls, bad)
    with pytest.raises(ValueError, match="different bills"):
        T.passed_senate_tally(cls, out[1:])


def test_rerun_writes_nothing_and_a_change_only_appends(cfg):
    t = Table(cfg.ideology_dir, "senate_bill_outcomes")
    before = t.path.read_text()
    assert BO.run(cfg)["new_versions_written"] == 0
    changed = {**BILLS, "BILLSTATUS-119s3.xml": bill(3, "FX00001", act("2025-02-01", "Introduced in Senate", "10000", "Library of Congress")
                                                   + act("2025-09-01", PASS_LOC, "17000", "Library of Congress"))}
    write_archive(cfg, changed, when="2026-02-01T11:00:00Z")
    assert BO.run(cfg)["new_versions_written"] == 1
    assert t.path.read_text().startswith(before) and t.verify() == []
    assert [h["content"]["passed_senate"] for h in t.history((119, "S3"))] == [False, True]


def test_no_llm_or_network_in_the_outcome_rule():
    src = (ROOT / "src" / "civicalign" / "ideology" / "bill_outcomes.py").read_text()
    allowed = {"argparse", "hashlib", "json", "re", "sys", "xml.etree.ElementTree", "zipfile"}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            assert all(a.name in allowed for a in node.names), [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            local = ("config", "bills", "ingest", "records", "store", "bill_tallies")
            if node.level == 0:
                assert node.module in allowed, node.module
            elif node.module is None:          # from . import x
                assert all(a.name in local for a in node.names), [a.name for a in node.names]
            else:
                assert node.module in local, node.module
    assert not re.search(r"openai|anthropic|langchain|claude|gpt-|llama|transformers|subprocess|urllib|requests|socket", src, re.I)


# ---- the committed tables against the raw archive -----------------------------------------------------

@pytest.fixture(scope="module")
def real():
    if not (DEFAULT.ideology_dir / "senate_bill_outcomes.jsonl").exists():
        pytest.skip("no committed outcome records")
    if not DEFAULT.billflow_zip.exists():
        pytest.skip("no local bill-status archive")
    snap = json.loads((DEFAULT.raw_dir / "SNAPSHOT.json").read_text())
    arch = next(s for s in snap["sources"] if s["file"] == DEFAULT.billflow_zip.name)
    if hashlib.sha256(DEFAULT.billflow_zip.read_bytes()).hexdigest() != arch["sha256"]:
        pytest.skip("the local archive is not the snapshot's")
    raw = {}
    with zipfile.ZipFile(DEFAULT.billflow_zip) as z:
        for n in z.namelist():
            data = z.read(n); text = data.decode()
            num = re.search(r"<bill>.*?<number>(\d+)</number>", text, re.S).group(1)
            own = re.search(r"<actions>(.*?)</actions>", text, re.S)      # the bill's own actions, not its related bills'
            own = own.group(1) if own else ""
            raw[f"S{num}"] = {"sha": hashlib.sha256(data).hexdigest(), "code17000": "<actionCode>17000</actionCode>" in own,
                              "signed": "<text>Signed by President." in own, "became": "<text>Became Public Law" in own,
                              "engrossed": "<type>Engrossed in Senate</type>" in text,
                              "laws": re.findall(r"<laws>.*?</laws>", text, re.S), "member": n}
    out = {r["bill_id"]: r for r in BO.current(DEFAULT)}
    if set(out) != set(raw):
        pytest.skip("the committed tables are from a different archive version than the local file")
    return raw, out, BL.current(DEFAULT)


def test_every_count_traces_to_the_official_bill_status_record(real):
    raw, out, cls = real
    t = T.passed_senate_tally(cls, list(out.values()))
    passed, enacted = set(t["passed_senate"]["bill_ids"]), set(t["enacted"]["bill_ids"])
    # separate code: a plain text search of each bill's own XML
    has_law = {b for b, r in raw.items() if (r["laws"] and "<item>" in r["laws"][0]) or r["became"]}
    assert passed == {b for b, r in raw.items() if r["code17000"]}
    assert enacted == {b for b, r in raw.items() if r["signed"]} | has_law
    assert set(t["public_law_number_recorded"]["bill_ids"]) == has_law
    assert set(t["public_law_number_pending"]["bill_ids"]) == {b for b, r in raw.items() if r["signed"]} - has_law
    assert t["public_law_number_recorded"]["count"] + t["public_law_number_pending"]["count"] == t["enacted"]["total"]
    for b in passed:
        assert out[b]["bill_fingerprint"] == raw[b]["sha"], "the outcome record is the XML it was read from"
        assert out[b]["bill_source_url"].endswith("/" + raw[b]["member"])
        assert any(a["text"].startswith("Passed/agreed to in Senate") for a in out[b]["loc_passage_actions"])
    for part in ("passed_senate", "enacted"):
        assert T.trace_problems(t[part]) == []
        by = {c: set(v["bill_ids"]) for c, v in t[part]["by_classification"].items()}
        for c, ids in by.items():
            assert all({r["bill_id"]: r for r in cls}[b]["sponsor_classification"] == c for b in ids)


def test_the_three_passage_signals_agree_on_the_real_archive(real):
    raw, out, _ = real
    assert BO.evidence_disagreements(list(out.values())) == []
    assert {b for b, r in raw.items() if r["engrossed"]} == {b for b, o in out.items() if o["passed_senate"]}


def test_committed_outcome_table_verifies(real):
    assert Table(DEFAULT.ideology_dir, "senate_bill_outcomes").verify() == []
    assert all(not r["fixture"] for r in real[1].values())


def test_nothing_calls_a_signed_bill_not_yet_law():
    for f in ("bill_outcomes.py", "bill_tallies.py", "records.py"):
        src = (ROOT / "src" / "civicalign" / "ideology" / f).read_text().lower()
        for phrase in ("not yet law", "not counted as law", "not law yet", "became_law"):
            assert phrase not in src, (f, phrase)


# ---- the daily refresh: verify, and the table versions the page is built from --------------------------------

def test_verify_passes_when_current_and_reports_a_stale_table(cfg):
    assert BO.verify(cfg) == []
    before = BO.table_fingerprints(cfg)
    changed = {**BILLS, "BILLSTATUS-119s3.xml": bill(3, "FX00001", act("2025-02-01", "Introduced in Senate", "10000", "Library of Congress")
                                                   + act("2025-09-01", PASS_FLOOR) + act("2025-09-01", PASS_LOC, "17000", "Library of Congress"),
                                                   engrossed=True)}
    write_archive(cfg, changed, when="2026-02-01T11:00:00Z")        # a newer verified snapshot, tables not yet refreshed
    probs = BO.verify(cfg)
    assert any("bill_sponsor_classifications" in p and "not current" in p for p in probs)
    assert any("senate_bill_outcomes" in p and "not current" in p for p in probs)
    assert (BL.run(cfg)["new_versions_written"], BO.run(cfg)["new_versions_written"]) == (1, 1), "only the changed bill is appended"
    assert BO.verify(cfg) == []
    after = BO.table_fingerprints(cfg)
    assert set(after) == {"bill_sponsor_classifications", "senate_bill_outcomes"} and all(after[k] != before[k] for k in after)
    assert (BL.run(cfg)["new_versions_written"], BO.run(cfg)["new_versions_written"]) == (0, 0), "an unchanged rerun writes nothing"
    assert outcomes(cfg)["S3"]["passed_senate"]


def test_verify_reports_a_broken_table(cfg):
    f = cfg.ideology_dir / "senate_bill_outcomes.jsonl"
    lines = f.read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if '"signed_date":null' in l)
    lines[i] = lines[i].replace('"signed_date":null', '"signed_date":"2025-01-01"', 1)   # still a valid record, but edited
    f.write_text("\n".join(lines) + "\n")
    assert any(p.startswith("senate_bill_outcomes:") for p in BO.verify(cfg))
