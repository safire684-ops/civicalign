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
    assert "dUS" not in M, "the cross-scale gap is not shipped"


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

    shown = sorted((g for g in report.gatekeeping if g.is_reportable), key=lambda g: -abs(g.gbi_vs_baseline))[:4]
    for g in shown:
        assert f"{g.lib_reported} of {g.lib_referred} ({g.survival_liberal:.1f}%)" in text
        assert f"{g.con_reported} of {g.con_referred} ({g.survival_conservative:.1f}%)" in text
        # stated without its sign character, which the report writes as &minus;
        assert f"{abs(g.gbi_vs_baseline):.1f}" in text


def test_report_and_demo_describe_the_same_committee_measure():
    """They drifted once: the report quoted member averages while the page plotted
    bill survival. Both must now describe bill survival."""
    demo, rep = DEMO.read_text(), REPORT.read_text()
    assert "What has it sent forward?" in demo
    assert "What each committee has sent forward" in rep
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
    assert "nRightOfPublic" not in P and "gap" not in P
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
    assert "than the Senate middle" in text and "on the voter measure" in text


def test_demo_committee_module_shows_both_references():
    text = DEMO.read_text()
    assert 'id="committee-drift-module"' in text
    X = _block("X")
    assert "usM" not in X, "the voter estimate is not drawn on the senators' scale"
    assert all("cndMedian" not in c and "cndMean" not in c for c in X["committees"])
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
    m = re.search(r'<details class="explore" id="explore">\s*<summary>.*?Where familiar senators sit.*?</summary>\s*<div class="ruler" id="ruler">', text, re.S)
    assert m, "the landmark ruler must live inside its own disclosure under the cards"


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
        assert '<details class="more' in sec or v == "your-senators", f"{v} has no disclosure"
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
    assert "the position a '+(right?'conservative':'liberal')+' gatekeeper would sit in" in text
    assert "Where senators divided on these votes:" in text
    assert "than the Senate middle" in text



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
                "'+it.label+'", "'+G.worst.name+'", "'+t.who+'", "'+t.url+'", "'+t.use+'", "'+s.party+'"):
        assert raw not in joined, f"unescaped data string {raw} inserted into HTML"
    for wrapped in ("esc(s.name)", "esc(st.name)", "esc(c.name)", "esc(d.n)", "esc(it.label)",
                    "esc(G.worst.name)", "esc(t.who)", "esc(t.url)"):
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
    assert text.count("<p class=\"sr-only\">") >= 4
    sen = text.split("function senatorTrack(")[1].split("\n  }")[0]
    sta = text.split("function stateTrack(")[1].split("\n  }")[0]
    assert "p100(s.record)" in sen and "st.center" not in sen
    assert "p100(st.center)" in sta and "s.record" not in sta
    assert "the middle of the Senate is at '+p100(P.chM)" in text
    assert "60th vote from the left at '+p100(P.pivot)" in text
    assert "members\\u2019 midpoint at '+p100(c.median)" in text
    assert "Positions on the 0-to-100 scale, from most liberal to most conservative" in text


def test_pill_carries_an_icon_and_does_not_rely_on_green():
    text = DEMO.read_text()
    css = (DEMO.parent / "civicalign.css").read_text()
    rule = css.split(".pill.aligned,.pill.neutral{")[1].split("}")[0]
    assert "#22c55e" not in rule and "green" not in rule
    assert "<span class=\"ic\" aria-hidden=\"true\">'+sp.i+'</span>" in text
    assert "i:'\\u2248'" in text and "i:d>0?'\\u2192':'\\u2190'" in text


def test_page_keeps_static_styling_in_the_external_stylesheet():
    """Only dynamic values (track positions, computed heights) may be inline;
    every static rule lives in civicalign.css."""
    import re
    inline = re.findall(r'style="([^"]*)"', DEMO.read_text())
    static = [s for s in inline if not s.startswith("--") and not s.startswith("height:'+")]
    assert not static, static


# ---- the senator view explains the gap in plain terms, from the data ----

