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
from civicalign.explain import context as C, relevance as R
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


def test_references_are_structured_with_scope_pinpoint_and_relationship():
    refs = C.extract_references(XML)
    by = {(r["cite"], r["text"]): r for r in refs}
    nea = by[("usc/50/1622", "50 U.S.C. 1622")]
    assert nea["scope"] == "section" and nea["relationship"] == R.CROSS_REFERENCE_REQUIRED
    amended = by[("usc/8/1226", "8 U.S.C. 1226(c)(1)")]
    assert amended["scope"] == "node" and amended["pinpoint"] == ["c", "1"] and amended["relationship"] == R.REPLACED_TEXT
    pl = {r["cite"]: r for r in refs if r["legal_doc"] == "public-law"}
    assert pl["pl/119/21"]["pl_section"] == "100051" and pl["pl/119/21"]["scope"] == "section"
    assert pl["pl/118/47"]["pl_division"] == "division F" and pl["pl/118/47"]["relationship"] == R.CROSS_REFERENCE_ONLY


def test_selection_takes_the_cited_node_and_caps():
    refs = C.extract_references(XML)
    sel = C.select_sections(refs, is_cra=False)
    assert sel["required"] == ["/us/usc/t50/s1622", "/us/usc/t8/s1226/c/1"] and sel["amended"] == ["/us/usc/t8/s1226/c/1"] and sel["status"] == "ok"
    many = [{"legal_doc": "usc", "cite": f"usc/42/{n}", "text": f"42 U.S.C. {n}", "scope": "section", "pinpoint": [], "relationship": R.AMENDED_TARGET,
             "basis": "x", "pl_section": None, "pl_division": None} for n in range(1, 20)]
    sel = C.select_sections(many, is_cra=False)
    assert sel["status"] == "exceeds_cap" and sel["required"] == []
    cra = C.select_sections(refs, is_cra=True)
    assert cra["required"] == [] and "/us/usc/t50/s1622" in cra["tracked_only"]


DEF_XML = b'''<?xml version="1.0"?><bill><legis-body>
<section><enum>103.</enum><header>Border security</header><subsection><enum>(a)</enum><text>There is appropriated $1 for the following:</text>
<paragraph><enum>(4)</enum><text>Necessary expenses relating to the biometric entry and exit system under section 7208 of the Intelligence Reform and Terrorism Prevention Act of 2004 (<external-xref legal-doc="usc" parsable-cite="usc/8/1365b">8 U.S.C. 1365b</external-xref>).</text></paragraph></subsection></section>
<section><enum>202.</enum><header>Enforcement</header><paragraph><enum>(9)</enum><header>Arrests</header>
<subparagraph><enum>(D)</enum><header>Covered unlawful alien defined</header><text>In this paragraph, the term <term>covered unlawful alien</term> means an adult alien who&#8212;</text>
<clause><enum>(ii)</enum><text>is inadmissible under section 212(a)(2) of such Act (<external-xref legal-doc="usc" parsable-cite="usc/8/1182">8 U.S.C. 1182(a)(2)</external-xref>);</text></clause>
<clause><enum>(iv)</enum><text>is the subject of a detainer issued pursuant to section 236, 241(a), or 287 of such Act (<external-xref legal-doc="usc" parsable-cite="usc/8/1226">8 U.S.C. 1226</external-xref>, 1231(a), or 1357); or</text></clause>
<clause><enum>(v)</enum><text>has been charged with an offense described in section 275 or 276 of such Act (8 U.S.C. 1325 or 1326).</text></clause></subparagraph></paragraph></section>
<section><enum>3.</enum><text>That the national emergency declared pursuant to the National Emergencies Act (<external-xref legal-doc="usc" parsable-cite="usc/50/1601">50 U.S.C. 1601 et seq.</external-xref>) is terminated, as defined in section 3 of the Act (<external-xref legal-doc="usc" parsable-cite="usc/5/551">5 U.S.C. 551(13)</external-xref>).</text></section>
</legis-body></bill>'''


