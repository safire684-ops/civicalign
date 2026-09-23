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

from civicalign.build_demo import peer_words
from civicalign.config import DEFAULT
from civicalign.pipeline import run
from civicalign.representation import Representation, representations, state_expectation
from civicalign.sources import elections
from civicalign.sources.rosters import Senator

A = "\u2019"
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
    assert "peerWords(pc.status,last)" in before
    assert "senatorPos(s).w" not in before and "sp.w" not in before, "the Senate-middle sentence is not the headline"
    assert "Where they sit in the Senate" in card and "'+sp.w+'" in card.split("Where they sit in the Senate")[1]
    assert "takeaway(st)" in _js() and "comparable '+g+' senators" in _fn("takeaway")
    sec = _markup().split('<section id="your-senators"')[1].split("</section>")[0]
    assert sec.index('id="stateinput"') < sec.index('id="cards"') < sec.index('id="stateblock"')


# 2. the state comparison is the peer rule on election results, not survey subtraction
def test_2_state_comparison_uses_election_peers_not_survey(report):
    R = _block("R")
    assert R["rule"]["source"].startswith("MIT Election Data and Science Lab")
    for b, s in R["senators"].items():
        assert s["st"] == report.senators[b].state
        for p in s["peers"]:
            assert p["st"] != s["st"] and abs(R["states"][p["st"]]["gop"] - R["states"][s["st"]]["gop"]) <= R["rule"]["window"] + 1e-9
    track = _fn("peerTrack")
    assert "pc.low" in track and "st.center" not in track and "P.usM" not in track and "M.usM" not in track


# 3. the survey estimate stays visually and mathematically separate
def test_3_survey_estimate_stays_separate():
    js = _js()
    for fn in ("peerTrack", "peerWhy", "senatorCard", "votesList", "takeaway", "peerWords"):
        body = _fn(fn)
        assert "st.center" not in body and "usM" not in body and "V.states[code].center" not in body, fn
    render = js.split("function render(code){")[1].split("window.addEventListener('resize'")[0]
    assert "This is a separate survey measure and is not directly compared with your senators." in render
    assert "stateTrack(st,se)" in render and "R." not in _fn("stateTrack")
    R = _block("R")
    assert "center" not in json.dumps(R) and "mrp" not in json.dumps(R) and "expected" not in json.dumps(R)


# 4. no Voteview-vs-survey arithmetic returns
def test_4_no_cross_scale_arithmetic_returns():
    js = _js()
    for pat in (r"record\s*-\s*st\.center", r"st\.center\s*-\s*s\.record", r"record\s*-\s*(P|V|M)\.usM",
                r"low\s*-\s*st\.center", r"st\.center\s*-\s*pc\.", r"actual\s*-\s*(P|V|M)\.usM"):
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


# 6. the classification comes from the backend, not UI logic
def test_6_status_is_not_computed_in_the_page():
    js = _js()
    for fn in ("peerWords", "senatorCard", "takeaway"):
        body = _fn(fn)
        assert "pc.status" in body or "status===" in body, fn
    for fn in ("peerWords", "peerTrack", "senatorCard", "takeaway"):
        body = _fn(fn)
        assert "Math.min(" not in body and "Math.max(" not in body and "median" not in body.replace("pc.median", ""), fn
    assert "status==='within'" in _fn("peerWords") and "status==='unstable'" in _fn("peerWords")


# 7. both senators from a state use the same state-election input and the same pool
def test_7_both_senators_share_the_state_input(report):
    R = _block("R")
    for c in report.peers:
        assert R["states"][c.state]["gop"] == pytest.approx(c.state_lean, abs=1e-4)
    ga = [x for x in report.peers if x.state == "GA"]
    assert len(ga) == 2 and ga[0].state_lean == ga[1].state_lean
    assert [p.bioguide for p in ga[0].peers] == [p.bioguide for p in ga[1].peers]
    assert "Both senators are compared with the same pool of other states." in _js()


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
    why = _fn("peerWhy")
    assert "recent presidential vote" in why and "rs.byYear[y]" in why and "Average used for matching" in why
    assert "How were these peers chosen?" in _fn("senatorCard")
    assert "recent presidential vote used for peer matching: '+(R.rule?R.rule.years.join(' · ')" in _js()


