"""The integrated site: one page built from Engine B's results and the legislative drop.

Pins that the drop is imported byte for byte and refused if changed, that a broken id stops
the build, that the split rule behaves, that the page never invents a comparison or a score,
and that the independent checker catches tampering with each thing it recounts.
"""
import copy
import json
import re
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


# ---- the split rule ----
SCORES = {"a": -.5, "b": -.4, "c": -.3, "x": .3, "y": .4, "z": .5}


@pytest.mark.parametrize("positions, want", [
    ({"a": "Yea", "b": "Yea", "c": "Nay", "x": "Nay", "y": "Nay", "z": "Yea"}, "yes_liberal"),
    ({"a": "Nay", "b": "Nay", "c": "Nay", "x": "Yea", "y": "Yea", "z": "Yea"}, "yes_conservative"),
    ({"a": "Yea", "b": "Yea", "c": "Yea", "x": "Yea", "y": "Yea", "z": "Yea"}, None),      # everyone together
    ({"a": "Yea", "b": "Nay", "x": "Nay", "y": "Nay"}, None),                              # a tie on one side
    ({"a": "Not Voting", "b": "Present", "x": "Yea", "y": "Yea"}, None),                   # one side has no votes
    ({"zero": "Yea", "a": "Nay", "x": "Yea"}, "yes_conservative"),                         # a zero score counts for neither
])
def test_the_split_rule(positions, want):
    scores = {**SCORES, "zero": 0.0}
    assert L.vote_division(positions, scores) == want
    assert S.site_division(positions, scores) == want


def test_a_tampered_split_label_or_policy_area_is_caught(built):
    d = copy.deepcopy(built["derived"])
    flip = next(k for k, v in d["division"].items() if v == "yes_liberal")
    d["division"][flip] = "yes_conservative"
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: every split label")
    d = copy.deepcopy(built["derived"])
    d["policy_area"]["s5"] = "Sports and Recreation"
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: policy areas")
    d = copy.deepcopy(built["derived"])
    d["status"]["s5"]["enacted"] = not d["status"]["s5"]["enacted"]
    assert failed(S.site_derived_checks(DEFAULT, built["raw"], built["drop"], d), "Site: bill status")


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


def test_no_issue_score_is_calculated():
    """Issue Positions lists votes. It never turns them into a ratio, share or percent."""
    body = TEMPLATE[TEMPLATE.index("function issues("):TEMPLATE.index("/* ---- Bills ---- */")]
    assert "%" not in body and "/n" not in body and "Math." not in body
    assert "#/vote/" in body, "every label links to the actual vote"
    assert "there is no issue score" in body


def test_missing_data_says_so():
    for phrase in ["Estimated Net Worth", "Stocks Held"]:
        assert re.search(phrase + r"</b><span>\$\{NA\}", TEMPLATE), phrase
    assert "No policy area in available official data" in TEMPLATE
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


def test_committee_notes_and_corrections_are_shown():
    assert "esc(c.correction_note)" in TEMPLATE and "c.notes.map" in TEMPLATE and "P.party" in TEMPLATE and "P.caucus" in TEMPLATE


def test_the_page_is_light_only():
    assert "prefers-color-scheme" not in TEMPLATE and "color-scheme:light" in TEMPLATE
    assert "civicalign.css" not in TEMPLATE, "the shared stylesheet carries a dark theme"


def test_the_division_rule_is_published(built):
    assert any(r["id"] == L.DIVISION_RULE and r["rule"] == L.DIVISION_TEXT for r in built["core"]["rules"])
    assert L.DIVISION_RULE in (ROOT / "METHODOLOGY.md").read_text()


def test_both_update_chains_build_the_site_before_the_tests():
    for f in (ROOT / "scripts" / "update.sh", ROOT / ".github" / "workflows" / "update.yml"):
        text = f.read_text()
        assert text.index("civicalign.build_pages") < text.index("civicalign.build_site") < text.index("-m pytest -q")


def test_the_home_page_opens_the_site():
    assert "url=civicalign.html" in (ROOT / "demo" / "index.html").read_text()
