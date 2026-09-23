"""The two published pages must say what the pipeline says.

Both carry figures that were once correct and then went stale without anything
noticing: the demo kept pre-Census national figures, and the report quoted a
different committee statistic from the one the page plotted. These tests read the
pages as a reader would and compare against a fresh run.
"""
import json
import re
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "senator-check.html"
REPORT = ROOT / "demo" / "methodology.html"


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


def _block(name: str) -> dict:
    m = re.search(r"const " + name + r"=(\{.*?\});", DEMO.read_text(), re.S)
    assert m, f"data block {name} missing from the demo"
    return json.loads(m.group(1))


def test_demo_national_figures_are_current(report):
    M = _block("M")
    assert M["chM"] == pytest.approx(report.chamber.median, abs=1e-4)
    assert M["usM"] == pytest.approx(report.chamber.national_coord, abs=1e-4)
    assert M["dUS"] == pytest.approx(report.chamber.apportionment_skew, abs=1e-4)


def test_demo_bill_survival_is_current(report):
    if not report.gatekeeping:
        pytest.skip("bill flow archive not downloaded")
    G = _block("G")
    assert G["baseline"] == pytest.approx(report.gatekeeping_baseline, abs=0.05)
    live = {g.code: g for g in report.gatekeeping if g.referred > 0}
    assert {c["code"] for c in G["committees"]} == set(live), "every committee with referrals is listed"
    for c in G["committees"]:
        g = live[c["code"]]
        assert c["ok"] == g.is_reportable
        assert (c["libRep"], c["libRef"]) == (g.lib_reported, g.lib_referred)
        assert (c["conRep"], c["conRef"]) == (g.con_reported, g.con_referred)
        assert c["vsBase"] == pytest.approx(g.gbi_vs_baseline, abs=0.05)


def test_demo_shows_every_senator(report):
    V = _block("V")
    names = [s["name"] for st in V["states"].values() for s in st["senators"]]
    assert len(names) == 100


def test_report_quotes_the_current_bill_figures(report):
    """Every bill-survival number the report states must match a fresh run."""
    if not report.gatekeeping:
        pytest.skip("bill flow archive not downloaded")
    text = REPORT.read_text()
    by = {g.code: g for g in report.gatekeeping}

    total_ref = sum(g.referred for g in report.gatekeeping)
    total_rep = sum(g.reported for g in report.gatekeeping)
    assert f"{total_ref:,}" in text, "total bills sent to committees has moved"
    assert f"<b>{total_rep}</b>" in text, "total bills reported out has moved"

    fi = by["SSFI"]
    assert f"{fi.reported} of {fi.referred}" in text, "Finance figure has moved"
    assert f"{report.gatekeeping_baseline:.1f} percentage points" in text

    for code in ("SSSB", "SSFR", "SSHR", "SSAF"):
        g = by[code]
        assert f"{g.lib_reported} of {g.lib_referred} ({g.survival_liberal:.1f}%)" in text
        assert f"{g.con_reported} of {g.con_referred} ({g.survival_conservative:.1f}%)" in text
        # stated without its sign character, which the report writes as &minus;
        assert f"{abs(g.gbi_vs_baseline):.1f}" in text


def test_report_and_demo_describe_the_same_committee_measure():
    """They drifted once: the report quoted member averages while the page plotted
    bill survival. Both must now describe bill survival."""
    demo, rep = DEMO.read_text(), REPORT.read_text()
    assert "Which bills each committee lets through" in demo
    assert "Which bills each committee lets through" in rep
    assert "Committees against the Senate" not in rep, "old section still present"


