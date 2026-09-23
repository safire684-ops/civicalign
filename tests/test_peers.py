"""The peer comparison: the fixed rule, its honesty at the edges, and the page."""
import json
import re
from pathlib import Path

import pytest

from civicalign.build_demo import peer_words
from civicalign.config import DEFAULT
from civicalign.peers import (INSUFFICIENT, MIN_PEERS, UNSTABLE, UNSUPPORTED, WINDOW, WINDOWS, PARTY_CAUCUS,
                              INDEPENDENT_CAUCUS, caucus_group, conclusion, peer_comparisons, status_from)
from civicalign.pipeline import run
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
    return json.loads(m.group(1))


def _js():
    return "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))


def _fn(name):
    return _js().split("function " + name + "(")[1].split("\n  }")[0]


def _toy():
    roster = {"A": Senator("A", "A Dem", "GA", "Democrat"), "B": Senator("B", "B Dem", "GA", "Democrat"),
              "C": Senator("C", "C Dem", "AZ", "Democrat"), "D": Senator("D", "D Dem", "MI", "Democrat"),
              "E": Senator("E", "E Ind", "NV", "Independent", "Democrat"), "F": Senator("F", "F Dem", "PA", "Democrat"),
              "G": Senator("G", "G Dem", "WI", "Democrat"), "H": Senator("H", "H Dem", "NH", "Democrat"),
              "I": Senator("I", "I Rep", "NC", "Republican"), "J": Senator("J", "J Dem", "CA", "Democrat")}
    shares = {"GA": .51, "AZ": .515, "MI": .50, "NV": .497, "PA": .502, "WI": .502, "NH": .48, "NC": .514, "CA": .36}
    def sl(u, s): return elections.StateLean(u, s, {2016: s, 2020: s, 2024: s})
    lean = elections.ElectionLean(years=(2016, 2020, 2024), states={u: sl(u, s) for u, s in shares.items()},
                                  national_gop_two_party=.49, national_by_year={2016: .49, 2020: .48, 2024: .51})
    scores = {"A": -.54, "B": -.47, "C": -.30, "D": -.28, "E": -.18, "F": -.16, "G": -.39, "H": -.21, "I": .69, "J": -.55}
    return roster, lean, scores


# 1. same-caucus peers only
def test_1_same_caucus_only(report):
    for c in report.peers:
        assert all(caucus_group(report.senators[p.bioguide]) == c.group for p in c.peers), c.name
    assert caucus_group(Senator("x", "x", "XX", "Democrat")) == "Democratic"
    assert caucus_group(Senator("x", "x", "XX", "Republican")) == "Republican"
    assert caucus_group(Senator("x", "x", "XX", "Independent", "Democrat")) == "Democratic"


# 2. focal state excluded; 3. the two senators of a state never peer each other
def test_2_and_3_own_state_excluded(report):
    for c in report.peers:
        assert all(p.state != c.state for p in c.peers), c.name
    roster, lean, scores = _toy()
    cs = {c.bioguide: c for c in peer_comparisons(scores, roster, lean)}
    assert "B" not in {p.bioguide for p in cs["A"].peers} and "A" not in {p.bioguide for p in cs["B"].peers}
    assert [p.bioguide for p in cs["A"].peers] == [p.bioguide for p in cs["B"].peers], "same-party senators of one state share one pool"


# 4. similarity uses the documented election measure
def test_4_similarity_is_the_three_cycle_two_party_share(report):
    for c in report.peers:
        assert c.state_lean == report.election.lean(c.state)
        for p in c.peers:
            assert abs(report.election.lean(p.state) - c.state_lean) <= WINDOW + 1e-12
    R = _block("R")
    assert R["rule"]["years"] == list(report.election.years) and R["rule"]["source"].startswith("MIT Election Data")


