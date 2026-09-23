"""The product correction: CivicAlign gives perspective, not an ideology lookup.

Pillar 4's primary result is state-relative (the election-result regression on
the senators' own scale), the survey estimate stays separate, Pillar 5 leads with
the seats-versus-nation comparison, and committees are read against the
Senate-wide baseline. These tests pin that hierarchy and the guardrails around it.
"""
import json
import re
from pathlib import Path

import pytest

from civicalign.build_demo import state_rel_words
from civicalign.config import DEFAULT
from civicalign.pipeline import run
from civicalign.representation import Representation, representations, state_expectation
from civicalign.sources import elections
from civicalign.sources.rosters import Senator

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "senator-check.html"
REPORT = ROOT / "demo" / "methodology.html"


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


def _block(name):
    m = re.search(r"const " + name + r"=(\{.*?\});", DEMO.read_text(), re.S)
    assert m, name
    return json.loads(m.group(1))


def _js():
    return "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))


def _fn(name):
    return _js().split("function " + name + "(")[1].split("\n  }")[0]


def _markup():
    return DEMO.read_text().split("<script>")[0]


# 1. the primary senator result is state-relative, not Senate-middle-relative
def test_1_primary_senator_result_is_state_relative():
    card = _fn("senatorCard")
    before = card.split('<details class="more">')[0]
    assert "stateRelWords(rr,last,st.name)" in before
    assert "senatorPos(s).w" not in before and "sp.w" not in before, "the Senate-middle sentence is not the headline"
    assert "Where they sit in the Senate" in card and "'+sp.w+'" in card.split("Where they sit in the Senate")[1]
    assert "takeaway(st)" in _js() and "typical range for states that vote like" in _fn("takeaway")
    sec = _markup().split('<section id="your-senators"')[1].split("</section>")[0]
    assert sec.index('id="stateref"') < sec.index('id="cards"') < sec.index('id="stateblock"')


# 2. the state comparison is the election regression, not survey subtraction
def test_2_state_comparison_uses_the_election_regression(report):
    R = _block("R")
    assert R["source"].startswith("MIT Election Data and Science Lab")
    assert R["fit"]["n"] == report.fit.n and R["fit"]["slope"] == pytest.approx(report.fit.slope, abs=1e-4)
    for b, s in R["senators"].items():
        x = R["states"][s["st"]]["gop"]
        assert s["expected"] == pytest.approx(R["fit"]["intercept"] + R["fit"]["slope"] * x, abs=2e-3)
        assert s["residual"] == pytest.approx(s["actual"] - s["expected"], abs=2e-3)
    ref = _fn("stateRefCard")
    assert "R.states" in ref and "st.center" not in ref and "P.usM" not in ref and "M.usM" not in ref


# 3. the survey estimate stays visually and mathematically separate
def test_3_survey_estimate_stays_separate():
    js = _js()
    for fn in ("stateRefCard", "stateRefWhy", "senatorCard", "votesList", "takeaway", "stateRelWords"):
        body = _fn(fn)
        assert "st.center" not in body and "usM" not in body and "V.states[code].center" not in body, fn
    render = js.split("function render(code){")[1].split("window.addEventListener('resize'")[0]
    assert "This is a separate survey measure and is not directly compared with the senators above." in render
    assert "stateTrack(st,se)" in render and "R." not in _fn("stateTrack")
    R = _block("R")
    assert "center" not in json.dumps(R) and "mrp" not in json.dumps(R)


