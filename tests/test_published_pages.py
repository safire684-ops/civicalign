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
    live = {g.code: g for g in report.gatekeeping if g.is_reportable}
    assert {c["code"] for c in G["committees"]} == set(live)
    for c in G["committees"]:
        g = live[c["code"]]
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


def test_demo_carries_landmarks_receipts_and_public_grid(report):
    L = json.loads(re.search(r"const L=(\[.*?\]);", DEMO.read_text(), re.S).group(1))
    R = _block("R")
    P = _block("P")
    assert len(L) == len(report.landmarks) and L[0]["label"] == report.landmarks[0].label
    assert set(R) == set(report.receipts)
    assert len(P["dots"]) == 100
    assert P["usM"] == pytest.approx(report.chamber.national_coord, abs=1e-3)
    assert P["nRightOfPublic"] + P["nLeftOfPublic"] == 100


def test_demo_uses_the_external_stylesheet_and_no_percentage_score():
    text = DEMO.read_text()
    assert '<link rel="stylesheet" href="civicalign.css">' in text
    assert (DEMO.parent / "civicalign.css").exists()
    assert "representation match" not in text.lower(), "the percentage metric was dropped"
    assert "points further" in text and "Aligned with State Consensus" in text


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
    assert "$('gates').innerHTML=survivalBars(code)" in text
    # the committee list is alphabetical, not ranked
    assert "a.name.localeCompare(b.name)" in text


def test_no_smooth_scroll_or_hover_animation():
    css = (DEMO.parent / "civicalign.css").read_text()
    assert "scroll-behavior:smooth" not in css
    assert "transform:scale" not in css.split("/* ---- Senate vs the public ---- */")[1].split("/* ---- committees")[0]


def test_existing_measures_and_thresholds_are_preserved():
    text = DEMO.read_text()
    assert "var thr=0.15;" in text
    assert "Warning: This committee acts as a " in text
    assert "What it actually passed:" in text
    assert "Aligned with State Consensus" in text and "points further" in text
    assert "A vote where this gap showed" in text



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