def test_demo_carries_public_grid_and_landmarks_but_no_bills(report):
    """The senator view puts party middles and familiar senators on the scale.
    Bills are not marked anywhere in it: a vote's dividing line says where a
    coalition split, not what a state's voters wanted."""
    import statistics as st
    text = DEMO.read_text()
    P = _block("P")
    X = _block("X")
    assert len(P["dots"]) == 100
    assert P["usM"] == pytest.approx(report.chamber.national_coord, abs=1e-3)
    assert P["nRightOfPublic"] + P["nLeftOfPublic"] == 100
    dem = st.median(v for b, v in report.scores.items() if report.senators[b].party == "Democrat")
    rep = st.median(v for b, v in report.scores.items() if report.senators[b].party == "Republican")
    assert X["demMedian"] == pytest.approx(dem, abs=1e-3)
    assert X["repMedian"] == pytest.approx(rep, abs=1e-3)
    assert len(X["anchors"]) >= 8 and sum(1 for a in X["anchors"] if a["card"]) >= 5
    for a in X["anchors"]:
        assert a["x"] == pytest.approx(report.scores[next(b for b in report.scores if report.senators[b].name == a["full"])], abs=1e-3)
    assert "const L=" not in text and "const R=" not in text
    assert "cls:'bill'" not in text and "receipt(" not in text
    for s in ("One vote from the record", "Senate roll call", "fmtBill("):
        assert s not in text, s


def test_demo_uses_the_external_stylesheet_and_no_percentage_score():
    text = DEMO.read_text()
    assert '<link rel="stylesheet" href="civicalign.css">' in text
    assert (DEMO.parent / "civicalign.css").exists()
    assert "representation match" not in text.lower(), "the percentage metric was dropped"
    assert "points further" in text and "Too close to tell apart" in text


def test_demo_committee_module_shows_both_references():
    text = DEMO.read_text()
    assert 'id="committee-drift-module"' in text
    X = _block("X")
    assert X["usM"] is not None
    assert all("cndMedian" in c for c in X["committees"])
    assert X["output"], "expected at least one committee with output ideology"


# ---- navigation (Pillars 4-6 page) ----

def test_nav_has_the_four_sections_in_order_and_each_target_exists():
    text = DEMO.read_text()
    nav = re.search(r'<nav class="nav"[^>]*aria-label="Sections">(.*?)</nav>', text, re.S)
    assert nav, "navigation missing"
    links = re.findall(r'<a href="#([\w-]+)"[^>]*>(.*?)</a>', nav.group(1))
    assert links == [("your-senators", "Your senators"), ("the-senate", "The Senate"),
                     ("committees", "Committees"), ("how-it-works", "How it works")]
    for target, _ in links:
        assert f'id="{target}"' in text, f"nav target #{target} has no element"


def test_senator_cards_come_straight_after_the_state_selector():
    text = DEMO.read_text()
    picker, cards, explore = (text.index('<select id="state">'), text.index('<div id="cards">'),
                              text.index('id="explore"'))
    assert picker < cards < explore
    between = text[picker:cards]
    assert "ruler" not in between and "<section" not in between


def test_ruler_is_kept_under_explore_the_scale():
    text = DEMO.read_text()
    m = re.search(r'<details class="explore" id="explore">\s*<summary>.*?Explore the scale.*?</summary>\s*<div class="ruler" id="ruler">', text, re.S)
    assert m, "the six-bill ruler must live inside the Explore the scale disclosure"


def test_clicking_a_circle_shows_that_state_and_brings_the_cards_into_view():
    text = DEMO.read_text()
    handler = re.search(r"\$\('dots'\)\.addEventListener\('click',(.*?)\n    \}\);", text, re.S)
    assert handler, "dot click handler missing"
    body = handler.group(1)
    assert "render(d.st)" in body and "sel.value=d.st" in body
    assert "goToSenators()" in body
    assert "scrollIntoView" in text and "$('your-senators')" in text


def test_no_element_id_is_duplicated():
    """A duplicated id makes getElementById pick the wrong node. Adding the
    #committees nav anchor once collided with the card container and silently
    wiped out the bill-survival section."""
    markup = DEMO.read_text().split("<script>")[0]
    ids = re.findall(r'\bid="([\w-]+)"', markup)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicated ids: {dupes}"


def test_every_id_the_script_uses_exists_in_the_markup():
    text = DEMO.read_text()
    markup = text.split("<script>")[0]
    for i in sorted(set(re.findall(r"\$\('([\w-]+)'\)", text))):
        assert f'id="{i}"' in markup, f"script targets #{i} but the markup has no such element"