# 4. no Voteview-vs-survey arithmetic returns
def test_4_no_cross_scale_arithmetic_returns():
    js = _js()
    for pat in (r"record\s*-\s*st\.center", r"st\.center\s*-\s*s\.record", r"record\s*-\s*(P|V|M)\.usM",
                r"expected\s*-\s*st\.center", r"st\.center\s*-\s*rr\.", r"actual\s*-\s*(P|V|M)\.usM"):
        assert not re.search(pat, js), pat
    src = "".join(p.read_text() for p in (ROOT / "src" / "civicalign").glob("*.py"))
    for pat in (r"senator_coord\s*-\s*[\w.]*state_coord", r"state_coord\s*-\s*[\w.]*senator_coord",
                r"ideology\s*-\s*[\w.]*state_coord", r"state_coord\s*-\s*[\w.]*ideology",
                r"predicted\s*-\s*[\w.]*state_coord", r"state_coord\s*-\s*[\w.]*predicted"):
        assert not re.search(pat, src), pat


# 5. no politician ranking or score
def test_5_no_ranking_or_score_in_the_payload_or_page():
    for name in ("R", "E", "F"):
        dumped = json.dumps(_block(name)).lower()
        for w in ('"rank"', '"score"', '"grade"', '"of":', "alignment"):
            assert w not in dumped, (name, w)
    t = re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", DEMO.read_text(), flags=re.S).lower()
    for w in ("alignment score", "representation score", "defiance", "match %", "rank #", "grade a", "betray", "defies",
              "fails to represent", "misaligned", "unrepresentative", "more representative"):
        assert w not in t, w


# 6. expected position comes from the backend, not UI logic
def test_6_expected_position_is_not_computed_in_the_page():
    js = _js()
    assert "R.fit.slope*" not in js.replace(" ", "") and "intercept+" not in js.replace(" ", "")
    for fn in ("stateRefCard", "senatorCard", "stateRelWords", "takeaway"):
        body = _fn(fn)
        assert "rs.expected" in body or "rr.zone" in body or "rr.residual" in body or "stateRelWords(rr" in body, fn
        assert "slope" not in body and "intercept" not in body, fn
    assert "rr.zone==='within'" in _fn("stateRelWords") and "rr.zone==='clear'" in _fn("stateRelWords")


# 7. both senators from a state use the same state-election input
def test_7_both_senators_share_the_state_input(report):
    R = _block("R")
    by_state = {}
    for b, s in R["senators"].items():
        by_state.setdefault(s["st"], set()).add((s["expected"], s["band"]))
    assert len(by_state) == 50 and all(len(v) == 1 for v in by_state.values())
    ga = [x for x in report.representation if x.state == "GA"]
    assert len(ga) == 2 and ga[0].state_lean == ga[1].state_lean == report.election.lean("GA")


# 8. actual senator coordinates are the live Voteview scores (rebuilt weekly)
def test_8_actual_coordinates_are_the_current_scores(report):
    R = _block("R")
    assert set(R["senators"]) == set(report.scores)
    for b, s in R["senators"].items():
        assert s["actual"] == pytest.approx(report.scores[b], abs=1e-3)
    y = (ROOT / ".github" / "workflows" / "update.yml").read_text()
    assert "civicalign.build_demo" in y and "civicalign.agents.supervisor" in y


# 9. the state election input is inspectable on the page
def test_9_state_election_input_is_shown(report):
    R = _block("R")
    for usps, sl in report.election.states.items():
        if usps in R["states"]:
            assert R["states"][usps]["gop"] == pytest.approx(sl.gop_two_party, abs=1e-4)
            assert set(R["states"][usps]["byYear"]) == {str(y) for y in report.election.years}
    why = _fn("stateRefWhy")
    assert "recent presidential voting" in why and "rs.byYear[y]" in why and "Average used by CivicAlign" in why
    assert "Why this is the '+stName+' reference" in _fn("stateRefCard")


