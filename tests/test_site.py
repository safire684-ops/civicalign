"""The integrated site: one page built from Engine B's results and the legislative drop.

Pins that the drop is imported byte for byte and refused if changed, that a broken id stops
the build, that the split rule behaves, that the page never invents a comparison or a score,
and that the independent checker catches tampering with each thing it recounts.
"""
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from civicalign import build_pages as BP
from civicalign import build_site as BS
from civicalign import legislative as L
from civicalign.agents import supervisor as S
from civicalign.config import DEFAULT
from civicalign.ideology import bills as BL

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "src" / "civicalign" / "templates" / "site.template.html").read_text()
DROP_FILES = ("meta", "senators", "votes", "positions", "bills", "committee_votes", "nominations")


@pytest.fixture(scope="module")
def built():
    core, derived, engine = BS.assemble(DEFAULT)
    return {"core": core, "derived": derived, "engine": engine, "drop": L.load(DEFAULT), "raw": S.eb_raw(DEFAULT)}


def _fake_drop(tmp_path):
    src = L.latest_dir(DEFAULT)
    dest = tmp_path / "drop"
    dest.mkdir()
    for f in src.iterdir():
        (dest / f.name).write_bytes(f.read_bytes())
    return dest


def failed(results, name):
    return any(c.name.startswith(name) and not c.ok for c in results)


# ---- the import ----
def test_the_drop_is_a_verbatim_copy_with_a_manifest():
    d = L.latest_dir(DEFAULT)
    manifest = json.loads((d / "MANIFEST.json").read_text())
    assert set(manifest["files"]) == set(L.FILES)
    assert all(L.sha_file(d / n) == h for n, h in manifest["files"].items())


def test_a_changed_drop_file_is_refused(tmp_path):
    d = _fake_drop(tmp_path)
    (d / "votes.json").write_text("[]")
    cfg = type("C", (), {"ideology_dir": tmp_path / "ideology", "congress": DEFAULT.congress})()
    home = L.root(cfg)
    home.mkdir(parents=True)
    d.rename(home / "2026-10-29")
    with pytest.raises(L.LegislativeError, match="does not match its manifest"):
        L.load(cfg)
    assert failed(S.site_drop_checks(home / "2026-10-29"), "Site: legislative files match")


def test_an_existing_drop_is_never_overwritten(tmp_path):
    cfg = type("C", (), {"ideology_dir": tmp_path / "ideology", "congress": DEFAULT.congress})()
    d = _fake_drop(tmp_path)
    assert L.import_drop(d, cfg).exists()
    with pytest.raises(L.LegislativeError, match="never overwritten"):
        L.import_drop(d, cfg)


def test_a_drop_for_another_congress_is_refused(tmp_path):
    cfg = type("C", (), {"ideology_dir": tmp_path / "ideology", "congress": 118})()
    with pytest.raises(L.LegislativeError, match="Congress 119"):
        L.import_drop(_fake_drop(tmp_path), cfg)


# ---- the joins ----
def test_the_real_drop_joins(built):
    assert L.problems(built["drop"], set(BL.current_sponsor_scores(DEFAULT))) == []


@pytest.mark.parametrize("break_it, expect", [
    (lambda d: d["positions"]["119-1-4"].__setitem__("X000000", "Yea"), "unknown senator"),
    (lambda d: d["votes"][0].__setitem__("bill", "s999999"), "unknown bill"),
    (lambda d: d["bills"][0]["votes"].append("119-9-9"), "unknown vote"),
    (lambda d: d["nominations"][0]["votes"].append("119-9-9"), "unknown vote"),
    (lambda d: d["votes"][0]["nominations"].append("PN0-0"), "unknown nomination"),
])
def test_a_broken_id_is_named(built, break_it, expect):
    drop = copy.deepcopy({k: built["drop"][k] for k in DROP_FILES})
    break_it(drop)
    bad = L.problems(drop, set(BL.current_sponsor_scores(DEFAULT)))
    assert any(expect in b for b in bad)
    assert failed(S.site_join_checks(drop, set(BL.current_sponsor_scores(DEFAULT))), "Site: every senator, vote, bill")


def test_a_broken_join_stops_the_build(monkeypatch):
    monkeypatch.setattr(L, "problems", lambda *_: ["position by unknown senator X"])
    with pytest.raises(BP.BuildError, match="does not join"):
        BS.assemble(DEFAULT)