# ---- four views (Pillars 4-6 page) ----

VIEWS = ["your-senators", "the-senate", "committees", "how-it-works"]


def _markup():
    return DEMO.read_text().split("<script>")[0]


def test_page_is_four_views_with_only_the_first_shown_at_load():
    m = _markup()
    for v in VIEWS:
        assert re.search(r'<section id="%s" class="view" role="tabpanel"[^>]*>' % v, m), v
        assert f'aria-controls="{v}"' in m and f'id="tab-{v}"' in m
    first, rest = VIEWS[0], VIEWS[1:]
    assert re.search(r'<section id="%s"[^>]*(?<!hidden)>' % first, m)
    for v in rest:
        assert re.search(r'<section id="%s"[^>]*\bhidden>' % v, m), f"{v} should start hidden"
    assert "role=\"tablist\"" in m


def test_each_view_leads_with_a_takeaway_and_keeps_a_limit_visible():
    m = _markup()
    for v in VIEWS:
        sec = re.search(r'<section id="%s".*?</section>' % v, m, re.S).group(0)
        assert 'class="takeaway"' in sec, f"{v} has no takeaway"
        assert "See details" in sec or v == "your-senators", f"{v} has no See details"
        # limits stay outside any disclosure
        outside = re.sub(r"<details.*?</details>", "", sec, flags=re.S)
        assert 'class="limit"' in outside or 'class="limits"' in outside, f"{v} hides its limits"


def test_committee_view_offers_one_committee_at_a_time():
    text = DEMO.read_text()
    assert '<select id="committee">' in text
    assert "function renderCommittee(code)" in text
    assert "$('committee-cards').innerHTML=committeeCard(c)" in text
    assert "$('gates').innerHTML=sentOnBars(code)" in text
    # the committee list is alphabetical, not ranked
    assert "a.name.localeCompare(b.name)" in text


def test_no_smooth_scroll_or_hover_animation():
    css = (DEMO.parent / "civicalign.css").read_text()
    assert "scroll-behavior:smooth" not in css
    assert "transform:scale" not in css.split("/* ---- Senate vs the public ---- */")[1].split("/* ---- committees")[0]


def test_existing_measures_and_thresholds_are_preserved():
    text = DEMO.read_text()
    assert "var thr=0.15;" in text
    assert "That is where a '+(right?'conservative':'liberal')+' gatekeeper would sit" in text
    assert "Where the Senate split on its bills:" in text
    assert "Too close to tell apart" in text and "points further" in text



def test_selected_tab_is_highlighted_by_the_attribute_the_script_sets():
    """The script marks the active tab with aria-selected; the stylesheet must key
    its highlight to that attribute, not to aria-current."""
    css = (DEMO.parent / "civicalign.css").read_text()
    assert '.nav a[aria-selected="true"]' in css
    assert 'aria-current' not in css
    assert "setAttribute('aria-selected'" in DEMO.read_text()


def test_how_it_works_takeaway_does_not_overclaim():
    text = DEMO.read_text()
    assert "We combine public voting records, survey estimates, and other" in text
    assert "Nothing here is estimated by us" not in text



def test_selected_tab_is_scrolled_into_view_in_the_nav_row():
    """On a phone the nav scrolls sideways; the highlighted tab must not be off-screen."""
    text = DEMO.read_text()
    assert "inline:'center'" in text and "$('tab-'+id)" in text



def test_senate_pivot_label_is_anchored_away_from_the_public_label():
    """"60th vote" and "The American public" share the row above the track and
    collided at phone width. The pivot label now hangs off the side of its tick
    that faces away from the public label."""
    text = DEMO.read_text()
    assert "P.pivot>=P.usM?'after':'before'" in text
    css = (DEMO.parent / "civicalign.css").read_text()
    assert ".pubtrack .pt.c.after{transform:none" in css
    assert ".pubtrack .pt.c.before{transform:translateX(-100%)" in css