# 5, 6. the window and minimum are fixed and documented
def test_5_and_6_rule_is_fixed_and_documented():
    assert WINDOW == 0.04 and MIN_PEERS == 6 and WINDOWS == (0.02, 0.03, 0.04, 0.05)
    R = _block("R")
    assert R["rule"]["window"] == WINDOW and R["rule"]["minPeers"] == MIN_PEERS and R["rule"]["windows"] == list(WINDOWS)
    r = REPORT.read_text()
    assert "within &plusmn;4 points" in r and "at least 6" in r and "&plusmn;2, &plusmn;3, &plusmn;4, &plusmn;5" in r
    why = _fn("peerWhy")
    assert "(rule.window*100)" in why and "rule.minPeers" in why and "never widens the window" in why


# 7. no automatic widening
def test_7_no_widening_to_manufacture_a_result(report):
    src = (ROOT / "src" / "civicalign" / "peers.py").read_text()
    code = src.split('"""')[2]   # after the module docstring
    assert "while" not in code and "window +=" not in code and "window *=" not in code, "no loop that grows the window"
    for c in report.peers:
        if c.status == INSUFFICIENT:
            assert c.n < MIN_PEERS and c.sensitivity[WINDOW] == INSUFFICIENT
    roster, lean, scores = _toy()
    cs = {c.bioguide: c for c in peer_comparisons(scores, roster, lean)}
    assert cs["I"].status == INSUFFICIENT and cs["I"].n == 0


# 8. sensitivity across windows is checked; 9. unstable wording
def test_8_and_9_sensitivity_and_unstable_wording(report):
    for c in report.peers:
        assert set(c.sensitivity) == set(WINDOWS)
        assert c.status == status_from(c.sensitivity, WINDOW)
    assert status_from({0.02: "outside_liberal", 0.03: "within", 0.04: "within", 0.05: "within"}, 0.04) == UNSTABLE
    assert status_from({0.02: INSUFFICIENT, 0.03: "within", 0.04: "within", 0.05: "within"}, 0.04) == "within"
    assert status_from({0.02: INSUFFICIENT, 0.03: INSUFFICIENT, 0.04: INSUFFICIENT, 0.05: "within"}, 0.04) == INSUFFICIENT
    assert peer_words(UNSTABLE, "X") == "The comparison changes depending on which nearby states are included, so CivicAlign does not show a simple peer-range conclusion."
    assert "does not show a simple peer-range conclusion" in _fn("peerWords")
    unstable = [c for c in report.peers if c.status == UNSTABLE]
    assert unstable, "the current data has window-dependent cases; they must be labelled"
    R = _block("R")
    assert all(R["senators"][c.bioguide]["status"] == UNSTABLE for c in unstable)


# 10. insufficient groups degrade honestly
def test_10_insufficient_degrades_honestly(report):
    assert peer_words(INSUFFICIENT, "X") == "There are not enough comparable senators in the same caucus group from similarly voting states for a stable comparison."
    R = _block("R")
    for c in report.peers:
        if c.status == INSUFFICIENT:
            assert R["senators"][c.bioguide]["status"] == INSUFFICIENT and R["senators"][c.bioguide]["n"] < MIN_PEERS
    track = _fn("peerTrack")
    assert "usable=pc.n>=R.rule.minPeers" in track and "no peer range is drawn" in track


# 11, 12, 13. no rankings, no superlatives, no verdicts
def test_11_12_13_no_ranking_superlative_or_verdict():
    t = re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", DEMO.read_text(), flags=re.S)
    low = t.lower()
    for w in ("most liberal", "most conservative", "#1", "furthest", "rank", "outlier senator", "more liberal than all",
              "aligned", "misaligned", "represents the state", "unrepresentative", "defies", "betrays", "extreme", "moderate"):
        assert w not in low, w
    assert "Listed by state, not ordered by position." in t
    R = _block("R")
    for s in R["senators"].values():
        assert "rank" not in json.dumps(s).lower() and "score" not in json.dumps(s).lower()
        sts = [p["st"] for p in s["peers"]]
        assert sts == sorted(sts), "peers are listed by state"


