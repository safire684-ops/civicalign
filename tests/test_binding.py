"""Pillar 1, Stage 2: deterministic classification, binding, text selection,
CRA metadata, provenance and the supervisor's re-derivation."""
import json
from datetime import date
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.explain import binding as B
from civicalign.sources.billstatus import Action, BillRecord, RecordedVote, TextVersion, version_code
from civicalign.sources.rollcalls import RollCall
from civicalign.sources.senate_votes import SenateVote, normalise_measure

ROOT = Path(__file__).resolve().parents[1]
BDIR = ROOT / "data" / "explanations" / "119"


def _rc(question, bill="S2", date_="2026-06-05"):
    return RollCall(number=822, date=date_, bill=bill, question=question, result="Bill Passed", cutpoint=None, yea_is_right=None)


def _senate(question="On Passage of the Bill", title="S. 2, As Amended", doc_type="S.", number="2"):
    return SenateVote(congress=119, session=2, number=163, date="2026-06-05", time="04:42 AM", question=question,
                      question_text=f"{question} S. 2", title=title, document_text="An original bill",
                      result="Bill Passed", result_text="Bill Passed (52-47)", majority_requirement="1/2",
                      document_type=doc_type, document_number=number, amendment_number="", amendment_to_document="",
                      yeas=52, nays=47, present=0, absent=1, votes={}, members={})


def _bill(origin="Senate", btype="S", versions=(), actions=(), title="Secure America Act"):
    return BillRecord(congress=119, bill_type=btype, number=2, origin_chamber=origin, title=title, short_title="",
                      update_date="2026-06-11", text_versions=tuple(versions), actions=tuple(actions), laws=(), sha256="x", filename="BILLSTATUS-119s2.xml")


def tv(code, d, name=""):
    return TextVersion(name=name or code, code=code, date=d, url=f"https://www.govinfo.gov/content/pkg/BILLS-119s2{code}/xml/BILLS-119s2{code}.xml", urls=())


# ---- classification ----

def test_kind_comes_from_the_official_question_never_from_a_bill_number():
    assert B.classify(_rc("On the Cloture Motion"), None, None).kind == B.CLOTURE
    assert B.classify(_rc("On the Motion to Proceed", bill="SJRES18"), None, None).kind == B.MOTION_TO_PROCEED
    assert B.classify(_rc("On the Joint Resolution", bill="SJRES18"), None, None).kind == B.JOINT_RESOLUTION_PASSAGE
    assert B.classify(_rc("On the Point of Order", bill="HJRES88"), None, None).kind == B.POINT_OF_ORDER
    assert B.classify(_rc("On the Motion to Table", bill="S5"), None, None).kind == B.MOTION_TO_TABLE
    assert B.classify(_rc("On the Nomination", bill=""), None, None).kind == B.NOMINATION
    assert B.classify(_rc("On the Resolution", bill="SRES100"), None, None).kind == B.OTHER
    assert B.classify(_rc("Something new", bill="S1"), None, None).kind == B.OTHER
    for q in ("On the Cloture Motion", "On the Motion to Proceed", "On the Amendment", "On the Motion to Table", "On the Point of Order", "On the Nomination"):
        assert not B.classify(_rc(q), None, None).summary_eligible


def test_passage_as_amended_needs_corroboration_and_agreement():
    plain = B.classify(_rc("On Passage of the Bill"), _senate(title="S. 2"), None, "Passed Senate by Yea-Nay Vote.")
    assert plain.kind == B.PASSAGE and plain.summary_eligible
    amended = B.classify(_rc("On Passage of the Bill"), _senate(), None, "Passed Senate with an amendment by Yea-Nay Vote. 52 - 47.")
    assert amended.kind == B.PASSAGE_AS_AMENDED and "As Amended" in " ".join(amended.basis)
    conflict = B.classify(_rc("On Passage of the Bill"), _senate(title="S. 2"), None, "Passed Senate with an amendment")
    assert conflict.kind == B.OTHER and not conflict.summary_eligible and conflict.conflict
    q_conflict = B.classify(_rc("On Passage of the Bill"), _senate(question="On the Cloture Motion"), None, "")
    assert q_conflict.kind == B.OTHER