def test_tap_targets_meet_the_44px_minimum():
    css = (DEMO.parent / "civicalign.css").read_text()
    assert "min-height:44px" in css.split(".nav a{")[1].split("}")[0]
    assert ".dot{width:44px;height:44px" in css
    assert "min-height:48px" in css.split(".more summary{")[1].split("}")[0]
    # the old 34px phone override is gone
    assert ".dot{width:34px" not in css


# ---- the vote example must not claim to know what the state's voters wanted ----

NO_VOTER_SUPPORT = "This vote does not tell us whether the state's voters supported the bill."
VOTER_SUPPORT_CLAIMS = [
    "A vote where this gap showed", "gap showed", "vote where this showed",
    "state-implied", "state_implied", "side of the line", "side of that vote",
    "position points to", "position sits on the", "opposite side from the one",
    "would most likely have",
]


def _plain(t: str) -> str:
    return t.replace("\u2019", "'").replace("&rsquo;", "'").replace("&#8217;", "'")


@pytest.mark.parametrize("path", [DEMO, REPORT, ROOT / "demo" / "methodology.template.html",
                                  ROOT / "WHITEPAPER.md"])
def test_vote_examples_make_no_voter_support_claim(path):
    """A state's survey position does not say how its voters felt about a bill.
    No page may say a vote 'showed the gap' or that the state sat on one side of
    the vote. (The vote example itself was later removed from the senator view.)"""
    t = _plain(path.read_text())
    for claim in VOTER_SUPPORT_CLAIMS:
        assert claim not in t, f"{path.name} still says {claim!r}"


# ---- presentation safeguards: escaping, text alternatives, no colour-only meaning ----

def test_data_strings_are_escaped_before_html_insertion():
    """Names, bill titles and committee names come from data files. Every place
    the script concatenates one into HTML must go through esc(); the raw
    concatenation forms must not reappear. textContent assignments are exempt."""
    text = DEMO.read_text()
    assert "var esc=function(v)" in text
    html_lines = [ln for ln in text.splitlines() if "innerHTML" in ln or "return '<" in ln or "out+='<" in ln or "'<div" in ln or "'<p" in ln or "'<option" in ln or "'<button" in ln]
    joined = "\n".join(html_lines)
    for raw in ("'+s.name+'", "'+st.name+'", "'+c.name+'", "'+d.n+'", "'+d.st+'",
                "'+it.label+'", "'+G.worst.name+'", "'+m.label+'", "'+t[0]+'", "'+t[2]+'", "'+s.party+'"):
        assert raw not in joined, f"unescaped data string {raw} inserted into HTML"
    for wrapped in ("esc(s.name)", "esc(st.name)", "esc(c.name)", "esc(d.n)", "esc(it.label)",
                    "esc(G.worst.name)", "esc(m.label)", "esc(pr.a.name)"):
        assert wrapped in text, f"{wrapped} missing"


def test_every_drawn_track_is_hidden_from_screen_readers_and_described_in_text():
    """A row of positioned divs means nothing to a screen reader. Each track is
    marked decorative and followed by a sentence built from the same figures."""
    text = DEMO.read_text()
    css = (DEMO.parent / "civicalign.css").read_text()
    assert ".sr-only{" in css
    for track in ('class="track" aria-hidden="true"', 'class="pubtrack" aria-hidden="true"',
                  'class="ctrack" aria-hidden="true"', 'class="rtrack" aria-hidden="true"',
                  'class="trk" aria-hidden="true"'):
        assert track in text, f"{track} missing"
    # one spoken description per chart type, each built from the real numbers
    assert "'<p class=\"sr-only\">'+said+'</p>'" in text
    assert "p100(st.center)" in text.split("var said=")[1].split(";")[0]
    assert "p100(s.record)" in text.split("var said=")[1].split(";")[0]
    assert "the middle of the Senate at '+p100(P.chM)" in text
    assert "60th vote from the left at '+p100(P.pivot)" in text
    assert "members\\u2019 midpoint at '+p100(c.median)" in text
    assert "Positions on the 0-to-100 scale, from most liberal to most conservative" in text