def test_relevance_classes_come_from_location_in_the_voted_xml():
    a = R.analyse(DEF_XML)
    by = {r["text"]: r for r in a["references"]}
    assert by["8 U.S.C. 1365b"]["relationship"] == R.CROSS_REFERENCE_ONLY, "names a system by its statutory home"
    assert by["8 U.S.C. 1182(a)(2)"]["relationship"] == R.DEFINITION_REQUIRED and by["8 U.S.C. 1182(a)(2)"]["pinpoint"] == ["a", "2"]
    assert by["8 U.S.C. 1226"]["relationship"] == R.DEFINITION_REQUIRED
    assert by["50 U.S.C. 1601 et seq."]["scope"] == "act_as_a_whole" and by["50 U.S.C. 1601 et seq."]["relationship"] == R.CROSS_REFERENCE_ONLY
    assert by["5 U.S.C. 551(13)"]["relationship"] == R.DEFINITION_REQUIRED, "imports a definition"
    gaps = {g["kind"]: g for g in a["gaps"]}
    assert gaps["citation_list_continues_untagged"]["text"] == "8 U.S.C. 1226, 1231(a), or 1357"
    assert gaps["untagged_citation"]["text"] == "8 U.S.C. 1325 or 1326"
    assert all(g["relationship"] == R.DEFINITION_REQUIRED and g["resolved"] for g in a["gaps"])
    sel = C.select_sections(a["references"], False, a["gaps"])
    assert sel["status"] == "ok" and "/us/usc/t8/s1365b" in sel["tracked_only"]
    assert "/us/usc/t8/s1182/a/2" in sel["required"] and "/us/usc/t8/s1182" not in sel["required"]
    assert {"/us/usc/t8/s1231/a", "/us/usc/t8/s1325", "/us/usc/t8/s1326", "/us/usc/t8/s1357"} <= set(sel["required"])
    assert "/us/usc/t50/s1601" in sel["tracked_only"]
    # an unresolvable group in the same place keeps the context pending
    bad = DEF_XML.replace(b"(8 U.S.C. 1325 or 1326)", b"(8 U.S.C. 1325\xe2\x80\x931330)")
    b2 = R.analyse(bad)
    assert C.select_sections(b2["references"], False, b2["gaps"])["status"] == "unresolved_citations"


def _parse(text):
    """Fallback citations from one untagged clause inside a definition."""
    xml = ('<bill><legis-body><section><enum>1.</enum><header>Terms defined</header><text>' + text + '</text></section></legis-body></bill>').encode()
    a = R.analyse(xml)
    return [(r["text"], r["rule"][:2]) for r in a["references"] if r["source"] == "fallback_explicit_usc"], a


def test_fallback_grammar_recognises_only_the_demonstrated_forms():
    assert _parse("an offense described in section 275 or 276 of such Act (8 U.S.C. 1325 or 1326).")[0] == [("8 U.S.C. 1325", "R1"), ("8 U.S.C. 1326", "R1")]
    assert _parse("under such Act (42 U.S.C. 1484, 1485, and 1486(a)(2)).")[0] == [("42 U.S.C. 1484", "R1"), ("42 U.S.C. 1485", "R1"), ("42 U.S.C. 1486(a)(2)", "R1")]
    assert _parse("section 7 (15 U.S.C. 78m(a), 78o(d)).")[0] == [("15 U.S.C. 78m(a)", "R1"), ("15 U.S.C. 78o(d)", "R1")]
    for vague in ("that section", "this chapter", "applicable law", "section 275 of such Act", "such Act (8 U.S.C. 1101 et seq.)",
                  "(5 U.S.C. 551\u2013558)", "(42 U.S.C. 247d\u20137e(e)(1)(D))", "(50 U.S.C. App. 2401)", "(8 U.S.C. 1325; 18 U.S.C. 1)",
                  "(8 U.S.C. 1101 note)", "(24 U.S.C. ch. 5)", "8 U.S.C. 1325 or 1326 without a parenthesis", "(8 U.S.C. 1325 or section 3)"):
        found, a = _parse(vague)
        assert found == [], vague
        assert all(not g["resolved"] for g in a["gaps"]), vague