def test_each_measure_has_its_own_chart_with_only_its_own_scale():
    """The senator's chart carries only Voteview marks (the senator and the Senate
    middle); the state's chart carries only survey marks (the state estimate, its
    range, the national estimate). Neither draws the other."""
    text = DEMO.read_text()
    sen = text.split("function senatorTrack(")[1].split("\n  }")[0]
    sta = text.split("function stateTrack(")[1].split("\n  }")[0]
    assert "X.chMedian" in sen and "st." not in sen and "P.usM" not in sen
    assert "P.usM" in sta and "state-error-band" in sta and "s.record" not in sta and "X.chMedian" not in sta
    assert "{x:X.demMedian,label:'Middle Democrat',cls:'dem'}" in text
    assert "The American public" not in text
    assert "function stagger(" in text and "var(--rows,1)" in css_text()


def css_text():
    return (DEMO.parent / "civicalign.css").read_text()


# ---- the five methodology concerns, fixed in wording and counts ----

def _prose(path):
    """Page text with the data blocks removed, so bill titles cannot trip a check."""
    import re
    return re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", path.read_text(), flags=re.S)


@pytest.mark.parametrize("path", [DEMO, REPORT, ROOT / "demo" / "methodology.template.html"])
def test_scales_are_described_as_separate_and_uncompared(path):
    t = _prose(path)
    for claim in ("exact same scale", "very same scale", "compared directly", "same ideological dimension",
                  "rough comparison", "one 0-to-100 line", "on one line and subtract"):
        assert claim not in t, f"{path.name} still says {claim!r}"
    assert "different rulers" in t or "different measurement systems" in t or "different kinds of data" in t
    assert "not directly compared" in t or "not compared" in t or "does not currently have that bridge" in t


def test_splits_are_not_presented_as_bill_ideology():
    t = _prose(DEMO)
    assert "whether the bill itself was liberal or conservative" in t
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


def test_no_alignment_label_survives():
    t = _prose(DEMO)
    for label in ("Aligned with State Consensus", "Statistically Aligned", "Too close to", "Within the estimated range",
                  "side of the state estimate", "left of the state", "right of the state"):
        assert label not in t, label
    r = REPORT.read_text()
    assert "one standard error" in r and "not 95%" in r


def test_page_displays_the_0_to_100_scale_but_keeps_raw_data(report):
    text = DEMO.read_text()
    assert "var p100=function(v){return Math.round(v*50+50)}" in text
    assert "var d100=function(v){return Math.round(Math.abs(v)*50)}" in text
    prose = _prose(text if False else DEMO)
    assert "from 0 (most liberal) to 100 (most conservative)" in prose
    assert "&minus;1 (most liberal)" not in prose
    assert "← More liberal" in prose and "More conservative →" in prose
    # the data blocks still carry the raw -1..+1 figures, unchanged
    M = _block("M")
    assert M["chM"] == pytest.approx(report.chamber.median, abs=1e-4)
    assert -1 <= M["chM"] <= 1
    # the arithmetic section shows both
    assert "shown as x × 50 + 50" in text and "signed(s.record,3)" in text
    assert 'href="methodology.html"' in text


def test_report_uses_the_0_to_100_scale_with_raw_beside_it(report):
    r = REPORT.read_text()
    os_ = next(a for a in report.positions if a.bioguide == "O000174")
    assert "Each scale you see runs from 0 to 100." in r
    assert f'<td class="n">{os_.senator_coord * 50 + 50:.1f}</td>' in r
    assert f'<td class="n">{os_.state_coord * 50 + 50:.1f} &plusmn;' in r
    assert f"raw score {'+' if os_.senator_coord >= 0 else '&minus;'}{abs(os_.senator_coord):.3f}" in r
    assert f"<b>{report.chamber.median * 50 + 50:.1f}</b>" in r
    assert "shown separately" in r
    assert "more than 7.5 points" in r