# 10. the fixed rule and its uncertainty states drive the wording
def test_10_rule_drives_the_wording(report):
    assert peer_words("within", "Kaine") == f"Kaine{A}s voting record falls within the observed range of same-party senators from similarly voting states."
    assert peer_words("outside_liberal", "Warnock") == f"Warnock{A}s voting record falls outside that peer range on the more liberal side."
    assert peer_words("outside_conservative", "Scott") == f"Scott{A}s voting record falls outside that peer range on the more conservative side."
    R = _block("R")
    for c in report.peers:
        assert R["senators"][c.bioguide]["status"] == c.status
    page = DEMO.read_text(); r = REPORT.read_text()
    for w in ("chance would explain", "statistically significant", "typical position based on", "typical range based on", "Expected for"):
        assert w not in page, w
    assert "typical position" not in page.split("<script>")[0].lower()
    assert "observed range" in r and "peer" in r


# 11. policy receipts never claim voter disagreement
def test_11_votes_make_no_voter_claim():
    F = _block("F")
    assert F["votes"] and all(v["summary"] == "" for v in F["votes"])
    assert all(set(v["votes"].values()) <= {"Yea", "Nay"} for v in F["votes"])
    vl = _fn("votesList")
    assert "they do not say what the state’s voters wanted." in vl
    assert "These are recent recorded votes that contribute to '+last+'’s overall voting record" in vl
    assert "do not on their own explain the comparison above" in vl
    for w in ("voters opposed", "voters supported", "against the state", "why the senator differs", "explains the difference"):
        assert w not in vl.lower(), w
    assert "voteview.com/rollcall" in F["votes"][0]["url"]


# 12. Senate context is secondary on the senator card
def test_12_senate_context_is_secondary():
    card = _fn("senatorCard")
    i_state = card.index("peerWords(pc.status,last)")
    i_votes = card.index("Recent votes in this record")
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
    assert ".mark.peerrange{" in css and ".atag.peer{" in css
    track = _fn("peerTrack")
    assert "Peer middle" in track and "scalename" in track
    sec = _markup().split('<section id="your-senators"')[1].split("</section>")[0]
    outside = re.sub(r"<details.*?</details>", "", sec, flags=re.S)
    assert outside.count('class="limit"') == 1


# 20. every primary visual answers "compared with what?"
def test_20_every_primary_visual_names_its_reference():
    js = _js()
    track = _fn("peerTrack")
    assert "Bar: lowest to highest peer record · Tick: peer middle" in track and "Dot: '+last+'’s Senate voting record" in track
    assert "Compared with <span class=\"kick2\">'+cmp+'</span>" in _fn("senatorCard")
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


def test_correction_pass_hierarchy_and_defensibility():
    """The targeted correction: no normative or significance wording, the survey
    context collapsed and demoted, the familiar-senators fold off the first view,
    and the committee baseline described without a cause."""
    page = DEMO.read_text()
    m = _markup()
    first = m.split('<section id="your-senators"')[1].split("</section>")[0]
    assert 'id="explore"' not in first and 'id="explore"' in m.split('<section id="the-senate"')[1].split("</section>")[0]
    assert '<details class="more context" id="voterctx">' in first and "<summary><span>Additional voter context</span></summary>" in first
    assert first.index('id="stateinput"') < first.index('id="cards"') < first.index('id="voterctx"')
    js = _js()
    assert "is not directly compared with your senators" in js.split("$('qsub-voters').textContent=")[1].split(";\n")[0]
    base = js.split("$('basenote').innerHTML=")[1].split(";\n")[0]
    assert "Republicans hold the majority" not in base and "because" not in base
    assert "compares each committee with that Senate-wide pattern rather than with zero" in base
    for w in ("Republicans hold the majority", "majority control", "chance would explain", "Expected for a state like", "Expected for states with", "typical range based on"):
        assert w not in page, w
    assert "Republicans hold the majority" not in REPORT.read_text() and "majority control" not in REPORT.read_text()