def test_fallback_inherits_the_title_of_a_tagged_citation_and_keeps_provenance():
    xml = ('<bill><legis-body><section id="s9"><enum>9.</enum><header>Terms defined</header><text>a detainer issued pursuant to section 236, 241(a), '
           'or 287 of such Act (<external-xref legal-doc="usc" parsable-cite="usc/8/1226">8 U.S.C. 1226</external-xref>, 1231(a), or 1357); or</text>'
           '</section></legis-body></bill>').encode()
    a = R.analyse(xml)
    fb = [r for r in a["references"] if r["source"] == "fallback_explicit_usc"]
    assert [(r["cite"], r["pinpoint"], r["scope"]) for r in fb] == [("usc/8/1231", ["a"], "node"), ("usc/8/1357", [], "section")]
    r = fb[0]
    assert r["rule"].startswith("R2") and r["source_fragment"] == "(8 U.S.C. 1226, 1231(a), or 1357)"
    assert r["source_sha256"] == hashlib.sha256(xml).hexdigest() and r["container"]["id"] == "s9" and r["text_part"] == "tail of external-xref"
    assert (r["char_start"], r["char_end"]) == (0, len(", 1231(a), or 1357)"))
    assert [x["source"] for x in a["references"]] == ["structured_xref", "fallback_explicit_usc", "fallback_explicit_usc"]
    g = a["gaps"][0]
    assert g["provisions"] == ["8 U.S.C. 1226", "8 U.S.C. 1231(a)", "8 U.S.C. 1357"] and g["untagged_provisions"] == ["8 U.S.C. 1231(a)", "8 U.S.C. 1357"]
    # a tagged citation not opening the parenthetical is not continued
    assert not R.analyse(xml.replace(b"of such Act (<external", b"of such Act <external"))["gaps"][0]["resolved"]


def test_governing_phrase_strips_only_the_designation():
    assert R.governing_phrase("That, pursuant to section 202 of the National Emergencies Act (") == "That, pursuant to"
    assert R.governing_phrase("implementing agreements under section 287(g) of the Immigration and Nationality Act (").endswith("agreements under")
    assert R.parse_display("8 U.S.C. 1226, 1231(a), or 1357", "usc/8/1226")["scope"] == "unparsed"
    assert R.parse_display("Section 1(j)(3)", "usc/43/1")["pinpoint"] == ["j", "3"]
    assert R.parse_display("2 U.S.C. 682 et seq.", "usc/2/682")["scope"] == "act_as_a_whole"


def test_node_and_lead_in_are_cut_byte_exact():
    sec = (b'<section identifier="/us/usc/t8/s1182"><num>1182</num><heading>Inadmissible aliens</heading>'
           b'<subsection identifier="/us/usc/t8/s1182/a"><num>(a)</num><heading>Classes</heading><chapeau>aliens who are:</chapeau>'
           b'<paragraph identifier="/us/usc/t8/s1182/a/1"><num>(1)</num><content>health</content></paragraph>'
           b'<paragraph identifier="/us/usc/t8/s1182/a/2"><num>(2)</num><heading>Criminal</heading><subparagraph identifier="/us/usc/t8/s1182/a/2/A"><content>x</content></subparagraph></paragraph>'
           b'</subsection><notes><note>long history</note></notes></section>')
    node, tag = uscode.extract_node(sec, "/us/usc/t8/s1182/a/2")
    assert tag == "paragraph" and node.startswith(b'<paragraph identifier="/us/usc/t8/s1182/a/2">') and node.endswith(b"</paragraph>") and b"health" not in node
    assert uscode.lead_in(uscode.extract_node(sec, "/us/usc/t8/s1182/a")[0]).endswith(b"<chapeau>aliens who are:</chapeau>")
    assert uscode.lead_in(sec).endswith(b"<heading>Inadmissible aliens</heading>")
    assert uscode.extract_node(sec, "/us/usc/t8/s1182/b") is None


class _FakeCode(C.Code):
    def __init__(self, section_bytes):
        self._sec = section_bytes

    def section(self, cite_title, section, vote_date, relationship):
        frag = self._sec
        return {"type": "us_code", "identifier": f"/us/usc/t{cite_title}/s{section}", "title": cite_title, "section": section,
                "as_of": {"release_point": "119-1", "date": "2025-01-29", "rule": "r"}, "archive_sha256": "a", "fragment_sha256": hashlib.sha256(frag).hexdigest(),
                "bytes": len(frag), "heading": "h", "relationship": relationship, "status": "fetched", "_bytes": frag, "_content": frag.decode()}