def test_supported_kinds_are_exactly_the_stage_2_set():
    assert B.SUPPORTED_KINDS == {B.PASSAGE, B.PASSAGE_AS_AMENDED, B.JOINT_RESOLUTION_PASSAGE}
    for k in B.SUPPORTED_KINDS:
        assert k in B.HEADINGS and k in B.YEA_NAY and k in B.NEXT_STEP
    assert B.HEADINGS[B.JOINT_RESOLUTION_PASSAGE] == ("If the resolution passes", "If the resolution does not pass")


# ---- CRA ----

def test_cra_metadata_is_read_from_the_official_title_only():
    t = ('A joint resolution providing for congressional disapproval under chapter 8 of title 5, United States Code, '
         'of the rule submitted by the Environmental Protection Agency relating to "Reconsideration of the Standards".')
    c = B.cra_from_title(t)
    assert c.is_cra and c.agency == "Environmental Protection Agency" and c.rule_title == "Reconsideration of the Standards"
    assert "5 U.S.C. 801(b)" in c.consequence_ref and c.underlying_rule_source is None and c.underlying_rule_sha256 is None
    assert not B.cra_from_title("A joint resolution to direct the removal of United States Armed Forces from hostilities").is_cra
    assert not B.cra_from_title("A joint resolution terminating the national emergency declared to impose duties").is_cra
    short = B.cra_from_title('A joint resolution disapproving the rule submitted by the Bureau of Consumer Financial Protection relating to "Overdraft Lending".')
    assert short.is_cra and short.agency == "Bureau of Consumer Financial Protection" and short.title_form == "disapproving the rule"
    assert version_code("https://www.govinfo.gov/content/pkg/PLAW-119publ98/uslm/PLAW-119publ98.xml") == "pl"
    plain = B.cra_from_title("Providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Bureau of Land Management relating to Coastal Plain Oil and Gas Leasing Program Record of Decision.")
    assert plain.is_cra and plain.agency == "Bureau of Land Management" and plain.rule_title == "Coastal Plain Oil and Gas Leasing Program Record of Decision"


# ---- text selection ----

def test_senate_origin_passage_as_amended_binds_the_engrossment_on_the_vote_date():
    bill = _bill(versions=[tv("is", "2025-01-15"), tv("pcs", "2026-05-20"), tv("es", "2026-06-05"), tv("enr", ""), tv("pl", "2026-06-11")])
    r = B.select_text(B.PASSAGE_AS_AMENDED, bill, "2026-06-05", today=date(2026, 9, 1))
    assert r.status == B.TEXT_BOUND and r.version.code == "es"


def test_enrolled_and_public_law_are_never_selected():
    bill = _bill(versions=[tv("enr", ""), tv("pl", "2026-06-11")])
    r = B.select_text(B.PASSAGE, bill, "2026-06-05", today=date(2026, 9, 1))
    assert r.status == B.TEXT_AMBIGUOUS and r.version is None
    bill = _bill(versions=[tv("is", "2025-01-15"), tv("enr", ""), tv("pl", "2026-06-11")])
    r = B.select_text(B.PASSAGE, bill, "2026-06-05", today=date(2026, 9, 1))
    assert r.version.code == "is"


def test_house_origin_unamended_takes_the_latest_pre_vote_senate_side_version():
    bill = _bill(origin="House", btype="HR", versions=[tv("ih", "2025-01-01"), tv("eh", "2025-03-10"), tv("rds", "2025-03-11"), tv("pcs", "2025-03-12"), tv("enr", "")])
    r = B.select_text(B.PASSAGE, bill, "2025-03-14", today=date(2026, 9, 1))
    assert r.status == B.TEXT_BOUND and r.version.code == "pcs"


def test_same_day_versions_resolve_by_precedence_not_ambiguity():
    bill = _bill(origin="House", btype="HR", versions=[tv("eh", "2025-03-11"), tv("rds", "2025-03-11")])
    r = B.select_text(B.PASSAGE, bill, "2025-03-14", today=date(2026, 9, 1))
    assert r.status == B.TEXT_BOUND and r.version.code == "rds" and "precedence" in r.selection_reason


def test_amended_without_engrossment_is_pending_then_ambiguous():
    bill = _bill(origin="House", btype="HR", versions=[tv("eh", "2025-06-01")])
    assert B.select_text(B.PASSAGE_AS_AMENDED, bill, "2025-07-01", today=date(2025, 7, 10)).status == B.TEXT_PENDING
    assert B.select_text(B.PASSAGE_AS_AMENDED, bill, "2025-07-01", today=date(2026, 9, 1)).status == B.TEXT_AMBIGUOUS


