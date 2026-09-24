"""Pillar 1, Stage 2.5: reference extraction, the section-selection policy,
release-point selection, section extraction and hashing, CRS relationship,
CRA rule binding and modes, GAO determinations, completeness and generation
states, and packet integrity. No generated prose anywhere."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.explain import context as C
from civicalign.sources import federal_register as fr, publaw, uscode

ROOT = Path(__file__).resolve().parents[1]
BDIR = ROOT / "data" / "explanations" / "119"
CDIR = BDIR / "context"
PDIR = BDIR / "packets"
RAW = ROOT / "data" / "raw" / "explanations"

XML = b'''<?xml version="1.0"?><bill bill-stage="Engrossed-in-Senate"><legis-body>
<section id="s1"><enum>1.</enum><header>Findings</header><text>Under section 202(a) of the National Emergencies Act (<external-xref legal-doc="usc" parsable-cite="usc/50/1622">50 U.S.C. 1622</external-xref>) the emergency is terminated.</text></section>
<section id="s2"><enum>2.</enum><header>Amendment</header><subsection><enum>(a)</enum><text>Section 236(c)(1) of the Immigration and Nationality Act (<external-xref legal-doc="usc" parsable-cite="usc/8/1226">8 U.S.C. 1226(c)(1)</external-xref>) is amended by striking "or" at the end.</text></subsection>
<subsection><enum>(b)</enum><text>There is appropriated $1,000, for the purposes provided in paragraph (3) of section 100051 of <external-xref legal-doc="public-law" parsable-cite="pl/119/21">Public Law 119\xe2\x80\x9321</external-xref>, and amounts under division F of <external-xref legal-doc="public-law" parsable-cite="pl/118/47">Public Law 118\xe2\x80\x9347</external-xref> are rescinded.</text></subsection></section>
</legis-body></bill>'''


def test_references_are_structured_and_amendatory_status_is_local():
    refs = C.extract_references(XML)
    cites = [(r["legal_doc"], r["cite"], r["amendatory"]) for r in refs]
    assert ("usc", "usc/50/1622", False) in cites and ("usc", "usc/8/1226", True) in cites
    pl = {r["cite"]: r for r in refs if r["legal_doc"] == "public-law"}
    assert pl["pl/119/21"]["pl_section"] == "100051" and pl["pl/118/47"]["pl_division"] == "division F"


def test_selection_policy_prefers_amended_sections_and_caps():
    refs = C.extract_references(XML)
    sel = C.select_sections(refs, is_cra=False)
    assert sel["required"] == ["/us/usc/t8/s1226"] and sel["amended"] == ["/us/usc/t8/s1226"] and sel["status"] == "ok"
    many = [{"legal_doc": "usc", "cite": f"usc/42/{n}", "text": "", "amendatory": True, "pl_section": None, "pl_division": None} for n in range(1, 20)]
    sel = C.select_sections(many, is_cra=False)
    assert sel["status"] == "exceeds_cap" and sel["required"] == []
    assert C.select_sections(refs, is_cra=True)["required"] == []


def test_release_point_in_force_never_after_the_vote():
    pts = uscode.parse_release_points("Public Law 118-274 (01/06/2025) Public Law 119-1 (01/29/2025) Public Law 119-4 (03/15/2025)")
    assert [p.label for p in pts] == ["118-274", "119-1", "119-4"]
    assert uscode.in_force(pts, "2025-01-20").label == "118-274"
    assert uscode.in_force(pts, "2025-01-29").label == "119-1"
    assert uscode.in_force(pts, "2025-03-14").label == "119-1"
    assert uscode.in_force(pts, "2024-12-01") is None
    assert uscode.archive_name("8", pts[1]) == "xml_usc08@119-1.zip" and uscode.title_code("5a") == "05a"


def test_in_force_rule_uses_published_archives_and_the_classification_table():
    pts = uscode.parse_release_points("Public Law 119-18 (06/12/2025) Public Law 119-23 (07/07/2025) Public Law 119-26 (07/16/2025)")
    published = {"119-18": {"xml_usc02@119-18.zip", "xml_usc21@119-18.zip"}, "119-23": set(), "119-26": set()}
    table = "21    801          nt new           119-26   1\n43    1601         nt new           119-23   1\n21    822                          119-26   3(b)-(f)\n"
    cl = uscode.parse_classification(table)
    assert cl == {"119-26": {("21", "801"), ("21", "822")}, "119-23": {("43", "1601")}}
    ok = uscode.in_force_for_section(pts, published, cl, "2025-07-17", "2", "682")
    assert ok["status"] == "ok" and ok["release_point"].label == "119-18" and ok["intervening"] == ["119-23", "119-26"] and ok["affected_by"] == []
    amb = uscode.in_force_for_section(pts, published, cl, "2025-07-17", "21", "801")
    assert amb["status"] == "ambiguous" and amb["affected_by"] == ["119-26"]
    unknown = uscode.in_force_for_section(pts, published, {}, "2025-07-17", "2", "682")
    assert unknown["status"] == "ambiguous" and "not in classification table" in unknown["affected_by"][0]
    assert uscode.in_force_for_section(pts, {"119-18": set()}, cl, "2025-07-17", "2", "682")["status"] == "no_published_archive"
    assert uscode.in_force_for_section(pts, published, cl, "2025-06-12", "2", "682")["intervening"] == []
    assert uscode.archives_listed('href="xml_usc02@119-18.zip" x xml_usc21@119-18.zip', pts[0]) == {"xml_usc02@119-18.zip", "xml_usc21@119-18.zip"}


def test_section_extraction_is_balanced_and_byte_exact():
    title = b'<usc><section identifier="/us/usc/t8/s1225"><num>1225</num></section><section identifier="/us/usc/t8/s1226"><heading>Apprehension</heading><subsection identifier="/us/usc/t8/s1226/a"><section identifier="/us/usc/t8/s1226/nested"/></subsection></section><section identifier="/us/usc/t8/s1227"/></usc>'
    frag = uscode.extract_section(title, "/us/usc/t8/s1226")
    assert frag.startswith(b'<section identifier="/us/usc/t8/s1226">') and frag.endswith(b"</section>") and b"s1227" not in frag
    assert uscode.section_heading(frag) == "Apprehension"
    assert uscode.extract_section(title, "/us/usc/t8/s9999") is None
    dashed = '<usc><section identifier="/us/usc/t15/s80a\u20131"><heading>x</heading></section></usc>'.encode("utf8")
    assert uscode.extract_section(dashed, "/us/usc/t15/s80a-1") is not None, "hyphen citation finds the en-dash identifier"
    assert uscode.parse_classification("15    80a\u20131          119-26   1\n") == {"119-26": {("15", "80a-1")}}
    law = b'<pLaw><section identifier="/us/pl/119/21/tI/s100051"><num value="100051"/>x</section><section identifier="/us/pl/119/21/s100052"/></pLaw>'
    assert publaw.extract_section(law, "100051").endswith(b"x</section>") and publaw.extract_section(law, "1") is None


def test_summary_relationship_rules():
    s = [{"version_code": "00", "action_desc": "Introduced in Senate", "action_date": "2025-01-01", "text": "a", "sha256": "x"},
         {"version_code": "55", "action_desc": "Passed Senate", "action_date": "2025-03-01", "text": "b", "sha256": "y"}]
    assert C.summary_relationship(s, "2025-03-01", "es")["version_relationship"] == "MATCHED"
    assert C.summary_relationship(s[:1], "2025-03-01", "es")["version_relationship"] == "PRE_AMENDMENT"
    assert C.summary_relationship(s[:1], "2025-03-01", "pcs")["version_relationship"] == "EARLIER_SAME_TEXT"
    assert C.summary_relationship([], "2025-03-01", "pcs")["version_relationship"] == "UNKNOWN"
    assert not C.summary_relationship(s[:1], "2025-03-01", "es")["usable"]


def test_federal_register_citation_parsing_and_matching():
    assert fr.citation_in("relating to X (89 Fed. Reg. 71160 (September 3, 2024))") == (89, 71160, "2024-09-03")
    assert fr.citation_in("(90 Fed. Reg. 7464; published January 21, 2025)") == (90, 7464, "2025-01-21")
    assert fr.citation_in("(90 Fed. Reg. 2621), and such rule") == (90, 2621, None)
    assert fr.citation_in("no citation here") is None and fr.volume_year(90) == 2025
    docs = [fr.FrDocument("a", "89 FR 71160", "Protection of Marine Archaeological Resources", "Rule", "2024-09-03", ("BOEM",), "u", None, 71160),
            fr.FrDocument("b", "89 FR 71157", "Other", "Rule", "2024-09-03", ("FDA",), "u", None, 71157)]
    assert [d.document_number for d in fr.match_citation(docs, 89, 71160)] == ["a"]
    assert fr.title_agrees("Protection of Marine Archaeological Resources", docs[0].title)
    assert "per_page=1000" in fr.query_url(fr.day_params("2024-12-30"))


def test_gao_determination_is_identified_not_retrieved():
    t = ("That Congress disapproves the rule submitted by the Bureau of Land Management relating to X (issued November 20, 2024, as a record of decision, "
         "and a letter of opinion from the Government Accountability Office dated June 25, 2025, printed in the Congressional Record on June 26, 2025, "
         "on pages S3552–S3554, concluding that such record of decision is a rule under the Congressional Review Act), and such rule shall have no force or effect.")
    g = C.gao_determination(t)
    assert g["type"] == "GAO_RULE_DETERMINATION" and g["opinion_date"] == "2025-06-25" and g["congressional_record_pages"] == "S3552-S3554"
    assert g["status"] == "identified_not_retrieved" and g["source_url"] is None
    assert C.gao_determination("nothing") is None


# ---- the real records, when present ----

@pytest.fixture(scope="module")
def records():
    if not CDIR.exists():
        pytest.skip("no context records")
    return {p.name: json.loads(p.read_text()) for p in sorted(CDIR.glob("vote_*.context.json"))}


def _binding(name):
    return json.loads((BDIR / name.replace(".context.json", ".json")).read_text())


def test_records_carry_no_generated_prose_and_follow_the_state_rules(records):
    expect = {"COMPLETE": "READY_FOR_GENERATION", "LIMITED": "READY_WITH_LIMITS", "PENDING": "SOURCE_CONTEXT_PENDING", "AMBIGUOUS": "SOURCE_CONTEXT_AMBIGUOUS"}
    for name, c in records.items():
        for k in ("decision", "if_succeeds", "if_fails", "summary", "explanation"):
            assert k not in c
        b = _binding(name)
        if b["verification"]["status"] == "VERIFIED" and b["text_binding"]["status"] == "TEXT_BOUND":
            assert c["generation"]["status"] == expect[c["completeness"]["status"]], name
        if c["completeness"]["status"] in ("COMPLETE", "LIMITED"):
            assert not c["completeness"]["missing"], name
        if b["cra"]["is_cra"]:
            assert c["cra"]["mode"] in ("resolution_only", "rule_bound") and c["completeness"]["status"] != "COMPLETE", name
        else:
            assert c["cra"]["mode"] == "not_cra"
        if c.get("release_point"):
            assert c["release_point"]["date"] <= c["vote"]["date"], name
        for rec in c["existing_law_context"]:
            if rec["status"] == "fetched":
                assert rec["as_of"]["date"] <= c["vote"]["date"] and rec["fragment_sha256"], name
                assert rec["in_force_check"]["status"] == "ok", name
            if rec["status"] == "in_force_ambiguous":
                assert c["generation"]["status"] == "SOURCE_CONTEXT_AMBIGUOUS", name


def test_s5_remains_ambiguous(records):
    s5 = [c for c in records.values() if c["vote"]["measure"] == "S5"]
    if not s5:
        pytest.skip("S.5 not built yet")
    assert s5[0]["generation"]["status"] == "SOURCE_CONTEXT_AMBIGUOUS"
    assert any("not retrievable" in m or "in_force_ambiguous" in m for m in s5[0]["completeness"]["missing"])


def test_packets_contain_only_hashed_artefacts(records):
    packets = sorted(PDIR.glob("vote_*.packet.json")) if PDIR.exists() else []
    ready = {n for n, c in records.items() if c["generation"]["status"] in ("READY_FOR_GENERATION", "READY_WITH_LIMITS")}
    assert {p.name.replace(".packet.json", ".context.json") for p in packets} == ready
    for p in packets:
        pk = json.loads(p.read_text()); b = _binding(p.name.replace(".packet.json", ".json"))
        assert hashlib.sha256(pk["voted_text"]["content"].encode()).hexdigest() == b["text_binding"]["sha256"]
        for rec in pk["existing_law_context"]:
            assert hashlib.sha256(rec["content"].encode()).hexdigest() == rec["sha256"] and rec["as_of"]
        for law in pk["cited_public_laws_not_included"]:
            assert "content" not in law and law["sha256"]
        summ = pk["official_summary"]
        if summ.get("content"):
            assert summ["version_relationship"] in ("MATCHED", "EARLIER_SAME_TEXT") and hashlib.sha256(summ["content"].encode()).hexdigest() == summ["sha256"]
        cra = pk["cra_context"]
        if cra["mode"] != "not_cra":
            assert cra["statutory_consequence_source"]["identifier"] == "/us/usc/t5/s801"
            assert hashlib.sha256(cra["statutory_consequence_source"]["content"].encode()).hexdigest() == cra["statutory_consequence_source"]["sha256"]
            assert cra["underlying_rule"] is None or cra["underlying_rule"]["content_included"] is False
            assert any("Senate passage is not enactment" in l for l in cra["limits"])
        assert "no browsing, no retrieval, no model memory for facts" in pk["maker_rules"]
        assert pk["receipt_scaffold"]["yea_means"] and pk["receipt_scaffold"]["heading_success"]


def test_first_cohort_readiness(records):
    by = {c["vote"]["measure"]: c for c in records.values()}
    cohort = ["SJRES10", "SJRES37", "SJRES49", "SJRES71", "SJRES81", "SJRES77", "SJRES88", "HJRES142", "S2", "HR4"]
    for m in cohort:
        if m in by:
            assert by[m]["generation"]["status"] == "READY_FOR_GENERATION", (m, by[m]["completeness"])
    if "S2" in by:
        assert len([r for r in by["S2"]["existing_law_context"] if r["status"] == "fetched"]) == 7
        assert by["S2"]["public_laws"][0]["fragments"][0]["status"] == "fetched"


def test_supervisor_reproduces_context(records):
    from civicalign.agents.supervisor import checks
    from civicalign.pipeline import run
    results = checks(run(DEFAULT), DEFAULT, ROOT / "demo" / "senator-check.html")
    c = next(x for x in results if x.name.startswith("Pillar 1 context"))
    assert c.ok, c.detail