def test_oversized_whole_sections_are_never_injected():
    big = b'<section identifier="/us/usc/t21/s802"><num>802</num>' + b"x" * (C.FULL_SECTION_MAX_CHARS + 10) + b"</section>"
    rec = _FakeCode(big).provision("/us/usc/t21/s802", "21", "802", "2025-03-14", [R.AMENDED_TARGET], ["b"], include=True)
    assert rec["status"] == "fragment_selection_required" and "_content" not in rec and rec["inclusion"] == R.REFERENCE_TRACKED
    small = b'<section identifier="/us/usc/t21/s803"><num>803</num>short</section>'
    ok = _FakeCode(small).provision("/us/usc/t21/s803", "21", "803", "2025-03-14", [R.AMENDED_TARGET], ["b"], include=True)
    assert ok["status"] == "fetched" and ok["_content"] == small.decode() and ok["inclusion"] == R.CONTENT_INCLUDED
    tracked = _FakeCode(big).provision("/us/usc/t21/s802", "21", "802", "2025-03-14", [R.CROSS_REFERENCE_ONLY], ["b"], include=False)
    assert tracked["status"] == "fetched" and "_content" not in tracked and tracked["fragment_sha256"], "tracked: hash kept, no content"
    missing_node = _FakeCode(small).provision("/us/usc/t21/s803/q", "21", "803", "2025-03-14", [R.DEFINITION_REQUIRED], ["b"], include=True)
    assert missing_node["status"] == "node_not_found" and "_content" not in missing_node


def test_packet_metrics_and_budget():
    law = [{"content": "a" * 100, "hierarchy": [{"content": "b" * 10}]}]
    m = C.packet_metrics("t" * 50, law, {"statutory_consequence_source": {"content": "c" * 5}}, {"content": "s" * 7}, [{}], [{}, {}])
    assert m == {"voted_text_chars": 50, "context_chars": 115, "official_summary_chars": 7, "total_source_chars": 172, "source_count": 4,
                 "included_context_fragment_count": 2, "hierarchy_fragment_count": 1, "tracked_reference_count": 3}
    assert C.budget_for(m)["status"] == "WITHIN_BUDGET"
    assert C.budget_for(dict(m, total_source_chars=C.PACKET_REVIEW_CHARS + 1))["status"] == "REVIEW_REQUIRED"


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
            assert rec["inclusion"] == R.CONTENT_INCLUDED and set(rec["relationships"]) & R.REQUIRED
            for h in rec["hierarchy"]:
                assert hashlib.sha256(h["content"].encode()).hexdigest() == h["sha256"]
            if rec["scope"] == "section":
                assert len(rec["content"]) <= C.FULL_SECTION_MAX_CHARS
        for t in pk["tracked_references"]:
            assert "content" not in t and t["content_included"] is False and t["inclusion"] == R.REFERENCE_TRACKED
        assert pk["metrics"] == C.packet_metrics(pk["voted_text"]["content"], pk["existing_law_context"], pk["cra_context"], pk["official_summary"],
                                                 pk["tracked_references"], pk["cited_public_laws_not_included"])
        assert pk["budget"]["status"] == ("REVIEW_REQUIRED" if pk["metrics"]["total_source_chars"] > C.PACKET_REVIEW_CHARS else "WITHIN_BUDGET")
        assert pk["receipt_scaffold"] == b["receipt"] and pk["receipt_scaffold"]["next_step"]["case"] != "UNDETERMINED"
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
    """All ten first-cohort cases are source-complete. S.2 became complete only
    when its four untagged provisions (two citation groups naming five provisions,
    one of them tagged) were recovered by the narrow fallback grammar and bound to
    the Code in force at the vote. Its packet exceeds the review threshold, so a
    person must confirm its size before any Maker reads it."""
    by = {c["vote"]["measure"]: c for c in records.values()}
    cohort = ["SJRES10", "SJRES37", "SJRES49", "SJRES71", "SJRES81", "SJRES77", "SJRES88", "HJRES142", "S2", "HR4"]
    for m in cohort:
        assert by[m]["generation"]["status"] == "READY_FOR_GENERATION", (m, by[m]["completeness"])
        assert by[m]["budget"]["status"] == ("REVIEW_REQUIRED" if m == "S2" else "WITHIN_BUDGET"), m
    s2 = by["S2"]
    groups = s2["citation_gaps"]
    assert len(groups) == 2 and all(g["resolved"] for g in groups)
    assert sum(len(g["provisions"]) for g in groups) == 5 and sum(len(g["untagged_provisions"]) for g in groups) == 4
    assert sorted(p for g in groups for p in g["untagged_provisions"]) == ["8 U.S.C. 1231(a)", "8 U.S.C. 1325", "8 U.S.C. 1326", "8 U.S.C. 1357"]
    law = {e["identifier"]: e for e in s2["existing_law_context"]}
    assert "/us/usc/t8/s1182" not in law and law["/us/usc/t8/s1182/a/2"]["relationships"] == [R.DEFINITION_REQUIRED]
    for ident in ("/us/usc/t8/s1231/a", "/us/usc/t8/s1325", "/us/usc/t8/s1326", "/us/usc/t8/s1357"):
        e = law[ident]
        assert e["status"] == "fetched" and e["inclusion"] == R.CONTENT_INCLUDED and e["as_of"]["release_point"] == "119-95", ident
        assert any(x["source"] == "fallback_explicit_usc" for x in e["cited_as"]), ident
    assert law["/us/usc/t8/s1231/a"]["scope"] == "node" and law["/us/usc/t8/s1231/a"]["bytes"] < law["/us/usc/t8/s1231/a"]["section_bytes"]
    assert law["/us/usc/t8/s1365b"]["inclusion"] == R.REFERENCE_TRACKED
    assert all(len(json.dumps(e)) < 10 ** 6 for e in s2["existing_law_context"])
    pk = json.loads((PDIR / "vote_119_2_00163.packet.json").read_text())
    assert pk["metrics"]["total_source_chars"] > C.PACKET_REVIEW_CHARS and pk["budget"]["status"] == "REVIEW_REQUIRED"
    assert all(len(e["content"]) <= C.FULL_SECTION_MAX_CHARS for e in pk["existing_law_context"] if e["scope"] == "section")
    # "et seq." citations are tracked, not injected (50 U.S.C. 1601 is not the termination rule)
    for m in ("SJRES10", "SJRES71"):
        assert [(e["identifier"], e["inclusion"]) for e in by[m]["existing_law_context"]] == [("/us/usc/t50/s1601", R.REFERENCE_TRACKED)]
    for m in ("SJRES37", "SJRES49", "SJRES77", "SJRES81", "SJRES88"):
        assert [(e["identifier"], e["relationships"], e["inclusion"]) for e in by[m]["existing_law_context"]] == \
            [("/us/usc/t50/s1622", [R.CROSS_REFERENCE_REQUIRED], R.CONTENT_INCLUDED)]
    assert [(e["identifier"], e["inclusion"]) for e in by["HR4"]["existing_law_context"]] == [("/us/usc/t2/s682", R.REFERENCE_TRACKED)]