# 14. no direct survey arithmetic
def test_14_no_survey_arithmetic():
    js = _js()
    for fn in ("peerWords", "peerTrack", "peerWhy", "senatorCard", "takeaway"):
        body = _fn(fn)
        assert "st.center" not in body and "usM" not in body, fn
    src = (ROOT / "src" / "civicalign" / "peers.py").read_text()
    assert "state_coord" not in src and "mrp" not in src and "state_prefs" not in src
    R = _block("R")
    assert "center" not in json.dumps(R) and "usM" not in json.dumps(R)


# 15. Senate-middle context stays secondary
def test_15_senate_context_is_secondary():
    card = _fn("senatorCard")
    assert card.index("peerWords(pc.status,last)") < card.index("Recent votes in this record") < card.index("Where they sit in the Senate")
    assert "senatorTrack(s)" in card.split("Where they sit in the Senate")[1]
    assert "sp.w" not in card.split('<details class="more">')[0]


# 16. survey context stays collapsed and separate
def test_16_survey_context_collapsed():
    m = DEMO.read_text().split("<script>")[0]
    first = m.split('<section id="your-senators"')[1].split("</section>")[0]
    assert '<details class="more context" id="voterctx">' in first
    assert first.index('id="cards"') < first.index('id="voterctx"')
    assert "is not directly compared with your senators" in _js()


# 17. peer states and count are inspectable
def test_17_peer_states_and_count_inspectable(report):
    R = _block("R")
    for c in report.peers:
        s = R["senators"][c.bioguide]
        assert s["n"] == c.n and s["states"] == c.peer_states
    card = _fn("senatorCard")
    assert "pc.n+' senator'+(pc.n===1?'':'s')+' in the '+groupLabel(pc)" in card and "pc.states.length+' other state'" in card
    assert "Peer states ('+pc.states.length+')" in _fn("peerWhy")
    assert "recent presidential vote used for peer matching" in _js()


# 18. peer senator identities only under details and unranked
def test_18_peer_identities_under_details_only():
    card = _fn("senatorCard")
    before = card.split('<details class="more">')[0]
    assert "pc.peers" not in before and "p.name" not in before
    why = _fn("peerWhy")
    assert "byState[k].map(esc)" in why and "Object.keys(byState).sort()" in why and ".sort(function" not in why.split("byState")[0]


# 19. the supervisor reproduces every public peer result
def test_19_supervisor_reproduces_peers(report):
    from civicalign.agents.supervisor import checks
    results = checks(report, DEFAULT, DEMO)
    names = {c.name: c for c in results}
    for n in ("every senator's peer group, range, status and sensitivity", "peer rule: fixed window, minimum and cross-window check",
              "page: every senator's peer comparison rebuilt from raw files", "page: the peer rule shown is the rule used",
              "page: peer lists are by state, not ordered by position"):
        assert n in names and names[n].ok, n


# 20. the rebuild is deterministic
def test_20_rebuild_is_deterministic(report):
    from civicalign.build_demo import _state_relative_block
    a = json.dumps(_state_relative_block(report, DEFAULT), sort_keys=False)
    b = json.dumps(_state_relative_block(run(DEFAULT), DEFAULT), sort_keys=False)
    assert a == b
    R = _block("R")
    assert list(R["states"]) == sorted(R["states"])


def test_conclusion_edges():
    assert conclusion(-0.5, [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1], 6) == "outside_liberal"
    assert conclusion(0.5, [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1], 6) == "outside_conservative"
    assert conclusion(-0.4, [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1], 6) == "within", "equal to the edge is within"
    assert conclusion(-0.5, [-0.4, -0.3], 6) == INSUFFICIENT