# 10. regression uncertainty drives the wording
def test_10_uncertainty_drives_the_wording(report):
    assert state_rel_words("within", -0.1, "Kaine", "Virginia") == \
        "Kaine’s voting record is within the typical range for states that vote like Virginia."
    assert state_rel_words("beyond", -0.5, "Warnock", "Georgia") == \
        "Warnock’s voting record is more liberal than the typical range for states that vote like Georgia."
    assert state_rel_words("clear", 0.8, "Johnson", "Wisconsin").endswith("That difference is larger than chance would explain.")
    for x in report.representation:
        if abs(x.residual) <= x.band:
            assert x.zone == "within"
        elif abs(x.t_stat) > 2:
            assert x.zone == "clear"
        else:
            assert x.zone == "beyond"
    R = _block("R")
    for b, s in R["senators"].items():
        exp = "within" if abs(s["residual"]) <= s["band"] else ("clear" if abs(s["t"]) > 2 else "beyond")
        assert s["zone"] == exp, b
    js = _fn("stateRelWords")
    assert "within the typical range" in js and "larger than chance would explain" in js
    r = REPORT.read_text()
    assert "typical range" in r and "larger than chance would explain" in r


# 11. policy receipts never claim voter disagreement
def test_11_votes_make_no_voter_claim():
    F = _block("F")
    assert F["votes"] and all(v["summary"] == "" for v in F["votes"])
    assert all(set(v["votes"].values()) <= {"Yea", "Nay"} for v in F["votes"])
    vl = _fn("votesList")
    assert "They do not say what the state’s voters wanted." in vl
    for w in ("voters opposed", "voters supported", "against the state", "why the senator differs", "explains the difference"):
        assert w not in vl.lower(), w
    assert "voteview.com/rollcall" in F["votes"][0]["url"]


# 12. Senate context is secondary on the senator card
def test_12_senate_context_is_secondary():
    card = _fn("senatorCard")
    i_state = card.index("stateRelWords(rr,last,st.name)")
    i_votes = card.index("See their actual votes")
    i_senate = card.index("Where they sit in the Senate")
    assert i_state < i_votes < i_senate
    assert "senatorTrack(s)" in card.split("Where they sit in the Senate")[1]
    assert "Within the Senate itself" in card


# 13. Pillar 5 leads with the election-results structural comparison
def test_13_senate_view_leads_with_seats_versus_nation(report):
    sec = _markup().split('<section id="the-senate"')[1].split("</section>")[0]
    assert sec.index('id="seatscard"') < sec.index('id="pubcard"')
    E = _block("E")
    assert E["seatsMinusNational"] == pytest.approx(report.chamber_lean.skew_points, abs=0.01)
    assert E["nationalGop"] == pytest.approx(report.election.national_gop_two_party, abs=1e-4)
    assert E["seatsGop"] == pytest.approx(report.chamber_lean.senate_lean, abs=1e-4)
    js = _js()
    assert "percentage points more '+side+'" in js and "Every state gets two Senate seats." in js
    for w in ("bias", "unfair", "veto over the public", "anti-democratic"):
        assert w not in js.split("$('seatscard').innerHTML=")[1].split(";\n")[0].lower(), w


# 14. committee comparisons include the Senate-wide baseline
def test_14_committee_bill_flow_shows_the_senate_wide_baseline():
    bars = _fn("sentOnBars")
    assert "G.baseline" in bars and 'class="compare"' in bars
    assert "Senate-wide" in bars and "This committee" in bars
    assert "Compared with the Senate overall" in bars
    assert "further toward" in bars and "further away from" in bars


# 15. small samples produce weak wording
def test_15_small_samples_stay_weak():
    js = _js()
    assert "Too few bills to compare the two sides fairly" in js and "Limited data" in js
    assert "Early signal" in js and "too little data for a strong conclusion" in js
    assert "Not enough data yet" in js and "weak=o.n<15" in js


# 16. no roll-call cutpoint is called bill ideology
def test_16_no_cutpoint_is_bill_ideology():
    js = _js()
    assert "It does not tell us whether the bill itself was liberal or conservative." in js
    for w in ("liberal bill", "conservative bill", "the bill is liberal", "the bill is conservative"):
        assert w not in js.lower(), w