def test_supervisor_reproduces_context(records):
    from civicalign.agents.supervisor import checks
    from civicalign.pipeline import run
    results = checks(run(DEFAULT), DEFAULT, ROOT / "demo" / "senator-check.html")
    c = next(x for x in results if x.name.startswith("Pillar 1 context"))
    assert c.ok, c.detail


def _scratch_records(tmp_path):
    import dataclasses
    import shutil
    from civicalign.config import Config
    dst = tmp_path / "119"
    shutil.copytree(BDIR, dst)

    class Scratch(Config):
        @property
        def bindings_dir(self):
            return dst
    return Scratch(**{f.name: getattr(DEFAULT, f.name) for f in dataclasses.fields(DEFAULT)}), dst


def _rewrite(path, fn):
    doc = json.loads(path.read_text()); fn(doc); path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def test_stage_2_5_records_belong_to_the_current_snapshot(records):
    r = C.freshness(DEFAULT)
    assert r["checked"] == len(records) and not r["stale"] and not r["no_context_yet"], r


def test_freshness_gate_fails_on_records_from_another_snapshot(tmp_path):
    cfg, d = _scratch_records(tmp_path)
    assert not C.freshness(cfg)["stale"]
    # a binding re-derived with a different text than its context was built from
    _rewrite(d / "vote_119_2_00163.json", lambda b: b["text_binding"].update(sha256="0" * 64))
    # a CRS summary that no longer matches this snapshot's bill status
    _rewrite(d / "context" / "vote_119_1_00095.context.json", lambda c: c["official_summary"].update(version_code="99"))
    # a packet whose receipt came from an older binding
    _rewrite(d / "packets" / "vote_119_1_00160.packet.json", lambda p: p["receipt_scaffold"]["vote_result"].update(statement="old"))
    stale = " ".join(C.freshness(cfg)["stale"])
    assert "vote_119_2_00163.context.json: built from binding" in stale
    assert "vote_119_1_00095.context.json: CRS summary" in stale
    assert "vote_119_1_00160.packet.json: receipt differs" in stale


def test_a_new_vote_without_context_is_reported_not_mixed(tmp_path):
    cfg, d = _scratch_records(tmp_path)
    (d / "context" / "vote_119_1_00095.context.json").unlink()
    r = C.freshness(cfg)
    assert r["no_context_yet"] == ["vote_119_1_00095.json"]
    assert any("packet with no context record" in s for s in r["stale"]), "a packet may never outlive its context"