def test_georgia_reads_as_the_audit_found(report):
    """Both Georgia Democrats sit below every Democratic peer from similarly voting
    states, and the conclusion holds at every window."""
    for b in ("O000174", "W000790"):
        c = next(x for x in report.peers if x.bioguide == b)
        assert c.status == "outside_liberal" and c.n >= MIN_PEERS
        assert set(c.sensitivity.values()) == {"outside_liberal"}
        assert peer_words(c.status, "X").endswith("on the more liberal side.")


# ---- caucus-group terminology and fail-closed grouping ----

def _public_text():
    t = re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", DEMO.read_text(), flags=re.S)
    return t + REPORT.read_text()


def test_c1_no_public_text_says_same_party():
    t = _public_text().lower()
    assert "same-party" not in t and "same party" not in t.replace("\"same party\" would be the wrong phrase", "")
    assert "senators in the same caucus group" in t


def test_c2_independents_are_never_displayed_as_democrats(report):
    R = _block("R")
    for c in report.peers:
        if c.party == "Independent":
            assert R["senators"][c.bioguide]["party"] == "Independent" and R["senators"][c.bioguide]["independent"] is True
    js = _js()
    assert "esc(s.party)" in _fn("senatorCard"), "the badge shows the roster party"
    assert "groupLabel(pc)" in _fn("senatorCard") and "'Democratic caucus'" in _fn("groupLabel")
    assert "is an Independent who caucuses with the Democrats" in _fn("peerWhy")
    assert "Democrats plus the\n      Independents who caucus with them" in DEMO.read_text().split("<script>")[0]


def test_c3_unknown_party_cannot_become_a_caucus():
    for party in ("Libertarian", "Unknown", "", "Green", "democrat"):
        assert caucus_group(Senator("x", "x", "XX", party)) is None, party
    assert caucus_group(Senator("x", "x", "XX", "Independent")) is None, "no caucus field -> no group"
    assert caucus_group(Senator("x", "x", "XX", "Independent", "Green")) is None
    roster, lean, scores = _toy()
    roster["E"] = Senator("E", "E Odd", "NV", "Libertarian")
    cs = {c.bioguide: c for c in peer_comparisons(scores, roster, lean)}
    assert cs["E"].status == UNSUPPORTED and cs["E"].group is None and cs["E"].peers == ()
    assert all("E" not in {p.bioguide for p in c.peers} for c in cs.values()), "an unsupported senator is nobody's peer"
    assert peer_words(UNSUPPORTED, "X") == "CivicAlign does not have a verified caucus group for this senator, so no peer comparison is shown."
    assert "status==='unsupported'" in _fn("peerWords")


def test_c4_current_caucus_mapping_is_explicit(report):
    assert PARTY_CAUCUS == {"Republican": "Republican", "Democrat": "Democratic"}
    assert INDEPENDENT_CAUCUS == {"Democrat": "Democratic", "Republican": "Republican"}
    inds = [s for s in report.senators.values() if s.party == "Independent"]
    assert inds and all(s.caucus == "Democrat" for s in inds), [(s.name, s.caucus) for s in inds]
    assert all(s.party in ("Republican", "Democrat", "Independent") for s in report.senators.values())
    assert not [c for c in report.peers if c.status == UNSUPPORTED]
    from civicalign.agents.supervisor import checks
    names = {c.name: c for c in checks(report, DEFAULT, DEMO)}
    n = "caucus grouping explicit: no unrecognised party, Independents by roster caucus"
    assert n in names and names[n].ok
    src = (ROOT / "src" / "civicalign" / "peers.py").read_text().split('"""')[2]
    assert 'else "Democratic"' not in src and "else 'Democratic'" not in src, "no silent default"


def test_c5_thirty_votes_is_a_display_rule_not_a_validity_claim():
    t = _public_text().lower()
    for w in ("statistically valid", "minimum floor votes", "statistical validity"):
        assert w not in t, w
    assert "waits until a senator has at least 30 recorded floor votes before showing a voting-position estimate" in t
    assert "this senator has not reached that threshold yet" in t