def test_a_wrong_count_on_a_vote_is_caught(built):
    drop = copy.deepcopy({k: built["drop"][k] for k in DROP_FILES})
    drop["votes"][0]["counts"]["yea"] += 1
    assert failed(S.site_join_checks(drop, set(BL.current_sponsor_scores(DEFAULT))), "Site: every roll call's counts")
    drop = copy.deepcopy({k: built["drop"][k] for k in DROP_FILES})
    drop["votes"][1]["by_party"]["D"]["Yea"] = 999
    assert failed(S.site_join_checks(drop, set(BL.current_sponsor_scores(DEFAULT))), "Site: every roll call's counts")


# ---- what kind of evidence each vote is ----
def _vote(qt="passage", mt="bill", meaning=True, kind="passed"):
    return {"question_type": qt, "measure_type": mt, "meaning": {"yes_means": "y", "no_means": "n", "outcome_kind": kind} if meaning else None}


@pytest.mark.parametrize("vote, want", [
    (_vote("passage"), "direct"), (_vote("amendment", "amendment"), "direct"), (_vote("motion_to_concur"), "direct"),
    (_vote("cloture"), "procedural"), (_vote("motion_to_proceed"), "procedural"), (_vote("motion_to_waive", "amendment"), "procedural"),
    (_vote("nomination", "nomination"), "nomination"), (_vote("cloture", "nomination"), "nomination"),
    (_vote(meaning=False), "insufficient"), (_vote(kind="unexplained"), "insufficient"), (_vote("nomination", "nomination", meaning=False), "insufficient"),
])
def test_vote_evidence(vote, want):
    assert L.vote_evidence(vote) == want and S.site_evidence(vote) == want


@pytest.mark.parametrize("by_party, want", [
    ({"D": {"Yea": 40, "Nay": 2}, "R": {"Yea": 3, "Nay": 50}}, "opposed"),
    ({"D": {"Yea": 40}, "R": {"Yea": 50}}, "together"),
    ({"D": {"Yea": 20, "Nay": 20}, "R": {"Nay": 50}}, "no_majority"),
    ({"D": {"Not Voting": 2}, "R": {"Yea": 50}}, "no_majority"),
])
def test_party_majorities(by_party, want):
    assert L.party_majorities(by_party) == want and S.site_majorities(by_party) == want


def test_a_tampered_label_or_policy_area_is_caught(built):
    d = copy.deepcopy(built["derived"])
    d["evidence"]["119-1-4"] = "procedural"
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: every evidence")
    d = copy.deepcopy(built["derived"])
    d["parties"]["119-1-4"] = "together" if d["parties"]["119-1-4"] != "together" else "opposed"
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: every evidence")
    d = copy.deepcopy(built["derived"])
    d["policy_area"]["s5"] = "Sports and Recreation"
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: policy areas")
    d = copy.deepcopy(built["derived"])
    d["status"]["s5"]["enacted"] = not d["status"]["s5"]["enacted"]
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: bill status")


# ---- data dates and the comparison between the two systems ----
def test_every_difference_from_voteview_must_be_disclosed(built):
    core = copy.deepcopy(built["core"])
    assert not failed(S.site_reconcile_checks(DEFAULT, built["raw"], built["drop"], core), "Site: every difference")
    core["reconcile"]["positions"] = {}
    core["reconcile"]["tallies"] = {}
    assert built["core"]["reconcile"]["tallies"] == {} or failed(S.site_reconcile_checks(DEFAULT, built["raw"], built["drop"], core), "Site: every difference")
    core = copy.deepcopy(built["core"])
    core["reconcile"]["newer_count"] += 1
    assert failed(S.site_reconcile_checks(DEFAULT, built["raw"], built["drop"], core), "Site: every difference")


def test_an_older_source_cannot_be_called_latest(built):
    core = copy.deepcopy(built["core"])
    row = next(r for r in core["dates"]["rows"] if r["label"].startswith("Official Senate"))
    row["checked"] = "2020-01-01"
    row["status"] = "Latest available"
    assert failed(S.site_reconcile_checks(DEFAULT, built["raw"], built["drop"], core), "Site: every data date")
    core = copy.deepcopy(built["core"])
    next(r for r in core["dates"]["rows"] if r["label"] == "Committee votes")["checked"] = "2030-01-01"
    assert failed(S.site_reconcile_checks(DEFAULT, built["raw"], built["drop"], core), "Site: every data date")