def test_floor_amendments_before_a_failed_vote_make_pre_vote_text_ambiguous():
    acts = [Action(date="2025-09-18", text="Amendment SA 100 agreed to in Senate by Voice Vote.", source="Senate", recorded_votes=())]
    bill = _bill(versions=[tv("pcs", "2025-09-10")], actions=acts)
    assert B.select_text(B.PASSAGE, bill, "2025-09-19", today=date(2026, 9, 1)).status == B.TEXT_AMBIGUOUS


def test_two_engrossments_at_the_vote_fail_closed():
    bill = _bill(versions=[tv("es", "2026-06-05"), tv("cps", "2026-06-05")])
    assert B.select_text(B.PASSAGE_AS_AMENDED, bill, "2026-06-05", today=date(2026, 9, 1)).status == B.TEXT_AMBIGUOUS


def test_unsupported_kinds_need_no_text_and_missing_bill_is_pending():
    assert B.select_text(B.CLOTURE, None, "2026-06-05").status == B.TEXT_NOT_REQUIRED
    assert B.select_text(B.PASSAGE, None, "2026-06-05").status == B.TEXT_PENDING


def test_version_code_and_stage_attribute():
    assert version_code("https://www.govinfo.gov/content/pkg/BILLS-119s2es/xml/BILLS-119s2es.xml") == "es"
    assert version_code("https://www.govinfo.gov/content/pkg/BILLS-119hjres88rds/xml/BILLS-119hjres88rds.xml") == "rds"
    assert B.stage_matches("es", b'<?xml version="1.0"?><bill bill-stage="Engrossed-in-Senate">') is True
    assert B.stage_matches("eh", b'<bill bill-stage="Engrossed-in-Senate">') is False
    assert B.stage_matches("es", b"<bill>") is None
    assert normalise_measure("S.J.Res.", "18") == "SJRES18" and normalise_measure("H.R.", "6500") == "HR6500"


# ---- the real bindings, when present ----

@pytest.fixture(scope="module")
def bindings():
    if not BDIR.exists():
        pytest.skip("no bindings generated")
    return [json.loads(p.read_text()) for p in sorted(BDIR.glob("vote_*.json"))]


def test_bindings_cover_only_supported_kinds_and_carry_no_generated_text(bindings):
    for b in bindings:
        assert b["schema"] == "civicalign.binding/1.0"
        assert b["classification"]["kind"] in B.SUPPORTED_KINDS | {B.OTHER}
        for k in ("decision", "if_succeeds", "if_fails", "summary"):
            assert k not in b
        if b["classification"]["summary_eligible"]:
            assert b["verification"]["status"] == "VERIFIED" and b["text_binding"]["status"] == "TEXT_BOUND"
            assert b["text_binding"]["sha256"] and b["text_binding"]["version_code"] not in B.NEVER
        assert b["vote"]["senate_url"].startswith("https://www.senate.gov/legislative/LIS/roll_call_votes/")
        if b["cra"]["is_cra"]:
            assert b["cra"]["agency"] and b["cra"]["rule_title"] and b["cra"]["underlying_rule_source"] is None
        assert b["receipt"]["sources"] and all(s["url"].startswith("https://") for s in b["receipt"]["sources"])
        assert isinstance(b["history"], list)


def test_index_matches_files(bindings):
    idx = json.loads((BDIR / "index.json").read_text())
    assert len(idx["bound"]) == len(bindings)
    assert idx["rule"]["supported_kinds"] == sorted(B.SUPPORTED_KINDS)
    assert sum(idx["classified"].values()) >= 800


def test_supervisor_reproduces_the_bindings(bindings):
    from civicalign.agents.supervisor import checks
    from civicalign.pipeline import run
    results = checks(run(DEFAULT), DEFAULT, ROOT / "demo" / "senator-check.html")
    c = next(x for x in results if x.name.startswith("Pillar 1 bindings"))
    assert c.ok, c.detail


def test_rerun_is_a_no_op_offline(bindings):
    from civicalign.explain.bind import run as bind_run
    summary = bind_run(DEFAULT, offline=True, verbose=False)
    assert summary["writes"] == {"unchanged": len(bindings)}