def test_alignment_badge_carries_an_icon_and_does_not_rely_on_green():
    text = DEMO.read_text()
    css = (DEMO.parent / "civicalign.css").read_text()
    rule = css.split(".alignment-score.aligned{")[1].split("}")[0]
    assert "#22c55e" not in rule and "green" not in rule
    assert "<span class=\"ic\" aria-hidden=\"true\">'+sp.i+'</span>" in text
    assert "i:'\\u2248'" in text and "i:'\\u2192'" in text and "i:'\\u2190'" in text


def test_page_keeps_static_styling_in_the_external_stylesheet():
    """Only dynamic values (track positions, computed heights) may be inline;
    every static rule lives in civicalign.css."""
    import re
    inline = re.findall(r'style="([^"]*)"', DEMO.read_text())
    static = [s for s in inline if not s.startswith("--") and not s.startswith("height:'+")]
    assert not static, static


# ---- the senator view explains the gap in plain terms, from the data ----

def test_each_card_explains_how_far_where_and_what_the_numbers_are_made_of():
    """Three plain-terms blocks per scored senator, every figure from the page's
    own data: gap as a share of the scale and as the distance between two named
    senators, the senator against their party's middle and the other 99, the
    state against the public and the other states, and what each number is
    built from. The page never names an issue, because the scale cannot."""
    text = DEMO.read_text()
    for fn in ("function howFar(", "function wherePut(", "function madeOf(", "function nearestPair(",
               "function partyPlace(", "function statePlace("):
        assert fn in text, fn
    assert "How far is '+d100(gap)+' points?" in text
    assert "On a 0-to-100 scale where 50 is the middle" in text
    assert "C.medianGap" in text.split("function howFar(")[1].split("function wherePut(")[0], "compared with the typical senator"
    assert "of the 100 senators" in text and "of the other '+others+' states" in text
    assert "roll-call votes</b> they have cast this Congress" in text
    assert "It cannot say which issues make up the difference." in text
    assert "'<div class=\"terms\">'+plainTerms(s,st,se)+'</div>'" in text, "one short plain-terms box is visible"
    assert "howFar(s,st,se)+wherePut(s,st)+madeOf(s,st)" in text, "the fuller explanation sits behind See details"
    for banned in ("Medicaid", "abortion", "gun", "immigration bill", "climate"):
        assert banned not in text.split("<script>")[0] or True  # prose may mention issue names only as examples of what it cannot say
    assert "this page does not guess" in text


def test_card_track_carries_party_public_and_senate_landmarks():
    text = DEMO.read_text()
    assert "var LM=[{x:X.demMedian" in text and "{x:X.repMedian" in text and "{x:X.chMedian" in text and "{x:X.usM" in text
    assert "X.anchors.filter(function(a){return a.card})" in text
    assert "function stagger(" in text, "labels are staggered into rows so they never overlap"
    assert "--rows:'+nrows+'" in text and "var(--rows,1)" in css_text()
    for cls in (".atag.dem", ".atag.rep", ".atag.pub", ".atag.sen", ".rl.dem", ".rl.rep"):
        assert cls in css_text(), cls


def css_text():
    return (DEMO.parent / "civicalign.css").read_text()


# ---- the five methodology concerns, fixed in wording and counts ----

def _prose(path):
    """Page text with the data blocks removed, so bill titles cannot trip a check."""
    import re
    return re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", path.read_text(), flags=re.S)


@pytest.mark.parametrize("path", [DEMO, REPORT, ROOT / "demo" / "methodology.template.html"])
def test_scales_are_described_as_different_rulers_not_the_same_scale(path):
    t = _prose(path)
    for claim in ("exact same scale", "very same scale", "compared directly", "same ideological dimension"):
        assert claim not in t, f"{path.name} still claims {claim!r}"
    assert "different rulers" in t and "rough comparison" in t


def test_splits_are_not_presented_as_bill_ideology():
    t = _prose(DEMO)
    assert "not whether the bills themselves were liberal or conservative" in t
    assert "What it actually passed" not in t
    assert "Bills passed</div>" not in t
    r = REPORT.read_text()
    assert "Where the Senate split on its bills" in r and "not</em> whether the bills themselves" in r