# 17. sponsor ideology is not bill ideology
def test_17_sponsor_is_not_bill_ideology():
    bars = _fn("sentOnBars")
    assert "Sponsor = the senator who introduced the bill." in bars
    assert "This describes the sponsor, not the ideology of the bill." in bars


# 18. existing provenance/snapshot/supervisor safeguards remain
def test_18_safeguards_remain(report):
    from civicalign.agents.supervisor import checks
    results = checks(report, DEFAULT, DEMO)
    names = [c.name for c in results]
    assert all(c.ok for c in results), [c.name for c in results if not c.ok]
    for n in ("senator-vs-state-pattern line refitted", "every senator's expected position, residual, range, zone",
              "Senate seats' vote share minus the national vote", "page: every senator's vote on the published floor votes",
              "page: no cross-scale derived fields in the public payload", "page: no ranking or cross-scale field in the new blocks"):
        assert n in names, n
    y = (ROOT / ".github" / "workflows" / "update.yml").read_text()
    assert "civicalign.agents.verify" in y and "needs.update.result == 'success'" in y
    assert (ROOT / "data" / "raw" / "SNAPSHOT.json").exists()


# 19. mobile first view remains easy to understand
def test_19_mobile_first_view_stays_light():
    css = (ROOT / "demo" / "civicalign.css").read_text()
    assert ".mtag.bot{top:calc(26px + var(--row,0) * 16px)" in css, "senator labels stagger instead of colliding"
    assert ".atag.exp.edge-r{transform:translateX(-100%)" in css and ".atag.exp.edge-l{transform:none" in css
    ref = _fn("stateRefCard")
    assert "edge-r" in ref and "rows=" in ref
    sec = _markup().split('<section id="your-senators"')[1].split("</section>")[0]
    outside = re.sub(r"<details.*?</details>", "", sec, flags=re.S)
    assert outside.count('class="limit"') == 1


# 20. every primary visual answers "compared with what?"
def test_20_every_primary_visual_names_its_reference():
    js = _js()
    assert "Expected for a state like '+stName+'" in _fn("stateRefCard")
    assert "typical range for states with a similar voting pattern" in _fn("stateRefCard")
    assert "National vote: '+pct(E.nationalGop)" in js and "Average across Senate seats" in js
    assert "Senate middle" in _fn("committeeCard") and "Senate middle" in _fn("floorSplit") and "Senate middle" in _fn("senatorTrack")
    assert "National voter estimate" in _fn("stateTrack")
    assert "Senate-wide" in _fn("sentOnBars")


def test_relative_residual_property_still_holds():
    """A uniform shift of every senator changes no residual: the measure is
    relative to the Senate-wide pattern, never an absolute distance to voters."""
    roster = {"A": Senator("A", "A", "WY", "Republican"), "B": Senator("B", "B", "CA", "Democrat"),
              "C": Senator("C", "C", "OH", "Republican"), "D": Senator("D", "D", "GA", "Democrat")}
    def sl(u, s):
        return elections.StateLean(u, s, {2016: s, 2020: s, 2024: s})
    lean = elections.ElectionLean(years=(2016, 2020, 2024),
                                  states={"WY": sl("WY", .73), "CA": sl("CA", .40), "OH": sl("OH", .56), "GA": sl("GA", .51)},
                                  national_gop_two_party=.4915, national_by_year={2016: .4889, 2020: .4773, 2024: .5075})
    base = {"A": .6, "B": -.4, "C": .2, "D": -.3}
    f1, r1 = representations(base, roster, lean)
    f2, r2 = representations({k: v + .25 for k, v in base.items()}, roster, lean)
    for a, b in zip(r1, r2):
        assert a.residual == pytest.approx(b.residual) and a.band == pytest.approx(b.band) and a.zone == b.zone
    exp, band = state_expectation(f1, [x.state_lean for x in r1], .51)
    assert exp == pytest.approx(f1.predict(.51)) and band > 0