def test_small_committees_show_counts_without_a_verdict():
    text = DEMO.read_text()
    assert "Too few bills to compare the two sides fairly" in text and "Limited data" in text
    assert "Not shown for this committee" not in text
    assert "formally reported the bill to the full Senate" in text
    assert "House bills sent to Senate committees are not counted" in text
    G = _block("G")
    assert G["asOf"], "the bill-status download date must be shown"
    assert any(not c["ok"] for c in G["committees"]), "small committees are listed too"
    r = REPORT.read_text()
    assert "What is counted, exactly." in r and G["asOf"] in r


# ---- the brief's twelve guarantees: simple on the surface, rigorous underneath ----

def _visible(path=None):
    """Page prose outside the data blocks and outside any <details> disclosure."""
    text = (path or DEMO).read_text()
    text = re.sub(r"<script>.*?</script>", "", text, flags=re.S)
    return re.sub(r"<details.*?</details>", "", text, flags=re.S)


def test_1_never_claims_a_validated_common_scale():
    t = _prose(DEMO) + REPORT.read_text() + (ROOT / "README.md").read_text()
    for claim in ("validated common scale", "same scale, so the two can be compared directly",
                  "exact same scale", "very same scale", "on one 0-to-100 scale:", "This measures the distance between them"):
        assert claim not in t, claim
    assert "approximate comparison" in t.lower() and "measured differently" in t or "built differently" in t


def test_2_never_calls_a_cutpoint_bill_ideology():
    t = (_prose(DEMO) + REPORT.read_text()).lower()
    assert "it does not tell us whether the bill itself was liberal or conservative" in t
    t = t.replace("does not necessarily tell us the ideology of the bill", "")
    for claim in ("bill ideology", "liberal bill", "conservative bill", "ideology of the bill"):
        assert claim not in t, claim


def test_3_survey_vintage_is_visible_on_the_first_screen():
    v = _visible()
    first = v.split('id="the-senate"')[0]
    assert "American Ideology Project" in first and "2020 wave" in first


def test_4_pending_bills_are_not_called_dead(report):
    v = _prose(DEMO).lower()
    for w in ("killed", "buried", "graveyard", "suppress", "dead bills", "bills die"):
        assert w not in v, w
    assert "not dead" in v and "not yet sent forward" in v


def test_5_sponsor_ideology_is_not_bill_ideology():
    t = DEMO.read_text()
    assert "Grouped by the voting record of each bill\\u2019s sponsor" in t
    assert "does not necessarily tell us the ideology of the bill" in t


def test_6_small_samples_show_caution_or_withhold_conclusions():
    t = DEMO.read_text()
    assert "Early signal" in t and "too little for a strong conclusion" in t
    assert "Not enough data yet" in t and "Limited data" in t
    assert "weak=o.n<15" in t


def test_7_and_8_every_view_answers_one_question_with_a_plain_takeaway():
    t = DEMO.read_text()
    for view in ("your-senators", "the-senate", "committees", "how-it-works"):
        panel = t.split(f'<section id="{view}"')[1].split("</section>")[0]
        assert 'class="takeaway"' in panel, view
    assert "See your senator's voting pattern and your state's voter estimate" in t
    # generated takeaways are plain sentences without raw decimals
    for fn in ("$('take-senators').textContent=t", "$('take-senate').textContent=", "$('take-committee').textContent="):
        assert fn in t


def test_9_every_view_has_one_short_visible_caveat():
    t = DEMO.read_text()
    for view in ("your-senators", "the-senate", "committees"):
        panel = t.split(f'<section id="{view}"')[1].split("</section>")[0]
        outside = re.sub(r"<details.*?</details>", "", panel, flags=re.S)
        assert outside.count('class="limit"') == 1, view


def test_10_default_card_is_not_overloaded_with_benchmarks():
    card = DEMO.read_text().split("function render(code){")[1].split("window.addEventListener('resize'")[0]
    before_details = card.split("<details class=\"more\">")[0]
    for secondary in ("X.demMedian", "X.repMedian", "X.anchors", "s.rank", "howFar(", "wherePut("):
        assert secondary not in before_details, secondary
    assert "'<div class=\"terms\">'+madeOf(s)+'</div>'" in card