def test_the_page_labels_dates_and_differences():
    assert "Older snapshot" in TEMPLATE or "statusChip" in TEMPLATE
    assert "Sources differ." in TEMPLATE and 'id="dates"' in TEMPLATE and "newerText()" in TEMPLATE


# ---- Engine B's numbers are reused, not recalculated ----
def test_senate_and_committee_numbers_are_engine_b_s(built):
    p = BP.payload(DEFAULT)
    s = built["core"]["senate"]
    for key in ("plain", "weighted", "median", "diff"):
        assert s[key]["v"] == p["p5"][key]["v"] and s[key]["d"] == p["p5"][key]["d"]
    assert s["wording"] == p["p5"]["wording"]
    for c in p["p6"]["committees"]:
        mine = next(x for x in built["core"]["committees"] if x["code"] == c["code"])
        assert mine["committee_median"] == c["committee_median"] and mine["sentence"] == c["sentence"]
        assert mine["referred"] == c["bills"]["referred"]["total"]["v"]
    for st in p["p4"]["states"]:
        for e in st["senators"]:
            mine = next(x for x in built["core"]["senators"] if x["id"] == e["id"])
            assert mine["position"] == e["senator_score"] and mine["party"] == e["party"]


def test_build_pages_output_does_not_depend_on_the_site():
    text = (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert "import legislative" not in text and "build_site" not in text


# ---- what must stay unavailable ----
def test_the_state_comparison_stays_unavailable(built):
    seated = [s for s in built["core"]["senators"] if s["seated"]]
    assert len(seated) == 100
    for s in seated:
        assert s["public"]["distance"]["s"] == "NOT_AVAILABLE" and s["public"]["distance"]["v"] is None
        assert s["public"]["state_on_senator_scale"]["v"] is None
        assert "p0" not in s["public"]["state_public_estimate"] and "p1" not in s["public"]["state_public_estimate"]
    assert "<h3>State vs Senator</h3>" in TEMPLATE
    assert 'class="big-n na">${NA}</span>' in TEMPLATE


def test_a_published_state_distance_is_caught(built):
    core = copy.deepcopy(built["core"])
    s = next(x for x in core["senators"] if x["seated"])
    s["public"]["distance"].update(s="AVAILABLE", v=0.2)
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: state and public comparisons")
    core = copy.deepcopy(built["core"])
    next(x for x in core["senators"] if x["seated"])["public"]["state_public_estimate"]["p1"] = "50.4"
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: state and public comparisons")


def test_a_wrong_senator_or_committee_on_the_page_is_caught(built):
    core = copy.deepcopy(built["core"])
    core["senators"][0]["position"]["v"] += .1
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: every senator's position")
    core = copy.deepcopy(built["core"])
    next(x for x in core["senators"] if x["seated"])["party"] = "X"
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: every senator's position")
    core = copy.deepcopy(built["core"])
    core["committees"][0]["members"].pop()
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: committee members")
    core = copy.deepcopy(built["core"])
    core["committees"][0]["members"][0]["title"] = "Chairman" if core["committees"][0]["members"][0]["title"] != "Chairman" else None
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: committee members")
    core = copy.deepcopy(built["core"])
    core["committees"][0]["referred"] += 1
    assert failed(S.site_core_checks(DEFAULT, built["raw"], core, "NONE"), "Site: committee members")


# ---- no invented data on the page ----
@pytest.mark.parametrize("phrase", ["/100", "moderate", "centrist", "political center", "liberal bills", "conservative bills",
                                    "extreme", "biased", "% aligned", "alignment", "voted for the", " won ", " lost "])
def test_the_page_carries_no_banned_wording(phrase):
    shell = TEMPLATE.lower().replace("civicalign", "")
    assert phrase not in shell, phrase


def test_the_checker_catches_banned_wording(built):
    assert failed(S.site_page_checks(built["drop"], TEMPLATE + "<p>A moderate senator</p>"), "Site: none of the banned")


def _issues():
    return TEMPLATE[TEMPLATE.index("function evidenceRow("):TEMPLATE.index("/* ---- Bills ---- */")]


def test_issue_positions_never_rates_a_senator():
    """It lists votes. No ratio, share or percent, and no side label for a senator or an issue."""
    body = _issues()
    assert "%" not in body and "Math." not in body and "liberal side" not in body and "conservative side" not in body
    assert "vote_division" not in TEMPLATE and "division" not in TEMPLATE
    assert "no issue score" in body


def test_issue_positions_explains_and_sources_every_vote():
    body = _issues()
    assert "esc(mine)" in body and "esc(other)" in body and "partyLine(v.by_party)" in body
    assert 'ext(v.source_url,"Official Senate roll call")' in body and 'ext(rec.url,"Congress.gov record")' in body
    assert "Insufficient evidence" in body and 'data-lazy="${later' in body


def test_nominations_are_separate_from_policy_areas():
    body = _issues()
    assert 'if(v.measure_type=="nomination"){noms.push(v);continue}' in body and "aren't policy stances" in body


def test_old_issue_rule_is_gone():
    assert not hasattr(L, "vote_division") and not hasattr(S, "site_division")


def test_missing_data_says_so():
    for phrase in ["Estimated Net Worth", "Stocks Held"]:
        assert re.search(phrase + r"</b><span>\$\{NA\}", TEMPLATE), phrase
    assert "No verified policy area" in TEMPLATE
    assert "Explanation coming soon" in TEMPLATE
    assert "how each member voted isn't in this data" in TEMPLATE


def test_only_verified_explanations_show_text():
    body = TEMPLATE[TEMPLATE.index("function explanationBlock"):TEMPLATE.index("function billBody")]
    assert 'e.status=="verified"||e.status=="approved"' in body and "still being checked" in body
    assert "Provisional facts" in TEMPLATE and "esc(k.about)" in TEMPLATE
    assert "Show the source" in TEMPLATE and "esc(f.quote)" in TEMPLATE


def test_nominations_are_labelled_as_nominations():
    assert 'nomination:["Nomination","nom"]' in TEMPLATE
    assert "This is a nomination, not a bill" in TEMPLATE
    assert 'class="chip nom">Nomination' in TEMPLATE


def test_the_page_script_parses_and_defines_what_it_uses():
    """Runs the page's script through a real JavaScript parser, and checks each helper it calls exists."""
    script = TEMPLATE[TEMPLATE.rindex("<script>") + 8:TEMPLATE.rindex("</script>")]
    assert 'const NAMES={D:"Democrat"' in script and 'const COUNT_KEYS=[' in script
    node = shutil.which("node")
    if node:
        done = subprocess.run([node, "--check", "-"], input=script, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
    defined = set(re.findall(r"(?:const|let|function)\s+([A-Za-z_$][\w$]*)", script))
    defined |= {n for group in re.findall(r"const\s+((?:[A-Za-z_$][\w$]*=[^;]*?,)+)", script) for n in re.findall(r"([A-Za-z_$][\w$]*)=", group)}
    for name in ("NAMES", "COUNT_KEYS", "cvBody", "cvRow", "evidenceRow", "differNote", "dataNote", "datesCard", "newerText", "ruleText", "partyLine", "LEG", "POSN", "COMV", "MEMB"):
        assert name in defined, name


def test_committee_notes_and_corrections_are_shown():
    assert "esc(c.correction_note)" in TEMPLATE and "c.notes.map" in TEMPLATE and "P.party" in TEMPLATE and "P.caucus" in TEMPLATE


def test_the_page_is_light_only():
    assert "prefers-color-scheme" not in TEMPLATE and "color-scheme:light" in TEMPLATE
    assert "civicalign.css" not in TEMPLATE, "the shared stylesheet carries a dark theme"


def test_the_issue_rules_are_published(built):
    rules = {r["id"]: r["rule"] for r in built["core"]["rules"]}
    assert rules[L.EVIDENCE_RULE] == L.EVIDENCE_TEXT and rules[L.PARTY_RULE] == L.PARTY_TEXT
    text = (ROOT / "METHODOLOGY.md").read_text()
    assert L.EVIDENCE_RULE in text and L.PARTY_RULE in text and "vote_division_v1" in text


def test_the_methodology_page_matches_the_site_and_stays_light():
    page = BP.build(DEFAULT)["methodology.html"]
    assert 'color-scheme:light' in page and 'civicalign.html#/senate' in page and "--alert:#b4532a" in page
    # the old page keeps its own look, available for rollback
    assert "--alert:#b4532a" not in BP.build(DEFAULT)["senator-check.html"]


def test_both_update_chains_build_the_site_before_the_tests():
    for f in (ROOT / "scripts" / "update.sh", ROOT / ".github" / "workflows" / "update.yml"):
        text = f.read_text()
        assert text.index("civicalign.build_pages") < text.index("civicalign.build_site") < text.index("-m pytest -q")


def test_the_home_page_opens_the_site():
    assert "url=civicalign.html" in (ROOT / "demo" / "index.html").read_text()