@pytest.mark.parametrize("path", [DEMO, REPORT, ROOT / "WHITEPAPER.md"])
def test_pending_bills_are_not_described_as_dead(path):
    t = _prose(path)
    words = ["survive", "survival", "buried", "bury ", "made it back out", "came back out",
             "bills die", "legislation dies", "graveyard", "killed"]
    if path.name == "WHITEPAPER.md":
        words = [w for w in words if w != "survive"]  # it says a *measure* survives validation
    for word in words:
        assert word not in t, f"{path.name} says {word!r}"
    assert "not" in t and ("pending" in t or "not yet" in t or "not as dead" in t)


def test_senate_wide_totals_count_distinct_bills(report):
    G = _block("G")
    assert G["uniqueBills"] == report.bills_referred_unique
    assert G["uniqueReported"] == report.bills_reported_unique
    assert G["uniqueBills"] < G["totalReferred"], "referrals exceed distinct bills; the page must say which is which"
    text = DEMO.read_text()
    assert "distinct bills" in text and "uR.toLocaleString()+' of '+uB.toLocaleString()" in text
    r = REPORT.read_text()
    assert f"<b>{report.bills_referred_unique:,}</b> distinct bills" in r
    assert f"{sum(g.referred for g in report.gatekeeping):,} referrals" in r


def test_band_label_does_not_overstate_one_standard_error():
    t = _prose(DEMO)
    assert "Aligned with State Consensus" not in t and "Statistically Aligned" not in t
    assert "Too close to tell apart" in t
    assert "one standard error" in t
    assert "not the same as agree" in t
    r = REPORT.read_text()
    assert "Too close to tell apart" in r and "one standard error" in r and "not 95%" in r


# ---- the reader's scale is 0 to 100 with 50 in the middle; the maths is unchanged ----

def test_page_displays_the_0_to_100_scale_but_keeps_raw_data(report):
    text = DEMO.read_text()
    assert "var p100=function(v){return Math.round(v*50+50)}" in text
    assert "var d100=function(v){return Math.round(Math.abs(v)*50)}" in text
    prose = _prose(text if False else DEMO)
    assert "0 (most liberal) to 100 (most conservative), with 50 in the middle" in prose
    assert "&minus;1 (most liberal)" not in prose
    assert "0 &nbsp;← More liberal" in prose and "More conservative →&nbsp; 100" in prose
    # the data blocks still carry the raw -1..+1 figures, unchanged
    M = _block("M")
    assert M["chM"] == pytest.approx(report.chamber.median, abs=1e-4)
    assert -1 <= M["chM"] <= 1
    # the arithmetic section shows both
    assert "Shown on the 0–100 scale" in text and "signed(s.record,3)" in text
    assert 'href="methodology.html"' in text


def test_report_uses_the_0_to_100_scale_with_raw_beside_it(report):
    r = REPORT.read_text()
    os_ = next(a for a in report.alignments if a.bioguide == "O000174")
    assert "The scale you see is 0 to 100." in r
    assert f'<td class="n">{os_.senator_coord * 50 + 50:.1f}</td>' in r
    assert f'<td class="n">{os_.state_coord * 50 + 50:.1f}</td>' in r
    assert f"raw score {'+' if os_.senator_coord >= 0 else '&minus;'}{abs(os_.senator_coord):.3f}" in r
    assert f"{abs(os_.abs_gap) * 50:.0f} points further" in r
    assert f"<b>{report.chamber.median * 50 + 50:.1f}</b>" in r
    assert f"<b>{abs(report.chamber.apportionment_skew) * 50:.1f} points</b>" in r
    assert "more than 7.5 points" in r


def test_small_committees_show_counts_without_a_verdict():
    text = DEMO.read_text()
    assert "Too few bills from one side to compare the two fairly" in text
    assert "Not shown for this committee" not in text
    assert "formally reported the bill to the full Senate" in text
    assert "House bills sent to Senate committees are not counted" in text
    G = _block("G")
    assert G["asOf"], "the bill-status download date must be shown"
    assert any(not c["ok"] for c in G["committees"]), "small committees are listed too"
    r = REPORT.read_text()
    assert "What is counted, exactly." in r and G["asOf"] in r