def test_11_technical_terms_stay_out_of_the_default_experience():
    v = _visible()
    for term in ("DW-NOMINATE", "Nokken", "MRP", "cloture", "cutpoint", "CCD", "CND", "COI", "GBI",
                 "median drift", "mean drift", "ideal point", "standard error", "apportionment skew"):
        assert term not in v, term
    # the generated text on the first screen avoids them too; the technical names
    # live only in disclosures ("Why does this happen?", See details) and the report
    js = "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))
    stakes = js.split("$('stakes').innerHTML=")[1].split(";\n")[0]
    assert "cloture threshold" in stakes
    assert "cloture" not in js.replace(stakes, "")
    for fn in ("function senatorPos(", "function senatorTrack(", "function stateTrack(", "function stateVsNation(", "function driftWords(", "function sentOnBars(", "function floorSplit("):
        body = js.split(fn)[1].split("\n  }")[0]
        for term in ("Nokken", "MRP", "cutpoint", "standard error", "cloture", "ideal point"):
            assert term not in body, f"{term} in {fn}"


def test_12_detailed_methodology_remains_available():
    t = DEMO.read_text()
    assert 'href="methodology.html"' in t
    assert "Show the math" in t and 'id="workings"' in t and 'id="srcs"' in t
    assert "signed(s.record,3)" in t, "raw arithmetic is still shown in full"


def test_sources_are_credible_publishers_with_full_links(report):
    M = _block("M")
    assert len(M["sources"]) >= 6
    ok_hosts = ("voteview.com", "github.com/unitedstates", "unitedstates.github.io", "doi.org", "dataverse.harvard.edu", "census.gov", "govinfo.gov")
    for s in M["sources"]:
        assert set(s) >= {"what", "who", "url", "file", "use"}, s
        assert s["url"].startswith("https://") and s["file"].startswith("https://"), s["what"]
        assert any(h in s["url"] for h in ok_hosts) and any(h in s["file"] for h in ok_hosts), s["what"]
    text = DEMO.read_text()
    assert "<h3>Sources</h3>" in text and "M.sources.map(srcRow)" in text


# ---- no arithmetic across the two unbridged scales, anywhere a reader can see ----

CROSS_SCALE_PHRASES = [
    "points apart", "gap of ", "times the typical senator", "distance from their state",
    "distance from their own state", "widest gap", "points further", "further left than",
    "further right than", "points to the right of the american public", "points to the left of the american public",
    "points to the right of the public", "points to the left of the public",
    "points to the right of the country", "points to the left of the country",
    "points right of the country", "points left of the country", "points from their state",
    "one of the most liberal", "one of the most conservative", "% match", "senators right of the public",
    "senators to the right of the country", "gap: ", "side of the state estimate", "left of the state",
    "right of the state", "within the estimated range", "too close to", "crosses over", "alignment score",
    "distance from your state", "gap between senator and state",
]


def test_no_user_facing_arithmetic_across_the_two_scales():
    """A Voteview senator or chamber figure is never subtracted from an American
    Ideology Project voter estimate in anything a reader sees: page prose, the
    script that writes the page, the screen-reader text, the report, the README.
    Senator-to-senator and committee-to-Senate figures (one scale) are allowed."""
    page = re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", DEMO.read_text(), flags=re.S).lower()
    report = REPORT.read_text().lower()
    readme = (ROOT / "README.md").read_text().lower()
    for phrase in CROSS_SCALE_PHRASES:
        assert phrase not in page, f"page: {phrase!r}"
        assert phrase not in report, f"report: {phrase!r}"
    for phrase in ("points apart", "widest gap", "gap of ", "one of the most liberal"):
        assert phrase not in readme, f"readme: {phrase!r}"
    # the script never renders a subtraction of the two coordinates as a number
    js = "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))
    for expr in ("d100(s.record-st.center)", "d100(gap)", "d100(P.gap)", "d100(c.cndMedian)", "d100(o.vsUS)",
                 "d100(d.vsUS)", "d100(d.vsState)", "P.nRightOfPublic", "C.medianGap", "s.rank", "amongSenators(",
                 "aligned(", "M.dUS", "X.usM"):
        assert expr not in js, expr
    # the report's committee tables compare committees with the Senate only
    assert "vs. public" not in report and "against the public" not in report
    wp = (ROOT / "WHITEPAPER.md").read_text()
    assert "vs. public" not in wp


def test_separate_measures_wording_is_what_the_reader_sees():
    js = "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))
    assert "than the Senate middle" in js and "about at the Senate middle" in js
    assert "on the voter measure" in js
    assert "are shown on separate scales" in js and "not directly compared" in js
    t = re.sub(r"\s+", " ", DEMO.read_text())
    assert "shown separately and no distance between them is calculated" in t




# ---- the six guarantees: no senator-versus-state operation of any kind in public code ----

def _js():
    return "".join(re.findall(r"<script>(.*?)</script>", DEMO.read_text(), re.S))


def test_g1_public_code_never_subtracts_a_voter_estimate_from_a_legislator_score():
    js = _js()
    for pat in (r"record\s*-\s*st\.center", r"st\.center\s*-\s*s\.record", r"record\s*-\s*(P|V|M)\.usM",
                r"(P|M|X)\.chM(edian)?\s*-\s*(P|M|V)\.usM", r"(P|M|V)\.usM\s*-\s*(P|M|X)\.chM",
                r"c\.median\s*-\s*(P|M|X)\.usM", r"o\.coi\s*-\s*(P|M|X)\.usM"):
        assert not re.search(pat, js), pat
    # and the builder never ships such a difference
    src = (ROOT / "src" / "civicalign" / "build_demo.py").read_text()
    blocks = src.split("def _blocks(")[1].split("\ndef build(")[0]
    for pat in (r"senator_coord\s*-\s*[\w.]*(national_coord|state_coord)", r"round\([^)]*(signed_gap|abs_gap)", r"\.cnd\b", r"vs_public", r"spec_score", r"\.rank\b", r"crosses_over"):
        assert not re.search(pat, blocks), pat


def test_g2_public_code_never_compares_the_two_scales_with_greater_or_less_than():
    js = _js()
    for pat in (r"record\s*[<>]=?\s*st\.center", r"st\.center\s*[<>]=?\s*s\.record", r"chM\s*[<>]=?\s*(P|M|V)\.usM",
                r"(P|M|V)\.usM\s*[<>]=?\s*(P|M|X)\.chM", r"record\s*[<>]=?\s*(P|V|M)\.usM"):
        assert not re.search(pat, js), pat


def test_g3_no_senator_is_classified_left_or_right_of_their_state():
    t = re.sub(r"const [A-Z]=[\{\[].*?[\}\]];", "", DEMO.read_text(), flags=re.S).lower()
    for phrase in ("left of the state", "right of the state", "side of the state", "left of georgia", "right of georgia",
                   "more liberal than the state", "more conservative than the state", "than their state", "than the state estimate"):
        assert phrase not in t, phrase


def test_g4_no_check_of_a_senator_against_the_state_uncertainty_band():
    js = _js()
    assert "aligned(" not in js and "<=se" not in js.replace(" ", "") and "M.se[code]" in js, "the band is drawn, never tested against a senator"
    assert not re.search(r"Math\.abs\(s\.record\s*-\s*st\.center\)", js)


def test_g5_no_ranking_of_senators_by_senator_versus_state_distance():
    V = _block("V")
    for st in V["states"].values():
        for s in st["senators"]:
            assert not ({"rank", "gap", "score", "crosses", "dir"} & set(s)), s
    t = DEMO.read_text().lower()
    assert "widest gap" not in t and "th widest" not in t


def test_g6_no_cross_scale_derived_fields_in_the_public_payload():
    forbidden = {"gap", "score", "rank", "crosses", "dir", "vsState", "vsUS", "nRightOfPublic", "nLeftOfPublic",
                 "medianGap", "skew", "dUS", "cndMedian", "cndMean", "crossCount", "moreCons", "moreLib"}

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    text = DEMO.read_text()
    assert "const C=" not in text
    found = {k for name in "VMXPG" for k in keys(_block(name)) if k in forbidden}
    assert not found, found
    # the state estimates ride along on their own scale only
    assert len(_block("P")["stateEstimates"]) == 50
